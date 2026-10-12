"""SYNTHETIC DEMONSTRATION DATA — NOT REAL JOB POSTINGS.

Standalone manual bootstrap using this checkout's public backend only.
"""

import argparse
from pathlib import Path
import sqlite3
import sys

PUBLIC_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PUBLIC_ROOT / "src"))

from internship_agent.demo import NOTICE, create_demo  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=NOTICE + " Create an offline demo database.")
    parser.add_argument("--resume", action="store_true", help="Explicitly recover an owned partial demo.")
    args = parser.parse_args()
    print(NOTICE)
    try:
        result = create_demo(resume=args.resume)
    except (OSError, ValueError, sqlite3.Error) as error:
        # Do not print exception paths or arbitrary input text into reports.
        print(f"Demo initialization refused or failed ({type(error).__name__}).", file=sys.stderr)
        print("Review data/demo/ and docs/DEMO_GUIDE.md; existing output is preserved.", file=sys.stderr)
        return 1
    print(f"Created {result.path.relative_to(PUBLIC_ROOT).as_posix()}")
    print(f"Synthetic jobs: {result.jobs}; synthetic application records: {result.applications}")
    print(f"SQLite integrity: {result.validation['integrity_check']}; "
          f"foreign-key violations: {result.validation['foreign_key_violations']}; "
          f"schema version: {result.validation['schema_version']}")
    print(f"Fixture fingerprint: {result.fixture_fingerprint}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
