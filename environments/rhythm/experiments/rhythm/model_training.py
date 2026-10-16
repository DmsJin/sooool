"""Shared simulation evidence helpers."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def _append(path,data):
 with Path(path).open("a") as f:f.write(json.dumps(data,separators=(",",":"),allow_nan=False)+"\n")
