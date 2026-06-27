@echo off
SETLOCAL ENABLEDELAYEDEXPANSION

:: ORBIT Windows Setup Script
:: Equivalent to install/setup.sh for Windows environments.
:: Requires Python 3.12+ installed and on PATH.
::
:: Usage:
::   setup.bat                                    Minimal install (default deps)
::   setup.bat --profile default                  Recommended default setup
::   setup.bat --profile llama-cpp                Direct GGUF model loading
::   setup.bat --list-profiles                    List available profiles
::   setup.bat --profile default --wizard         Install + run interactive wizard
::   setup.bat --download-gguf gemma3-270m        Download a GGUF model
::   setup.bat --profile llama-cpp --download-gguf gemma3-270m
::   setup.bat --torch-backend cpu                Force CPU-only PyTorch
::   setup.bat --torch-backend cuda               Force CUDA PyTorch
::   setup.bat --help

SET "SCRIPT_DIR=%~dp0"
SET "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
FOR %%I IN ("%SCRIPT_DIR%\..") DO SET "PROJECT_ROOT=%%~fI"
SET "VENV_DIR=%PROJECT_ROOT%\venv"
SET "TOML_FILE=%SCRIPT_DIR%\dependencies.toml"
SET "GGUF_MODELS_CONFIG=%SCRIPT_DIR%\gguf-models.json"

SET "PROFILES="
SET "DOWNLOAD_GGUF=false"
SET "GGUF_MODEL="
SET "LIST_PROFILES=false"
SET "TORCH_BACKEND=auto"
SET "RUN_WIZARD=false"
SET "PYTHON_CMD="
SET "NEEDS_TORCH=false"
SET "NEEDS_VLLM=false"
SET "TORCH_SPEC=torch"
SET "TORCHVISION_SPEC="
SET "VLLM_SPEC=vllm"

:: ---------------------------------------------------------------------------
:: Argument parsing
:: ---------------------------------------------------------------------------
:parse_loop
IF "%~1"=="" GOTO :parse_done
SET "_ARG=%~1"

IF /I "!_ARG!"=="--profile"         GOTO :arg_profile
IF /I "!_ARG!"=="-p"                GOTO :arg_profile
IF /I "!_ARG!"=="--profiles"        GOTO :arg_profiles
IF /I "!_ARG!"=="--download-gguf"   GOTO :arg_gguf
IF /I "!_ARG!"=="--gguf-models-config" (
    SHIFT & SET "GGUF_MODELS_CONFIG=%~1" & SHIFT & GOTO :parse_loop
)
IF /I "!_ARG!"=="--list-profiles"   (SET "LIST_PROFILES=true"  & SHIFT & GOTO :parse_loop)
IF /I "!_ARG!"=="--list"            (SET "LIST_PROFILES=true"  & SHIFT & GOTO :parse_loop)
IF /I "!_ARG!"=="--torch-backend"   GOTO :arg_torch
IF /I "!_ARG!"=="--wizard"          (SET "RUN_WIZARD=true"     & SHIFT & GOTO :parse_loop)
IF /I "!_ARG!"=="--python-cmd"      (SHIFT & SET "PYTHON_CMD=%~1" & SHIFT & GOTO :parse_loop)
IF /I "!_ARG!"=="--help"            GOTO :show_help
IF /I "!_ARG!"=="-h"                GOTO :show_help
echo ERROR: Unknown option: !_ARG!
echo Use --help for available options.
exit /b 1

:arg_profile
SHIFT
IF "%~1"=="" GOTO :parse_loop
IF "!PROFILES!"=="" (SET "PROFILES=%~1") ELSE (SET "PROFILES=!PROFILES! %~1")
SHIFT
GOTO :parse_loop

:arg_profiles
SHIFT
IF "%~1"=="" GOTO :parse_loop
SET "_RAW=%~1"
SET "PROFILES=!_RAW:,= !"
SHIFT
GOTO :parse_loop

:arg_gguf
SET "DOWNLOAD_GGUF=true"
SHIFT
IF NOT "%~1"=="" (
    SET "_NEXT=%~1"
    IF NOT "!_NEXT:~0,1!"=="-" (SET "GGUF_MODEL=%~1" & SHIFT)
)
GOTO :parse_loop

:arg_torch
SHIFT
SET "TORCH_BACKEND=%~1"
SHIFT
GOTO :parse_loop

:parse_done

:: ---------------------------------------------------------------------------
:: Find Python interpreter
:: ---------------------------------------------------------------------------
IF NOT "%PYTHON_CMD%"=="" GOTO :python_found
:: Try the Python Launcher (py.exe) first — it bypasses Microsoft Store App Execution Aliases.
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

:python_found
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
FOR /F "tokens=*" %%V IN ('!PYTHON_CMD! -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')"') DO (
    echo [INFO] Using Python %%V ^(!PYTHON_CMD!^)
)

:: ---------------------------------------------------------------------------
:: Validate dependencies.toml
:: ---------------------------------------------------------------------------
IF NOT EXIST "%TOML_FILE%" (
    echo ERROR: dependencies.toml not found at: %TOML_FILE%
    exit /b 1
)

:: ---------------------------------------------------------------------------
:: --list-profiles
:: ---------------------------------------------------------------------------
IF "%LIST_PROFILES%"=="true" (
    echo Available dependency profiles:
    "!PYTHON_CMD!" "%SCRIPT_DIR%\win_setup_helper.py" list "%TOML_FILE%"
    exit /b 0
)

:: ---------------------------------------------------------------------------
:: Torch backend auto-detection (cuda or cpu; metal is Linux/macOS only)
:: ---------------------------------------------------------------------------
IF /I "!TORCH_BACKEND!"=="metal" (
    echo ERROR: Metal backend is macOS-only. Use 'cpu' or 'cuda' on Windows.
    exit /b 1
)
IF /I "!TORCH_BACKEND!"=="auto" (
    WHERE nvidia-smi >NUL 2>&1
    IF NOT ERRORLEVEL 1 (
        SET "TORCH_BACKEND=cuda"
        echo [INFO] NVIDIA GPU detected - using CUDA PyTorch wheels.
    ) ELSE (
        SET "TORCH_BACKEND=cpu"
        echo [INFO] No NVIDIA GPU detected - using CPU PyTorch wheels.
    )
) ELSE (
    echo [INFO] Torch backend ^(--torch-backend^): !TORCH_BACKEND!
)

:: ---------------------------------------------------------------------------
:: Download-only mode: no profiles, just GGUF download
:: ---------------------------------------------------------------------------
IF "%DOWNLOAD_GGUF%"=="true" IF "!PROFILES!"=="" (
    echo [INFO] Download-only mode - skipping full dependency install.
    IF NOT EXIST "%VENV_DIR%\Scripts\activate.bat" (
        "!PYTHON_CMD!" -m venv "%VENV_DIR%"
        IF ERRORLEVEL 1 (echo ERROR: Failed to create virtual environment. & exit /b 1)
    )
    CALL "%VENV_DIR%\Scripts\activate.bat"
    pip install requests tqdm pyyaml >NUL
    GOTO :do_gguf_download
)

:: ---------------------------------------------------------------------------
:: Create virtual environment
:: ---------------------------------------------------------------------------
IF NOT EXIST "%VENV_DIR%\Scripts\activate.bat" (
    echo [INFO] Creating Python virtual environment...
    "!PYTHON_CMD!" -m venv "%VENV_DIR%"
    IF ERRORLEVEL 1 (echo ERROR: Failed to create virtual environment. & exit /b 1)
    echo [OK] Virtual environment created at: %VENV_DIR%
)

:: ---------------------------------------------------------------------------
:: Activate virtual environment
:: ---------------------------------------------------------------------------
echo [INFO] Activating virtual environment...
CALL "%VENV_DIR%\Scripts\activate.bat"

:: ---------------------------------------------------------------------------
:: Upgrade pip
:: ---------------------------------------------------------------------------
echo [INFO] Upgrading pip...
python -m pip install --upgrade pip
IF ERRORLEVEL 1 echo WARNING: Could not upgrade pip. Continuing with current version.

:: ---------------------------------------------------------------------------
:: Ensure TOML parser is available (needed for Python ^< 3.11)
:: ---------------------------------------------------------------------------
python -c "import tomllib" 2>NUL
IF ERRORLEVEL 1 (
    echo [INFO] Installing tomli ^(TOML parser for Python ^< 3.11^)...
    pip install tomli
    IF ERRORLEVEL 1 (echo ERROR: Failed to install tomli. & exit /b 1)
)

:: ---------------------------------------------------------------------------
:: Resolve dependencies to a temp requirements file
:: ---------------------------------------------------------------------------
SET "TEMP_REQS=%TEMP%\orbit_reqs_%RANDOM%.txt"

IF "!PROFILES!"=="" (
    echo [INFO] Installing default dependencies...
    python "%SCRIPT_DIR%\win_setup_helper.py" resolve "%TOML_FILE%" > "%TEMP_REQS%"
) ELSE (
    echo [INFO] Installing default + profiles: !PROFILES!
    python "%SCRIPT_DIR%\win_setup_helper.py" resolve "%TOML_FILE%" !PROFILES! > "%TEMP_REQS%"
)
IF ERRORLEVEL 1 (
    echo ERROR: Failed to resolve dependencies from dependencies.toml.
    DEL /F /Q "%TEMP_REQS%" 2>NUL
    exit /b 1
)

:: ---------------------------------------------------------------------------
:: Extract torch / torchvision / vllm for platform-specific wheel installation
:: ---------------------------------------------------------------------------
findstr /R "^torch " "%TEMP_REQS%" >NUL 2>&1
IF NOT ERRORLEVEL 1 (
    SET "NEEDS_TORCH=true"
    FOR /F "tokens=*" %%L IN ('findstr /R "^torch " "%TEMP_REQS%"') DO SET "TORCH_SPEC=%%L"
)
findstr /R "^torch==" "%TEMP_REQS%" >NUL 2>&1
IF NOT ERRORLEVEL 1 (
    SET "NEEDS_TORCH=true"
    FOR /F "tokens=*" %%L IN ('findstr /R "^torch==" "%TEMP_REQS%"') DO SET "TORCH_SPEC=%%L"
)
findstr /R "^torchvision" "%TEMP_REQS%" >NUL 2>&1
IF NOT ERRORLEVEL 1 (
    SET "NEEDS_TORCH=true"
    FOR /F "tokens=*" %%L IN ('findstr /R "^torchvision" "%TEMP_REQS%"') DO SET "TORCHVISION_SPEC=%%L"
)
findstr /R "^vllm" "%TEMP_REQS%" >NUL 2>&1
IF NOT ERRORLEVEL 1 (
    SET "NEEDS_VLLM=true"
    FOR /F "tokens=*" %%L IN ('findstr /R "^vllm" "%TEMP_REQS%"') DO SET "VLLM_SPEC=%%L"
)

:: Remove torch/torchvision/vllm from main requirements — installed separately below
python -c "import re; lines=open(r'%TEMP_REQS%').readlines(); out=[l for l in lines if not re.match(r'^(torch|torchvision|vllm)([>=!<\s]|$)', l)]; open(r'%TEMP_REQS%','w').writelines(out)"

:: ---------------------------------------------------------------------------
:: Install main requirements
:: ---------------------------------------------------------------------------
echo [INFO] Installing dependencies...
pip install -r "%TEMP_REQS%"
IF ERRORLEVEL 1 (
    echo ERROR: Failed to install requirements.
    DEL /F /Q "%TEMP_REQS%" 2>NUL
    exit /b 1
)
DEL /F /Q "%TEMP_REQS%" 2>NUL

:: ---------------------------------------------------------------------------
:: Install PyTorch with platform-specific wheels
:: ---------------------------------------------------------------------------
IF "!NEEDS_TORCH!"=="true" (
    IF /I "!TORCH_BACKEND!"=="cuda" (
        echo [INFO] Installing PyTorch (CUDA)...
        pip install "!TORCH_SPEC!" --index-url https://download.pytorch.org/whl/cu121
        IF ERRORLEVEL 1 (echo ERROR: Failed to install PyTorch ^(CUDA^). & exit /b 1)
        IF NOT "!TORCHVISION_SPEC!"=="" (
            pip install "!TORCHVISION_SPEC!" --index-url https://download.pytorch.org/whl/cu121
            IF ERRORLEVEL 1 (echo ERROR: Failed to install torchvision ^(CUDA^). & exit /b 1)
        )
    ) ELSE (
        echo [INFO] Installing PyTorch (CPU)...
        pip install "!TORCH_SPEC!" --index-url https://download.pytorch.org/whl/cpu
        IF ERRORLEVEL 1 (echo ERROR: Failed to install PyTorch ^(CPU^). & exit /b 1)
        IF NOT "!TORCHVISION_SPEC!"=="" (
            pip install "!TORCHVISION_SPEC!" --index-url https://download.pytorch.org/whl/cpu
            IF ERRORLEVEL 1 (echo ERROR: Failed to install torchvision ^(CPU^). & exit /b 1)
        )
    )
)

:: ---------------------------------------------------------------------------
:: Install vLLM (CUDA only — not supported on Windows CPU or macOS)
:: ---------------------------------------------------------------------------
IF "!NEEDS_VLLM!"=="true" (
    IF /I "!TORCH_BACKEND!"=="cuda" (
        echo [INFO] Installing vLLM...
        pip install "!VLLM_SPEC!"
        IF ERRORLEVEL 1 echo WARNING: vLLM install failed. Continuing without it.
    ) ELSE (
        echo [INFO] Skipping vLLM ^(requires CUDA backend^).
    )
)

:: ---------------------------------------------------------------------------
:: Run interactive wizard
:: ---------------------------------------------------------------------------
IF "%RUN_WIZARD%"=="true" (
    IF NOT EXIST "%SCRIPT_DIR%\wizard.py" (
        echo ERROR: wizard.py not found at: %SCRIPT_DIR%\wizard.py
        exit /b 1
    )
    echo.
    echo === ORBIT Setup Wizard - Provider Configuration ===
    python "%SCRIPT_DIR%\wizard.py" "%PROJECT_ROOT%"
    IF ERRORLEVEL 1 (echo ERROR: Wizard exited with an error. & exit /b 1)
)

:: ---------------------------------------------------------------------------
:: Download GGUF model
:: ---------------------------------------------------------------------------
:do_gguf_download
IF "%DOWNLOAD_GGUF%"=="true" (
    IF "!GGUF_MODEL!"=="" SET "GGUF_MODEL=gemma3-270m"
    IF NOT EXIST "%GGUF_MODELS_CONFIG%" (
        echo ERROR: GGUF models config not found: %GGUF_MODELS_CONFIG%
        exit /b 1
    )
    IF NOT EXIST "%PROJECT_ROOT%\models" MKDIR "%PROJECT_ROOT%\models"
    FOR /F "tokens=1,2 delims=|" %%A IN ('python -c "import json; m=json.load(open(r'%GGUF_MODELS_CONFIG%'))['models']['!GGUF_MODEL!']^; print(m['repo_id']+'|'+m['filename'])"') DO (
        SET "REPO_ID=%%A"
        SET "DL_FILENAME=%%B"
    )
    IF "!REPO_ID!"=="" (
        echo ERROR: Model '!GGUF_MODEL!' not found in !GGUF_MODELS_CONFIG!
        exit /b 1
    )
    IF NOT EXIST "%PROJECT_ROOT%\models\!DL_FILENAME!" (
        echo [INFO] Downloading !GGUF_MODEL! from !REPO_ID!...
        python "%SCRIPT_DIR%\download_hf_gguf_model.py" --repo-id "!REPO_ID!" --filename "!DL_FILENAME!" --output-dir "%PROJECT_ROOT%\models"
        IF ERRORLEVEL 1 (echo ERROR: GGUF download failed. & exit /b 1)
        echo [OK] Saved to: %PROJECT_ROOT%\models\!DL_FILENAME!
    ) ELSE (
        echo [INFO] !GGUF_MODEL! already exists at %PROJECT_ROOT%\models\!DL_FILENAME!
    )
)

:: ---------------------------------------------------------------------------
:: Copy .env template if not present
:: ---------------------------------------------------------------------------
IF EXIST "%PROJECT_ROOT%\server\env.example" (
    IF NOT EXIST "%PROJECT_ROOT%\server\.env" (
        COPY /Y "%PROJECT_ROOT%\server\env.example" "%PROJECT_ROOT%\server\.env" >NUL
        echo [OK] Created server\.env from template.
    )
)

:: ---------------------------------------------------------------------------
:: Summary
:: ---------------------------------------------------------------------------
echo.
echo === Setup completed successfully! ===
IF "!PROFILES!"=="" (
    echo   Installed: default dependencies
) ELSE (
    echo   Installed: default + !PROFILES!
)
IF "!NEEDS_TORCH!"=="true" echo   Torch backend: !TORCH_BACKEND!
IF "%DOWNLOAD_GGUF%"=="true" echo   GGUF model: !GGUF_MODEL!
echo.
echo To start ORBIT:
echo   bin\orbit.bat start
exit /b 0

:: ---------------------------------------------------------------------------
:: Help
:: ---------------------------------------------------------------------------
:show_help
echo.
echo ORBIT Windows Setup Script
echo Equivalent to install/setup.sh for Windows environments.
echo.
echo Usage:
echo   setup.bat [OPTIONS]
echo.
echo Options:
echo   --profile, -p ^<name^>      Add a dependency profile (repeatable)
echo   --profiles ^<list^>         Comma-separated profile list
echo   --list-profiles, --list   List available dependency profiles
echo   --download-gguf [model]   Download a GGUF model (default: gemma3-270m)
echo   --gguf-models-config ^<f^>  Path to GGUF models JSON config
echo   --torch-backend ^<mode^>    Force PyTorch backend: auto, cpu, cuda (default: auto)
echo   --wizard                  Run the interactive provider configuration wizard
echo   --python-cmd ^<cmd^>        Python executable to use (skips auto-detection)
echo   --help, -h                Show this help message
echo.
echo Examples:
echo   setup.bat                                       Minimal install
echo   setup.bat --profile default                     Recommended setup
echo   setup.bat --list-profiles                       List all profiles
echo   setup.bat --profile llama-cpp --download-gguf gemma3-270m
echo   setup.bat --profiles "default,database,files"
echo   setup.bat --profile default --wizard
echo   setup.bat --torch-backend cuda                  Force CUDA wheels
exit /b 0
