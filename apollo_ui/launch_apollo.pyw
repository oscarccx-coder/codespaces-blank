from pathlib import Path
import sys
import traceback
from apollo_storage import StorageLayout

BASE_DIR = Path(__file__).resolve().parent
STORAGE = StorageLayout(BASE_DIR)
STORAGE.ensure_layout()
LOG_PATH = STORAGE.logs / "apollo_error.log"

# Ensure local imports resolve even under pythonw.exe.
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

try:
    import main
    main.main()
except BaseException:
    LOG_PATH.write_text(
        traceback.format_exc(),
        encoding="utf-8"
    )
    raise
