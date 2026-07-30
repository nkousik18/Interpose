#!/usr/bin/env python
"""Thin launcher so `python agents/aml-investigator/run_investigation.py` works
without a separate install step -- puts `src/` on `sys.path` and delegates to
`aml_investigator.run.main`, the same "run the script directly" pattern each
mcp-servers/*/src/server.py already uses.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from aml_investigator.run import main  # noqa: E402

if __name__ == "__main__":
    main()
