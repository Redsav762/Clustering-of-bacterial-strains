import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from scipy.cluster.hierarchy import dendrogram

from strain_clustering import (
    NUMERIC_FEATURES,
    DataValidationError,
    analyze_strains,
    generate_demo_data,
    validate_data,
)


st.set_page_config(
    page_title="Кластеризация штаммов бактерий",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
        .stApp {
            background: #f5f8fb;
        }
        .stApp,
        .stApp * {
            color: #183247 !important;
        }
        [data-testid="stSidebar"] {
            background: #edf4f6;
            border-right: 1px solid #d8e5e9;
        }
        h1, h2, h3 {
            color: #123b52 !important;
            letter-spacing: -0.02em;
        }
        [data-testid="stCaptionContainer"],
        [data-testid="stCaptionContainer"] * {
            color: #506b7a !important;
        }
        [data-testid="stMetric"] {
            background: #ffffff;
            border: 1px solid #d9e5ea;
            border-top: 3px solid #0f8b8d;
            border-radius: 10px;
            padding: 16px 18px;
            box-shadow: 0 3px 12px rgba(26, 62, 80, 0.06);
        }
        [data-testid="stMetricLabel"],
        [data-testid="stMetricLabel"] * {
            color: #506b7a !important;
        }
        [data-testid="stMetricValue"],
        [data-testid="stMetricValue"] * {
            color: #0c6670 !important;
        }
        .stTabs [data-baseweb="tab-list"] {
            gap: 8px;
            border-bottom: 1px solid #d8e3e8;
        }
        .stTabs [data-baseweb="tab"],
        .stTabs [data-baseweb="tab"] * {
            color: #456171 !important;
            font-weight: 500;
        }
        .stTabs [aria-selected="true"],
        .stTabs [aria-selected="true"] * {
            color: #0f766e !important;
        }
        .stApp button[data-testid^="stBaseButton"],
        [data-testid="stFileUploader"] button {
            background-color: #ffffff !important;
            border: 1px solid #b8cbd4 !important;
            border-radius: 7px;
        }
        .stApp button[data-testid^="stBaseButton"]:hover,
        [data-testid="stFileUploader"] button:hover {
            background-color: #edf4f6 !important;
            border-color: #0f8b8d !important;
        }
        .stApp button:focus-visible {
            outline: 2px solid #0f8b8d !important;
            outline-offset: 2px;
        }
        [data-testid="stDownloadButton"] button,
        [data-testid="stDownloadButton"] button:hover,
        [data-testid="stDownloadButton"] button:focus,
        [data-testid="stDownloadButton"] button:active {
            background-color: #0f766e !important;
            border: 1px solid #0f766e !important;
            border-radius: 7px;
        }
        [data-testid="stDownloadButton"] button:hover,
        [data-testid="stDownloadButton"] button:active {
            background-color: #115e59 !important;
            border-color: #115e59 !important;
        }
        [data-testid="stDownloadButton"] button,
        [data-testid="stDownloadButton"] button * {
            color: #183247 !important;
        }
        [data-testid="stLatex"],
        [data-testid="stLatex"] * {
            background: transparent !important;
        }
        [data-testid="stExpander"] details,
        [data-testid="stExpander"] summary,
        [data-testid="stExpander"] summary:hover,
        [data-testid="stExpander"] summary:focus,
        [data-testid="stExpander"] summary:active,
        [data-testid="stExpander"] details[open] summary,
        [data-testid="stExpander"] summary * {
            background-color: transparent !important;
            box-shadow: none !important;
        }
        [data-testid="stDataFrame"] {
            background: #ffffff;
        }
        #MainMenu, footer {
            visibility: hidden;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

FEATURE_LABELS = {
    "strain_id": "Штамм",
    "cluster_label": "Кластер",
    "cluster_size": "Число штаммов",
    "dominant_source": "Преобладающий источник",
    "source": "Источник",
    "growth_rate": "Скорость роста",
    "product_yield": "Выход продукта",
    "pH_tolerance": "Толерантность к pH",
    "GC_content": "GC-состав, %",
    "genome_size_mbp": "Размер генома, Мбп",
    "has_plasmid": "Наличие плазмиды",
}

CLUSTER_COLORS = [
    "#0f766e",
    "#2563eb",
    "#d97706",
    "#7c3aed",
    "#db2777",
    "#059669",
    "#dc2626",
    "#4f46e5",
    "#0891b2",
    "#65a30d",
]


def csv_bytes(dataframe, index=False):
    return dataframe.to_csv(index=index).encode("utf-8-sig")


def feature_label(feature):
    return FEATURE_LABELS.get(feature, feature.replace("_", " ").capitalize())


def format_decimal(value):
    return f"{value:.3f}".replace(".", ",")


SOURCE_LABELS = {
    "soil": "почва",
    "water": "вода",
    "gut": "кишечник",
}


def silhouette_description(score):
    if score >= 0.7:
        return "высокая разделимость: кластеры чётко отделены друг от друга"
    if score >= 0.5:
        return "хорошая разделимость: структура кластеров выражена достаточно явно"
    if score >= 0.25:
        return (
            "умеренная разделимость: группы различимы, но часть штаммов "
            "находится близко к границам соседних кластеров"
        )
    if score >= 0:
        return "слабая разделимость: структуру кластеров стоит трактовать осторожно"
    return "возможно, часть штаммов отнесена к неподходящим кластерам"


def cluster_feature_differences(cluster_data, all_data):
    cluster_means = cluster_data[NUMERIC_FEATURES].mean()
    overall_means = all_data[NUMERIC_FEATURES].mean()
    overall_stds = all_data[NUMERIC_FEATURES].std(ddof=0).replace(0, np.nan)
    deviations = ((cluster_means - overall_means) / overall_stds).dropna()
    deviations = deviations[deviations.abs() > 1e-12]
    strongest = deviations.abs().sort_values(ascending=False).head(2).index

    differences = []
    for feature in strongest:
        direction = "выше" if deviations[feature] > 0 else "ниже"
        differences.append(
            f"**{feature_label(feature)}** {direction} среднего "
            f"({format_decimal(cluster_means[feature])} против "
            f"{format_decimal(overall_means[feature])} по всему набору)"
        )
    return differences


st.title("Кластеризация штаммов бактерий")
st.markdown(
    "Научный дашборд для комплексного сравнения штаммов: иерархическая "
    "кластеризация, оценка качества разбиения и визуализация в пространстве "
    "главных компонент."
)
st.info(
    "**Что мы считаем и зачем.** Программа оценивает попарную похожесть "
    "штаммов по пяти количественным признакам, наличию плазмиды и источнику "
    "выделения, а затем объединяет наиболее похожие штаммы в группы. Это "
    "помогает находить закономерности и формулировать гипотезы для дальнейшего "
    "исследования, но не доказывает видовую принадлежность или родство штаммов."
)

with st.sidebar:
    st.header("Источник данных")
    source_option = st.radio(
        "Выберите способ получения данных",
        options=["Демонстрационные данные", "Загрузить CSV"],
        label_visibility="collapsed",
    )
    uploaded_file = None
    if source_option == "Загрузить CSV":
        uploaded_file = st.file_uploader(
            "CSV-файл с данными штаммов",
            type=["csv"],
            help="Первая строка файла должна содержать названия колонок.",
        )
    else:
        st.caption("Демонстрационный набор рассчитывается автоматически.")
    st.divider()
    st.caption("При смене источника данных все результаты и графики обновляются.")

if source_option == "Демонстрационные данные":
    raw_data = generate_demo_data()
else:
    if uploaded_file is None:
        st.subheader("Загрузка собственных данных")
        st.info("Выберите CSV-файл в боковой панели, чтобы начать анализ.")
        st.markdown("Файл должен содержать следующие обязательные колонки:")
        required_columns = [
            "strain_id",
            *list(NUMERIC_FEATURES),
            "has_plasmid",
            "source",
        ]
        st.markdown("\n".join(f"- `{column}`" for column in required_columns))
        st.caption(
            "`strain_id` — идентификатор штамма; `has_plasmid` — 0 или 1; "
            "`source` — soil, water или gut; остальные колонки — числовые признаки."
        )
        st.stop()

    try:
        raw_data = pd.read_csv(uploaded_file)
    except UnicodeDecodeError:
        st.error(
            "Не удалось прочитать CSV-файл. Проверьте кодировку файла; "
            "рекомендуется сохранить данные в UTF-8."
        )
        st.stop()
    except pd.errors.EmptyDataError:
        st.error("CSV-файл пуст или не содержит таблицу с данными.")
        st.stop()
    except pd.errors.ParserError as exc:
        st.error(f"Не удалось разобрать структуру CSV-файла: {exc}")
        st.stop()
    except OSError as exc:
        st.error(f"Не удалось открыть загруженный файл: {exc}")
        st.stop()
    except Exception as exc:
        st.error(f"Не удалось прочитать CSV-файл: {exc}")
        st.stop()

try:
    cleaned_data = validate_data(raw_data)
    result = analyze_strains(cleaned_data)
except DataValidationError as exc:
    st.error(f"Данные не прошли проверку: {exc}")
    st.stop()
except (ValueError, TypeError, KeyError) as exc:
    st.error(f"Не удалось выполнить расчёт. Проверьте корректность данных: {exc}")
    st.stop()


data = result.data
n = len(data)
k = int(result.optimal_k)
strain_ids = data["strain_id"].astype(str).tolist()
clusters = pd.DataFrame(result.clusters, columns=["strain_id", "cluster_label"])
cluster_labels = clusters["cluster_label"].to_numpy()
silhouette_scores = result.silhouette_scores.copy()
best_silhouette = float(silhouette_scores["silhouette_score"].max())

metric_columns = st.columns(3)
metric_columns[0].metric("Оптимальное число кластеров", k)
metric_columns[1].metric(
    "Лучший коэффициент силуэта", format_decimal(best_silhouette)
)
metric_columns[2].metric("Количество штаммов", n)
st.info(
    f"**Почему получилось k = {k}.** При этом числе кластеров коэффициент "
    f"силуэта равен **{format_decimal(best_silhouette)}** — это максимум среди "
    f"проверенных значений k от {int(silhouette_scores['k'].min())} до "
    f"{int(silhouette_scores['k'].max())}. Ориентировочно здесь "
    f"{silhouette_description(best_silhouette)}. Это оптимум по выбранной "
    "математической метрике, а не доказательство существования строго "
    "определённого числа биологических групп."
)
st.divider()

pca_tab, dendrogram_tab, k_tab, clusters_tab, method_tab, data_tab = st.tabs(
    ["PCA", "Дендрограмма", "Подбор k", "Кластеры", "Методика", "Данные"]
)

with pca_tab:
    st.subheader("Проекция штаммов на главные компоненты")
    coordinates = np.asarray(result.pca_coordinates)
    explained_variance = np.asarray(result.explained_variance_ratio, dtype=float)
    pca_data = pd.DataFrame(
        {
            "strain_id": data["strain_id"].to_numpy(),
            "cluster_label": cluster_labels,
            "PC1": coordinates[:, 0],
            "PC2": coordinates[:, 1],
        }
    )
    pca_plot_data = pca_data.copy()
    pca_plot_data["strain_id"] = pca_plot_data["strain_id"].astype(str)

    pca_figure = go.Figure()
    for color_index, cluster in enumerate(sorted(pca_plot_data["cluster_label"].unique())):
        cluster_data = pca_plot_data.loc[
            pca_plot_data["cluster_label"] == cluster
        ]
        pca_figure.add_trace(
            go.Scatter(
                x=cluster_data["PC1"],
                y=cluster_data["PC2"],
                mode="markers+text",
                name=f"Кластер {cluster}",
                text=cluster_data["strain_id"],
                textposition="top center",
                textfont={"size": 10, "color": "#334155"},
                marker={
                    "size": 12,
                    "color": CLUSTER_COLORS[color_index % len(CLUSTER_COLORS)],
                    "line": {"width": 1, "color": "#ffffff"},
                    "opacity": 0.9,
                },
                hovertemplate=(
                    "<b>Штамм %{text}</b><br>"
                    f"Кластер: {cluster}<br>"
                    "PC1: %{x:.3f}<br>PC2: %{y:.3f}<extra></extra>"
                ),
            )
        )

    pca_figure.update_layout(
        template="plotly_white",
        height=610,
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        font={"color": "#294556"},
        xaxis_title=(
            f"PC1 ({explained_variance[0] * 100:.1f}% объяснённой дисперсии)"
        ),
        yaxis_title=(
            f"PC2 ({explained_variance[1] * 100:.1f}% объяснённой дисперсии)"
        ),
        legend={
            "title": "Кластер",
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "x": 0,
            "bgcolor": "rgba(255,255,255,0.85)",
        },
        margin={"l": 65, "r": 35, "t": 90, "b": 65},
        hovermode="closest",
    )
    pca_figure.update_xaxes(
        gridcolor="#e4edf1",
        zeroline=True,
        zerolinecolor="#b8cbd4",
        zerolinewidth=1,
    )
    pca_figure.update_yaxes(
        gridcolor="#e4edf1",
        zeroline=True,
        zerolinecolor="#b8cbd4",
        zerolinewidth=1,
    )
    st.plotly_chart(
        pca_figure,
        width="stretch",
        config={"displaylogo": False, "responsive": True},
    )
    st.caption("Подписи и всплывающие подсказки показывают идентификаторы штаммов.")
    st.markdown(
        "**Как читать график.** Каждая точка — один штамм, цвет — назначенный "
        "кластер. Близкие точки имеют похожие сочетания признаков. Две главные "
        f"компоненты сохраняют **{explained_variance.sum() * 100:.1f}%** "
        "вариации предобработанных данных, поэтому проекция передаёт структуру "
        "лишь приблизительно. Сама кластеризация выполнена по полной матрице "
        "расстояний, а не только по этим двум осям."
    )
    st.download_button(
        "Скачать координаты PCA (CSV)",
        data=csv_bytes(pca_data),
        file_name="pca_coordinates.csv",
        mime="text/csv",
        key="download_pca_csv",
    )

with dendrogram_tab:
    st.subheader("Иерархическая кластеризация методом Уорда")
    st.markdown(
        "**Что показывает дерево.** Внизу находятся отдельные штаммы, а линии "
        "показывают их последовательное объединение. Чем выше соединяются две "
        "ветви, тем больше различие между объединяемыми группами. Красная "
        f"горизонтальная линия разрезает дерево так, чтобы получилось **k = {k}** "
        "кластеров."
    )
    Z = np.asarray(result.linkage_matrix)
    if k < n:
        threshold = float((Z[-k, 2] + Z[-k + 1, 2]) / 2)
    else:
        threshold = 0.0

    dendrogram_figure, axis = plt.subplots(figsize=(max(12, n * 0.6), 6.5))
    dendrogram_figure.patch.set_facecolor("#ffffff")
    axis.set_facecolor("#ffffff")
    try:
        dendrogram(
            Z,
            labels=strain_ids,
            ax=axis,
            leaf_rotation=45,
            leaf_font_size=10,
            color_threshold=threshold,
            above_threshold_color="#64748b",
        )
        axis.axhline(
            threshold,
            color="#dc2626",
            linestyle="--",
            linewidth=1.5,
            label=f"Порог отсечения для k = {k}",
        )
        axis.set_title(f"Разбиение на {k} кластеров", color="#123b52", pad=14)
        axis.set_xlabel("Штамм")
        axis.set_ylabel("Расстояние Уорда")
        axis.grid(axis="y", color="#dce7eb", linestyle=":", linewidth=0.8)
        axis.set_axisbelow(True)
        axis.spines["top"].set_visible(False)
        axis.spines["right"].set_visible(False)
        axis.legend(loc="upper right", frameon=False)
        dendrogram_figure.tight_layout()
        st.pyplot(dendrogram_figure, width="stretch")
    finally:
        plt.close(dendrogram_figure)

    st.caption(
        f"Пунктирная линия соответствует порогу {format_decimal(threshold)} "
        f"и выбранному числу кластеров k = {k}."
    )
    distance_matrix = pd.DataFrame(
        np.asarray(result.distance_matrix),
        index=strain_ids,
        columns=strain_ids,
    )
    distance_matrix.index.name = "strain_id"
    st.download_button(
        "Скачать матрицу расстояний (CSV)",
        data=csv_bytes(distance_matrix, index=True),
        file_name="distance_matrix.csv",
        mime="text/csv",
        key="download_distance_matrix_csv",
    )

with k_tab:
    st.subheader("Выбор числа кластеров по коэффициенту силуэта")
    score_plot_data = silhouette_scores.sort_values("k")
    score_figure = go.Figure()
    score_figure.add_trace(
        go.Scatter(
            x=score_plot_data["k"],
            y=score_plot_data["silhouette_score"],
            mode="lines+markers",
            name="Коэффициент силуэта",
            line={"color": "#0f8b8d", "width": 2.5},
            marker={"color": "#0f8b8d", "size": 9},
            hovertemplate="k = %{x}<br>Силуэт = %{y:.3f}<extra></extra>",
        )
    )
    optimal_points = score_plot_data.loc[score_plot_data["k"] == k]
    if not optimal_points.empty:
        score_figure.add_trace(
            go.Scatter(
                x=optimal_points["k"],
                y=optimal_points["silhouette_score"],
                mode="markers",
                name="Оптимальное k",
                marker={
                    "color": "#d97706",
                    "size": 15,
                    "symbol": "diamond",
                    "line": {"color": "#ffffff", "width": 1.5},
                },
                hovertemplate=(
                    "<b>Оптимум</b><br>k = %{x}<br>"
                    "Силуэт = %{y:.3f}<extra></extra>"
                ),
            )
        )
    score_figure.add_vline(
        x=k,
        line_dash="dash",
        line_color="#d97706",
        annotation_text=f"Оптимум: k = {k}",
        annotation_position="top",
        annotation_font_color="#9a5b06",
    )
    score_figure.update_layout(
        template="plotly_white",
        height=490,
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        font={"color": "#294556"},
        xaxis_title="Число кластеров (k)",
        yaxis_title="Коэффициент силуэта",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0},
        margin={"l": 65, "r": 35, "t": 80, "b": 60},
        hovermode="x unified",
    )
    score_figure.update_xaxes(dtick=1, gridcolor="#e4edf1")
    score_figure.update_yaxes(gridcolor="#e4edf1", zerolinecolor="#b8cbd4")
    st.plotly_chart(
        score_figure,
        width="stretch",
        config={"displaylogo": False, "responsive": True},
    )
    st.caption(
        "Чем выше коэффициент силуэта, тем лучше штаммы отделены от соседних "
        f"кластеров. Выбрано k = {k}."
    )
    st.markdown(
        "**Что означает силуэт.** Для каждого штамма `a(i)` — среднее расстояние "
        "до остальных штаммов своего кластера, а `b(i)` — среднее расстояние до "
        "ближайшего другого кластера. Для него вычисляется:"
    )
    st.latex(r"s(i) = \frac{b(i) - a(i)}{\max\{a(i), b(i)\}}")
    st.markdown(
        "Значение ближе к **1** означает, что штамм находится намного ближе к "
        "своей группе, чем к соседней. Значение около **0** указывает на "
        "близость к границе кластеров, а отрицательное — на возможное "
        "неправильное отнесение. На графике показано среднее значение по всем "
        "штаммам для каждого `k`."
    )
    score_display = score_plot_data.rename(
        columns={"k": "Число кластеров k", "silhouette_score": "Коэффициент силуэта"}
    ).round(4)
    st.dataframe(score_display, width="stretch", hide_index=True)

with clusters_tab:
    st.subheader("Принадлежность штаммов к кластерам")
    cluster_display = clusters.rename(
        columns={"strain_id": "Штамм", "cluster_label": "Кластер"}
    )
    st.dataframe(cluster_display, width="stretch", hide_index=True)

    cluster_export = data.copy()
    cluster_export["cluster_label"] = cluster_labels
    st.download_button(
        "Скачать штаммы и кластеры (CSV)",
        data=csv_bytes(cluster_export),
        file_name="clusters.csv",
        mime="text/csv",
        key="download_clusters_csv",
    )
    st.caption("Выгрузка содержит все очищенные исходные колонки и метку кластера.")

    st.subheader("Характеристики кластеров")
    st.markdown(
        "Средние значения исходных количественных признаков и преобладающий "
        "источник для каждого кластера."
    )
    cluster_summary = result.cluster_summary.copy()
    summary_labels = {
        column: feature_label(column)
        for column in [
            "cluster_label",
            "cluster_size",
            *list(NUMERIC_FEATURES),
            "dominant_source",
        ]
    }
    summary_display = cluster_summary.round(3).rename(columns=summary_labels)
    source_column = FEATURE_LABELS["dominant_source"]
    summary_display[source_column] = summary_display[source_column].replace(
        SOURCE_LABELS
    )
    st.dataframe(summary_display, width="stretch", hide_index=True)
    st.download_button(
        "Скачать характеристики кластеров (CSV)",
        data=csv_bytes(cluster_summary),
        file_name="cluster_summary.csv",
        mime="text/csv",
        key="download_cluster_summary_csv",
    )

    st.subheader("Почему получились такие группы")
    st.markdown(
        "Ниже перечислены самые заметные отличия средних значений кластера от "
        "средних по всему набору. Для сравнения признаков между собой отличия "
        "измеряются в стандартных отклонениях. Это помогает понять результат, "
        "но не означает, что только эти признаки повлияли на разбиение."
    )
    available_clusters = sorted(cluster_export["cluster_label"].unique())
    for cluster in available_clusters:
        cluster_data = cluster_export.loc[
            cluster_export["cluster_label"] == cluster
        ]
        summary_row = cluster_summary.loc[
            cluster_summary["cluster_label"] == cluster
        ].iloc[0]
        dominant_source = summary_row["dominant_source"]
        source_name = SOURCE_LABELS.get(dominant_source, dominant_source)
        differences = cluster_feature_differences(cluster_data, data)

        with st.expander(
            f"Кластер {cluster} — штаммов: {len(cluster_data)}",
            expanded=cluster == available_clusters[0],
        ):
            st.markdown(
                f"**Состав:** {', '.join(cluster_data['strain_id'])}"
            )
            st.markdown(f"- Преобладающий источник: **{source_name}**.")
            st.markdown(
                f"- Плазмида есть у **{cluster_data['has_plasmid'].mean():.0%}** "
                "штаммов группы."
            )
            if differences:
                st.markdown("**Наиболее заметные отличия от общего среднего:**")
                for difference in differences:
                    st.markdown(f"- {difference}")
            else:
                st.markdown(
                    "Средние числовые признаки совпадают со средними по набору; "
                    "различия могут быть связаны с распределением внутри группы, "
                    "плазмидой или источником."
                )
    st.caption(
        "Кластеризация использует всю совокупность признаков. Представленные "
        "описания объясняют наблюдаемые различия, но не являются правилами "
        "классификации или доказательством причинно-следственных связей."
    )

with method_tab:
    st.subheader("Как из исходной таблицы получаются кластеры")

    st.markdown("**1. Зачем нужна предобработка**")
    st.markdown(
        "Признаки измерены в разных шкалах: например, GC-состав выражается "
        "десятками процентов, а наличие плазмиды — только 0 или 1. Без "
        "подготовки признаки с большими числами непропорционально сильно "
        "влияли бы на евклидово расстояние. Поэтому каждый числовой признак "
        "стандартизируется: из значения вычитается среднее, а результат делится "
        "на стандартное отклонение."
    )
    st.latex(r"z = \frac{x - \mu}{\sigma}")
    st.markdown(
        "После стандартизации среднее каждого признака равно 0, а стандартное "
        "отклонение неконстантных признаков — 1. Категориальный источник "
        "преобразуется в три отдельных бинарных столбца методом one-hot: "
        "`soil`, `water`, `gut`. Так категории "
        "можно использовать в расчёте расстояний без искусственного порядка "
        "«почва < вода < кишечник»."
    )

    st.markdown("**2. Как измеряется похожесть штаммов**")
    st.markdown(
        "Для каждой пары штаммов вычисляются три независимые компоненты "
        "расстояния: евклидово расстояние по стандартизованным числовым "
        "признакам, расстояние Хэмминга для плазмиды и евклидово расстояние "
        "между one-hot векторами источника. Каждая компонента делится на своё "
        "максимальное значение, чтобы находиться в сопоставимом диапазоне."
    )
    st.latex(
        r"D = 0.6 D_{numeric} + 0.2 D_{plasmid} + 0.2 D_{source}"
    )
    st.markdown(
        "Чем меньше итоговое `D`, тем более похожи штаммы. Веса **0,6 / 0,2 / "
        "0,2** заданы условием задачи: наибольший вклад внесён количественными "
        "характеристиками, а бинарный и категориальный признаки дополняют его. "
        "Эти веса влияют на результат и не являются универсальными для всех "
        "биологических исследований."
    )

    st.markdown("**3. Как строятся кластеры**")
    st.markdown(
        "Сначала каждый штамм считается отдельным кластером. Затем метод Уорда "
        "последовательно объединяет группы, выбирая объединение с наименьшим "
        "приростом внутрикластерного разброса. В этой работе метод применяется "
        "к итоговой взвешенной матрице расстояний, как указано в задании. "
        "Дендрограмма сохраняет историю таких объединений."
    )

    st.markdown("**4. Почему выбирается оптимальное k**")
    st.markdown(
        "Одно и то же дерево можно разрезать на разное число групп. Поэтому "
        "программа последовательно получает разбиения для допустимых значений "
        "`k` и сравнивает их по среднему коэффициенту силуэта. Выбирается `k` "
        "с максимальным значением метрики: при нём объекты в среднем наиболее "
        "близки к своей группе и наиболее удалены от соседних. Для набора из 20 "
        "штаммов проверяются все значения от 2 до 10."
    )

    st.markdown("**5. Зачем нужен PCA**")
    st.markdown(
        "Исходное пространство признаков многомерно и не может быть напрямую "
        "показано на плоском графике. PCA строит две новые оси, сохраняющие "
        "как можно большую долю вариации данных. Это упрощает визуальное "
        "изучение групп, но не заменяет полный расчёт: кластеризация уже "
        "выполнена до построения проекции."
    )

    st.warning(
        "**Как правильно трактовать результат.** Демонстрационный набор "
        "синтетический и содержит случайные значения, поэтому найденные группы "
        "показывают работу алгоритма, а не реальные биологические закономерности. "
        "На результат также влияют выбранные веса и метрики. Номера кластеров "
        "являются техническими метками: кластер 3 не «лучше» кластера 1."
    )

with data_tab:
    st.subheader("Исходные данные после проверки")
    st.caption(f"Показаны {n} штаммов в исходном порядке строк.")
    st.dataframe(data, width="stretch", hide_index=True)
    if source_option == "Демонстрационные данные":
        st.caption(
            "Демонстрационные данные создаются генератором случайных чисел с "
            "фиксированным seed = 123, поэтому таблица и результаты "
            "воспроизводятся при каждом запуске."
        )

    with st.expander("Что означают столбцы таблицы"):
        feature_descriptions = pd.DataFrame(
            [
                ("strain_id", "Уникальный идентификатор штамма."),
                ("growth_rate", "Количественная характеристика скорости роста."),
                ("product_yield", "Количественная характеристика выхода продукта."),
                ("pH_tolerance", "Устойчивость штамма к условиям pH."),
                ("GC_content", "Доля гуанина и цитозина в составе генома, %."),
                ("genome_size_mbp", "Размер генома в миллионах пар оснований."),
                ("has_plasmid", "Наличие плазмиды: 1 — есть, 0 — нет."),
                ("source", "Источник выделения: почва, вода или кишечник."),
            ],
            columns=["Столбец", "Значение"],
        )
        st.dataframe(feature_descriptions, width="stretch", hide_index=True)
