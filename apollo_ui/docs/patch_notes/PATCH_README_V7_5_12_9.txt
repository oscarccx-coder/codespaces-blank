Apollo 7.5.12.9 — XTTS Windows Batch Quoting Fix

Install over Apollo 7.5.12.8 with Apollo completely closed.

FIXED ERROR
-----------
The 7.5.12.8 installer could fail at PyTorch version detection with:

  python.exe" -c "import' is not recognized as an internal or external command

This was a Windows CMD nested-quote parsing problem, not a PyTorch problem.

7.5.12.9 avoids FOR /F command substitution entirely for that step.
It runs Python normally, captures the version into a temporary file, validates it,
then selects the matching TorchCodec version.

INSTALL
-------
1. Extract the Safe Cumulative Update over Apollo.
2. Run apply_update_7_5_12_9.bat.
3. Run install_xtts_v2.bat.
4. Restart Apollo after XTTS completes.
