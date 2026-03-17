@echo off
setlocal enableextensions

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

set "VENV_DIR=.venv_windows"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
set "REQUIREMENTS_FILE=wic_app\requirements.txt"
set "APP_ENTRYPOINT=wic_app\app.py"
set "REQ_HASH_FILE=%VENV_DIR%\.requirements.sha256"

call :find_python
if errorlevel 1 goto :pause_and_exit

call :ensure_venv
if errorlevel 1 goto :pause_and_exit

if not exist "%REQUIREMENTS_FILE%" (
  echo Error: missing %REQUIREMENTS_FILE%
  exit /b 1
)

for /f %%I in ('%PYTHON_CMD% -c "import hashlib, pathlib; print(hashlib.sha256(pathlib.Path(r\"%REQUIREMENTS_FILE%\").read_bytes()).hexdigest())"') do set "CURRENT_HASH=%%I"
set "INSTALLED_HASH="
if exist "%REQ_HASH_FILE%" set /p INSTALLED_HASH=<"%REQ_HASH_FILE%"

set "INSTALL_DEPS="
"%VENV_PY%" -c "import streamlit" >nul 2>&1 || set "INSTALL_DEPS=1"
if not "%CURRENT_HASH%"=="%INSTALLED_HASH%" set "INSTALL_DEPS=1"

if defined INSTALL_DEPS (
  echo Installing/updating dependencies...
  "%VENV_PY%" -m pip install --upgrade pip || goto :pause_and_exit
  "%VENV_PY%" -m pip install -r "%REQUIREMENTS_FILE%" || goto :pause_and_exit
  >"%REQ_HASH_FILE%" echo %CURRENT_HASH%
) else (
  echo Dependencies are up to date.
)

echo Starting WIC Reclassification Studio...
"%VENV_PY%" -m streamlit run "%APP_ENTRYPOINT%"
set "EXIT_CODE=%ERRORLEVEL%"

echo.
echo WIC Studio stopped.
if not "%EXIT_CODE%"=="0" (
  echo Streamlit exited with code %EXIT_CODE%.
)
pause
exit /b %EXIT_CODE%

:find_python
where py >nul 2>&1
if not errorlevel 1 (
  set "PYTHON_CMD=py -3"
  exit /b 0
)
where python >nul 2>&1
if not errorlevel 1 (
  set "PYTHON_CMD=python"
  exit /b 0
)
echo Error: python3 is not installed or not in PATH.
exit /b 1

:ensure_venv
if exist "%VENV_PY%" exit /b 0

if exist "%VENV_DIR%" (
  set "BACKUP_DIR=%VENV_DIR%.broken.%RANDOM%%RANDOM%"
  echo Detected unusable Windows virtual environment at %VENV_DIR%.
  move "%VENV_DIR%" "%BACKUP_DIR%" >nul || (
    echo Error: Could not move old %VENV_DIR%.
    exit /b 1
  )
  echo Moved old environment to %BACKUP_DIR%
)

echo Creating Windows virtual environment (%VENV_DIR%)...
%PYTHON_CMD% -m venv "%VENV_DIR%" || exit /b 1

if exist "%VENV_PY%" exit /b 0

echo Error: failed to create %VENV_DIR%.
exit /b 1

:pause_and_exit
set "EXIT_CODE=%ERRORLEVEL%"
pause
exit /b %EXIT_CODE%
