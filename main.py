"""Fernwire command-line mode: mirror the Windows default output to other devices.

    python main.py              mirror to external devices only
    python main.py --virtual    also mirror to virtual devices

For the window, run:  python -m fernwire.ui
"""

from fernwire.cli import main

if __name__ == "__main__":
    main()
