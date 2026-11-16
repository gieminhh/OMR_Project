import json
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from main import process_omr
from modules.export_excel import export_excel
from modules.image_processing import load_image
from modules.scoring import load_answer_key, score_answers
from modules.validation import VALID_KEY_VALUES, validate_answer_key, validate_answers

try:
    from PIL import Image, ImageTk
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False


COLOR_APP_BG        = "#F1F5F9"
COLOR_CARD_BG       = "#FFFFFF"
COLOR_BORDER        = "#E2E8F0"
COLOR_PRIMARY       = "#2563EB"
COLOR_TEXT_MAIN     = "#0F172A"
COLOR_TEXT_MUTED    = "#64748B"


PASTEL_CORRECT_BG   = "#DCFCE7"
PASTEL_CORRECT_FG   = "#15803D"
PASTEL_WRONG_BG     = "#FEE2E2"
PASTEL_WRONG_FG     = "#B91C1C"
PASTEL_BLANK_BG     = "#FEF9C3"
PASTEL_BLANK_FG     = "#A16207"
PASTEL_MULTI_BG     = "#FFEDD5"
PASTEL_MULTI_FG     = "#C2410C"


ROW_CORRECT_BG      = "#D1E7DD"
ROW_CORRECT_FG      = "#0F5132"
ROW_WRONG_BG        = "#F8D7DA"
ROW_WRONG_FG        = "#842029"
ROW_BLANK_BG        = "#FFF3CD"
ROW_BLANK_FG        = "#664D03"
ROW_MULTI_BG        = "#FFE5D0"
ROW_MULTI_FG        = "#7C2D12"
ROW_NORMAL_BG       = "#FFFFFF"
ROW_NORMAL_FG       = "#1E293B"

ROW_LABELS = {
    "correct": "✓ Đúng",
    "wrong": "✗ Sai",
    "blank": "— Bỏ trống",
    "multiple": "⚠ Nhiều đáp án",
}
UNSCORED_ROW_TAGS = {"BLANK": "blank", "MULTIPLE": "multiple"}


class ManualAnswerKeyDialog(tk.Toplevel):
    def __init__(
        self,
        parent,
        initial_answers: list[str] | None = None,
        on_save=None,
    ):
        super().__init__(parent)
        self.title("NHẬP ĐÁP ÁN CHUẨN – 50 CÂU")
        self.geometry("620x680")
        self.minsize(580, 520)
        self.configure(bg=COLOR_APP_BG)

        self.on_save_callback = on_save

        self.vars: list[tk.StringVar] = []
        self.combos: list[ttk.Combobox] = []

        try:
            self.transient(parent)
            self.grab_set()
        except Exception:
            pass

        self._create_widgets(initial_answers)

    def _create_widgets(self, initial_answers: list[str] | None):
        header_frame = tk.Frame(self, bg=COLOR_CARD_BG, bd=1, relief="solid")
        header_frame.pack(side="top", fill="x", padx=12, pady=(10, 6))

        title_lbl = tk.Label(
            header_frame,
            text="NHẬP ĐÁP ÁN CHUẨN – 50 CÂU",
            font=("Segoe UI", 12, "bold"),
            bg=COLOR_CARD_BG,
            fg=COLOR_TEXT_MAIN,
        )
        title_lbl.pack(anchor="w", padx=12, pady=(10, 2))

        sub_lbl = tk.Label(
            header_frame,
            text="Chọn đáp án A, B, C hoặc D cho từng câu (bắt buộc đủ 50 câu). Có thể chọn hoặc gõ phím A/B/C/D.",
            font=("Segoe UI", 9),
            bg=COLOR_CARD_BG,
            fg=COLOR_TEXT_MUTED,
        )
        sub_lbl.pack(anchor="w", padx=12, pady=(0, 10))


        tools_frame = tk.Frame(self, bg=COLOR_APP_BG)
        tools_frame.pack(side="top", fill="x", padx=12, pady=(0, 6))

        self.lbl_counter = tk.Label(
            tools_frame,
            text="Đã chọn: 0/50 câu",
            font=("Segoe UI", 9, "bold"),
            bg=COLOR_APP_BG,
            fg=COLOR_PRIMARY,
        )
        self.lbl_counter.pack(side="left", padx=4)

        btn_clear = ttk.Button(
            tools_frame, text="Xóa hết", command=self.clear_all, style="Action.TButton"
        )
        btn_clear.pack(side="right", padx=4)

        for opt in ("D", "C", "B", "A"):
            b = ttk.Button(
                tools_frame,
                text=f"Tất cả {opt}",
                command=lambda o=opt: self.fill_all(o),
                style="Action.TButton",
            )
            b.pack(side="right", padx=2)

        lbl_quick = tk.Label(
            tools_frame,
            text="Điền nhanh:",
            font=("Segoe UI", 9),
            bg=COLOR_APP_BG,
            fg=COLOR_TEXT_MUTED,
        )
        lbl_quick.pack(side="right", padx=(8, 2))


        container = tk.Frame(self, bg=COLOR_CARD_BG, bd=1, relief="solid")
        container.pack(side="top", fill="both", expand=True, padx=12, pady=4)

        canvas = tk.Canvas(container, bg=COLOR_CARD_BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg=COLOR_CARD_BG)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )

        canvas_window = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")

        def _on_canvas_configure(event):
            canvas.itemconfig(canvas_window, width=event.width)

        canvas.bind("<Configure>", _on_canvas_configure)
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")


        def _on_mousewheel(event):
            delta = -1 if event.delta < 0 else 1
            canvas.yview_scroll(delta, "units")

        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        self.bind("<Destroy>", lambda e: canvas.unbind_all("<MouseWheel>"))


        cols_box = tk.Frame(scrollable_frame, bg=COLOR_CARD_BG)
        cols_box.pack(fill="both", expand=True, padx=16, pady=8)

        left_col = tk.Frame(cols_box, bg=COLOR_CARD_BG)
        left_col.pack(side="left", fill="both", expand=True)

        sep = ttk.Separator(cols_box, orient="vertical")
        sep.pack(side="left", fill="y", padx=12)

        right_col = tk.Frame(cols_box, bg=COLOR_CARD_BG)
        right_col.pack(side="left", fill="both", expand=True)


        for i in range(1, 51):
            col = left_col if i <= 25 else right_col
            init_val = ""
            if initial_answers and i - 1 < len(initial_answers):
                val = str(initial_answers[i - 1]).strip().upper()
                if val in VALID_KEY_VALUES:
                    init_val = val

            var = tk.StringVar(value=init_val)
            self.vars.append(var)

            row = tk.Frame(col, bg=COLOR_CARD_BG, pady=2)
            row.pack(fill="x", padx=4)

            lbl = tk.Label(
                row,
                text=f"Câu {i:02d}:",
                font=("Segoe UI", 9, "bold"),
                width=7,
                anchor="w",
                bg=COLOR_CARD_BG,
                fg=COLOR_TEXT_MAIN,
            )
            lbl.pack(side="left")

            cb = ttk.Combobox(
                row,
                textvariable=var,
                values=("A", "B", "C", "D"),
                state="readonly",
                width=5,
                font=("Segoe UI", 9, "bold"),
            )
            cb.pack(side="left", padx=4)
            cb.bind("<<ComboboxSelected>>", lambda e: self._on_change())
            cb.bind("<KeyPress>", lambda e, v=var: self._on_key_press(e, v))
            self.combos.append(cb)

        self._on_change()


        bottom_frame = tk.Frame(self, bg=COLOR_CARD_BG, bd=1, relief="solid")
        bottom_frame.pack(side="bottom", fill="x", padx=12, pady=(6, 10))

        inner_bottom = tk.Frame(bottom_frame, bg=COLOR_CARD_BG)
        inner_bottom.pack(fill="x", padx=8, pady=8)

        btn_save = ttk.Button(
            inner_bottom,
            text="💾 Lưu & sử dụng",
            command=self.on_save,
            style="Action.TButton",
        )
        btn_save.pack(side="left", padx=4)

        btn_cancel = ttk.Button(
            inner_bottom,
            text="❌ Hủy",
            command=self.destroy,
            style="Action.TButton",
        )
        btn_cancel.pack(side="right", padx=4)

    def _on_key_press(self, event, var: tk.StringVar):
        char = (event.char or "").upper()
        if char in VALID_KEY_VALUES:
            var.set(char)
            self._on_change()
            return "break"
        return None

    def _on_change(self):
        valid_count = sum(answer in VALID_KEY_VALUES for answer in self.get_answers())
        self.lbl_counter.configure(
            text=f"Đã chọn: {valid_count}/50 câu",
            fg="#16A34A" if valid_count == 50 else COLOR_PRIMARY,
        )

    def get_answers(self) -> list[str]:
        return [v.get().strip().upper() for v in self.vars]

    def set_answer(self, index: int, value: str):
        if 0 <= index < len(self.vars):
            self.vars[index].set(value.strip().upper())
            self._on_change()

    def fill_all(self, value: str):
        val = value.strip().upper()
        if val in VALID_KEY_VALUES:
            for v in self.vars:
                v.set(val)
            self._on_change()

    def clear_all(self):
        for var in self.vars:
            var.set("")
        self._on_change()

    def on_save(self):
        answers = self.get_answers()
        v_res = validate_answer_key(answers)
        if not v_res["valid"]:
            missing = v_res["missing_indices"]
            missing_str = ", ".join(map(str, missing[:10])) + ("..." if len(missing) > 10 else "")
            messagebox.showwarning(
                "Chưa đủ 50 câu",
                f"Chưa điền đủ 50 câu! Còn thiếu {len(missing)} câu chưa chọn đáp án hợp lệ.\n"
                f"Các câu còn thiếu: {missing_str}\n"
                f"Vui lòng chọn đáp án A, B, C hoặc D cho tất cả 50 câu.",
                parent=self,
            )
            return

        if self.on_save_callback:
            self.on_save_callback(answers)
        self.destroy()


class SimpleOMRApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PHẦN MỀM ĐỌC PHIẾU TRẮC NGHIỆM OMR 50 CÂU")
        self.geometry("1200x740")
        self.minsize(1020, 640)
        self.configure(bg=COLOR_APP_BG)


        self.image_path: Path | None = None
        self.loaded_image: np.ndarray | None = None
        self.display_image: np.ndarray | None = None
        self.student_answers: list[str] | None = None
        self.answer_key: list[str] | None = None
        self.score_result: dict | None = None
        self._photo_ref = None


        self._setup_styles()
        self._create_widgets()
        self._draw_placeholder()
        self._set_status("Sẵn sàng. Hãy chọn ảnh phiếu để bắt đầu.")

    def _setup_styles(self):
        self.style = ttk.Style(self)
        if "clam" in self.style.theme_names():
            self.style.theme_use("clam")


        self.style.configure(
            "Action.TButton",
            font=("Segoe UI", 9, "bold"),
            padding=(8, 5),
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
        toolbar_frame = tk.Frame(self, bg=COLOR_CARD_BG, bd=1, relief="solid", highlightthickness=0)
        toolbar_frame.pack(side="top", fill="x", padx=12, pady=(10, 6))

        inner_tb = tk.Frame(toolbar_frame, bg=COLOR_CARD_BG)
        inner_tb.pack(fill="x", padx=8, pady=8)

        self.btn_open = ttk.Button(
            inner_tb, text="📂 Chọn ảnh", command=self.on_open_image, style="Action.TButton"
        )

        self.btn_scan = ttk.Button(
            inner_tb, text="🔍 Đọc phiếu", command=self.on_scan_sheet, style="Action.TButton", state="disabled"
        )

        self.btn_key = ttk.Button(
            inner_tb, text="📋 Nạp JSON", command=self.on_load_key, style="Action.TButton"
        )

        self.btn_manual_key = ttk.Button(
            inner_tb, text="✏️ Nhập thủ công", command=self.on_manual_key, style="Action.TButton"
        )

        self.btn_export_key = ttk.Button(
            inner_tb, text="💾 Xuất JSON", command=self.on_export_key_json, style="Action.TButton"
        )

        self.btn_score = ttk.Button(
            inner_tb, text="⭐ Chấm điểm", command=self.on_score, style="Action.TButton", state="disabled"
        )

        self.btn_excel = ttk.Button(
            inner_tb, text="📊 Xuất Excel", command=self.on_export_excel, style="Action.TButton", state="disabled"
        )


        buttons = (
            self.btn_open, self.btn_scan, self.btn_key, self.btn_manual_key,
            self.btn_export_key, self.btn_score, self.btn_excel,
        )
        for button in buttons:
            button.pack(side="left", padx=2)

        self.lbl_key_status = tk.Label(
            inner_tb,
            text="● Chưa có đáp án chuẩn",
            font=("Segoe UI", 9, "bold"),
            bg="#F1F5F9",
            fg=COLOR_TEXT_MUTED,
            padx=8,
            pady=3,
            bd=1,
            relief="solid",
        )
        self.lbl_key_status.pack(side="right", padx=4)


        content_box = tk.Frame(self, bg=COLOR_APP_BG)
        content_box.pack(fill="both", expand=True, padx=12, pady=4)


        left_card = tk.Frame(content_box, bg=COLOR_CARD_BG, bd=1, relief="solid")
        left_card.pack(side="left", fill="both", expand=True, padx=(0, 6))

        left_header = tk.Frame(left_card, bg=COLOR_CARD_BG)
        left_header.pack(fill="x", padx=12, pady=8)

        lbl_img_title = tk.Label(
            left_header,
            text="HÌNH ẢNH PHIẾU THI",
            font=("Segoe UI", 11, "bold"),
            fg=COLOR_TEXT_MAIN,
            bg=COLOR_CARD_BG,
        )
        lbl_img_title.pack(side="left")

        self.lbl_image_info = tk.Label(
            left_header,
            text="Chưa có ảnh",
            font=("Segoe UI", 9),
            fg=COLOR_TEXT_MUTED,
            bg=COLOR_CARD_BG,
        )
        self.lbl_image_info.pack(side="right")

        self.canvas = tk.Canvas(left_card, bg="#F8FAFC", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.canvas.bind("<Configure>", self._on_canvas_resize)


        right_card = tk.Frame(content_box, bg=COLOR_CARD_BG, bd=1, relief="solid", width=480)
        right_card.pack(side="right", fill="both", expand=False, padx=(6, 0))
        right_card.pack_propagate(False)

        right_header = tk.Frame(right_card, bg=COLOR_CARD_BG)
        right_header.pack(fill="x", padx=12, pady=8)

        lbl_res_title = tk.Label(
            right_header,
            text="KẾT QUẢ NHẬN DIỆN & ĐIỂM SỐ",
            font=("Segoe UI", 11, "bold"),
            fg=COLOR_TEXT_MAIN,
            bg=COLOR_CARD_BG,
        )
        lbl_res_title.pack(side="left")


        score_card = tk.Frame(right_card, bg="#F8FAFC", bd=1, relief="solid")
        score_card.pack(fill="x", padx=10, pady=(0, 6))

        lbl_score_caption = tk.Label(
            score_card,
            text="ĐIỂM SỐ BÀI THI",
            font=("Segoe UI", 8, "bold"),
            fg=COLOR_TEXT_MUTED,
            bg="#F8FAFC",
        )
        lbl_score_caption.pack(anchor="w", padx=12, pady=(6, 0))

        self.lbl_score = tk.Label(
            score_card,
            text="-- / 10",
            font=("Segoe UI", 26, "bold"),
            fg=COLOR_PRIMARY,
            bg="#F8FAFC",
        )
        self.lbl_score.pack(anchor="w", padx=12, pady=(0, 0))

        self.lbl_stats = tk.Label(
            score_card,
            text="Chưa có dữ liệu bài thi. Hãy chọn ảnh và bấm 'Đọc phiếu'.",
            font=("Segoe UI", 9),
            fg=COLOR_TEXT_MUTED,
            bg="#F8FAFC",
        )
        self.lbl_stats.pack(anchor="w", padx=12, pady=(0, 6))


        chips_frame = tk.Frame(right_card, bg=COLOR_CARD_BG)
        chips_frame.pack(fill="x", padx=10, pady=(0, 6))

        self.chip_correct = self._make_pastel_chip(chips_frame, "✓ Đúng", "--", PASTEL_CORRECT_BG, PASTEL_CORRECT_FG, 0)
        self.chip_wrong   = self._make_pastel_chip(chips_frame, "✗ Sai", "--", PASTEL_WRONG_BG, PASTEL_WRONG_FG, 1)
        self.chip_blank   = self._make_pastel_chip(chips_frame, "⚪ Trống", "--", PASTEL_BLANK_BG, PASTEL_BLANK_FG, 2)
        self.chip_multi   = self._make_pastel_chip(chips_frame, "⚠ Nhiều ô", "--", PASTEL_MULTI_BG, PASTEL_MULTI_FG, 3)


        lbl_tbl_title = tk.Label(
            right_card,
            text="CHI TIẾT 50 CÂU TRẢ LỜI",
            font=("Segoe UI", 9, "bold"),
            fg=COLOR_TEXT_MUTED,
            bg=COLOR_CARD_BG,
        )
        lbl_tbl_title.pack(anchor="w", padx=12, pady=(2, 2))

        table_box = tk.Frame(right_card, bg=COLOR_CARD_BG)
        table_box.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        cols = ("question", "student", "correct", "result")
        self.tree = ttk.Treeview(table_box, columns=cols, show="headings", selectmode="browse")

        for column, title, width, min_width, anchor in (
            ("question", "Câu", 55, 45, "center"),
            ("student", "Học sinh", 85, 75, "center"),
            ("correct", "Đáp án đúng", 95, 85, "center"),
            ("result", "Đánh giá", 170, 140, "w"),
        ):
            self.tree.heading(column, text=title, anchor=anchor)
            self.tree.column(column, width=width, minwidth=min_width, anchor=anchor)

        for tag, background, foreground in (
            ("correct", ROW_CORRECT_BG, ROW_CORRECT_FG),
            ("wrong", ROW_WRONG_BG, ROW_WRONG_FG),
            ("blank", ROW_BLANK_BG, ROW_BLANK_FG),
            ("multiple", ROW_MULTI_BG, ROW_MULTI_FG),
            ("normal", ROW_NORMAL_BG, ROW_NORMAL_FG),
        ):
            self.tree.tag_configure(tag, background=background, foreground=foreground)

        scroll_y = ttk.Scrollbar(table_box, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll_y.set)

        self.tree.pack(side="left", fill="both", expand=True)
        scroll_y.pack(side="right", fill="y")


        status_bar_frame = tk.Frame(self, bg=COLOR_CARD_BG, height=28, bd=1, relief="solid")
        status_bar_frame.pack(side="bottom", fill="x")

        self.lbl_status = tk.Label(
            status_bar_frame,
            text="Sẵn sàng.",
            font=("Segoe UI", 9),
            bg=COLOR_CARD_BG,
            fg=COLOR_TEXT_MAIN,
            anchor="w",
            padx=10,
        )
        self.lbl_status.pack(fill="x", pady=4)

    def _make_pastel_chip(self, parent, title: str, initial_val: str, bg_color: str, fg_color: str, col: int) -> tk.Label:
        parent.columnconfigure(col, weight=1)
        chip = tk.Frame(parent, bg=bg_color, bd=1, relief="solid")
        chip.grid(row=0, column=col, padx=3, sticky="ew")

        lbl_title = tk.Label(chip, text=title, font=("Segoe UI", 8, "bold"), fg=fg_color, bg=bg_color)
        lbl_title.pack(anchor="center", pady=(4, 0))

        val_label = tk.Label(chip, text=initial_val, font=("Segoe UI", 13, "bold"), fg=fg_color, bg=bg_color)
        val_label.pack(anchor="center", pady=(0, 4))
        return val_label

    def _set_status(self, text: str, is_error: bool = False):
        self.lbl_status.configure(
            text=text,
            fg="#DC2626" if is_error else COLOR_TEXT_MAIN,
        )

    def _draw_placeholder(self):
        self.canvas.delete("all")
        w = max(self.canvas.winfo_width(), 400)
        h = max(self.canvas.winfo_height(), 400)

        self.canvas.create_text(
            w // 2,
            h // 2 - 20,
            text="📷",
            font=("Segoe UI", 36),
            fill="#CBD5E1",
        )
        self.canvas.create_text(
            w // 2,
            h // 2 + 30,
            text="Chưa có ảnh phiếu trắc nghiệm",
            font=("Segoe UI", 12, "bold"),
            fill=COLOR_TEXT_MUTED,
        )
        self.canvas.create_text(
            w // 2,
            h // 2 + 55,
            text="Nhấn 'Chọn ảnh' trên thanh công cụ để mở phiếu thi (.jpg, .png)",
            font=("Segoe UI", 9),
            fill="#94A3B8",
        )


    def on_open_image(self):
        path = filedialog.askopenfilename(
            title="Chọn ảnh phiếu trắc nghiệm OMR",
            filetypes=[("Tệp ảnh", "*.png;*.jpg;*.jpeg;*.bmp"), ("Tất cả", "*.*")],
        )
        if not path:
            return

        try:

            image_path = Path(path)
            image = load_image(image_path)
            preview = image.copy()
            self._render_image(preview)
            self.image_path = image_path
            self.loaded_image = image
            self.display_image = preview


            h, w = self.loaded_image.shape[:2]
            self.lbl_image_info.configure(text=f"{self.image_path.name} ({w}×{h})")


            self.student_answers = None
            self.score_result = None
            self._clear_table()


            self.lbl_score.configure(text="-- / 10", fg=COLOR_PRIMARY)
            self._update_stat_chips()
            self.lbl_stats.configure(text=f"Đã mở: {self.image_path.name}. Hãy nhấn 'Đọc phiếu'.")


            self.btn_scan.configure(state="normal")
            self.btn_score.configure(state="disabled")
            self.btn_excel.configure(state="disabled")

            self._set_status(f"Đã chọn ảnh: {self.image_path.name}")
        except Exception as exc:
            messagebox.showerror("Lỗi đọc ảnh", str(exc), parent=self)
            self._set_status(f"Lỗi đọc ảnh: {exc}", is_error=True)

    def on_scan_sheet(self):
        if self.image_path is None:
            return

        self._set_status("Đang xử lý nhận diện phiếu 50 câu qua OpenCV...")
        self.update_idletasks()

        try:

            result = process_omr(self.image_path, debug=False)
            answers = result["answers"]
            validation = validate_answers(answers)
            if not validation["valid"]:
                messagebox.showwarning("Cảnh báo dữ liệu", "; ".join(validation["errors"]), parent=self)

            annotated = result.get("annotated_image")
            if annotated is not None:
                self._render_image(annotated)
                self.display_image = annotated
            self.student_answers = answers
            self._show_unscored(validation)
            self.btn_excel.configure(state="normal")

            blank, multi = validation["blank_count"], validation["multiple_count"]
            stats = f"Đã nhận diện đủ 50 câu (Bỏ trống: {blank}, Tô nhiều: {multi})"
            if self.answer_key:
                stats += ". Đã có đáp án chuẩn, hãy bấm 'Chấm điểm'."
                status = "Đọc phiếu thành công. Hãy nhấn 'Chấm điểm' để tính điểm theo đáp án chuẩn."
            else:
                status = "Đọc phiếu thành công (50 câu). Có thể nạp/nhập đáp án chuẩn để chấm điểm hoặc xuất Excel ngay."
            self.lbl_stats.configure(text=stats)
            self._set_status(status)
        except Exception as exc:
            messagebox.showerror("Lỗi nhận diện phiếu", str(exc), parent=self)
            self._set_status(f"Lỗi nhận diện phiếu: {exc}", is_error=True)

    def on_load_key(self):
        path = filedialog.askopenfilename(
            title="Chọn file đáp án chuẩn (JSON)",
            filetypes=[("Tệp JSON", "*.json"), ("Tất cả", "*.*")],
        )
        if not path:
            return

        try:
            new_key = load_answer_key(path)
            self._apply_new_answer_key(new_key, Path(path).name)
        except Exception as exc:
            messagebox.showerror("Lỗi nạp đáp án chuẩn", str(exc), parent=self)
            self._set_status(f"Lỗi nạp đáp án chuẩn: {exc}", is_error=True)

    def on_manual_key(self):
        return ManualAnswerKeyDialog(
            parent=self,
            initial_answers=self.answer_key,
            on_save=lambda answers: self._apply_new_answer_key(answers, "Thủ công (50 câu)"),
        )

    def on_export_key_json(self):
        if not self.answer_key:
            messagebox.showwarning(
                "Chưa có đáp án chuẩn",
                "Chưa có bộ đáp án chuẩn nào được nạp hoặc nhập.\n"
                "Vui lòng nạp file JSON hoặc nhập thủ công trước khi xuất.",
                parent=self,
            )
            return
        answers = self.answer_key
        v_res = validate_answer_key(answers)
        if not v_res["valid"]:
            missing = v_res["missing_indices"]
            missing_str = ", ".join(map(str, missing[:10])) + ("..." if len(missing) > 10 else "")
            messagebox.showwarning(
                "Chưa đủ 50 câu",
                f"Cần đủ 50 đáp án hợp lệ (A, B, C, D) trước khi xuất file JSON!\nCòn thiếu {len(missing)} câu: {missing_str}",
                parent=self,
            )
            return

        save_path = filedialog.asksaveasfilename(
            title="Lưu file đáp án chuẩn JSON",
            initialfile="dap_an_chuan_50_cau.json",
            defaultextension=".json",
            filetypes=[("Tệp JSON", "*.json"), ("Tất cả", "*.*")],
            confirmoverwrite=True,
            parent=self,
        )
        if not save_path:
            return

        try:
            path = Path(save_path)
            data = {"answers": list(answers)}
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            self._set_status(f"Đã xuất đáp án chuẩn ra file: {path.name}")
            messagebox.showinfo(
                "Thành công",
                f"Đã lưu đáp án chuẩn ra file JSON thành công:\n{path}",
                parent=self,
            )
        except Exception as exc:
            messagebox.showerror("Lỗi lưu JSON", f"Không ghi được file JSON: {exc}", parent=self)
            self._set_status(f"Lỗi xuất JSON: {exc}", is_error=True)

    def _apply_new_answer_key(self, key: list[str], source_name: str):
        self.answer_key = list(key)
        self.lbl_key_status.configure(
            text=f"✓ Đáp án: {source_name}",
            bg=PASTEL_CORRECT_BG,
            fg=PASTEL_CORRECT_FG,
        )


        validation = None
        if self.student_answers is not None:
            validation = validate_answers(self.student_answers)
        self._show_unscored(validation)
        if validation is None:
            self._set_status(f"Đã nạp đáp án chuẩn: {source_name}.")
        else:
            self.lbl_stats.configure(text=f"Đã cập nhật đáp án chuẩn ({source_name}). Hãy nhấn 'Chấm điểm' lại.")
            self._set_status(f"Đã cập nhật đáp án ({source_name}). Hãy bấm 'Chấm điểm' để tính lại.")

    def _show_unscored(self, validation: dict | None):
        self.score_result = None
        self.lbl_score.configure(text="Chưa chấm", fg=COLOR_TEXT_MUTED)
        self.btn_score.configure(state="normal" if validation is not None and self.answer_key else "disabled")
        if validation is not None:
            self._update_table_unscored()
            self._update_stat_chips(blank=validation["blank_count"], multi=validation["multiple_count"])

    def on_score(self):
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

            out = export_excel(self.score_result, save_path, answers=self.student_answers)
            mode_name = (
                "kết quả chấm điểm đầy đủ" if self.score_result is not None else "kết quả nhận diện (chưa chấm)"
            )

            self._set_status(f"Xuất Excel thành công: {Path(out).name}")
            messagebox.showinfo("Thành công", f"Đã xuất {mode_name} ra file:\n{out}", parent=self)
        except Exception as exc:
            messagebox.showerror("Lỗi xuất Excel", str(exc), parent=self)
            self._set_status(f"Lỗi xuất Excel: {exc}", is_error=True)


    def _update_table_unscored(self):
        self._clear_table()
        if not self.student_answers:
            return

        for i, ans in enumerate(self.student_answers, start=1):
            tag = UNSCORED_ROW_TAGS.get(ans, "normal")
            status = ROW_LABELS.get(tag, "Đã chọn")
            self.tree.insert("", "end", values=(i, ans, "--", status), tags=(tag,))

    def _update_table_scored(self):
        self._clear_table()
        if not self.score_result:
            return

        for item in self.score_result["details"]:
            result = item["result"]
            values = (item["question"], item["student"], item["correct"], ROW_LABELS.get(result, result))
            tag = result if result in ROW_LABELS else "normal"
            self.tree.insert("", "end", values=values, tags=(tag,))

    def _update_stat_chips(self, correct=None, wrong=None, blank=None, multi=None):
        chips = (self.chip_correct, self.chip_wrong, self.chip_blank, self.chip_multi)
        for chip, value in zip(chips, (correct, wrong, blank, multi)):
            chip.configure(text="--" if value is None else str(value))

    def _clear_table(self):
        self.tree.delete(*self.tree.get_children())

    def _on_canvas_resize(self, event):
        if self.display_image is not None:
            self._render_image(self.display_image)
        else:
            self._draw_placeholder()

    def _render_image(self, bgr_img: np.ndarray):
        if not _HAS_PIL:
            self.canvas.delete("all")
            self.canvas.create_text(
                150,
                50,
                text="Thiếu thư viện Pillow!",
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
    app = SimpleOMRApp()
    app.mainloop()


if __name__ == "__main__":
    launch_simple_app()
