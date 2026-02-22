#!/usr/bin/env python3
"""
Armor-themed alias for the core market/news refresh engine.
Primary entrypoint going forward; delegates to legacy module for compatibility.
"""
from run_uber_update import main


if __name__ == "__main__":
    main()

