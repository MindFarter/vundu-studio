#!/usr/bin/env python3
"""Vundu Studio - start with:  python3 vundu_studio.py"""
import os
import sys

if sys.version_info < (3, 9):
    sys.exit("Vundu Studio needs Python 3.9 or newer.")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from vundu.server import main  # noqa: E402

if __name__ == "__main__":
    main()
