"""Launcher cho giao diện OMR — chạy: python run_gui.py"""
import sys
from pathlib import Path

# Đảm bảo thư mục gốc dự án có trong sys.path
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import subprocess


def _try_venv_rerun() -> bool:
    """Nếu đang dùng Python sai, thử lại bằng interpreter trong .venv."""
    current = Path(sys.executable).resolve()
    candidates = [
        ROOT / ".venv" / "Scripts" / "python.exe",
        ROOT / ".venv" / "bin" / "python",
    ]
    for candidate in candidates:
        if not candidate.exists():
            continue
        if candidate.resolve() == current:
            continue
        try:
            subprocess.run([str(candidate), str(Path(__file__).resolve())], check=False)
            return True
        except OSError:
            continue
    return False


try:
    from gui.app import launch_app
except Exception as exc:  # noqa: BLE001
    text = str(exc).lower()
    if "tkinter" in text or "tk.tcl" in text or "tcl" in text or "_tkinter" in text:
        if _try_venv_rerun():
            raise SystemExit(0)
        print("Lỗi GUI: Tkinter/Tcl không khả dụng trong Python hiện tại.", file=sys.stderr)
        print("Dùng môi trường project đã cài sẵn: .\\.venv\\Scripts\\python.exe run_gui.py", file=sys.stderr)
        print("Hoặc cài Tkinter cho Python đang dùng: python -m pip install tk", file=sys.stderr)
        raise SystemExit(1)
    raise

if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")
    try:
        launch_app()
    except Exception as exc:  # noqa: BLE001
        text = str(exc).lower()
        if "tkinter" in text or "tk.tcl" in text or "tcl" in text or "_tkinter" in text:
            if _try_venv_rerun():
                raise SystemExit(0)
            print("Lỗi GUI: Tkinter/Tcl không khả dụng trong Python hiện tại.", file=sys.stderr)
            print("Dùng môi trường project đã cài sẵn: .\\.venv\\Scripts\\python.exe run_gui.py", file=sys.stderr)
            print("Hoặc cài Tkinter cho Python đang dùng: python -m pip install tk", file=sys.stderr)
            raise SystemExit(1)
        raise
