"""Giao diện Tkinter đọc và chấm điểm phiếu trắc nghiệm OMR 50 câu.

Bố cục giao diện:
  - Thanh công cụ trên cùng: Chọn ảnh, Đọc phiếu, Nạp đáp án, Chấm điểm, Xuất Excel.
  - Cột trái: Vùng hiển thị ảnh phiếu trắc nghiệm.
  - Cột phải: Bảng kết quả 50 câu kèm màu sắc trực quan và khối điểm số tổng quan.
"""

import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import cv2
import numpy as np

# Đảm bảo import được các module từ thư mục gốc
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from main import process_omr
from modules.export_excel import export_excel
from modules.image_processing import load_image
from modules.scoring import load_answer_key, score_answers
from modules.validation import validate_answers

try:
    from PIL import Image, ImageTk
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False


# ── BẢNG MÀU GIAO DIỆN HIỆN ĐẠI & PASTEL ──────────────────────────────
COLOR_APP_BG        = "#F1F5F9"   # Nền tổng thể cửa sổ (xám sáng nhẹ)
COLOR_CARD_BG       = "#FFFFFF"   # Nền các khung thẻ (trắng sạch)
COLOR_BORDER        = "#E2E8F0"   # Màu đường viền mảnh thanh lịch
COLOR_PRIMARY       = "#2563EB"   # Xanh dương nhấn hiện đại (Royal Blue)
COLOR_TEXT_MAIN     = "#0F172A"   # Màu chữ chính (Slate 900)
COLOR_TEXT_MUTED    = "#64748B"   # Màu chữ phụ (Slate 500)

# 4 màu pastel cho thẻ thống kê (Chips)
PASTEL_CORRECT_BG   = "#DCFCE7"   # Xanh lục pastel
PASTEL_CORRECT_FG   = "#15803D"
PASTEL_WRONG_BG     = "#FEE2E2"   # Đỏ hồng pastel
PASTEL_WRONG_FG     = "#B91C1C"
PASTEL_BLANK_BG     = "#FEF9C3"   # Vàng chanh pastel
PASTEL_BLANK_FG     = "#A16207"
PASTEL_MULTI_BG     = "#FFEDD5"   # Cam đào pastel
PASTEL_MULTI_FG     = "#C2410C"

# Màu tô cả dòng cho ttk.Treeview
ROW_CORRECT_BG      = "#D1E7DD"   # Xanh nhạt
ROW_CORRECT_FG      = "#0F5132"
ROW_WRONG_BG        = "#F8D7DA"   # Đỏ nhạt
ROW_WRONG_FG        = "#842029"
ROW_BLANK_BG        = "#FFF3CD"   # Vàng nhạt
ROW_BLANK_FG        = "#664D03"
ROW_MULTI_BG        = "#FFE5D0"   # Cam nhạt
ROW_MULTI_FG        = "#7C2D12"
ROW_NORMAL_BG       = "#FFFFFF"   # Trắng (chưa chấm)
ROW_NORMAL_FG       = "#1E293B"


class SimpleOMRApp(tk.Tk):
    """Ứng dụng Tkinter đọc và chấm điểm phiếu trắc nghiệm OMR 50 câu."""

    def __init__(self):
        super().__init__()
        self.title("PHẦN MỀM ĐỌC PHIẾU TRẮC NGHIỆM OMR 50 CÂU")
        self.geometry("1180x730")
        self.minsize(980, 620)
        self.configure(bg=COLOR_APP_BG)

        # Trạng thái dữ liệu
        self.image_path: Path | None = None
        self.loaded_image: np.ndarray | None = None
        self.display_image: np.ndarray | None = None
        self.student_answers: list[str] | None = None
        self.answer_key: list[str] | None = None
        self.score_result: dict | None = None
        self._photo_ref = None

        # Cấu hình giao diện
        self._setup_styles()
        self._create_widgets()
        self._draw_placeholder()
        self._set_status("Sẵn sàng. Hãy chọn ảnh phiếu để bắt đầu.")

    def _setup_styles(self):
        """Đồng bộ style cho các widget ttk bằng theme 'clam'."""
        self.style = ttk.Style(self)
        if "clam" in self.style.theme_names():
            self.style.theme_use("clam")

        # Nút bấm hành động trên thanh công cụ
        self.style.configure(
            "Action.TButton",
            font=("Segoe UI", 10, "bold"),
            padding=(12, 7),
            background="#FFFFFF",
            foreground=COLOR_TEXT_MAIN,
            borderwidth=1,
            relief="raised",
        )
        self.style.map(
            "Action.TButton",
            background=[("active", "#E2E8F0"), ("disabled", "#F1F5F9")],
            foreground=[("active", COLOR_PRIMARY), ("disabled", "#94A3B8")],
        )

        # Cấu hình bảng Treeview
        self.style.configure(
            "Treeview",
            font=("Segoe UI", 10),
            rowheight=26,
            background="#FFFFFF",
            fieldbackground="#FFFFFF",
            borderwidth=0,
        )
        self.style.configure(
            "Treeview.Heading",
            font=("Segoe UI", 10, "bold"),
            background="#F8FAFC",
            foreground=COLOR_TEXT_MAIN,
            relief="flat",
            padding=(6, 6),
        )
        self.style.map("Treeview.Heading", background=[("active", "#E2E8F0")])

    def _create_widgets(self):
        """Khởi tạo bố cục các thành phần giao diện."""
        # ═════════════════════════════════════════════════════════════════
        # 1. THANH NÚT TRÊN CÙNG (TOOLBAR)
        # ═════════════════════════════════════════════════════════════════
        toolbar_frame = tk.Frame(self, bg=COLOR_CARD_BG, bd=1, relief="solid", highlightthickness=0)
        toolbar_frame.pack(side="top", fill="x", padx=12, pady=(10, 6))

        inner_tb = tk.Frame(toolbar_frame, bg=COLOR_CARD_BG)
        inner_tb.pack(fill="x", padx=8, pady=8)

        self.btn_open = ttk.Button(
            inner_tb, text="📂 Chọn ảnh", command=self.on_open_image, style="Action.TButton"
        )
        self.btn_open.pack(side="left", padx=4)

        self.btn_scan = ttk.Button(
            inner_tb, text="🔍 Đọc phiếu", command=self.on_scan_sheet, style="Action.TButton", state="disabled"
        )
        self.btn_scan.pack(side="left", padx=4)

        self.btn_key = ttk.Button(
            inner_tb, text="📋 Nạp đáp án chuẩn", command=self.on_load_key, style="Action.TButton"
        )
        self.btn_key.pack(side="left", padx=4)

        self.btn_score = ttk.Button(
            inner_tb, text="⭐ Chấm điểm", command=self.on_score, style="Action.TButton", state="disabled"
        )
        self.btn_score.pack(side="left", padx=4)

        self.btn_excel = ttk.Button(
            inner_tb, text="📊 Xuất Excel", command=self.on_export_excel, style="Action.TButton", state="disabled"
        )
        self.btn_excel.pack(side="left", padx=4)

        # Huy hiệu trạng thái đáp án chuẩn ở bên phải
        self.lbl_key_status = tk.Label(
            inner_tb,
            text="● Chưa có đáp án chuẩn",
            font=("Segoe UI", 9, "bold"),
            bg="#F1F5F9",
            fg=COLOR_TEXT_MUTED,
            padx=10,
            pady=4,
            bd=1,
            relief="solid",
        )
        self.lbl_key_status.pack(side="right", padx=6)

        # ═════════════════════════════════════════════════════════════════
        # 2. VÙNG NỘI DUNG CHÍNH (BỐ CỤC 2 CỘT)
        # ═════════════════════════════════════════════════════════════════
        content_box = tk.Frame(self, bg=COLOR_APP_BG)
        content_box.pack(fill="both", expand=True, padx=12, pady=4)

        # ── CỘT TRÁI: KHUNG HIỂN THỊ ẢNH PHIẾU OMR ───────────────────
        left_card = tk.Frame(content_box, bg=COLOR_CARD_BG, bd=1, relief="solid")
        left_card.pack(side="left", fill="both", expand=True, padx=(0, 6))

        # Thanh tiêu đề cột trái
        left_header = tk.Frame(left_card, bg=COLOR_CARD_BG)
        left_header.pack(fill="x", padx=12, pady=(10, 6))

        tk.Label(
            left_header,
            text="📷 Ảnh phiếu trắc nghiệm",
            font=("Segoe UI", 11, "bold"),
            fg=COLOR_TEXT_MAIN,
            bg=COLOR_CARD_BG,
        ).pack(side="left")

        self.lbl_image_info = tk.Label(
            left_header,
            text="Chưa tải ảnh",
            font=("Segoe UI", 9),
            fg=COLOR_TEXT_MUTED,
            bg=COLOR_CARD_BG,
        )
        self.lbl_image_info.pack(side="right")

        # Canvas hiển thị ảnh (nền xám nhạt hiện đại)
        self.canvas = tk.Canvas(left_card, bg="#F8FAFC", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.canvas.bind("<Configure>", self._on_canvas_resize)

        # ── CỘT PHẢI: KHUNG KẾT QUẢ & CHẤM ĐIỂM ──────────────────────
        right_card = tk.Frame(content_box, bg=COLOR_CARD_BG, bd=1, relief="solid", width=470)
        right_card.pack(side="right", fill="both", expand=False, padx=(6, 0))
        right_card.pack_propagate(False)

        # Thanh tiêu đề cột phải
        tk.Label(
            right_card,
            text="📝 Kết quả nhận diện & Chấm điểm",
            font=("Segoe UI", 11, "bold"),
            fg=COLOR_TEXT_MAIN,
            bg=COLOR_CARD_BG,
        ).pack(anchor="w", padx=12, pady=(10, 6))

        # ── KHỐI ĐIỂM TỔNG QUAN NỔI BẬT (SCORE CARD) ─────────────────
        score_card = tk.Frame(
            right_card, bg="#EFF6FF", bd=1, relief="solid", highlightcolor="#BFDBFE"
        )
        score_card.pack(fill="x", padx=10, pady=(0, 8))

        tk.Label(
            score_card,
            text="ĐIỂM SỐ TỔNG QUAN",
            font=("Segoe UI", 9, "bold"),
            fg=COLOR_PRIMARY,
            bg="#EFF6FF",
        ).pack(anchor="center", pady=(8, 0))

        self.lbl_score = tk.Label(
            score_card,
            text="-- / 10",
            font=("Segoe UI", 30, "bold"),
            fg=COLOR_PRIMARY,
            bg="#EFF6FF",
        )
        self.lbl_score.pack(anchor="center", pady=(0, 2))

        # 4 ô thống kê pastel: Đúng, Sai, Trống, Nhiều ô
        chips_frame = tk.Frame(score_card, bg="#EFF6FF")
        chips_frame.pack(fill="x", padx=10, pady=(0, 8))

        self.chip_correct = self._make_pastel_chip(chips_frame, "✓ Đúng", "--", PASTEL_CORRECT_BG, PASTEL_CORRECT_FG, 0)
        self.chip_wrong   = self._make_pastel_chip(chips_frame, "✗ Sai", "--", PASTEL_WRONG_BG, PASTEL_WRONG_FG, 1)
        self.chip_blank   = self._make_pastel_chip(chips_frame, "⚪ Trống", "--", PASTEL_BLANK_BG, PASTEL_BLANK_FG, 2)
        self.chip_multi   = self._make_pastel_chip(chips_frame, "⚠ Nhiều ô", "--", PASTEL_MULTI_BG, PASTEL_MULTI_FG, 3)

        self.lbl_stats = tk.Label(
            score_card,
            text="Chưa có kết quả đọc phiếu",
            font=("Segoe UI", 9),
            fg=COLOR_TEXT_MUTED,
            bg="#EFF6FF",
        )
        self.lbl_stats.pack(anchor="center", pady=(0, 6))

        # ── BẢNG KẾT QUẢ 50 CÂU (TTK.TREEVIEW) ───────────────────────
        table_container = tk.Frame(right_card, bg="#FFFFFF")
        table_container.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        cols = ("question", "student", "correct", "result")
        self.tree = ttk.Treeview(table_container, columns=cols, show="headings", selectmode="browse")

        self.tree.heading("question", text="Câu")
        self.tree.heading("student", text="Đáp án HS")
        self.tree.heading("correct", text="Đáp án đúng")
        self.tree.heading("result", text="Kết quả")

        self.tree.column("question", width=55, anchor="center")
        self.tree.column("student", width=95, anchor="center")
        self.tree.column("correct", width=100, anchor="center")
        self.tree.column("result", width=130, anchor="center")

        # CẤU HÌNH TÔ MÀU CẢ DÒNG QUA TREEVIEW TAGS
        self.tree.tag_configure("correct",  background=ROW_CORRECT_BG, foreground=ROW_CORRECT_FG)
        self.tree.tag_configure("wrong",    background=ROW_WRONG_BG,   foreground=ROW_WRONG_FG)
        self.tree.tag_configure("blank",    background=ROW_BLANK_BG,   foreground=ROW_BLANK_FG)
        self.tree.tag_configure("multiple", background=ROW_MULTI_BG,   foreground=ROW_MULTI_FG)
        self.tree.tag_configure("normal",   background=ROW_NORMAL_BG,  foreground=ROW_NORMAL_FG)

        tree_scroll = ttk.Scrollbar(table_container, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)

        self.tree.pack(side="left", fill="both", expand=True)
        tree_scroll.pack(side="right", fill="y")

        # ═════════════════════════════════════════════════════════════════
        # 3. THANH TRẠNG THÁI PHÍA DƯỚI CÙNG (STATUSBAR)
        # ═════════════════════════════════════════════════════════════════
        status_bar_frame = tk.Frame(self, bg=COLOR_CARD_BG, height=28, bd=1, relief="solid")
        status_bar_frame.pack(side="bottom", fill="x", padx=12, pady=(0, 8))

        self.statusbar = tk.Label(
            status_bar_frame,
            text="",
            font=("Segoe UI", 9),
            bg=COLOR_CARD_BG,
            fg=COLOR_TEXT_MAIN,
            anchor="w",
            padx=10,
            pady=3,
        )
        self.statusbar.pack(fill="x")

    def _make_pastel_chip(
        self, parent, title: str, value: str, bg_color: str, fg_color: str, col_idx: int
    ) -> tk.Label:
        """Tạo một thẻ thống kê nhỏ xinh màu pastel."""
        parent.columnconfigure(col_idx, weight=1)
        chip = tk.Frame(parent, bg=bg_color, bd=1, relief="solid")
        chip.grid(row=0, column=col_idx, padx=2, pady=2, sticky="nsew")

        tk.Label(
            chip, text=title, font=("Segoe UI", 8, "bold"), fg=fg_color, bg=bg_color
        ).pack(anchor="center", pady=(3, 0))

        val_lbl = tk.Label(
            chip, text=value, font=("Segoe UI", 11, "bold"), fg=fg_color, bg=bg_color
        )
        val_lbl.pack(anchor="center", pady=(0, 3))
        return val_lbl

    def _set_status(self, message: str, is_error: bool = False):
        """Cập nhật thông báo thanh trạng thái."""
        prefix = "❌ " if is_error else "ℹ "
        self.statusbar.configure(
            text=f"{prefix}{message}",
            fg="#DC2626" if is_error else COLOR_TEXT_MAIN,
        )

    def _draw_placeholder(self):
        """Vẽ trạng thái chờ thân thiện trên Canvas khi chưa có ảnh."""
        self.canvas.delete("all")
        cw = max(self.canvas.winfo_width(), 300)
        ch = max(self.canvas.winfo_height(), 300)
        cx, cy = cw // 2, ch // 2

        self.canvas.create_text(
            cx, cy - 25,
            text="📄",
            font=("Segoe UI", 42),
            fill="#CBD5E1",
        )
        self.canvas.create_text(
            cx, cy + 25,
            text="Chưa có ảnh phiếu trắc nghiệm",
            font=("Segoe UI", 12, "bold"),
            fill="#64748B",
        )
        self.canvas.create_text(
            cx, cy + 50,
            text="Hãy nhấn nút '📂 Chọn ảnh' ở trên để bắt đầu",
            font=("Segoe UI", 10),
            fill="#94A3B8",
        )

    # ═════════════════════════════════════════════════════════════════
    # XỬ LÝ SỰ KIỆN (EVENT HANDLERS)
    # ═════════════════════════════════════════════════════════════════

    def on_open_image(self):
        """1. Chọn ảnh phiếu trắc nghiệm."""
        filetypes = [
            ("Hình ảnh phiếu", "*.png *.jpg *.jpeg *.bmp *.tiff *.webp"),
            ("Tất cả tệp", "*.*"),
        ]
        path = filedialog.askopenfilename(title="Chọn ảnh phiếu trắc nghiệm", filetypes=filetypes)
        if not path:
            return

        try:
            self.image_path = Path(path)
            self.loaded_image = load_image(self.image_path)
            self.display_image = self.loaded_image.copy()
            self._render_image(self.display_image)

            # Cập nhật thông tin ảnh
            h, w = self.loaded_image.shape[:2]
            self.lbl_image_info.configure(text=f"{self.image_path.name} ({w}×{h})")

            # Reset các kết quả trước đó
            self.student_answers = None
            self.score_result = None
            self._clear_table()

            # Đặt lại Score Card
            self.lbl_score.configure(text="-- / 10", fg=COLOR_PRIMARY)
            self._update_stat_chips(0, 0, 0, 0, is_reset=True)
            self.lbl_stats.configure(text=f"Đã mở: {self.image_path.name}. Hãy nhấn 'Đọc phiếu'.")

            # Điều khiển nút
            self.btn_scan.configure(state="normal")
            self.btn_score.configure(state="disabled")
            self.btn_excel.configure(state="disabled")

            self._set_status(f"Đã chọn ảnh: {self.image_path.name}")
        except Exception as exc:
            messagebox.showerror("Lỗi đọc ảnh", str(exc), parent=self)
            self._set_status(f"Lỗi đọc ảnh: {exc}", is_error=True)

    def on_scan_sheet(self):
        """2. Đọc phiếu 50 câu qua OpenCV."""
        if self.image_path is None:
            return

        self._set_status("Đang xử lý nhận diện phiếu 50 câu qua OpenCV...")
        self.update_idletasks()

        try:
            result = process_omr(self.image_path, debug=False)
            self.student_answers = result["answers"]

            # Hiển thị ảnh đã khoanh tròn các ô đã nhận diện
            annotated = result.get("annotated_image")
            if annotated is not None:
                self.display_image = annotated
                self._render_image(self.display_image)

            # Kiểm tra định dạng 50 câu
            v_res = validate_answers(self.student_answers)
            if not v_res["valid"]:
                messagebox.showwarning("Cảnh báo dữ liệu", "; ".join(v_res["errors"]), parent=self)

            # Cập nhật bảng kết quả (chưa chấm)
            self._update_table_unscored()

            # Bật nút chấm điểm và xuất Excel (Chế độ 1)
            self.btn_score.configure(state="normal" if self.answer_key else "disabled")
            self.btn_excel.configure(state="normal")

            # Tự động chấm điểm nếu đã nạp đáp án chuẩn từ trước
            if self.answer_key:
                self.on_score()
            else:
                self.lbl_score.configure(text="Chưa chấm", fg=COLOR_TEXT_MUTED)
                self.lbl_stats.configure(
                    text=f"Đã nhận diện đủ 50 câu (Bỏ trống: {v_res['blank_count']}, Tô nhiều: {v_res['multiple_count']})"
                )
                # Tuyệt đối không hiển thị số câu đã tô dưới nhãn "Đúng" khi chưa chấm
                self._update_stat_chips(
                    "--",
                    "--",
                    v_res["blank_count"],
                    v_res["multiple_count"],
                )
                self._set_status("Đọc phiếu thành công (50 câu). Có thể nạp đáp án chuẩn để chấm điểm hoặc xuất Excel ngay.")

        except Exception as exc:
            messagebox.showerror("Lỗi nhận diện phiếu", str(exc), parent=self)
            self._set_status(f"Lỗi nhận diện phiếu: {exc}", is_error=True)

    def on_load_key(self):
        """3. Nạp đáp án chuẩn từ file JSON."""
        path = filedialog.askopenfilename(
            title="Chọn file đáp án chuẩn (JSON)",
            filetypes=[("Tệp JSON", "*.json"), ("Tất cả", "*.*")],
        )
        if not path:
            return

        try:
            new_key = load_answer_key(path)
            self.answer_key = new_key
            self.lbl_key_status.configure(
                text=f"✓ Đáp án: {Path(path).name}",
                bg=PASTEL_CORRECT_BG,
                fg=PASTEL_CORRECT_FG,
            )
            self._set_status(f"Đã nạp đáp án chuẩn: {Path(path).name}")

            # Đồng bộ dữ liệu: Tính lại điểm ngay nếu đã đọc bài học sinh
            if self.student_answers is not None:
                self.on_score()
            else:
                self.btn_score.configure(state="disabled")

        except Exception as exc:
            messagebox.showerror("Lỗi nạp đáp án chuẩn", str(exc), parent=self)
            self._set_status(f"Lỗi nạp đáp án chuẩn: {exc}", is_error=True)

    def on_score(self):
        """4. Chấm điểm học sinh dựa trên đáp án chuẩn."""
        if not self.student_answers or not self.answer_key:
            messagebox.showinfo("Thông báo", "Cần đọc phiếu và nạp đáp án chuẩn trước khi chấm điểm.", parent=self)
            return

        try:
            self.score_result = score_answers(self.student_answers, self.answer_key)
            self._update_table_scored()

            score   = self.score_result["score"]
            correct = self.score_result["correct_count"]
            wrong   = self.score_result["wrong_count"]
            blank   = self.score_result["blank_count"]
            multi   = self.score_result["multiple_count"]

            # Cập nhật điểm số nổi bật (xanh khi đậu, đỏ khi trượt)
            color_score = "#16A34A" if score >= 5.0 else "#DC2626"
            self.lbl_score.configure(text=f"{score:.2f} / 10", fg=color_score)
            self.lbl_stats.configure(
                text=f"Đạt: {correct}/50 câu ({round(correct/50*100)}%) — Thang điểm 10"
            )
            self._update_stat_chips(correct, wrong, blank, multi)

            self.btn_excel.configure(state="normal")
            self._set_status(f"Chấm điểm xong! Điểm số: {score:.2f}/10 (Đúng {correct}/50 câu).")

        except Exception as exc:
            self.score_result = None
            messagebox.showerror("Lỗi chấm điểm", str(exc), parent=self)
            self._set_status(f"Lỗi chấm điểm: {exc}", is_error=True)

    def on_export_excel(self):
        """5. Xuất kết quả ra file Excel (Chế độ 1 hoặc Chế độ 2)."""
        if not self.student_answers:
            messagebox.showwarning("Cảnh báo", "Chưa có kết quả để xuất. Hãy đọc phiếu trước.", parent=self)
            return

        default_name = "ket_qua_omr.xlsx"
        if self.image_path:
            default_name = f"{self.image_path.stem}_ket_qua.xlsx"

        save_path = filedialog.asksaveasfilename(
            title="Lưu file kết quả Excel",
            initialfile=default_name,
            defaultextension=".xlsx",
            filetypes=[("Tệp Excel", "*.xlsx")],
        )
        if not save_path:
            return

        try:
            if self.score_result is not None:
                # Chế độ 2: Đã chấm điểm
                out = export_excel(self.score_result, save_path)
                mode_name = "kết quả chấm điểm đầy đủ"
            else:
                # Chế độ 1: Chưa chấm điểm (kết quả đọc thô)
                out = export_excel(None, save_path, answers=self.student_answers)
                mode_name = "kết quả nhận diện (chưa chấm)"

            self._set_status(f"Xuất Excel thành công: {Path(out).name}")
            messagebox.showinfo("Thành công", f"Đã xuất {mode_name} ra file:\n{out}", parent=self)
        except Exception as exc:
            messagebox.showerror("Lỗi xuất Excel", str(exc), parent=self)
            self._set_status(f"Lỗi xuất Excel: {exc}", is_error=True)

    # ═════════════════════════════════════════════════════════════════
    # CẬP NHẬT DỮ LIỆU & TÔ MÀU BẢNG (ROW COLORING)
    # ═════════════════════════════════════════════════════════════════

    def _update_table_unscored(self):
        """Cập nhật bảng 50 câu khi chưa chấm điểm."""
        self._clear_table()
        if not self.student_answers:
            return

        for i, ans in enumerate(self.student_answers, start=1):
            if ans == "BLANK":
                status, tag = "— Bỏ trống", "blank"
            elif ans == "MULTIPLE":
                status, tag = "⚠ Nhiều đáp án", "multiple"
            else:
                status, tag = "Đã chọn", "normal"

            # Gán tag màu cho toàn bộ dòng
            self.tree.insert("", "end", values=(i, ans, "--", status), tags=(tag,))

    def _update_table_scored(self):
        """Cập nhật bảng 50 câu sau khi chấm điểm: Tô màu cả dòng."""
        self._clear_table()
        if not self.score_result:
            return

        result_map = {
            "correct":  ("✓ Đúng",        "correct"),
            "wrong":    ("✗ Sai",         "wrong"),
            "blank":    ("— Bỏ trống",     "blank"),
            "multiple": ("⚠ Nhiều đáp án", "multiple"),
        }

        for item in self.score_result["details"]:
            q = item["question"]
            stu = item["student"]
            cor = item["correct"]
            res_text, tag = result_map.get(item["result"], (item["result"], "normal"))

            # Gán tag màu cho toàn bộ dòng
            self.tree.insert("", "end", values=(q, stu, cor, res_text), tags=(tag,))

    def _update_stat_chips(self, correct, wrong, blank, multi, is_reset: bool = False):
        """Cập nhật các số liệu trên 4 ô pastel."""
        if is_reset:
            self.chip_correct.configure(text="--")
            self.chip_wrong.configure(text="--")
            self.chip_blank.configure(text="--")
            self.chip_multi.configure(text="--")
        else:
            self.chip_correct.configure(text="--" if correct is None or correct == "--" else str(correct))
            self.chip_wrong.configure(text="--" if wrong is None or wrong == "--" else str(wrong))
            self.chip_blank.configure(text="--" if blank is None or blank == "--" else str(blank))
            self.chip_multi.configure(text="--" if multi is None or multi == "--" else str(multi))

    def _clear_table(self):
        """Xóa toàn bộ dòng trong bảng."""
        for item in self.tree.get_children():
            self.tree.delete(item)

    def _on_canvas_resize(self, event):
        """Tự động căn chỉnh ảnh khi khung Canvas đổi kích thước."""
        if self.display_image is not None:
            self._render_image(self.display_image)
        else:
            self._draw_placeholder()

    def _render_image(self, bgr_img: np.ndarray):
        """Hiển thị ảnh BGR lên Canvas với tỉ lệ tối ưu."""
        if not _HAS_PIL:
            self.canvas.delete("all")
            self.canvas.create_text(
                self.canvas.winfo_width() // 2,
                self.canvas.winfo_height() // 2,
                text="Cần cài Pillow để xem ảnh.\npip install Pillow",
                fill="#EF4444",
                font=("Segoe UI", 12, "bold"),
            )
            return

        cw = max(self.canvas.winfo_width(), 100)
        ch = max(self.canvas.winfo_height(), 100)

        rgb = cv2.cvtColor(bgr_img, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(rgb)
        img.thumbnail((cw - 16, ch - 16), Image.Resampling.LANCZOS)

        self._photo_ref = ImageTk.PhotoImage(img)
        self.canvas.delete("all")
        self.canvas.create_image(cw // 2, ch // 2, anchor="center", image=self._photo_ref)


def launch_simple_app():
    """Khởi chạy ứng dụng OMR đơn giản."""
    app = SimpleOMRApp()
    app.mainloop()


if __name__ == "__main__":
    launch_simple_app()
