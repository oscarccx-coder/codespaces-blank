Apollo 7.5.12.8 — TorchCodec + C-Drive XTTS Runtime Fix

Install over Apollo 7.5.12.7 with Apollo completely closed.

WHY THIS PATCH EXISTS
---------------------
The previous XTTS repair correctly fixed Transformers 5.x, but PyTorch 2.9+
then exposed Coqui's next runtime requirement: TorchCodec.

7.5.12.8 permanently adds that handling to Apollo.

INSTALL
-------
1. Extract the safe cumulative update over your Apollo folder.
2. Run apply_update_7_5_12_8.bat.
3. Run install_xtts_v2.bat.
4. Restart Apollo.
5. Voice Imprint Lab -> Check Voice + Engine Readiness.

MODEL LOCATION
--------------
The XTTS engine now defaults to:
  %LOCALAPPDATA%\Apollo\models\voice\xtts_v2

Apollo itself remains wherever you keep it (for example F:\Apollo\apollo 1\apollo_ui).

The installer does not claim completion unless Transformers, TorchCodec,
Coqui/XTTS imports and the required XTTS model files verify successfully.
