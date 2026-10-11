"""Entry point for the Keyboard Timer application.

Run from source:   python main.py
Self test:         python main.py --smoke
"""

import sys

from keyboard_timer.app import run

if __name__ == "__main__":
    sys.exit(run())
