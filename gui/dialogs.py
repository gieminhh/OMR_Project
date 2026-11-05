"""Các cửa sổ Dialog mở rộng cho giao diện OMR Scanner:
- Quản lý đợt thi (SessionManagerDialog)
- Quản lý học sinh & lớp (StudentManagerDialog)
- Quản lý mã đề & bộ đáp án (ExamCodeManagerDialog)
- Chấm bài hàng loạt (BatchProcessorDialog)
- Tạo mẫu phiếu A4 / PDF (SheetGeneratorDialog)
"""

from pathlib import Path
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Callable

import cv2
import numpy as np
from PIL import Image, ImageTk

from modules.advanced_export import export_session_report
from modules.batch_processor import BatchProcessor, BatchItem, read_answer_key_from_image
from modules.bubble_id_detection import detect_sheet_identifiers
from modules.demo_loader import load_demo_data
from modules.errors import OMRError
from modules.session_manager import SessionManager, DEFAULT_GRADE_SCALE
from modules.sheet_generator import generate_sheet, export_sheet_to_pdf, export_sheet_to_image

COLOR_BG = "#F0F4F8"
COLOR_PRIMARY = "#2E75B6"
COLOR_BTN_FG = "#FFFFFF"


def _styled_btn(parent, text, cmd, bg=COLOR_PRIMARY, fg=COLOR_BTN_FG, **kw):
    font = kw.pop("font", ("Segoe UI", 9, "bold"))
    return tk.Button(
        parent,
        text=text,
        command=cmd,
        bg=bg,
        fg=fg,
        font=font,
        relief="flat",
        cursor="hand2",
        padx=8,
        pady=4,
        activebackground="#1a5a9a",
        activeforeground="white",
        **kw,
    )


# ── 1. DIALOG QUẢN LÝ ĐỢT THI ────────────────────────────────────────────────

class SessionManagerDialog(tk.Toplevel):
    def __init__(self, parent, session_manager: SessionManager, current_session: str, on_select: Callable[[str], None]):
        super().__init__(parent)
        self.title("Quản lý Đợt thi")
        self.geometry("760x460")
        self.minsize(600, 380)
        self.configure(bg=COLOR_BG)
        self.grab_set()

        self.mgr = session_manager
        self.current_session = current_session
        self.on_select = on_select

        self._build_ui()
        self._load_sessions()

    def _build_ui(self):
        # Toolbar trên
        top_bar = tk.Frame(self, bg=COLOR_BG, padx=10, pady=8)
        top_bar.pack(fill="x")

        _styled_btn(top_bar, "➕  Tạo đợt thi mới", self._create_new_session, bg="#107C41").pack(side="left", padx=4)
        _styled_btn(top_bar, "✏️  Sửa thông tin", self._edit_session, bg="#1a5a9a").pack(side="left", padx=4)
        _styled_btn(top_bar, "🔄  Chấm lại đợt thi", self._re_grade, bg="#D83B01").pack(side="left", padx=4)
        _styled_btn(top_bar, "✔️  Chọn đợt thi này", self._select_current, bg="#0078D7").pack(side="right", padx=4)

        # Bảng danh sách
        table_frame = tk.Frame(self, bg=COLOR_BG, padx=10, pady=4)
        table_frame.pack(fill="both", expand=True)

        cols = ("code", "name", "subject", "date", "q_count", "classes", "status")
        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings", selectmode="browse")
        self.tree.heading("code", text="Mã đợt")
        self.tree.heading("name", text="Tên đợt thi")
        self.tree.heading("subject", text="Môn thi")
        self.tree.heading("date", text="Ngày thi")
        self.tree.heading("q_count", text="Số câu")
        self.tree.heading("classes", text="Lớp tham gia")
        self.tree.heading("status", text="Trạng thái")

        self.tree.column("code", width=80, anchor="center")
        self.tree.column("name", width=200)
        self.tree.column("subject", width=120)
        self.tree.column("date", width=100, anchor="center")
        self.tree.column("q_count", width=60, anchor="center")
        self.tree.column("classes", width=120)
        self.tree.column("status", width=80, anchor="center")

        sb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

    def _load_sessions(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        sessions = self.mgr.list_sessions()
        for s in sessions:
            tag = "selected" if s["session_code"] == self.current_session else ""
            classes_str = ", ".join(s.get("class_codes", []))
            self.tree.insert("", "end", iid=s["session_code"], values=(
                s["session_code"],
                s["name"],
                s["subject"],
                s["exam_date"],
                s["question_count"],
                classes_str,
                s["status"],
            ), tags=(tag,))

    def _create_new_session(self):
        # Dialog tạo mới đợt thi
        win = tk.Toplevel(self)
        win.title("Thêm đợt thi mới")
        win.geometry("400x320")
        win.configure(bg=COLOR_BG)
        win.grab_set()

        fields = [
            ("Mã đợt thi (giữ số 0, vd: 01, 02):", "code", "01"),
            ("Tên đợt thi:", "name", "Kiểm tra học kỳ 1"),
            ("Môn thi:", "subject", "Toán học"),
            ("Ngày thi (YYYY-MM-DD):", "date", "2026-10-25"),
            ("Danh sách lớp (cách nhau dấu phẩy):", "classes", "12A1, 12A2"),
        ]
        entries = {}
        for idx, (label, key, default) in enumerate(fields):
            tk.Label(win, text=label, bg=COLOR_BG, font=("Segoe UI", 9)).pack(anchor="w", padx=16, pady=(8, 2))
            ent = tk.Entry(win, font=("Segoe UI", 10))
            ent.insert(0, default)
            ent.pack(fill="x", padx=16)
            entries[key] = ent

        def save():
            try:
                code = entries["code"].get().strip()
                name = entries["name"].get().strip()
                subj = entries["subject"].get().strip()
                dt = entries["date"].get().strip()
                cls_list = [c.strip() for c in entries["classes"].get().split(",") if c.strip()]
                self.mgr.create_session(code, name, subj, dt, class_codes=cls_list)
                messagebox.showinfo("Thành công", f"Đã tạo đợt thi '{code}' thành công!", parent=win)
                win.destroy()
                self._load_sessions()
            except Exception as e:
                messagebox.showerror("Lỗi", str(e), parent=win)

        _styled_btn(win, "Lưu đợt thi", save, bg="#107C41").pack(pady=16)

    def _edit_session(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("Chú ý", "Vui lòng chọn đợt thi cần sửa.", parent=self)
            return
        code = str(self.tree.set(sel[0], "code") or sel[0]).strip()
        code = self.mgr.resolve_session_code(code)
        sess = self.mgr.get_session(code)
        if not sess:
            return

        win = tk.Toplevel(self)
        win.title(f"Sửa đợt thi {code}")
        win.geometry("400x300")
        win.configure(bg=COLOR_BG)
        win.grab_set()

        entries = {}
        for label, key, default in [
            ("Tên đợt thi:", "name", sess["name"]),
            ("Môn thi:", "subject", sess["subject"]),
            ("Ngày thi:", "date", sess["exam_date"]),
            ("Danh sách lớp:", "classes", ", ".join(sess.get("class_codes", []))),
        ]:
            tk.Label(win, text=label, bg=COLOR_BG, font=("Segoe UI", 9)).pack(anchor="w", padx=16, pady=(8, 2))
            ent = tk.Entry(win, font=("Segoe UI", 10))
            ent.insert(0, default)
            ent.pack(fill="x", padx=16)
            entries[key] = ent

        def update():
            try:
                cls_list = [c.strip() for c in entries["classes"].get().split(",") if c.strip()]
                self.mgr.update_session(
                    code,
                    name=entries["name"].get().strip(),
                    subject=entries["subject"].get().strip(),
                    exam_date=entries["date"].get().strip(),
                    class_codes=cls_list,
                )
                messagebox.showinfo("Thành công", "Đã cập nhật thông tin đợt thi!", parent=win)
                win.destroy()
                self._load_sessions()
            except Exception as e:
                messagebox.showerror("Lỗi", str(e), parent=win)

        _styled_btn(win, "Cập nhật", update, bg="#1a5a9a").pack(pady=16)

    def _select_current(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("Chú ý", "Vui lòng chọn đợt thi.", parent=self)
            return
        code = str(self.tree.set(sel[0], "code") or sel[0]).strip()
        code = self.mgr.resolve_session_code(code)
        self.on_select(code)
        self.destroy()

    def _re_grade(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("Chú ý", "Vui lòng chọn đợt thi cần chấm lại.", parent=self)
            return
        code = str(self.tree.set(sel[0], "code") or sel[0]).strip()
        code = self.mgr.resolve_session_code(code)
        if messagebox.askyesno("Xác nhận", f"Bạn có chắc muốn chấm lại toàn bộ các bài thi trong đợt '{code}'?", parent=self):
            try:
                count = self.mgr.re_grade_session(code)
                messagebox.showinfo("Hoàn tất", f"Đã chấm lại {count} bài thi trong đợt thi '{code}'.", parent=self)
            except Exception as e:
                messagebox.showerror("Lỗi", str(e), parent=self)


# ── 2. DIALOG QUẢN LÝ HỌC SINH & LỚP ─────────────────────────────────────────

class StudentManagerDialog(tk.Toplevel):
    def __init__(self, parent, session_manager: SessionManager):
        super().__init__(parent)
        self.title("Quản lý Học sinh và Lớp học")
        self.geometry("780x480")
        self.minsize(620, 380)
        self.configure(bg=COLOR_BG)
        self.grab_set()

        self.mgr = session_manager
        self._build_ui()
        self._load_students()

    def _build_ui(self):
        top_bar = tk.Frame(self, bg=COLOR_BG, padx=10, pady=8)
        top_bar.pack(fill="x")

        _styled_btn(top_bar, "📥  Nhập từ Excel", self._import_excel, bg="#107C41").pack(side="left", padx=4)
        _styled_btn(top_bar, "📥  Nhập từ CSV", self._import_csv, bg="#1a5a9a").pack(side="left", padx=4)
        _styled_btn(top_bar, "➕  Thêm học sinh", self._add_single_student, bg="#7B3F9E").pack(side="left", padx=4)

        # Ô tìm kiếm
        search_frame = tk.Frame(top_bar, bg=COLOR_BG)
        search_frame.pack(side="right", padx=4)
        tk.Label(search_frame, text="Tìm kiếm:", bg=COLOR_BG).pack(side="left", padx=2)
        self.search_ent = tk.Entry(search_frame, width=16)
        self.search_ent.pack(side="left", padx=2)
        self.search_ent.bind("<Return>", lambda e: self._load_students())
        _styled_btn(search_frame, "Tìm", self._load_students, bg="#555555").pack(side="left", padx=2)

        # Bảng
        table_frame = tk.Frame(self, bg=COLOR_BG, padx=10, pady=4)
        table_frame.pack(fill="both", expand=True)

        cols = ("code", "sbd", "name", "class")
        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings", selectmode="browse")
        self.tree.heading("code", text="Mã HS")
        self.tree.heading("sbd", text="Số báo danh (SBD)")
        self.tree.heading("name", text="Họ và tên")
        self.tree.heading("class", text="Lớp")

        self.tree.column("code", width=120, anchor="center")
        self.tree.column("sbd", width=140, anchor="center")
        self.tree.column("name", width=280)
        self.tree.column("class", width=120, anchor="center")

        sb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

    def _load_students(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        query = self.search_ent.get().strip() if hasattr(self, "search_ent") else None
        students = self.mgr.list_students(search=query if query else None)
        for s in students:
            self.tree.insert("", "end", values=(s["student_code"], s["sbd"], s["full_name"], s["class_code"]))

    def _import_excel(self):
        f = filedialog.askopenfilename(parent=self, filetypes=[("Excel Files", "*.xlsx")])
        if f:
            try:
                count = self.mgr.import_students_from_excel(f)
                messagebox.showinfo("Thành công", f"Đã nhập {count} học sinh từ file Excel!", parent=self)
                self._load_students()
            except Exception as e:
                messagebox.showerror("Lỗi nhập Excel", str(e), parent=self)

    def _import_csv(self):
        f = filedialog.askopenfilename(parent=self, filetypes=[("CSV Files", "*.csv")])
        if f:
            try:
                count = self.mgr.import_students_from_csv(f)
                messagebox.showinfo("Thành công", f"Đã nhập {count} học sinh từ file CSV!", parent=self)
                self._load_students()
            except Exception as e:
                messagebox.showerror("Lỗi nhập CSV", str(e), parent=self)

    def _add_single_student(self):
        win = tk.Toplevel(self)
        win.title("Thêm học sinh")
        win.geometry("360x280")
        win.configure(bg=COLOR_BG)
        win.grab_set()

        entries = {}
        for label, key, default in [
            ("Mã học sinh:", "code", "HS001"),
            ("Số báo danh (SBD):", "sbd", "001234"),
            ("Họ và tên:", "name", "Nguyễn Văn A"),
            ("Lớp:", "class", "12A1"),
        ]:
            tk.Label(win, text=label, bg=COLOR_BG, font=("Segoe UI", 9)).pack(anchor="w", padx=16, pady=(6, 2))
            ent = tk.Entry(win, font=("Segoe UI", 10))
            ent.insert(0, default)
            ent.pack(fill="x", padx=16)
            entries[key] = ent

        def save():
            try:
                self.mgr.add_student(
                    entries["code"].get().strip(),
                    entries["sbd"].get().strip(),
                    entries["name"].get().strip(),
                    entries["class"].get().strip(),
                )
                messagebox.showinfo("Thành công", "Đã thêm học sinh thành công!", parent=win)
                win.destroy()
                self._load_students()
            except Exception as e:
                messagebox.showerror("Lỗi", str(e), parent=win)

        _styled_btn(win, "Lưu", save, bg="#107C41").pack(pady=14)


# ── 3. DIALOG QUẢN LÝ MÃ ĐỀ & ĐÁP ÁN ─────────────────────────────────────────

class ReviewScannedKeysDialog(tk.Toplevel):
    """Cửa sổ xem trước, chỉnh sửa và xác nhận đáp án quét từ ảnh trước khi lưu."""
    def __init__(self, parent, session_manager: SessionManager, session_code: str, scanned_items: list[dict], on_saved_callback: Callable | None = None):
        super().__init__(parent)
        self.title("Xác nhận bộ đáp án nhận diện từ ảnh")
        self.geometry("860x520")
        self.minsize(720, 400)
        self.configure(bg=COLOR_BG)
        self.grab_set()

        self.mgr = session_manager
        self.session_code = session_code
        self.scanned_items = scanned_items
        self.on_saved_callback = on_saved_callback

        self._build_ui()

    def _build_ui(self):
        header_frame = tk.Frame(self, bg=COLOR_BG, padx=12, pady=10)
        header_frame.pack(fill="x")

        lbl_desc = tk.Label(
            header_frame,
            text=f"Kiểm tra và xác nhận các bộ đáp án quét được cho đợt thi: {self.session_code}\n"
                 f"(Mỗi ảnh đại diện cho 1 mã đề chuẩn, KHÔNG tạo bài thi học sinh).",
            font=("Segoe UI", 10, "bold"),
            bg=COLOR_BG,
            justify="left",
        )
        lbl_desc.pack(anchor="w")

        # Bảng danh sách ảnh đáp án
        table_frame = tk.Frame(self, bg=COLOR_BG, padx=12, pady=4)
        table_frame.pack(fill="both", expand=True)

        cols = ("file", "code", "sess_detected", "valid_count", "warning", "preview")
        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings", selectmode="browse")
        self.tree.heading("file", text="Tên file ảnh")
        self.tree.heading("code", text="Mã đề")
        self.tree.heading("sess_detected", text="Đợt trên phiếu")
        self.tree.heading("valid_count", text="Số câu hợp lệ")
        self.tree.heading("warning", text="Cảnh báo")
        self.tree.heading("preview", text="Xem trước đáp án")

        self.tree.column("file", width=140)
        self.tree.column("code", width=80, anchor="center")
        self.tree.column("sess_detected", width=90, anchor="center")
        self.tree.column("valid_count", width=90, anchor="center")
        self.tree.column("warning", width=180)
        self.tree.column("preview", width=240)

        sb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        self._populate_table()

        # Vùng chỉnh sửa chi tiết cho dòng đang chọn
        edit_frame = tk.LabelFrame(self, text="Chỉnh sửa mã đề & chuỗi đáp án đã chọn", bg=COLOR_BG, padx=10, pady=8)
        edit_frame.pack(fill="x", padx=12, pady=6)

        sub_f = tk.Frame(edit_frame, bg=COLOR_BG)
        sub_f.pack(fill="x", pady=2)
        tk.Label(sub_f, text="Mã đề:", bg=COLOR_BG, font=("Segoe UI", 9, "bold")).pack(side="left")
        self.ent_edit_code = tk.Entry(sub_f, width=10, font=("Segoe UI", 9))
        self.ent_edit_code.pack(side="left", padx=(6, 16))

        tk.Label(sub_f, text="Chuỗi 50 đáp án:", bg=COLOR_BG, font=("Segoe UI", 9, "bold")).pack(side="left")
        self.ent_edit_ans = tk.Entry(sub_f, font=("Segoe UI", 9))
        self.ent_edit_ans.pack(side="left", fill="x", expand=True, padx=6)

        _styled_btn(sub_f, "Cập nhật", self._apply_edit, bg="#1a5a9a").pack(side="right")

        self.tree.bind("<<TreeviewSelect>>", self._on_select_item)

        # Thanh nút bấm dưới cùng
        bottom_bar = tk.Frame(self, bg=COLOR_BG, padx=12, pady=10)
        bottom_bar.pack(fill="x")

        _styled_btn(bottom_bar, "💾  LƯU TẤT CẢ VÀO ĐỢT THI", self._save_all, bg="#107C41", font=("Segoe UI", 10, "bold")).pack(side="right", padx=6)
        _styled_btn(bottom_bar, "Đóng", self.destroy, bg="#666666").pack(side="right", padx=6)

    def _populate_table(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        for idx, item in enumerate(self.scanned_items):
            ans = item.get("answers", [])
            valid_c = sum(1 for a in ans if a in ("A", "B", "C", "D"))
            warns = "; ".join(item.get("review_reasons", [])) or (item.get("error_message") or "Hợp lệ")
            preview = "".join(ans[:20]) + ("..." if len(ans) > 20 else "")
            self.tree.insert("", "end", iid=str(idx), values=(
                item.get("filename", ""),
                item.get("exam_code") or "—",
                item.get("session_code") or "—",
                f"{valid_c}/50",
                warns,
                preview,
            ))

    def _on_select_item(self, event=None):
        sel = self.tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        item = self.scanned_items[idx]
        self.ent_edit_code.delete(0, "end")
        self.ent_edit_code.insert(0, item.get("exam_code") or "")
        self.ent_edit_ans.delete(0, "end")
        self.ent_edit_ans.insert(0, "".join(item.get("answers", [])))

    def _apply_edit(self):
        sel = self.tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        new_code = self.ent_edit_code.get().strip()
        new_ans_str = self.ent_edit_ans.get().strip().upper().replace(" ", "").replace(",", "")
        if len(new_ans_str) != 50:
            messagebox.showwarning("Chú ý", f"Chuỗi đáp án phải đủ 50 câu (hiện có {len(new_ans_str)} ký tự).", parent=self)
            return

        self.scanned_items[idx]["exam_code"] = new_code
        self.scanned_items[idx]["answers"] = list(new_ans_str)
        self.scanned_items[idx]["blank_questions"] = [i + 1 for i, a in enumerate(new_ans_str) if a not in ("A", "B", "C", "D")]
        self.scanned_items[idx]["review_reasons"] = []
        self._populate_table()
        messagebox.showinfo("Đã cập nhật", f"Đã cập nhật thông tin mã đề {new_code}!", parent=self)

    def _save_all(self):
        saved = 0
        overwritten = 0
        for item in self.scanned_items:
            ecode = item.get("exam_code")
            ans = item.get("answers", [])
            if not ecode or len(ans) != 50 or any(a not in ("A", "B", "C", "D") for a in ans):
                continue

            existing = self.mgr.get_answer_key(self.session_code, ecode)
            if existing:
                overwritten += 1
            self.mgr.set_answer_key(self.session_code, ecode, ans, source="omr_scan")
            saved += 1

        messagebox.showinfo(
            "Lưu thành công",
            f"Đã lưu thành công {saved} bộ đáp án chuẩn vào đợt thi '{self.session_code}'!\n"
            f"(Ghi đè {overwritten} mã đề đã có trước đó).",
            parent=self,
        )
        if self.on_saved_callback:
            self.on_saved_callback()
        self.destroy()


class ExamCodeManagerDialog(tk.Toplevel):
    def __init__(self, parent, session_manager: SessionManager, session_code: str, on_changed_callback: Callable | None = None):
        super().__init__(parent)
        self.title("Quản lý Mã đề & Bộ đáp án chuẩn")
        self.geometry("820x520")
        self.minsize(680, 400)
        self.configure(bg=COLOR_BG)
        self.grab_set()

        self.mgr = session_manager
        self.session_code = self.mgr.resolve_session_code(session_code)
        self.on_changed_callback = on_changed_callback
        self._build_ui()
        self._load_codes()

    def _build_ui(self):
        # Thanh chọn đợt thi và công cụ
        top_bar = tk.Frame(self, bg=COLOR_BG, padx=10, pady=8)
        top_bar.pack(fill="x")

        tk.Label(top_bar, text="Đợt thi:", bg=COLOR_BG, font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 4))
        sessions = self.mgr.list_sessions()
        sess_codes = [s["session_code"] for s in sessions] or [self.session_code]
        self.cbo_session = ttk.Combobox(top_bar, values=sess_codes, width=8, state="readonly")
        if self.session_code in sess_codes:
            self.cbo_session.set(self.session_code)
        elif sess_codes:
            self.cbo_session.set(sess_codes[0])
            self.session_code = sess_codes[0]
        self.cbo_session.pack(side="left", padx=(0, 10))
        self.cbo_session.bind("<<ComboboxSelected>>", self._on_session_changed)

        _styled_btn(top_bar, "➕  Thêm mã đề", self._add_exam_code, bg="#107C41").pack(side="left", padx=3)
        _styled_btn(top_bar, "📥  Excel", self._import_excel, bg="#1a5a9a").pack(side="left", padx=3)
        _styled_btn(top_bar, "📥  CSV", self._import_csv, bg="#7B3F9E").pack(side="left", padx=3)
        _styled_btn(top_bar, "📥  JSON", self._import_json, bg="#D83B01").pack(side="left", padx=3)
        _styled_btn(top_bar, "📷  Quét nhiều ảnh", self._import_from_sheet_images, bg="#B83B01").pack(side="left", padx=3)
        _styled_btn(top_bar, "🗑️  Xóa mã đề", self._delete_selected, bg="#666666").pack(side="left", padx=3)
        _styled_btn(top_bar, "🎯 Nạp Demo", self._load_demo, bg="#0078D7").pack(side="right", padx=3)

        # Bảng danh sách mã đề
        table_frame = tk.Frame(self, bg=COLOR_BG, padx=10, pady=4)
        table_frame.pack(fill="both", expand=True)

        cols = ("code", "source", "answers_preview", "created_at")
        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings", selectmode="browse")
        self.tree.heading("code", text="Mã đề")
        self.tree.heading("source", text="Nguồn")
        self.tree.heading("answers_preview", text="Xem trước đáp án (15 câu đầu)")
        self.tree.heading("created_at", text="Ngày tạo")

        self.tree.column("code", width=90, anchor="center")
        self.tree.column("source", width=100, anchor="center")
        self.tree.column("answers_preview", width=380)
        self.tree.column("created_at", width=140, anchor="center")

        sb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        # Thanh trạng thái dưới cùng
        self.lbl_status = tk.Label(self, text="", bg=COLOR_BG, font=("Segoe UI", 9, "bold"), anchor="w", padx=12, pady=6)
        self.lbl_status.pack(fill="x")

    def _on_session_changed(self, event=None):
        raw = self.cbo_session.get().strip()
        self.session_code = self.mgr.resolve_session_code(raw)
        self._load_codes()
        if self.on_changed_callback:
            self.on_changed_callback()

    def _load_codes(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        codes = self.mgr.list_exam_codes(self.session_code)
        for c in codes:
            ans = c.get("answers", [])
            preview = "".join(f"{idx+1}:{a} " for idx, a in enumerate(ans[:15])) + ("..." if len(ans) > 15 else "")
            self.tree.insert("", "end", iid=str(c["exam_code"]), values=(str(c["exam_code"]), c["source"], preview, c["created_at"][:19]))

        code_names = sorted([str(c["exam_code"]) for c in codes])
        std_codes = {"101", "102", "103", "104"}
        missing = std_codes - set(code_names)
        status_txt = f"Đợt thi '{self.session_code}': Đã có {len(codes)} mã đề ({', '.join(code_names) or 'Chưa có'})."
        if not missing:
            status_txt += " ✓ Đã đủ 4 mã đề chuẩn (101, 102, 103, 104)!"
            self.lbl_status.configure(text=status_txt, fg="#107C41")
        elif codes:
            status_txt += f" ⚠️ Còn thiếu: {', '.join(sorted(missing))}"
            self.lbl_status.configure(text=status_txt, fg="#C05000")
        else:
            status_txt += " ⚠️ Chưa có bộ đáp án chuẩn nào!"
            self.lbl_status.configure(text=status_txt, fg="#C00000")

    def _notify_change(self):
        self._load_codes()
        if self.on_changed_callback:
            try:
                self.on_changed_callback()
            except Exception:
                pass

    def _add_exam_code(self):
        win = tk.Toplevel(self)
        win.title(f"Thêm / Chỉnh sửa mã đề — Đợt {self.session_code}")
        win.geometry("540x360")
        win.minsize(480, 300)
        win.configure(bg=COLOR_BG)
        win.grab_set()

        tk.Label(win, text="Mã đề thi (vd: 101, 102, 103, 104):", bg=COLOR_BG, font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=16, pady=(12, 2))
        ent_code = tk.Entry(win, font=("Segoe UI", 10))
        ent_code.insert(0, "101")
        ent_code.pack(fill="x", padx=16)

        tk.Label(win, text="Chuỗi 50 đáp án (A/B/C/D, không dấu cách):", bg=COLOR_BG, font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=16, pady=(10, 2))
        txt_ans = tk.Text(win, height=5, font=("Segoe UI", 10))
        txt_ans.pack(fill="x", padx=16)
        txt_ans.insert("1.0", "ABCD" * 12 + "AB")

        lbl_count = tk.Label(win, text="Độ dài hiện tại: 50/50 câu", bg=COLOR_BG, font=("Segoe UI", 9, "italic"))
        lbl_count.pack(anchor="w", padx=16, pady=4)

        def on_txt_change(e=None):
            raw = txt_ans.get("1.0", "end").strip().upper().replace(" ", "").replace(",", "").replace("\n", "")
            lbl_count.configure(text=f"Độ dài hiện tại: {len(raw)}/50 câu")

        txt_ans.bind("<KeyRelease>", on_txt_change)

        def save():
            try:
                ecode = ent_code.get().strip()
                if not ecode:
                    raise OMRError("Mã đề không được để trống.")
                raw = txt_ans.get("1.0", "end").strip().upper().replace(" ", "").replace(",", "").replace("\n", "")
                if len(raw) != 50:
                    raise OMRError(f"Đáp án phải có đúng 50 câu; hiện có {len(raw)} câu.")
                ans_list = list(raw)

                # Kiểm tra nếu mã đã tồn tại, hỏi trước khi ghi đè
                existing = self.mgr.get_answer_key(self.session_code, ecode)
                if existing:
                    confirm = messagebox.askyesno(
                        "Xác nhận ghi đè",
                        f"Mã đề '{ecode}' đã có đáp án chuẩn trong đợt '{self.session_code}'.\n"
                        f"Bạn có muốn ghi đè bộ đáp án mới không?",
                        parent=win,
                    )
                    if not confirm:
                        return

                self.mgr.set_answer_key(self.session_code, ecode, ans_list, source="manual")
                messagebox.showinfo("Thành công", f"Đã lưu thành công bộ đáp án cho mã đề {ecode}!", parent=win)
                win.destroy()
                self._notify_change()
            except Exception as e:
                messagebox.showerror("Lỗi", str(e), parent=win)

        _styled_btn(win, "💾  Lưu bộ đáp án", save, bg="#107C41", font=("Segoe UI", 10, "bold")).pack(pady=12)

    def _import_excel(self):
        f = filedialog.askopenfilename(parent=self, filetypes=[("Excel Files", "*.xlsx")])
        if f:
            try:
                cnt = self.mgr.import_answer_keys_from_excel(self.session_code, f)
                messagebox.showinfo("Thành công", f"Đã nhập {cnt} bộ đáp án từ file Excel!", parent=self)
                self._notify_change()
            except Exception as e:
                messagebox.showerror("Lỗi nhập Excel", str(e), parent=self)

    def _import_csv(self):
        f = filedialog.askopenfilename(parent=self, filetypes=[("CSV Files", "*.csv")])
        if f:
            try:
                cnt = self.mgr.import_answer_keys_from_csv(self.session_code, f)
                messagebox.showinfo("Thành công", f"Đã nhập {cnt} bộ đáp án từ file CSV!", parent=self)
                self._notify_change()
            except Exception as e:
                messagebox.showerror("Lỗi nhập CSV", str(e), parent=self)

    def _import_json(self):
        f = filedialog.askopenfilename(parent=self, filetypes=[("JSON Files", "*.json")])
        if f:
            try:
                cnt = self.mgr.import_answer_keys_from_json(f, default_session_code=self.session_code)
                messagebox.showinfo("Thành công", f"Đã nhập {cnt} bộ đáp án từ file JSON!", parent=self)
                self._notify_change()
            except Exception as e:
                messagebox.showerror("Lỗi nhập JSON", str(e), parent=self)

    def _import_from_sheet_images(self):
        files = filedialog.askopenfilenames(
            parent=self,
            title="Chọn các ảnh phiếu đáp án chuẩn",
            filetypes=[("Image Files", "*.png;*.jpg;*.jpeg;*.bmp")],
        )
        if not files:
            return

        # Quét từng ảnh độc lập bằng read_answer_key_from_image (KHÔNG tạo kết quả học sinh)
        scanned_items = []
        for f in files:
            res = read_answer_key_from_image(f)
            scanned_items.append(res)

        # Mở dialog xem trước, chỉnh sửa và xác nhận
        ReviewScannedKeysDialog(
            parent=self,
            session_manager=self.mgr,
            session_code=self.session_code,
            scanned_items=scanned_items,
            on_saved_callback=self._notify_change,
        )

    def _delete_selected(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("Chú ý", "Vui lòng chọn một mã đề để xóa.", parent=self)
            return
        ecode = str(self.tree.set(sel[0], "code") or sel[0]).strip()
        confirm = messagebox.askyesno(
            "Xác nhận xóa",
            f"Bạn có chắc muốn xóa mã đề '{ecode}' khỏi đợt thi '{self.session_code}'?",
            parent=self,
        )
        if confirm:
            try:
                self.mgr.delete_exam_code(self.session_code, ecode)
                self._notify_change()
                messagebox.showinfo("Đã xóa", f"Đã xóa mã đề {ecode}!", parent=self)
            except Exception as e:
                messagebox.showerror("Lỗi", str(e), parent=self)

    def _load_demo(self):
        confirm = messagebox.askyesno(
            "Nạp dữ liệu Demo",
            "Bạn có muốn nạp dữ liệu mẫu (2 đợt thi 01-02, 4 lớp học, 43 học sinh và 8 bộ đáp án chuẩn 101-104)?\n\n"
            "Dữ liệu hiện có của bạn sẽ được bảo toàn nguyên vẹn.",
            parent=self,
        )
        if confirm:
            stats = load_demo_data(self.mgr)
            messagebox.showinfo(
                "Nạp Demo Hoàn tất",
                f"Đã nạp thành công:\n"
                f"- Đợt thi mới: {stats['sessions']}\n"
                f"- Lớp học mới: {stats['classes']}\n"
                f"- Học sinh: {stats['students']}\n"
                f"- Bộ đáp án chuẩn: {stats['exam_codes']}",
                parent=self,
            )
            self._notify_change()


# ── 4. DIALOG CHẤM BÀI HÀNG LOẠT (BATCH PROCESSING) ──────────────────────────

class BatchProcessorDialog(tk.Toplevel):
    def __init__(self, parent, session_manager: SessionManager, session_code: str):
        super().__init__(parent)
        self.mgr = session_manager
        self.session_code = self.mgr.resolve_session_code(session_code)
        self.title(f"Chấm bài thi hàng loạt — Đợt thi: {self.session_code}")
        self.geometry("960x560")
        self.minsize(780, 440)
        self.configure(bg=COLOR_BG)
        self.grab_set()

        self.processor = BatchProcessor(self.mgr, self.session_code)
        self._is_processing = False

        self._build_ui()

    def _build_ui(self):
        top_bar = tk.Frame(self, bg=COLOR_BG, padx=10, pady=8)
        top_bar.pack(fill="x")

        _styled_btn(top_bar, "➕  Chọn ảnh...", self._add_files, bg="#1a5a9a").pack(side="left", padx=4)
        _styled_btn(top_bar, "📁  Chọn cả thư mục...", self._add_folder, bg="#7B3F9E").pack(side="left", padx=4)
        _styled_btn(top_bar, "❌  Bỏ chọn ảnh", self._remove_selected, bg="#555555").pack(side="left", padx=4)
        _styled_btn(top_bar, "🗑️  Xóa toàn bộ", self._clear_all, bg="#777777").pack(side="left", padx=4)

        self.btn_run = _styled_btn(top_bar, "▶️  BẮT ĐẦU CHẤM", self._start_batch, bg="#107C41", font=("Segoe UI", 10, "bold"))
        self.btn_run.pack(side="right", padx=4)

        _styled_btn(top_bar, "🔁  Chấm lại bài lỗi", self._retry_failed, bg="#D83B01").pack(side="right", padx=4)
        _styled_btn(top_bar, "🎯 Nạp Demo", self._load_demo, bg="#1a5a9a").pack(side="right", padx=4)
        _styled_btn(top_bar, "📊  Xuất Excel 6 sheet", self._export_excel, bg="#0078D7").pack(side="right", padx=4)

        # Thanh tiến trình
        prog_frame = tk.Frame(self, bg=COLOR_BG, padx=10, pady=4)
        prog_frame.pack(fill="x")
        self.lbl_progress = tk.Label(prog_frame, text="Hàng đợi: 0 ảnh", bg=COLOR_BG, font=("Segoe UI", 9, "bold"))
        self.lbl_progress.pack(side="left")
        self.progress_bar = ttk.Progressbar(prog_frame, orient="horizontal", mode="determinate")
        self.progress_bar.pack(side="right", fill="x", expand=True, padx=(12, 0))

        # Bảng danh sách bài thi
        table_frame = tk.Frame(self, bg=COLOR_BG, padx=10, pady=4)
        table_frame.pack(fill="both", expand=True)

        cols = ("file", "status", "sbd", "name", "class", "code", "score", "correct", "note")
        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings", selectmode="browse")
        self.tree.heading("file", text="Tên file ảnh")
        self.tree.heading("status", text="Trạng thái")
        self.tree.heading("sbd", text="SBD")
        self.tree.heading("name", text="Họ và tên")
        self.tree.heading("class", text="Lớp")
        self.tree.heading("code", text="Mã đề")
        self.tree.heading("score", text="Điểm")
        self.tree.heading("correct", text="Số câu đúng")
        self.tree.heading("note", text="Ghi chú / Cần kiểm tra")

        self.tree.column("file", width=160)
        self.tree.column("status", width=100, anchor="center")
        self.tree.column("sbd", width=80, anchor="center")
        self.tree.column("name", width=140)
        self.tree.column("class", width=70, anchor="center")
        self.tree.column("code", width=70, anchor="center")
        self.tree.column("score", width=60, anchor="center")
        self.tree.column("correct", width=80, anchor="center")
        self.tree.column("note", width=180)

        sb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        self.tree.bind("<Double-1>", self._on_double_click_item)

    def _refresh_table(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        for idx, item in enumerate(self.processor.items):
            status_text = {
                "QUEUED": "⏳ Chờ xử lý",
                "PROCESSING": "⚙️ Đang xử lý",
                "SUCCESS": "✓ Thành công",
                "NEEDS_REVIEW": "⚠️ Cần kiểm tra",
                "FAILED": "✗ Thất bại",
            }.get(item.status, item.status)

            notes = "; ".join(item.review_reasons) if item.review_reasons else (item.error_message or "")
            self.tree.insert("", "end", iid=str(idx), values=(
                item.image_path.name,
                status_text,
                item.sbd or "—",
                item.student_name or "—",
                item.class_code or "—",
                item.exam_code or "—",
                item.score if item.score is not None else "—",
                f"{item.correct_count}/50" if item.correct_count is not None else "—",
                notes,
            ))
        self.lbl_progress.configure(text=f"Hàng đợi: {len(self.processor.items)} ảnh")

    def _add_files(self):
        files = filedialog.askopenfilenames(parent=self, filetypes=[("Image Files", "*.png;*.jpg;*.jpeg;*.bmp")])
        if files:
            added = self.processor.add_files(files)
            self._refresh_table()

    def _add_folder(self):
        d = filedialog.askdirectory(parent=self)
        if d:
            added = self.processor.add_directory(d)
            self._refresh_table()

    def _remove_selected(self):
        sel = self.tree.selection()
        if sel:
            idx = int(sel[0])
            self.processor.remove_item(idx)
            self._refresh_table()

    def _clear_all(self):
        if not self._is_processing:
            self.processor.clear()
            self._refresh_table()

    def _start_batch(self):
        if not self.processor.items:
            messagebox.showwarning("Chú ý", "Chưa có ảnh nào trong hàng đợi.", parent=self)
            return
        if self._is_processing:
            return

        # Xác định chính xác mã đợt thi và kiểm tra đáp án chuẩn
        self.session_code = self.mgr.resolve_session_code(self.session_code)
        codes = self.mgr.list_exam_codes(self.session_code)
        code_names = sorted([str(c["exam_code"]) for c in codes])

        if not codes:
            proceed = messagebox.askyesno(
                "Cảnh báo thiếu đáp án chuẩn",
                f"Đợt thi '{self.session_code}' hiện CHƯA CÓ đáp án chuẩn cho bất kỳ mã đề nào!\n\n"
                f"Nếu tiếp tục, hệ thống sẽ đọc SBD và đáp án tô trên phiếu nhưng KHÔNG THỂ CHẤM ĐIỂM "
                f"(các bài thi sẽ ở trạng thái 'Cần kiểm tra' và chưa có điểm chính thức).\n\n"
                f"Bạn có muốn tiếp tục chấm không?",
                parent=self,
            )
            if not proceed:
                return
        else:
            std_codes = {"101", "102", "103", "104"}
            missing_std = sorted(list(std_codes - set(code_names)))
            # Nếu đã có đủ 4 mã đề chuẩn (hoặc nhiều hơn), không cần hiện cảnh báo thiếu
            # Chỉ cảnh báo nếu còn thiếu mã trong bộ 101-104 và nhắc người dùng rõ ràng
            if missing_std and len(code_names) < 4:
                proceed = messagebox.askyesno(
                    "Xác nhận đáp án chuẩn",
                    f"Đợt thi '{self.session_code}' hiện đã có {len(code_names)} mã đề: {', '.join(code_names)}.\n"
                    f"Các mã đề chuẩn còn thiếu: {', '.join(missing_std)}.\n\n"
                    f"Nếu bài thi thuộc các mã chưa có đáp án, bài đó sẽ ở trạng thái 'Cần kiểm tra'.\n"
                    f"Bạn có muốn tiếp tục bắt đầu chấm không?",
                    parent=self,
                )
                if not proceed:
                    return

        self._is_processing = True
        self.btn_run.configure(state="disabled", text="ĐANG XỬ LÝ...")
        self.progress_bar["maximum"] = len(self.processor.items)
        self.progress_bar["value"] = 0

        def on_prog(current, total, item):
            self.after(0, lambda: self._update_progress_ui(current, total, item))

        def on_done(items):
            self.after(0, self._on_batch_complete)

        self.processor.process_all_async(on_progress=on_prog, on_complete=on_done)

    def _retry_failed(self):
        if self._is_processing:
            return
        count = self.processor.reset_for_retry(include_needs_review=True)
        if count == 0:
            messagebox.showinfo("Thông báo", "Không có bài nào bị lỗi hoặc cần kiểm tra.", parent=self)
            return
        self._refresh_table()
        self._start_batch()

    def _load_demo(self):
        confirm = messagebox.askyesno(
            "Nạp dữ liệu Demo",
            "Bạn có muốn nạp dữ liệu mẫu (2 đợt thi 01-02, 4 lớp học, 43 học sinh và 8 bộ đáp án chuẩn)?\n\n"
            "Dữ liệu của bạn sẽ được bảo toàn nguyên vẹn.",
            parent=self,
        )
        if confirm:
            stats = load_demo_data(self.mgr)
            messagebox.showinfo(
                "Nạp Demo Hoàn tất",
                f"Đã nạp thành công:\n"
                f"- Đợt thi: {stats['sessions']}\n"
                f"- Lớp học: {stats['classes']}\n"
                f"- Học sinh: {stats['students']}\n"
                f"- Bộ đáp án chuẩn: {stats['exam_codes']}",
                parent=self,
            )
            self._refresh_table()

    def _update_progress_ui(self, current, total, item):
        self.progress_bar["value"] = current
        self.lbl_progress.configure(text=f"Đang xử lý: {current}/{total} ảnh ({item.image_path.name})")
        self._refresh_table()

    def _on_batch_complete(self):
        self._is_processing = False
        self.btn_run.configure(state="normal", text="▶️  BẮT ĐẦU CHẤM")
        self.lbl_progress.configure(text=f"Hoàn thành toàn bộ lô: {len(self.processor.items)} bài!")
        self._refresh_table()
        messagebox.showinfo("Hoàn tất", f"Đã xử lý xong {len(self.processor.items)} bài thi!", parent=self)

    def _on_double_click_item(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        item = self.processor.items[idx]

        # Mở dialog xem chi tiết ảnh và kết quả
        win = tk.Toplevel(self)
        win.title(f"Chi tiết bài thi: {item.image_path.name}")
        win.geometry("800x600")
        win.configure(bg=COLOR_BG)

        # Hiển thị ảnh annotated nếu có
        img_p = item.annotated_image_path or item.image_path
        if img_p.is_file():
            bgr = cv2.imread(str(img_p))
            if bgr is not None:
                rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                pil_img = Image.fromarray(rgb)
                pil_img.thumbnail((450, 560), Image.LANCZOS)
                photo = ImageTk.PhotoImage(pil_img)
                lbl_img = tk.Label(win, image=photo, bg="black")
                lbl_img.image = photo
                lbl_img.pack(side="left", padx=10, pady=10)

        # Chi tiết bên phải
        info_frame = tk.Frame(win, bg=COLOR_BG, padx=12, pady=12)
        info_frame.pack(side="right", fill="both", expand=True)

        tk.Label(info_frame, text=f"File: {item.image_path.name}", bg=COLOR_BG, font=("Segoe UI", 11, "bold")).pack(anchor="w")
        tk.Label(info_frame, text=f"Trạng thái: {item.status}", bg=COLOR_BG, font=("Segoe UI", 10, "bold"), fg="red" if item.status != "SUCCESS" else "green").pack(anchor="w")
        tk.Label(info_frame, text=f"Số báo danh: {item.sbd or 'Không rõ'}", bg=COLOR_BG).pack(anchor="w")
        tk.Label(info_frame, text=f"Học sinh: {item.student_name or 'Chưa xác định'}", bg=COLOR_BG).pack(anchor="w")
        tk.Label(info_frame, text=f"Lớp: {item.class_code or 'Chưa xác định'}", bg=COLOR_BG).pack(anchor="w")
        tk.Label(info_frame, text=f"Mã đề: {item.exam_code or 'Không rõ'}", bg=COLOR_BG).pack(anchor="w")
        tk.Label(info_frame, text=f"Điểm số: {item.score if item.score is not None else '—'}", bg=COLOR_BG, font=("Segoe UI", 12, "bold"), fg="#C00000").pack(anchor="w", pady=6)

        if item.review_reasons:
            tk.Label(info_frame, text="Lý do cần kiểm tra:", bg=COLOR_BG, font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(8, 2))
            for r in item.review_reasons:
                tk.Label(info_frame, text=f"• {r}", bg=COLOR_BG, fg="red").pack(anchor="w")

    def _export_excel(self):
        f = filedialog.asksaveasfilename(parent=self, defaultextension=".xlsx", filetypes=[("Excel Workbook", "*.xlsx")])
        if f:
            try:
                export_session_report(self.mgr, self.session_code, f)
                messagebox.showinfo("Thành công", f"Đã xuất báo cáo đợt thi ra file:\n{f}", parent=self)
            except Exception as e:
                messagebox.showerror("Lỗi xuất Excel", str(e), parent=self)


# ── 5. DIALOG TẠO MẪU PHIẾU A4 / PDF ──────────────────────────────────────────

class SheetGeneratorDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Tạo mẫu phiếu trắc nghiệm chuẩn in ấn A4 / PDF")
        self.geometry("780x560")
        self.minsize(640, 420)
        self.configure(bg=COLOR_BG)
        self.grab_set()

        self._generated_sheet: np.ndarray | None = None
        self._preview_photo = None

        self._build_ui()
        self._generate_preview()

    def _build_ui(self):
        # Panel trái: cấu hình
        left = tk.Frame(self, bg=COLOR_BG, padx=12, pady=12, width=280)
        left.pack(side="left", fill="y")

        tk.Label(left, text="CẤU HÌNH MẪU PHIẾU", bg=COLOR_BG, font=("Segoe UI", 11, "bold"), fg=COLOR_PRIMARY).pack(anchor="w", pady=(0, 10))

        tk.Label(left, text="Phiên bản phiếu:", bg=COLOR_BG, font=("Segoe UI", 9, "bold")).pack(anchor="w")
        self.ver_var = tk.StringVar(value="V2")
        tk.Radiobutton(left, text="Template V2 (Có trường Đợt thi)", variable=self.ver_var, value="V2", bg=COLOR_BG, command=self._generate_preview).pack(anchor="w")
        tk.Radiobutton(left, text="Template V1 (Mẫu cũ không đợt thi)", variable=self.ver_var, value="V1", bg=COLOR_BG, command=self._generate_preview).pack(anchor="w")

        tk.Label(left, text="Số cột Đợt thi:", bg=COLOR_BG, font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(8, 2))
        self.col_var = tk.IntVar(value=2)
        tk.Radiobutton(left, text="2 chữ số (vd: 01, 02...)", variable=self.col_var, value=2, bg=COLOR_BG, command=self._generate_preview).pack(anchor="w")
        tk.Radiobutton(left, text="3 chữ số (vd: 001, 002...)", variable=self.col_var, value=3, bg=COLOR_BG, command=self._generate_preview).pack(anchor="w")

        tk.Label(left, text="Tiêu đề phiếu:", bg=COLOR_BG).pack(anchor="w", pady=(8, 2))
        self.ent_title = tk.Entry(left, font=("Segoe UI", 9))
        self.ent_title.insert(0, "PHIẾU TRẢ LỜI TRẮC NGHIỆM")
        self.ent_title.pack(fill="x")

        tk.Label(left, text="Môn thi:", bg=COLOR_BG).pack(anchor="w", pady=(8, 2))
        self.ent_subj = tk.Entry(left, font=("Segoe UI", 9))
        self.ent_subj.insert(0, "BÀI THI TỔNG HỢP")
        self.ent_subj.pack(fill="x")

        _styled_btn(left, "🔄 Cập nhật xem trước", self._generate_preview, bg="#1a5a9a").pack(fill="x", pady=12)

        tk.Label(left, text="XUẤT FILE IN:", bg=COLOR_BG, font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(12, 4))
        _styled_btn(left, "🖨️  Xuất file PDF (chuẩn A4)", self._export_pdf, bg="#107C41").pack(fill="x", pady=4)
        _styled_btn(left, "🖼️  Xuất file ảnh PNG", self._export_png, bg="#7B3F9E").pack(fill="x", pady=4)

        # Panel phải: Preview
        right = tk.Frame(self, bg="#333333", padx=8, pady=8)
        right.pack(side="right", fill="both", expand=True)

        self.lbl_preview = tk.Label(right, bg="#333333")
        self.lbl_preview.pack(fill="both", expand=True)

    def _generate_preview(self):
        title = self.ent_title.get().strip() if hasattr(self, "ent_title") else "PHIẾU TRẢ LỜI TRẮC NGHIỆM"
        subj = self.ent_subj.get().strip() if hasattr(self, "ent_subj") else "BÀI THI TỔNG HỢP"
        ver = self.ver_var.get()
        cols = self.col_var.get()

        self._generated_sheet = generate_sheet(
            template_version=ver,
            session_col_count=cols,
            exam_title=title,
            subject=subj,
        )

        rgb = cv2.cvtColor(self._generated_sheet, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(rgb)
        pil_img.thumbnail((460, 520), Image.LANCZOS)
        self._preview_photo = ImageTk.PhotoImage(pil_img)
        self.lbl_preview.configure(image=self._preview_photo)

    def _export_pdf(self):
        if self._generated_sheet is None:
            return
        f = filedialog.asksaveasfilename(parent=self, defaultextension=".pdf", filetypes=[("PDF Documents", "*.pdf")])
        if f:
            try:
                export_sheet_to_pdf(self._generated_sheet, f)
                messagebox.showinfo("Thành công", f"Đã xuất file PDF chuẩn in ấn A4:\n{f}", parent=self)
            except Exception as e:
                messagebox.showerror("Lỗi xuất PDF", str(e), parent=self)

    def _export_png(self):
        if self._generated_sheet is None:
            return
        f = filedialog.asksaveasfilename(parent=self, defaultextension=".png", filetypes=[("PNG Images", "*.png")])
        if f:
            try:
                export_sheet_to_image(self._generated_sheet, f)
                messagebox.showinfo("Thành công", f"Đã lưu ảnh phiếu:\n{f}", parent=self)
            except Exception as e:
                messagebox.showerror("Lỗi lưu ảnh", str(e), parent=self)
