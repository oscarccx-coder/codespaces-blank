import os, sys
from pathlib import Path
base = os.environ.get("APOLLO_BASE_DIR") or str(Path(__file__).resolve().parents[2])
if base not in sys.path: sys.path.insert(0, base)
from module import Module
m=Module({"validation":True,"base_dir":base})
assert m.self_test()
print("Fleet Manager tests passed.")
