@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "VENV=%ROOT%\.venv"
set "LOCAL_PYTHON=%ROOT%\.python"
set "BASE_PYTHON="

if not exist "%ROOT%\app.py" (
    echo [ОШИБКА] Рядом с run.bat не найден файл app.py.
    goto :early_error
)
if not exist "%ROOT%\requirements.txt" (
    echo [ОШИБКА] Рядом с run.bat не найден файл requirements.txt.
    goto :early_error
)

pushd "%ROOT%" >nul 2>&1
if errorlevel 1 (
    echo [ОШИБКА] Не удалось открыть папку проекта: %ROOT%
    goto :early_error
)

echo Папка проекта: %ROOT%
echo.

if exist "%VENV%\Scripts\python.exe" (
    "%VENV%\Scripts\python.exe" -c "import sys; raise SystemExit(0 if (3, 10) <= sys.version_info[:2] < (3, 14) else 1)" >nul 2>&1
    if not errorlevel 1 goto :dependencies
    echo Локальное окружение повреждено или использует неподдерживаемый Python.
    echo Оно будет создано заново.
)

if exist "%VENV%" (
    rmdir /s /q "%VENV%"
    if exist "%VENV%" (
        echo [ОШИБКА] Не удалось удалить старую папку .venv.
        echo Закройте приложение и другие программы, использующие её, затем повторите запуск.
        goto :error
    )
)

call :find_python
if not defined BASE_PYTHON call :install_python
if not defined BASE_PYTHON goto :error

echo Создание изолированного окружения .venv...
%BASE_PYTHON% -m venv "%VENV%"
if errorlevel 1 (
    echo [ОШИБКА] Не удалось создать виртуальное окружение.
    goto :error
)

:dependencies
echo Проверка версий библиотек...
"%VENV%\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check -r "%ROOT%\requirements.txt"
if errorlevel 1 (
    echo.
    echo [ОШИБКА] Не удалось установить или обновить библиотеки.
    echo При первой настройке нужен доступ к интернету. Проверьте соединение и повторите запуск.
    goto :error
)

"%VENV%\Scripts\python.exe" -m pip check >nul
if errorlevel 1 (
    echo [ОШИБКА] Обнаружен конфликт установленных библиотек:
    "%VENV%\Scripts\python.exe" -m pip check
    goto :error
)

"%VENV%\Scripts\python.exe" -c "import matplotlib, numpy, pandas, plotly, scipy, sklearn, streamlit" >nul 2>&1
if errorlevel 1 (
    echo [ОШИБКА] Библиотеки установлены, но хотя бы одна из них не загружается.
    "%VENV%\Scripts\python.exe" -c "import matplotlib, numpy, pandas, plotly, scipy, sklearn, streamlit"
    goto :error
)

echo Библиотеки в порядке. Запуск приложения...
echo Адрес: http://127.0.0.1:8501
echo Для остановки закройте это окно или нажмите Ctrl+C.
echo.
"%VENV%\Scripts\python.exe" -m streamlit run "%ROOT%\app.py" --server.address 127.0.0.1 --server.port 8501 --browser.gatherUsageStats false
if errorlevel 1 (
    echo.
    echo [ОШИБКА] Приложение завершилось с ошибкой. Проверьте сообщение выше.
    goto :error
)

popd
exit /b 0

:find_python
if exist "%LOCAL_PYTHON%\python.exe" (
    "%LOCAL_PYTHON%\python.exe" -c "import sys; raise SystemExit(0 if (3, 10) <= sys.version_info[:2] < (3, 14) else 1)" >nul 2>&1
    if not errorlevel 1 (
        set "BASE_PYTHON="%LOCAL_PYTHON%\python.exe""
        goto :eof
    )
)
for %%V in (3.11 3.12 3.13 3.10) do (
    py -%%V -c "import sys" >nul 2>&1
    if not errorlevel 1 (
        set "BASE_PYTHON=py -%%V"
        goto :eof
    )
)
python -c "import sys; raise SystemExit(0 if (3, 10) <= sys.version_info[:2] < (3, 14) else 1)" >nul 2>&1
if not errorlevel 1 (
    set "BASE_PYTHON=python"
    goto :eof
)
python3 -c "import sys; raise SystemExit(0 if (3, 10) <= sys.version_info[:2] < (3, 14) else 1)" >nul 2>&1
if not errorlevel 1 set "BASE_PYTHON=python3"
goto :eof

:install_python
echo Подходящий Python не найден. Будет установлен Python 3.11 локально в папку проекта.
echo Системный Python и его настройки изменены не будут.
echo Для скачивания нужен интернет.
set "PYTHON_INSTALLER=%TEMP%\strain-python-3.11.9-%RANDOM%%RANDOM%.exe"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe' -OutFile $env:PYTHON_INSTALLER"
if errorlevel 1 (
    echo [ОШИБКА] Не удалось скачать Python с python.org.
    del /q "%PYTHON_INSTALLER%" >nul 2>&1
    goto :eof
)
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "$s=Get-AuthenticodeSignature -FilePath $env:PYTHON_INSTALLER; if ($s.Status -ne 'Valid' -or $s.SignerCertificate.Subject -notmatch 'Python Software Foundation') { exit 1 }"
if errorlevel 1 (
    echo [ОШИБКА] Загруженный установщик не прошёл проверку цифровой подписи.
    del /q "%PYTHON_INSTALLER%" >nul 2>&1
    goto :eof
)
"%PYTHON_INSTALLER%" /quiet InstallAllUsers=0 TargetDir="%LOCAL_PYTHON%" Include_test=0 Include_launcher=0 Include_doc=0 Include_pip=1 PrependPath=0 Shortcuts=0 AssociateFiles=0
set "INSTALL_RESULT=%ERRORLEVEL%"
del /q "%PYTHON_INSTALLER%" >nul 2>&1
if not "%INSTALL_RESULT%"=="0" (
    echo [ОШИБКА] Установщик Python завершился с кодом %INSTALL_RESULT%.
    goto :eof
)
"%LOCAL_PYTHON%\python.exe" -c "import sys" >nul 2>&1
if errorlevel 1 (
    echo [ОШИБКА] Локальный Python установлен некорректно.
    goto :eof
)
set "BASE_PYTHON="%LOCAL_PYTHON%\python.exe""
goto :eof

:error
popd
:early_error
echo.
pause
exit /b 1
