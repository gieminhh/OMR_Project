"""Giao diện Tkinter cho hệ thống OMR — Phase 9.

Tính năng:
  - Load ảnh từ file hoặc chụp trực tiếp từ webcam (CameraDialog).
  - Dialog nhập/chỉnh đáp án chuẩn ngay trong GUI (50 câu × A/B/C/D).
  - Tự lưu đáp án chuẩn vào config/last_answer_key.json và tự load lại khi mở app.
  - Tự lưu đường dẫn ảnh/key cuối cùng vào config/app_state.json.

Bố cục:
  ┌──────────────────────────────────────────────────────────────────────┐
  │  Toolbar: [Chọn ảnh] [📷 Camera] [Nhập đáp án ▾] [Đọc phiếu]      │
  ├──────────────────────┬───────────────────────────────────────────────┤
  │   Preview ảnh        │  Bảng 50 câu (scrollable)                    │
  │   (annotated)        │  + Thống kê điểm                              │
  ├──────────────────────┴───────────────────────────────────────────────┤
  │  Statusbar                                         [Xuất Excel]      │
  └──────────────────────────────────────────────────────────────────────┘
"""

import json
import sys
import threading
import tkinter as tk
from pathlib import Path
from queue import Empty, Queue
from tkinter import filedialog, messagebox, ttk

import cv2
import numpy as np

# Thêm thư mục gốc vào path để import modules
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.errors import OMRError
from modules.image_processing import load_image, resize_image
from modules.export_excel import ExportError, export_excel
from modules.scoring import ScoringError, load_answer_key, score_answers
from modules.validation import validate_answers

try:
    from PIL import Image, ImageTk
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

# ─── Đường dẫn state/config ───────────────────────────────────────────────────
CONFIG_DIR        = ROOT / "config"
LAST_KEY_PATH     = CONFIG_DIR / "last_answer_key.json"   # đáp án chuẩn cuối cùng
APP_STATE_PATH    = CONFIG_DIR / "app_state.json"         # lưu trạng thái app

# ─── Hằng số giao diện ────────────────────────────────────────────────────────
APP_TITLE      = "OMR Scanner — Đọc phiếu trắc nghiệm"
PREVIEW_W      = 480
PREVIEW_H      = 620
TABLE_ROW_H    = 22
QUESTION_COUNT = 50
WORKER_POLL_MS = 50
CHOICES        = ("A", "B", "C", "D")

COLOR_CORRECT  = "#C6EFCE"
COLOR_WRONG    = "#FFC7CE"
COLOR_BLANK    = "#FFEB9C"
COLOR_MULTIPLE = "#BDD7EE"
COLOR_BTN      = "#2E75B6"
COLOR_BTN_FG   = "#FFFFFF"
COLOR_BG       = "#F0F4F8"
COLOR_TOOLBAR  = "#2E75B6"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _cv2_to_photoimage(bgr: np.ndarray, max_w: int, max_h: int):
    if not _HAS_PIL:
        return None
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    img = Image.fromarray(rgb)
    img.thumbnail((max_w, max_h), Image.LANCZOS)
    return ImageTk.PhotoImage(img)


def _btn(parent, text, cmd, bg=COLOR_BTN, width=18, **kw):
    return tk.Button(
        parent, text=text, command=cmd,
        bg=bg, fg=COLOR_BTN_FG,
        font=("Segoe UI", 10, "bold"),
        relief="flat", cursor="hand2",
        padx=10, pady=6, width=width,
        activebackground="#1a5a9a", activeforeground="white",
        **kw,
    )


def _load_json_safe(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _save_json_safe(path: Path, data) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return True
    except Exception:
        return False


# ─── Dialog nhập đáp án chuẩn ────────────────────────────────────────────────

class AnswerKeyDialog(tk.Toplevel):
    """Cửa sổ nhập/chỉnh 50 đáp án chuẩn — mỗi câu 4 radio button A/B/C/D."""

    def __init__(self, parent, initial_answers: list[str] | None = None):
        super().__init__(parent)
        self.title("Nhập đáp án chuẩn")
        self.resizable(False, False)
        self.grab_set()          # modal
        self.configure(bg=COLOR_BG)

        self._result: list[str] | None = None
        self._vars: list[tk.StringVar] = []

        self._build(initial_answers or ["A"] * QUESTION_COUNT)
        self.transient(parent)
        self.wait_window()

    # ── Kết quả ───────────────────────────────────────────────────────────────
    @property
    def answers(self) -> list[str] | None:
        return self._result

    # ── Giao diện ─────────────────────────────────────────────────────────────
    def _build(self, initial: list[str]):
        # Tiêu đề
        tk.Label(self, text="Nhập đáp án chuẩn (50 câu)",
                 bg=COLOR_TOOLBAR, fg="white",
                 font=("Segoe UI", 12, "bold"),
                 pady=10).pack(fill="x")

        tk.Label(self, text="Chọn A / B / C / D cho từng câu. Dữ liệu sẽ được lưu tự động.",
                 bg=COLOR_BG, fg="#444", font=("Segoe UI", 9)).pack(pady=(6, 2))

        # Vùng cuộn
        outer = tk.Frame(self, bg=COLOR_BG)
        outer.pack(fill="both", expand=True, padx=10, pady=4)

        canvas = tk.Canvas(outer, bg=COLOR_BG, highlightthickness=0,
                           width=520, height=460)
        sb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        inner = tk.Frame(canvas, bg=COLOR_BG)
        win_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _on_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfig(win_id, width=canvas.winfo_width())
        inner.bind("<Configure>", _on_configure)
        canvas.bind("<MouseWheel>",
                    lambda e: canvas.yview_scroll(-1 * (e.delta // 120), "units"))

        # Header hàng
        hdr_cfg = [("Câu", 40), ("A", 60), ("B", 60), ("C", 60), ("D", 60)]
        for col, (label, w) in enumerate(hdr_cfg):
            tk.Label(inner, text=label, width=w // 8,
                     bg="#4472C4", fg="white",
                     font=("Segoe UI", 9, "bold"),
                     relief="flat", pady=4).grid(
                row=0, column=col, padx=1, pady=(0, 2), sticky="ew")

        # 50 hàng × 4 radio
        RADIO_COLORS = {"A": "#d4edda", "B": "#cce5ff", "C": "#fff3cd", "D": "#f8d7da"}
        for q in range(QUESTION_COUNT):
            row = q + 1
            var = tk.StringVar(value=initial[q] if q < len(initial) else "A")
            self._vars.append(var)

            bg_row = "#FFFFFF" if q % 2 == 0 else "#F4F6FA"
            tk.Label(inner, text=str(q + 1),
                     bg=bg_row, fg="#333",
                     font=("Segoe UI", 9, "bold"),
                     width=5, anchor="center").grid(
                row=row, column=0, padx=1, pady=1, sticky="ew")

            for col, choice in enumerate(CHOICES):
                rb = tk.Radiobutton(
                    inner, text=choice, variable=var, value=choice,
                    bg=bg_row, activebackground=RADIO_COLORS[choice],
                    selectcolor=RADIO_COLORS[choice],
                    font=("Segoe UI", 9, "bold"),
                    indicatoron=True, cursor="hand2",
                    width=4, anchor="center",
                )
                rb.grid(row=row, column=col + 1, padx=1, pady=1, sticky="ew")

        for col in range(5):
            inner.columnconfigure(col, weight=1)

        # Nút
        btn_row = tk.Frame(self, bg=COLOR_BG)
        btn_row.pack(fill="x", padx=10, pady=8)

        _btn(btn_row, "✅  Lưu đáp án", self._save, bg="#107C41", width=16).pack(side="left", padx=4)
        _btn(btn_row, "🔄  Điền toàn bộ A", lambda: self._fill_all("A"), bg="#5B5EA6", width=18).pack(side="left", padx=4)
        _btn(btn_row, "❌  Huỷ", self.destroy, bg="#C00000", width=10).pack(side="right", padx=4)

    def _fill_all(self, choice: str):
        for var in self._vars:
            var.set(choice)

    def _save(self):
        self._result = [v.get() for v in self._vars]
        self.destroy()


# ─── Dialog Camera ────────────────────────────────────────────────────────────

class CameraDialog(tk.Toplevel):
    """Cửa sổ xem trước camera trực tiếp và chụp ảnh phiếu.

    Luồng hoạt động:
      - Thread nền mở cv2.VideoCapture rồi báo về main thread.
      - Main thread poll frame qua after(33ms) → hiển thị lên Canvas ~30fps.
      - Người dùng nhấn [📷 Chụp] → frame đóng băng, live feed dừng.
      - Nhấn [✅ Dùng ảnh này] → lưu JPEG vào output/camera/ rồi trả Path.
      - Nhấn [🔄 Chụp lại]    → tiếp tục live feed.
    """

    CAM_W, CAM_H       = 640, 480     # kích thước yêu cầu từ camera
    PREVIEW_W, PREVIEW_H = 620, 460   # kích thước hiển thị trong dialog

    def __init__(self, parent, cam_index: int = 0):
        super().__init__(parent)
        self.title("📷  Chụp ảnh từ camera")
        self.resizable(False, False)
        self.grab_set()
        self.configure(bg=COLOR_BG)

        self._cam_index = cam_index
        self._cap: cv2.VideoCapture | None = None
        self._running = False
        self._frozen = False
        self._frozen_frame: np.ndarray | None = None
        self._photo = None
        self._result_path: Path | None = None

        self._build()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.transient(parent)
        self._start_camera()
        self.wait_window()

    # ── Kết quả ───────────────────────────────────────────────────────────────

    @property
    def captured_path(self) -> Path | None:
        """Đường dẫn file ảnh đã chụp, hoặc None nếu huỷ."""
        return self._result_path

    # ── Giao diện ─────────────────────────────────────────────────────────────

    def _build(self):
        # Header
        tk.Label(self,
                 text="  📷  Đưa phiếu vào khung hình — đủ 4 góc — rồi nhấn Chụp",
                 bg=COLOR_TOOLBAR, fg="white",
                 font=("Segoe UI", 11, "bold"), pady=8,
                 anchor="w").pack(fill="x")

        # Chọn camera index
        sel_bar = tk.Frame(self, bg=COLOR_BG)
        sel_bar.pack(fill="x", padx=10, pady=(6, 2))
        tk.Label(sel_bar, text="Camera:", bg=COLOR_BG,
                 font=("Segoe UI", 9, "bold")).pack(side="left")
        self._cam_var = tk.IntVar(value=self._cam_index)
        for idx in range(4):
            tk.Radiobutton(sel_bar, text=f"  {idx}  ", variable=self._cam_var,
                           value=idx, bg=COLOR_BG, font=("Segoe UI", 9),
                           command=self._switch_camera,
                           cursor="hand2").pack(side="left", padx=2)

        # Canvas live feed
        self._canvas = tk.Canvas(self,
                                 width=self.PREVIEW_W, height=self.PREVIEW_H,
                                 bg="#111", highlightthickness=0)
        self._canvas.pack(padx=10, pady=4)
        self._placeholder_id = self._canvas.create_text(
            self.PREVIEW_W // 2, self.PREVIEW_H // 2,
            text="Đang kết nối camera…",
            fill="#88BBDD", font=("Segoe UI", 13))

        # Thanh nút
        btn_bar = tk.Frame(self, bg=COLOR_BG)
        btn_bar.pack(fill="x", padx=10, pady=8)

        self._btn_capture = _btn(btn_bar, "📷  Chụp", self._capture,
                                 bg="#C05000", width=14)
        self._btn_capture.pack(side="left", padx=4)

        self._btn_retake = _btn(btn_bar, "🔄  Chụp lại", self._retake,
                                bg="#5B5EA6", width=14)
        self._btn_retake.pack(side="left", padx=4)
        self._btn_retake.configure(state="disabled")

        self._btn_use = _btn(btn_bar, "✅  Dùng ảnh này", self._use_image,
                             bg="#107C41", width=18)
        self._btn_use.pack(side="left", padx=4)
        self._btn_use.configure(state="disabled")

        _btn(btn_bar, "❌  Huỷ", self._on_close,
             bg="#888888", width=10).pack(side="right", padx=4)

        # Gợi ý
        tk.Label(self,
                 text="💡  Đặt phiếu phẳng, đủ 4 góc, nền tương phản — "
                      "ảnh chụp được lưu vào output/camera/",
                 bg=COLOR_BG, fg="#666", font=("Segoe UI", 8)).pack(pady=(0, 6))

    # ── Camera ────────────────────────────────────────────────────────────────

    def _start_camera(self, index: int | None = None):
        if index is not None:
            self._cam_index = index
        self._stop_camera()
        self._frozen = False
        self._frozen_frame = None
        self._btn_capture.configure(state="disabled")
        self._btn_retake.configure(state="disabled")
        self._btn_use.configure(state="disabled")
        self._canvas.delete("all")
        self._placeholder_id = self._canvas.create_text(
            self.PREVIEW_W // 2, self.PREVIEW_H // 2,
            text=f"Đang mở camera {self._cam_index}…",
            fill="#88BBDD", font=("Segoe UI", 13))
        threading.Thread(target=self._open_cam_thread, daemon=True).start()

    def _open_cam_thread(self):
        """Mở camera trong thread nền để không đóng băng UI."""
        # CAP_DSHOW nhanh hơn trên Windows; fallback nếu không được
        cap = cv2.VideoCapture(self._cam_index, cv2.CAP_DSHOW)
        if not cap.isOpened():
            cap = cv2.VideoCapture(self._cam_index)
        if not cap.isOpened():
            msg = (f"❌  Không mở được camera {self._cam_index}.\n"
                   "Hãy kiểm tra kết nối hoặc chọn số camera khác.")
            self.after(0, lambda: self._canvas.itemconfig(
                self._placeholder_id, text=msg))
            return

        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  self.CAM_W)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.CAM_H)
        self._cap = cap
        self._running = True
        self.after(0, lambda: self._btn_capture.configure(state="normal"))
        self.after(0, lambda: self._canvas.delete(self._placeholder_id))
        self.after(0, self._poll_frame)

    def _poll_frame(self):
        """Lấy và hiển thị frame; lặp ~30fps qua after(33)."""
        if not self._running or self._frozen:
            return
        if self._cap is None or not self._cap.isOpened():
            return
        ret, frame = self._cap.read()
        if ret:
            self._show_frame(frame)
        self.after(33, self._poll_frame)

    def _show_frame(self, frame: np.ndarray):
        if not _HAS_PIL:
            return
        photo = _cv2_to_photoimage(frame, self.PREVIEW_W, self.PREVIEW_H)
        if photo is None:
            return
        self._photo = photo   # giữ reference
        self._canvas.delete("all")
        cx, cy = self.PREVIEW_W // 2, self.PREVIEW_H // 2
        self._canvas.create_image(cx, cy, anchor="center", image=self._photo)

    def _stop_camera(self):
        self._running = False
        if self._cap and self._cap.isOpened():
            self._cap.release()
        self._cap = None

    def _switch_camera(self):
        self._start_camera(self._cam_var.get())

    # ── Hành động nút ─────────────────────────────────────────────────────────

    def _capture(self):
        """Đóng băng frame hiện tại để người dùng xem lại."""
        if self._cap is None or not self._cap.isOpened():
            return
        ret, frame = self._cap.read()
        if not ret:
            messagebox.showwarning("Lỗi camera", "Không đọc được frame. Thử lại.")
            return
        self._frozen = True
        self._frozen_frame = frame
        self._show_frame(frame)

        # Overlay badge "CHỤP"
        self._canvas.create_rectangle(4, 4, 94, 30, fill="#C00000", outline="")
        self._canvas.create_text(49, 17, text="● ĐÓNG BĂNG",
                                 fill="white", font=("Segoe UI", 9, "bold"))

        self._btn_capture.configure(state="disabled")
        self._btn_retake.configure(state="normal")
        self._btn_use.configure(state="normal")

    def _retake(self):
        """Tiếp tục live feed để chụp lại."""
        self._frozen = False
        self._frozen_frame = None
        self._btn_capture.configure(state="normal")
        self._btn_retake.configure(state="disabled")
        self._btn_use.configure(state="disabled")
        self._poll_frame()

    def _use_image(self):
        """Lưu frame đóng băng thành JPEG và đóng dialog."""
        if self._frozen_frame is None:
            return
        import time
        out_dir = ROOT / "output" / "camera"
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        out_path = out_dir / f"capture_{ts}.jpg"

        ok, encoded = cv2.imencode(
            ".jpg", self._frozen_frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
        if not ok:
            messagebox.showerror("Lỗi", "Không thể mã hoá ảnh.")
            return
        encoded.tofile(str(out_path))
        self._result_path = out_path
        self._on_close()

    def _on_close(self):
        self._stop_camera()
        self.destroy()


# ─── App chính ────────────────────────────────────────────────────────────────

class OMRApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1140x740")
        self.minsize(900, 600)
        self.configure(bg=COLOR_BG)

        # State
        self._image_path: Path | None = None
        self._answer_key: list[str] | None = None   # đáp án chuẩn hiện tại
        self._result: dict | None = None
        self._score_result: dict | None = None
        self._photo = None

        self._build_ui()
        self._busy = False
        self._closed = False
        self._worker_results = Queue()
        self._worker_poll_id = self.after(WORKER_POLL_MS, self._poll_workers)
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self._restore_state()   # tự load đáp án chuẩn + đường dẫn ảnh cuối

    # ── Xây giao diện ─────────────────────────────────────────────────────────

    def _build_ui(self):
        self._build_toolbar()
        self._build_main()
        self._build_statusbar()

    def _build_toolbar(self):
        bar = tk.Frame(self, bg=COLOR_TOOLBAR, pady=8)
        bar.pack(fill="x", side="top")

        tk.Label(bar, text="  OMR Scanner",
                 bg=COLOR_TOOLBAR, fg="white",
                 font=("Segoe UI", 13, "bold")).pack(side="left", padx=(10, 24))

        self._btn_img = _btn(bar, "📂  Chọn ảnh phiếu",
                             self._pick_image, bg="#1a5a9a", width=20)
        self._btn_img.pack(side="left", padx=4)

        self._btn_camera = _btn(bar, "📷  Camera",
                                self._open_camera, bg="#7B3F9E", width=13)
        self._btn_camera.pack(side="left", padx=4)

        # Menu dropdown cho đáp án chuẩn
        key_frame = tk.Frame(bar, bg=COLOR_TOOLBAR)
        key_frame.pack(side="left", padx=4)

        self._btn_key_edit = _btn(key_frame, "📋  Nhập đáp án chuẩn",
                                  self._open_key_editor, bg="#1a5a9a", width=22)
        self._btn_key_edit.pack(side="left")

        self._btn_key_file = _btn(key_frame, "▾",
                                  self._show_key_menu, bg="#0f3d70", width=2)
        self._btn_key_file.pack(side="left", padx=(1, 0))

        self._btn_scan = _btn(bar, "🔍  Đọc phiếu",
                              self._run_scan, bg="#107C41", width=16)
        self._btn_scan.pack(side="left", padx=8)

        # Thông tin đường dẫn / đáp án
        self._lbl_info = tk.Label(bar, text="Chưa chọn ảnh",
                                  bg=COLOR_TOOLBAR, fg="#BDD7EE",
                                  font=("Segoe UI", 9), anchor="w")
        self._lbl_info.pack(side="left", padx=10, fill="x", expand=True)

        # Badge đáp án chuẩn
        self._lbl_key_badge = tk.Label(bar, text="Chưa có đáp án chuẩn",
                                       bg="#C05000", fg="white",
                                       font=("Segoe UI", 9, "bold"),
                                       padx=8, pady=3)
        self._lbl_key_badge.pack(side="right", padx=10)

    def _build_main(self):
        paned = tk.PanedWindow(self, orient="horizontal",
                               bg="#D0DAE8", sashwidth=5, sashrelief="flat")
        paned.pack(fill="both", expand=True, padx=8, pady=6)

        # Panel trái — preview ảnh
        left = tk.Frame(paned, bg=COLOR_BG)
        paned.add(left, minsize=320)

        tk.Label(left, text="Ảnh phiếu / Kết quả nhận diện",
                 bg=COLOR_BG, fg="#1a3a5c",
                 font=("Segoe UI", 10, "bold")).pack(pady=(4, 2))

        self._canvas = tk.Canvas(left, width=PREVIEW_W, height=PREVIEW_H,
                                 bg="#DDEEFF",
                                 highlightthickness=1, highlightbackground="#AACCEE")
        self._canvas.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        self._show_placeholder()

        # Panel phải — kết quả
        right = tk.Frame(paned, bg=COLOR_BG)
        paned.add(right, minsize=420)

        # Thanh thống kê
        sum_bar = tk.Frame(right, bg=COLOR_BG)
        sum_bar.pack(fill="x", padx=8, pady=(4, 2))
        self._lbl_score = tk.Label(sum_bar, text="Chưa có kết quả",
                                   bg=COLOR_BG, fg="#1a3a5c",
                                   font=("Segoe UI", 12, "bold"))
        self._lbl_score.pack(side="left")
        self._lbl_stats = tk.Label(sum_bar, text="",
                                   bg=COLOR_BG, fg="#555",
                                   font=("Segoe UI", 9))
        self._lbl_stats.pack(side="left", padx=10)

        # Bảng kết quả
        tbl_frame = tk.Frame(right, bg=COLOR_BG)
        tbl_frame.pack(fill="both", expand=True, padx=8, pady=(0, 4))

        style = ttk.Style()
        style.configure("Treeview",
                         font=("Segoe UI", 10), rowheight=TABLE_ROW_H)
        style.configure("Treeview.Heading",
                         font=("Segoe UI", 10, "bold"))
        style.map("Treeview", background=[("selected", "#BFCFE8")])

        cols = ("question", "student", "correct", "result")
        self._tree = ttk.Treeview(tbl_frame, columns=cols,
                                  show="headings", selectmode="browse", height=26)
        cfg = [
            ("question", "Câu",          60,  "center"),
            ("student",  "Đáp án HS",   110, "center"),
            ("correct",  "Đáp án đúng", 110, "center"),
            ("result",   "Kết quả",     170, "center"),
        ]
        for cid, heading, w, anchor in cfg:
            self._tree.heading(cid, text=heading)
            self._tree.column(cid, width=w, anchor=anchor, stretch=True)

        self._tree.tag_configure("correct",  background=COLOR_CORRECT)
        self._tree.tag_configure("wrong",    background=COLOR_WRONG)
        self._tree.tag_configure("blank",    background=COLOR_BLANK)
        self._tree.tag_configure("multiple", background=COLOR_MULTIPLE)

        sb = ttk.Scrollbar(tbl_frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

    def _build_statusbar(self):
        bar = tk.Frame(self, bg="#DDEEFF", height=40)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)

        self._lbl_status = tk.Label(bar, text="Sẵn sàng.",
                                    bg="#DDEEFF", fg="#1a3a5c",
                                    font=("Segoe UI", 9), anchor="w")
        self._lbl_status.pack(side="left", padx=12, fill="y")

        self._btn_excel = _btn(bar, "💾  Xuất Excel",
                               self._export_excel, bg="#107C41", width=16)
        self._btn_excel.pack(side="right", padx=12, pady=5)
        self._btn_excel.configure(state="disabled")

    # ── Khôi phục / lưu trạng thái ───────────────────────────────────────────

    def _restore_state(self):
        """Đọc đáp án chuẩn và đường dẫn ảnh từ lần dùng trước."""
        # 1. Đáp án chuẩn
        key_data = _load_json_safe(LAST_KEY_PATH, None)
        if isinstance(key_data, dict) and "answers" in key_data:
            answers = key_data["answers"]
        elif isinstance(key_data, list):
            answers = key_data
        else:
            answers = None

        if isinstance(answers, list) and len(answers) == QUESTION_COUNT:
            self._answer_key = answers
            self._set_status("✅ Đã tự load đáp án chuẩn từ lần trước.", "#107C41")
        else:
            self._answer_key = None

        # 2. Đường dẫn ảnh cuối
        state = _load_json_safe(APP_STATE_PATH, {})
        self._refresh_ui()
        last_image = state.get("last_image_path") if isinstance(state, dict) else None
        if isinstance(last_image, str) and last_image:
            self._load_image_path(Path(last_image))

    def _save_state(self):
        """Lưu đáp án chuẩn và đường dẫn ảnh hiện tại."""
        if self._answer_key:
            _save_json_safe(LAST_KEY_PATH, {"answers": self._answer_key})
        state = {}
        if self._image_path:
            state["last_image_path"] = str(self._image_path)
        _save_json_safe(APP_STATE_PATH, state)

    # ── Cập nhật UI ───────────────────────────────────────────────────────────

    def _refresh_ui(self):
        has_img = self._image_path is not None
        has_key = self._answer_key is not None

        # Nút Đọc phiếu
        self._btn_scan.configure(
            state="normal" if has_img and not self._busy else "disabled",
            bg="#107C41" if has_img and not self._busy else "#AAAAAA",
        )
        for button in (self._btn_img, self._btn_camera, self._btn_key_edit, self._btn_key_file):
            button.configure(state="disabled" if self._busy else "normal")
        self._btn_excel.configure(state="normal" if self._score_result and not self._busy else "disabled")

        # Thông tin ảnh
        if has_img:
            self._lbl_info.configure(text=str(self._image_path.name))
        else:
            self._lbl_info.configure(text="Chưa chọn ảnh")

        # Badge đáp án chuẩn
        if has_key:
            self._lbl_key_badge.configure(
                text="✓ Có đáp án chuẩn", bg="#107C41")
        else:
            self._lbl_key_badge.configure(
                text="Chưa có đáp án chuẩn", bg="#C05000")

    def _set_status(self, msg: str, color: str = "#1a3a5c"):
        self._lbl_status.configure(text=msg, fg=color)

    # ── Hành động người dùng ──────────────────────────────────────────────────

    def _pick_image(self):
        if self._busy:
            return
        path = filedialog.askopenfilename(
            parent=self,
            title="Chọn ảnh phiếu trắc nghiệm",
            filetypes=[
                ("Ảnh", "*.png *.jpg *.jpeg *.bmp *.tiff *.webp"),
                ("Tất cả", "*.*"),
            ],
        )
        if not path:
            return
        self._load_image_path(Path(path))

    def _open_camera(self):
        """Mở dialog camera; nếu người dùng chụp thì load ảnh vừa chụp."""
        if self._busy:
            return
        dlg = CameraDialog(self)
        captured = dlg.captured_path
        if captured and captured.is_file():
            self._load_image_path(captured)

    def _load_image_path(self, path: Path):
        """Đọc ảnh và thu nhỏ trong nền; chỉ cập nhật Tk ở luồng giao diện."""
        if self._busy:
            return
        self._busy = True
        self._image_path = None
        self._result = None
        self._score_result = None
        self._clear_table()
        self._show_placeholder()
        self._lbl_score.configure(text="Chưa có kết quả", fg="#1a3a5c")
        self._lbl_stats.configure(text="")
        self._btn_excel.configure(state="disabled")
        self._refresh_ui()
        self._lbl_info.configure(text=path.name)
        self._set_status(f"⏳ Đang tải ảnh: {path.name}…", COLOR_BTN)
        threading.Thread(target=self._image_worker, args=(path,), daemon=True).start()

    def _image_worker(self, path: Path):
        """Không gọi Tk, kể cả after(), từ worker."""
        try:
            preview = resize_image(load_image(path), max(PREVIEW_W, PREVIEW_H))
            self._worker_results.put(("image", (path, preview), None))
        except Exception as exc:
            self._worker_results.put(("image", None, exc))

    def _poll_workers(self):
        """Nhận dữ liệu/lỗi trong main thread, luôn khôi phục các nút."""
        if self._closed:
            return
        try:
            try:
                kind, payload, error = self._worker_results.get_nowait()
            except Empty:
                return
            try:
                if error is not None:
                    raise error
                if kind == "image":
                    path, preview = payload
                    self._show_image(preview)
                    self._image_path = path
                    self._save_state()
                    self._set_status(f"📂 Đã tải ảnh: {path.name}. Nhấn Đọc phiếu để nhận diện.")
                else:
                    self._on_scan_done(payload, None)
            except Exception as exc:
                self._result = None
                self._score_result = None
                self._clear_table()
                self._lbl_score.configure(text="Chưa có kết quả", fg="#1a3a5c")
                self._lbl_stats.configure(text="")
                self._set_status(f"❌ Lỗi: {exc}", "#C00000")
                messagebox.showerror("Lỗi tải ảnh" if kind == "image" else "Lỗi đọc phiếu", str(exc), parent=self)
            finally:
                self._busy = False
                if not self._closed:
                    self._refresh_ui()
        finally:
            if not self._closed:
                self._worker_poll_id = self.after(WORKER_POLL_MS, self._poll_workers)

    def destroy(self):
        """Dừng nhận kết quả khi đóng cửa sổ; không chờ worker làm treo UI."""
        self._closed = True
        poll_id = getattr(self, "_worker_poll_id", None)
        if poll_id is not None:
            self.after_cancel(poll_id)
            self._worker_poll_id = None
        super().destroy()

    def _show_key_menu(self):
        """Menu nhỏ: Load từ file / Xem đáp án hiện tại."""
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="📁  Load đáp án từ file JSON…",
                         command=self._pick_key_file)
        menu.add_command(label="📋  Nhập / chỉnh đáp án chuẩn…",
                         command=self._open_key_editor)
        if self._answer_key:
            menu.add_separator()
            menu.add_command(label="💾  Lưu đáp án ra file JSON…",
                             command=self._save_key_to_file)
        try:
            x = self._btn_key_file.winfo_rootx()
            y = self._btn_key_file.winfo_rooty() + self._btn_key_file.winfo_height()
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    def _pick_key_file(self):
        path = filedialog.askopenfilename(
            title="Chọn file đáp án chuẩn (JSON)",
            filetypes=[("JSON", "*.json"), ("Tất cả", "*.*")],
        )
        if not path:
            return
        try:
            key = load_answer_key(path)
            self._answer_key = key
            self._save_state()
            self._refresh_ui()
            self._set_status(f"✅ Đã load đáp án chuẩn từ: {Path(path).name}", "#107C41")
        except (ScoringError, OMRError) as exc:
            messagebox.showerror("Lỗi đáp án chuẩn", str(exc))

    def _open_key_editor(self):
        """Mở dialog nhập/chỉnh đáp án chuẩn."""
        dlg = AnswerKeyDialog(self, self._answer_key)
        if dlg.answers is not None:
            self._answer_key = dlg.answers
            self._save_state()
            self._refresh_ui()
            self._set_status("✅ Đáp án chuẩn đã được lưu tự động.", "#107C41")

    def _save_key_to_file(self):
        if not self._answer_key:
            return
        path = filedialog.asksaveasfilename(
            title="Lưu đáp án chuẩn",
            defaultextension=".json",
            initialfile="answer_key.json",
            filetypes=[("JSON", "*.json")],
        )
        if path:
            _save_json_safe(Path(path), {"answers": self._answer_key})
            self._set_status(f"✅ Đã lưu đáp án ra: {Path(path).name}", "#107C41")

    def _run_scan(self):
        if not self._image_path or self._busy:
            return
        self._busy = True
        self._result = None
        self._score_result = None
        self._clear_table()
        self._lbl_score.configure(text="Đang đọc phiếu…", fg=COLOR_BTN)
        self._lbl_stats.configure(text="")
        self._set_status("⏳ Đang xử lý ảnh…", COLOR_BTN)
        self._refresh_ui()
        threading.Thread(target=self._scan_worker, args=(self._image_path,), daemon=True).start()

    def _scan_worker(self, image_path: Path):
        """Chụp cố định đường dẫn đầu vào, chuyển kết quả/lỗi qua queue."""
        try:
            from main import process_omr
            result = process_omr(image_path, debug=False)
            self._worker_results.put(("scan", result, None))
        except Exception as exc:  # noqa: BLE001
            self._worker_results.put(("scan", None, exc))

    def _on_scan_done(self, result, error):
        if error:
            self._set_status(f"❌ Lỗi: {error}", "#C00000")
            messagebox.showerror("Lỗi đọc phiếu", str(error))
            self._btn_scan.configure(state="normal", bg="#107C41")
            return

        self._result = result
        annotated = result.get("annotated_image")
        if annotated is None:
            annotated = result.get("processed_image")
        if annotated is not None:
            self._show_image(annotated)

        answers = result.get("answers")
        if not answers:
            self._set_status("⚠ Không đọc được đáp án. Kiểm tra layout.", "#C05000")
            self._btn_scan.configure(state="normal", bg="#107C41")
            return

        vr = validate_answers(answers)
        if not vr["valid"]:
            self._set_status(
                f"⚠ Kết quả không hợp lệ: {'; '.join(vr['errors'])}", "#C05000")
            self._btn_scan.configure(state="normal", bg="#107C41")
            return

        score_result = None
        if self._answer_key:
            try:
                score_result = score_answers(answers, self._answer_key)
                self._score_result = score_result
            except (ScoringError, OMRError) as exc:
                messagebox.showwarning(
                    "Lỗi chấm điểm",
                    f"Đọc phiếu thành công nhưng không chấm được:\n{exc}"
                )

        self._populate_table(answers, score_result)
        self._update_summary(score_result, vr)
        self._btn_scan.configure(state="normal", bg="#107C41")

        if score_result:
            self._btn_excel.configure(state="normal")
            self._set_status(
                f"✅ Hoàn thành — Điểm: {score_result['score']}/10  "
                f"(Đúng {score_result['correct_count']}/50)",
                "#107C41",
            )
        else:
            self._btn_excel.configure(state="disabled")
            self._set_status(
                "✅ Đọc phiếu thành công (chưa chấm — nhập đáp án chuẩn để chấm điểm).",
                "#107C41",
            )

    def _export_excel(self):
        if not self._score_result:
            messagebox.showwarning("Chưa có kết quả", "Hãy đọc phiếu và chấm điểm trước.")
            return
        default = "ket_qua_omr.xlsx"
        if self._image_path:
            default = self._image_path.stem + "_result.xlsx"
        path = filedialog.asksaveasfilename(
            title="Lưu kết quả Excel",
            defaultextension=".xlsx",
            initialfile=default,
            filetypes=[("Excel", "*.xlsx"), ("Tất cả", "*.*")],
        )
        if not path:
            return
        try:
            out = export_excel(self._score_result, path)
            self._set_status(f"✅ Đã xuất: {out.name}", "#107C41")
            if messagebox.askyesno("Xuất thành công",
                                   f"Đã lưu:\n{out}\n\nMở file ngay không?"):
                import os
                os.startfile(str(out))
        except ExportError as exc:
            messagebox.showerror("Lỗi xuất Excel", str(exc))

    # ── Cập nhật bảng / ảnh ───────────────────────────────────────────────────

    def _show_image(self, bgr: np.ndarray):
        self._canvas.delete("all")
        photo = _cv2_to_photoimage(bgr, PREVIEW_W, PREVIEW_H)
        if not photo:
            self._canvas.create_text(
                PREVIEW_W // 2, PREVIEW_H // 2,
                text="[Cần Pillow để hiện ảnh]\npip install Pillow",
                fill="#FF6600", font=("Segoe UI", 11),
            )
            return
        self._photo = photo
        cw = self._canvas.winfo_width() or PREVIEW_W
        ch = self._canvas.winfo_height() or PREVIEW_H
        self._canvas.create_image(cw // 2, ch // 2, anchor="center", image=self._photo)

    def _show_placeholder(self):
        self._canvas.delete("all")
        self._canvas.create_text(
            PREVIEW_W // 2, PREVIEW_H // 2,
            text="Chọn ảnh và nhấn\n'Đọc phiếu' để bắt đầu",
            fill="#7FA0C0", font=("Segoe UI", 12),
        )

    def _clear_table(self):
        for row in self._tree.get_children():
            self._tree.delete(row)

    def _populate_table(self, answers: list[str], score_result: dict | None):
        self._clear_table()
        labels = {
            "correct":  "✓ Đúng",
            "wrong":    "✗ Sai",
            "blank":    "— Bỏ trống",
            "multiple": "⚠ Nhiều đáp án",
        }
        if score_result:
            for d in score_result["details"]:
                tag = d["result"]
                self._tree.insert("", "end",
                                  values=(d["question"], d["student"],
                                          d["correct"], labels.get(tag, tag)),
                                  tags=(tag,))
        else:
            for i, ans in enumerate(answers, 1):
                if ans == "BLANK":
                    tag, label = "blank", "— Bỏ trống"
                elif ans == "MULTIPLE":
                    tag, label = "multiple", "⚠ Nhiều đáp án"
                else:
                    tag, label = "correct", "(chưa chấm điểm)"
                self._tree.insert("", "end",
                                  values=(i, ans, "—", label),
                                  tags=(tag,))

    def _update_summary(self, score_result: dict | None, vr: dict):
        if score_result:
            score = score_result["score"]
            self._lbl_score.configure(
                text=f"Điểm: {score} / 10",
                fg="#107C41" if score >= 5 else "#C00000",
            )
            self._lbl_stats.configure(
                text=(f"  Đúng: {score_result['correct_count']}  |  "
                      f"Sai: {score_result['wrong_count']}  |  "
                      f"Bỏ trống: {score_result['blank_count']}  |  "
                      f"Nhiều đáp án: {score_result['multiple_count']}")
            )
        else:
            self._lbl_score.configure(
                text="Đọc thành công (chưa chấm điểm)", fg=COLOR_BTN)
            self._lbl_stats.configure(
                text=f"  Bỏ trống: {vr['blank_count']}  |  "
                     f"Nhiều đáp án: {vr['multiple_count']}")


# ─── Entry point ──────────────────────────────────────────────────────────────

def launch_app() -> None:
    """Khởi chạy ứng dụng GUI."""
    app = OMRApp()
    app.mainloop()


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    launch_app()
