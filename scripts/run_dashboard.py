"""Explicit manual launcher using only the current public checkout."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.dont_write_bytecode = True

from internship_agent.dashboard_launch import main

if __name__ == "__main__":
    raise SystemExit(main())
