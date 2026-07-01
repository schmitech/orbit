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
:: Try the Python Launcher (py.exe) first — it bypasses Microsoft Store App Execution Aliases.
SET "PYTHON_CMD="
WHERE py >NUL 2>&1
IF NOT ERRORLEVEL 1 (
    FOR %%V IN (3.14 3.13 3.12 3.11) DO (
        IF "!PYTHON_CMD!"=="" (
            py -%%V --version >NUL 2>&1
            IF NOT ERRORLEVEL 1 (
                FOR /F "tokens=*" %%P IN ('py -%%V -c "import sys; print(sys.executable)"') DO (
                    IF "!PYTHON_CMD!"=="" SET "PYTHON_CMD=%%P"
                )
            )
        )
    )
)
:: Fall back to named executables on PATH
FOR %%P IN (python3.14 python3.13 python3.12 python3 python) DO (
    IF "!PYTHON_CMD!"=="" (
        WHERE %%P >NUL 2>&1
        IF NOT ERRORLEVEL 1 (
            FOR /F "tokens=*" %%V IN ('%%P -c "import sys; print(sys.version_info >= (3,12))"') DO (
                IF "%%V"=="True" SET "PYTHON_CMD=%%P"
            )
        )
    )
)

IF "!PYTHON_CMD!"=="" (
    echo ERROR: Python 3.12 or higher is required but was not found.
    echo.
    echo If Python is installed but not detected, check for the Microsoft Store
    echo App Execution Alias: Settings ^> Apps ^> Advanced app settings ^>
    echo App execution aliases ^> turn off "python.exe" and "python3.exe".
    echo.
    echo Or install Python 3.12+ from https://www.python.org/downloads/
    echo and ensure "Add Python to PATH" is checked during installation.
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
