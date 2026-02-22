#!/usr/bin/env python3
"""
Legacy compatibility alias.

Primary engine entrypoint is now `scripts/run_arc_reactor_update.py`.
This shim exists so older commands/scripts continue to work.
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))
from run_arc_reactor_update import main


if __name__ == "__main__":
    print("INFO: Legacy refresh alias detected; running Arc Reactor engine instead.")
    main()
