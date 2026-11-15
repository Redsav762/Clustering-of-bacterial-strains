@echo off
setlocal EnableExtensions DisableDelayedExpansion

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "VENV=%ROOT%\.venv"
set "LOCAL_PYTHON=%ROOT%\.python"
set "BASE_PYTHON="

if not exist "%ROOT%\app.py" (
    echo [ERROR] app.py was not found next to run.bat.
    goto :early_error
)
if not exist "%ROOT%\requirements.txt" (
    echo [ERROR] requirements.txt was not found next to run.bat.
    goto :early_error
)

pushd "%ROOT%" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Cannot open the project folder: %ROOT%
    goto :early_error
)

echo Project folder: %ROOT%
echo.

if exist "%VENV%\Scripts\python.exe" (
    "%VENV%\Scripts\python.exe" -c "import sys; raise SystemExit(0 if (3, 10) <= sys.version_info[:2] < (3, 14) else 1)" >nul 2>&1
    if not errorlevel 1 goto :dependencies
    echo The local environment is damaged or uses an unsupported Python version.
    echo It will be created again.
)

if exist "%VENV%" (
    rmdir /s /q "%VENV%"
    if exist "%VENV%" (
        echo [ERROR] Cannot remove the old .venv folder.
        echo Close the application and other programs that use it, then try again.
        goto :error
    )
)

call :find_python
if not defined BASE_PYTHON call :install_python
if not defined BASE_PYTHON goto :error

echo Creating the isolated .venv environment...
%BASE_PYTHON% -m venv "%VENV%"
if errorlevel 1 (
    echo [ERROR] Cannot create the virtual environment.
    goto :error
)

:dependencies
echo Checking library versions...
echo The first installation can take several minutes. Please wait.
"%VENV%\Scripts\python.exe" -m pip install --disable-pip-version-check -r "%ROOT%\requirements.txt"
if errorlevel 1 (
    echo.
    echo [ERROR] Cannot install or update the libraries.
    echo An internet connection is required for the first setup. Check the connection and try again.
    goto :error
)

"%VENV%\Scripts\python.exe" -m pip check >nul
if errorlevel 1 (
    echo [ERROR] A library dependency conflict was detected:
    "%VENV%\Scripts\python.exe" -m pip check
    goto :error
)

"%VENV%\Scripts\python.exe" -c "import matplotlib, numpy, pandas, plotly, scipy, sklearn, streamlit" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] The libraries are installed, but at least one of them cannot be imported.
    "%VENV%\Scripts\python.exe" -c "import matplotlib, numpy, pandas, plotly, scipy, sklearn, streamlit"
    goto :error
)

echo The libraries are ready. Starting the application...
echo Address: http://127.0.0.1:8501
echo To stop the application, close this window or press Ctrl+C.
echo.
"%VENV%\Scripts\python.exe" -m streamlit run "%ROOT%\app.py" --server.address 127.0.0.1 --server.port 8501 --browser.gatherUsageStats false
if errorlevel 1 (
    echo.
    echo [ERROR] The application exited with an error. Check the messages above.
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
echo No suitable Python was found. Python 3.11 will be installed locally in the project folder.
echo The system Python and its settings will not be changed.
echo An internet connection is required for the download.
set "PYTHON_INSTALLER=%TEMP%\strain-python-3.11.9-%RANDOM%%RANDOM%.exe"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe' -OutFile $env:PYTHON_INSTALLER"
if errorlevel 1 (
    echo [ERROR] Cannot download Python from python.org.
    del /q "%PYTHON_INSTALLER%" >nul 2>&1
    goto :eof
)
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "$s=Get-AuthenticodeSignature -FilePath $env:PYTHON_INSTALLER; if ($s.Status -ne 'Valid' -or $s.SignerCertificate.Subject -notmatch 'Python Software Foundation') { exit 1 }"
if errorlevel 1 (
    echo [ERROR] The downloaded Python installer failed the digital signature check.
    del /q "%PYTHON_INSTALLER%" >nul 2>&1
    goto :eof
)
"%PYTHON_INSTALLER%" /quiet InstallAllUsers=0 TargetDir="%LOCAL_PYTHON%" Include_test=0 Include_launcher=0 Include_doc=0 Include_pip=1 PrependPath=0 Shortcuts=0 AssociateFiles=0
set "INSTALL_RESULT=%ERRORLEVEL%"
del /q "%PYTHON_INSTALLER%" >nul 2>&1
if not "%INSTALL_RESULT%"=="0" (
    echo [ERROR] The Python installer exited with code %INSTALL_RESULT%.
    goto :eof
)
"%LOCAL_PYTHON%\python.exe" -c "import sys" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] The local Python installation is broken.
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
