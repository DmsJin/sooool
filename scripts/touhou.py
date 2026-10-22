"""Launch touhou with the interpreter selected by sol env."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "environments/touhou")]

from environments.touhou.cli import main

if __name__ == "__main__":
    main()
