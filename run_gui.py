"""Launcher cho giao diện OMR — chạy: python run_gui.py"""
import sys
from pathlib import Path

# Đảm bảo thư mục gốc dự án có trong sys.path
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gui.app import launch_app

if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    launch_app()
