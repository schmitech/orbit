@echo off
SETLOCAL ENABLEDELAYEDEXPANSION

:: ORBIT CLI Windows Wrapper
:: Requires Python 3.12+ to be installed and accessible on PATH.

:: Resolve the directory containing this script, then the project root (one level up)
SET "SCRIPT_DIR=%~dp0"
SET "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
FOR %%I IN ("%SCRIPT_DIR%\..") DO SET "PROJECT_ROOT=%%~fI"

SET "ORBIT_PY=%SCRIPT_DIR%\orbit.py"

:: Activate virtual environment if one exists and we're not already inside one
IF "%VIRTUAL_ENV%"=="" (
    FOR %%V IN (
        "%PROJECT_ROOT%\venv\Scripts\activate.bat"
        "%PROJECT_ROOT%\.venv\Scripts\activate.bat"
        "%SCRIPT_DIR%\venv\Scripts\activate.bat"
        "%SCRIPT_DIR%\.venv\Scripts\activate.bat"
    ) DO (
        IF EXIST %%V (
            echo Activating virtual environment...
            CALL %%V
            GOTO :venv_done
        )
    )
)
:venv_done

:: Locate a suitable Python interpreter (3.12+)
SET "PYTHON_CMD="
FOR %%P IN (python3.12 python3.13 python3 python) DO (
    IF "!PYTHON_CMD!"=="" (
        WHERE %%P >NUL 2>&1
        IF NOT ERRORLEVEL 1 (
            FOR /F "tokens=*" %%V IN ('%%P -c "import sys; ok = sys.version_info >= (3,12); print(ok)"') DO (
                IF "%%V"=="True" SET "PYTHON_CMD=%%P"
            )
        )
    )
)

IF "%PYTHON_CMD%"=="" (
    echo ERROR: Python 3.12 or higher is required but was not found.
    echo Please install Python 3.12+ from https://www.python.org/downloads/ and ensure it is on your PATH.
    exit /b 1
)

IF NOT EXIST "%ORBIT_PY%" (
    echo ERROR: orbit.py not found at: %ORBIT_PY%
    exit /b 1
)

SET "PYTHONPATH=%PROJECT_ROOT%;%PYTHONPATH%"
SET "PYTHONUNBUFFERED=1"

"%PYTHON_CMD%" "%ORBIT_PY%" %*
exit /b %ERRORLEVEL%
