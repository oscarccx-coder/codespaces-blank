@echo off
setlocal EnableExtensions DisableDelayedExpansion
title Apollo - XTTS GPU Diagnostic
set "APOLLO_DIR=%~dp0.."
set "EXIT_CODE=0"
pushd "%APOLLO_DIR%" >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Cannot open the Apollo installation directory.
  set "EXIT_CODE=2"
  goto :FINISH
)
echo ==========================================================
echo APOLLO XTTS GPU / CUDA CHECK - NO INSTALLATION
echo ==========================================================
echo.
echo [INFO] This diagnostic does not install or change packages.
echo.
where nvidia-smi >nul 2>&1
if errorlevel 1 (
  echo [WARNING] nvidia-smi is not in PATH. Check NVIDIA driver installation.
) else (
  nvidia-smi --query-gpu=name,driver_version,memory.total,memory.used --format=csv
)
echo.
if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] Apollo private Python is missing.
  echo [FIX] Run Setup\01_INSTALL_APOLLO.bat then Setup\04_REPAIR_VOICE.bat.
  set "EXIT_CODE=3"
  goto :DONE
)
echo [CHECK] XTTS worker interpreter:
".venv\Scripts\python.exe" -c "import sys; print(sys.executable)"
if errorlevel 1 (
  echo [ERROR] Apollo Python could not start.
  set "EXIT_CODE=4"
  goto :DONE
)
echo [CHECK] CUDA-enabled Torch and a small CUDA operation:
".venv\Scripts\python.exe" -c "import torch; print('torch:',torch.__version__); print('CUDA build:',torch.version.cuda); print('CUDA available:',torch.cuda.is_available()); assert torch.cuda.is_available(), 'PyTorch cannot use CUDA; check NVIDIA drivers and your Apollo XTTS installation'; print('GPU:',torch.cuda.get_device_name(0)); x=torch.ones((32,32),device='cuda'); print('CUDA test:',float((x@x)[0,0].item())); torch.cuda.synchronize()"
if errorlevel 1 (
  echo [ERROR] XTTS GPU runtime is not ready in Apollo's private Python.
  echo [FIX] Do not reinstall global Python. Use Setup\04_REPAIR_VOICE.bat to repair Apollo's private XTTS stack if the diagnostics indicate a package mismatch.
  set "EXIT_CODE=5"
  goto :DONE
)
echo [OK] CUDA torch runtime works in the Apollo XTTS Python environment.
echo [NEXT] In Apollo Voice Imprint choose Device: CUDA, save, and test a short phrase.
:DONE
popd
:FINISH
echo.
echo [RESULT] GPU diagnostic exit code: %EXIT_CODE%
if not defined CI (
  echo Press any key to close this window.
  pause >nul
)
endlocal & exit /b %EXIT_CODE%
