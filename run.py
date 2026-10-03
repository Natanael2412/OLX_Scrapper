import json
from pathlib import Path
import engine

cfg = json.loads(Path("config.json").read_text()) if Path("config.json").exists() else {}
S = engine.new_state(); engine.run(cfg, S)
print(S["msg"], "| valid:", S["ok"], "| ditolak:", S["rejected"], "| request:", S["req"])
