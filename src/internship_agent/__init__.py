"""Local internship job storage and CSV exports."""

import sys

if sys.version_info < (3, 12):
    raise RuntimeError("Internship Agent 2027 requires Python 3.12 or newer.")

__version__ = "0.1.0"

# Keep runtime source-cache writes out of the read-only public demonstration.
sys.dont_write_bytecode = True
