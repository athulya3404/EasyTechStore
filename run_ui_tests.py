#!/usr/bin/env python
"""
EasyTech Store - Playwright UI/UX and Button Test Runner
Run automated browser tests with screenshot generation.
"""

import sys
import pytest

if __name__ == "__main__":
    print("=" * 70)
    print(" Running EasyTech Playwright UI/UX and Interactive Button Tests")
    print("=" * 70)
    
    args = [
        "-c", "tests/e2e/pytest.ini",
        "-o", "addopts=-p no:django",
        "tests/e2e/test_ui_buttons.py",
        "-v",
        "--browser", "chromium",
    ]
    if "--headed" in sys.argv:
        args.append("--headed")
        
    exit_code = pytest.main(args)
    sys.exit(exit_code)
