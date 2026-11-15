from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import pdist, squareform
from sklearn.decomposition import PCA
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler


NUMERIC_FEATURES = [
    "growth_rate",
    "product_yield",
    "pH_tolerance",
    "GC_content",
    "genome_size_mbp",
]
REQUIRED_COLUMNS = ["strain_id", *NUMERIC_FEATURES, "has_plasmid", "source"]


class DataValidationError(ValueError):
    pass


@dataclass
class ClusteringResult:
    data: pd.DataFrame
    optimal_k: int
    clusters: list[tuple[str, int]]
    cluster_summary: pd.DataFrame
    pca_coordinates: np.ndarray
    explained_variance_ratio: np.ndarray
    distance_matrix: np.ndarray
    silhouette_scores: pd.DataFrame
    linkage_matrix: np.ndarray


def generate_demo_data() -> pd.DataFrame:
    rng = np.random.RandomState(123)
    n = 20
    return pd.DataFrame(
        {
            "strain_id": [f"S{i:02d}" for i in range(1, n + 1)],
            "growth_rate": rng.uniform(0.5, 1.5, n),
            "product_yield": rng.uniform(1.5, 4.0, n),
            "pH_tolerance": rng.uniform(5.0, 9.0, n),
            "GC_content": rng.uniform(45.0, 65.0, n),
            "genome_size_mbp": rng.uniform(3.0, 6.0, n),
            "has_plasmid": rng.randint(0, 2, n),
            "source": rng.choice(["soil", "water", "gut"], n),
        }
    )


def validate_data(data: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(data, pd.DataFrame):
        raise DataValidationError("Данные должны быть объектом pandas DataFrame.")

    missing_columns = [column for column in REQUIRED_COLUMNS if column not in data.columns]
    if missing_columns:
        raise DataValidationError(
            "Отсутствуют обязательные колонки: " + ", ".join(missing_columns) + "."
        )

    duplicate_columns = data.columns[data.columns.duplicated()].unique().tolist()
    if duplicate_columns:
        raise DataValidationError(
            "Названия колонок не должны повторяться: "
            + ", ".join(map(str, duplicate_columns))
            + "."
        )

    if len(data) < 3:
        raise DataValidationError("Для кластеризации необходимо не менее 3 штаммов.")

    cleaned = data.copy()
    missing_counts = cleaned[REQUIRED_COLUMNS].isna().sum()
    missing_counts = missing_counts[missing_counts > 0]
    if not missing_counts.empty:
        details = ", ".join(
            f"{column} ({count})" for column, count in missing_counts.items()
        )
        raise DataValidationError(
            f"Обнаружены пропуски в обязательных колонках: {details}."
        )

    cleaned["strain_id"] = cleaned["strain_id"].astype(str).str.strip()
    if cleaned["strain_id"].eq("").any():
        raise DataValidationError(
            "Колонка 'strain_id' не должна содержать пустые идентификаторы."
        )
    duplicate_ids = cleaned.loc[
        cleaned["strain_id"].duplicated(keep=False), "strain_id"
    ].unique()
    if len(duplicate_ids) > 0:
        raise DataValidationError(
            "Значения strain_id должны быть уникальными. Повторяются: "
            + ", ".join(duplicate_ids)
            + "."
        )

    for column in NUMERIC_FEATURES:
        try:
            numeric = pd.to_numeric(cleaned[column], errors="raise")
            if np.iscomplexobj(numeric):
                raise ValueError
            values = numeric.to_numpy(dtype=float)
        except (TypeError, ValueError, OverflowError):
            raise DataValidationError(
                f"Колонка '{column}' должна содержать только числовые значения."
            ) from None
        if not np.isfinite(values).all():
            raise DataValidationError(
                f"Колонка '{column}' должна содержать только конечные числовые значения."
            )
        cleaned[column] = values

    try:
        plasmid = pd.to_numeric(cleaned["has_plasmid"], errors="raise")
        if np.iscomplexobj(plasmid):
            raise ValueError
        plasmid_values = plasmid.to_numpy(dtype=float)
    except (TypeError, ValueError, OverflowError):
        raise DataValidationError(
            "Колонка 'has_plasmid' должна содержать только значения 0 или 1."
        ) from None
    if not np.isfinite(plasmid_values).all() or not np.isin(
        plasmid_values, [0.0, 1.0]
    ).all():
        raise DataValidationError(
            "Колонка 'has_plasmid' должна содержать только значения 0 или 1."
        )
    cleaned["has_plasmid"] = plasmid_values.astype(int)

    cleaned["source"] = cleaned["source"].astype(str).str.strip()
    allowed_sources = ["soil", "water", "gut"]
    invalid_source_mask = ~cleaned["source"].isin(allowed_sources)
    if invalid_source_mask.any():
        invalid_sources = sorted(cleaned.loc[invalid_source_mask, "source"].unique())
        raise DataValidationError(
            "Колонка 'source' допускает только значения soil, water и gut. "
            "Недопустимые значения: " + ", ".join(invalid_sources) + "."
        )

    return cleaned


def _prepare_features(
    data: pd.DataFrame,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    numeric = StandardScaler().fit_transform(
        data[NUMERIC_FEATURES].to_numpy(dtype=float)
    )
    binary = data[["has_plasmid"]].to_numpy(dtype=float)
    source = pd.get_dummies(data["source"]).to_numpy(dtype=float)
    combined = np.hstack((numeric, binary, source))
    return numeric, binary, source, combined


def _normalized_distances(features: np.ndarray, metric: str) -> np.ndarray:
    distances = squareform(pdist(features, metric=metric))
    maximum = float(distances.max())
    if maximum == 0.0:
        return np.zeros_like(distances, dtype=float)
    return distances / maximum


def _distance_matrix_from_features(
    numeric: np.ndarray, binary: np.ndarray, source: np.ndarray
) -> np.ndarray:
    numeric_distances = _normalized_distances(numeric, "euclidean")
    binary_distances = _normalized_distances(binary, "hamming")
    source_distances = _normalized_distances(source, "euclidean")
    distances = (
        0.6 * numeric_distances
        + 0.2 * binary_distances
        + 0.2 * source_distances
    )
    distances = (distances + distances.T) / 2.0
    np.fill_diagonal(distances, 0.0)
    return distances


def compute_distance_matrix(data: pd.DataFrame) -> np.ndarray:
    cleaned = validate_data(data)
    numeric, binary, source, _ = _prepare_features(cleaned)
    return _distance_matrix_from_features(numeric, binary, source)


def analyze_strains(data: pd.DataFrame) -> ClusteringResult:
    cleaned = validate_data(data)
    numeric, binary, source, combined = _prepare_features(cleaned)
    distance_matrix = _distance_matrix_from_features(numeric, binary, source)
    linkage_matrix = linkage(squareform(distance_matrix), method="ward")

    n_rows = len(cleaned)
    score_records: list[tuple[int, float]] = []
    for k in range(2, min(10, n_rows - 1) + 1):
        labels = fcluster(linkage_matrix, t=k, criterion="maxclust")
        if len(np.unique(labels)) != k:
            continue
        score = float(
            silhouette_score(distance_matrix, labels, metric="precomputed")
        )
        if np.isfinite(score):
            score_records.append((k, score))

    if not score_records:
        raise DataValidationError(
            "Не удалось выбрать число кластеров: из-за одинаковых расстояний "
            "ни одно значение k не дало допустимого разбиения. "
            "Измените или дополните данные."
        )

    silhouette_scores = pd.DataFrame(
        score_records, columns=["k", "silhouette_score"]
    )
    optimal_k = max(score_records, key=lambda item: (item[1], -item[0]))[0]
    labels = fcluster(
        linkage_matrix, t=optimal_k, criterion="maxclust"
    ).astype(int)

    clusters = [
        (strain_id, int(label))
        for strain_id, label in zip(cleaned["strain_id"].tolist(), labels)
    ]

    summary_data = cleaned[REQUIRED_COLUMNS].copy()
    summary_data["cluster_label"] = labels
    aggregations = {"cluster_size": ("strain_id", "size")}
    aggregations.update(
        {feature: (feature, "mean") for feature in NUMERIC_FEATURES}
    )
    aggregations["dominant_source"] = (
        "source",
        lambda values: values.mode().min(),
    )
    cluster_summary = (
        summary_data.groupby("cluster_label", sort=True)
        .agg(**aggregations)
        .reset_index()
    )

    pca = PCA(n_components=2)
    pca_coordinates = pca.fit_transform(combined)

    return ClusteringResult(
        data=cleaned,
        optimal_k=int(optimal_k),
        clusters=clusters,
        cluster_summary=cluster_summary,
        pca_coordinates=pca_coordinates,
        explained_variance_ratio=pca.explained_variance_ratio_,
        distance_matrix=distance_matrix,
        silhouette_scores=silhouette_scores,
        linkage_matrix=linkage_matrix,
    )
