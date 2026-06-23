# ORBIT on Windows

> **Recommended path:** WSL 2 with the standard Linux setup (`./install/setup.sh`) gives you the broadest compatibility, including full GGUF, GPU, and audio provider support. Use the native Windows path when WSL 2 is not available or not desired.

## Prerequisites

- [Python 3.12+](https://www.python.org/downloads/) — check **"Add python.exe to PATH"** during install
- [Git for Windows](https://git-scm.com/download/win)

## Quick Start

```bat
git clone https://github.com/schmitech/orbit.git
cd orbit
install\setup.bat --profile default
bin\orbit.bat start
```

`setup.bat` handles everything automatically:

- Creates and activates a virtual environment at `venv\`
- Detects NVIDIA GPU presence and selects CUDA or CPU PyTorch wheels accordingly
- Installs all dependencies from `install\dependencies.toml`
- Copies `server\env.example` to `server\.env` if it does not already exist

## PowerShell

`bin\orbit.bat` and `install\setup.bat` work from both Command Prompt and PowerShell. If PowerShell blocks script execution, run this once to unlock it for the current user:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

## Setup Options

### Interactive wizard

The wizard walks you through provider and config selection after installing dependencies:

```bat
install\setup.bat --profile default --wizard
```

### Additional profiles

Profiles layer optional capability groups on top of the default install. To see what is available:

```bat
install\setup.bat --list-profiles
```

Install one or more additional profiles:

```bat
install\setup.bat --profile llama-cpp
install\setup.bat --profiles "default,database,files"
```

### Download a GGUF model

Downloads the model into `models\` and installs the `llama-cpp` profile if not already present:

```bat
install\setup.bat --profile llama-cpp --download-gguf gemma3-270m
```

Omit the model name to use the default (`gemma3-270m`):

```bat
install\setup.bat --download-gguf
```

### Force a PyTorch backend

`setup.bat` auto-detects CUDA via `nvidia-smi`. To override:

```bat
install\setup.bat --torch-backend cpu
install\setup.bat --torch-backend cuda
```

`metal` is macOS-only and will error on Windows.

### Full reference

```
install\setup.bat --help
```

## Running ORBIT

After setup, start and manage the server with `bin\orbit.bat`:

```bat
bin\orbit.bat start
bin\orbit.bat status
bin\orbit.bat stop
```

The wrapper auto-activates `venv\` if `VIRTUAL_ENV` is not already set, so you do not need to activate the virtual environment manually between sessions.

## Troubleshooting

| Symptom | Fix |
| :--- | :--- |
| `python` not found | Re-run the Python installer and check **"Add python.exe to PATH"**, or add it manually via System → Environment Variables |
| PowerShell execution policy error | Run `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser` |
| CUDA wheels installed but GPU not used | Confirm `nvidia-smi` is on your PATH and your CUDA driver is ≥ 12.1 |
| `tomllib` / `tomli` import error | Run `pip install tomli` inside the activated venv |
| GGUF download fails | Check your Hugging Face token if the model is gated; set `HF_TOKEN` in `server\.env` |
