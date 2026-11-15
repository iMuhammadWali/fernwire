"""Audio Splitter command-line mode: mirror the Windows default output to other devices.

    python main.py              mirror to external devices only
    python main.py --virtual    also mirror to virtual devices

For the window, run:  python -m audio_splitter.ui
"""

from audio_splitter.cli import main

if __name__ == "__main__":
    main()
