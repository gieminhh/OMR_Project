"""Kiểm thử tự động cho Giao diện OMR Tkinter và Quản lý Đáp án chuẩn."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import openpyxl

from gui.simple_app import ManualAnswerKeyDialog, SimpleOMRApp
from modules.scoring import load_answer_key, score_answers

ROOT = Path(__file__).resolve().parents[1]


class SimpleGuiTests(unittest.TestCase):
    def setUp(self):
        try:
            self.app = SimpleOMRApp()
            self.app.withdraw()  # Ẩn cửa sổ khi chạy test tự động
        except Exception as exc:
            self.skipTest(f"Môi trường không có Tkinter/Display: {exc}")

    def tearDown(self):
        if hasattr(self, "app"):
            self.app.destroy()

    def test_initial_state(self):
        """Kiểm tra trạng thái ban đầu của giao diện."""
        self.assertIsNone(self.app.image_path)
        self.assertIsNone(self.app.student_answers)
        self.assertIsNone(self.app.answer_key)
        self.assertIsNone(self.app.score_result)
        self.assertEqual(str(self.app.btn_scan["state"]), "disabled")
        self.assertEqual(str(self.app.btn_score["state"]), "disabled")
        self.assertEqual(str(self.app.btn_excel["state"]), "disabled")
        self.assertEqual(str(self.app.btn_export_key["state"]), "normal")
        self.assertEqual(self.app.chip_correct.cget("text"), "--")
        self.assertEqual(self.app.chip_wrong.cget("text"), "--")
        self.assertEqual(self.app.chip_blank.cget("text"), "--")
        self.assertEqual(self.app.chip_multi.cget("text"), "--")

    def test_scan_and_unscored_table_and_export(self):
        """Đọc phiếu thành công cập nhật bảng 50 câu và cho phép xuất Excel Chế độ 1."""
        sample_img = ROOT / "test_images" / "sample_photo.png"
        self.app.image_path = sample_img
        self.app.on_scan_sheet()

        self.assertIsNotNone(self.app.student_answers)
        self.assertEqual(len(self.app.student_answers), 50)
        # Bảng phải có đúng 50 dòng
        children = self.app.tree.get_children()
        self.assertEqual(len(children), 50)
        # Nút xuất Excel phải được bật ngay cả khi chưa chấm
        self.assertEqual(str(self.app.btn_excel["state"]), "normal")

        # Khi chưa chấm điểm: tuyệt đối không hiển thị số câu đã tô dưới nhãn Đúng
        self.assertEqual(self.app.chip_correct.cget("text"), "--")
        self.assertEqual(self.app.chip_wrong.cget("text"), "--")
        self.assertEqual(self.app.chip_blank.cget("text"), "0")
        self.assertEqual(self.app.chip_multi.cget("text"), "0")

        # Kiểm tra xuất Excel chế độ 1 (chưa chấm)
        with tempfile.TemporaryDirectory() as folder:
            out_file = Path(folder) / "unscored.xlsx"
            self.app.score_result = None  # Đảm bảo chưa chấm
            from modules.export_excel import export_excel
            export_excel(None, out_file, answers=self.app.student_answers)
            wb = openpyxl.load_workbook(out_file)
            self.assertEqual(wb.active["B1"].value, "Đáp án nhận diện")

    def test_load_key_and_scoring(self):
        """Nạp đáp án chuẩn và chấm điểm thành công."""
        self.app.student_answers = ["A"] * 50
        self.app.answer_key = ["A"] * 50

        self.app.on_score()

        self.assertIsNotNone(self.app.score_result)
        self.assertEqual(self.app.score_result["score"], 10.0)
        self.assertEqual(self.app.score_result["correct_count"], 50)
        self.assertEqual(str(self.app.btn_excel["state"]), "normal")

        # Sau khi chấm điểm: hiển thị số câu đúng và sai rõ ràng
        self.assertEqual(self.app.chip_correct.cget("text"), "50")
        self.assertEqual(self.app.chip_wrong.cget("text"), "0")
        self.assertEqual(self.app.chip_blank.cget("text"), "0")
        self.assertEqual(self.app.chip_multi.cget("text"), "0")

    def test_changing_answer_key_updates_score(self):
        """Thay đổi đáp án chuẩn sau khi đã chấm phải tính lại điểm, không giữ điểm cũ."""
        self.app.student_answers = ["A"] * 25 + ["B"] * 25

        # Lần 1: Chấm với key_1 (toàn A) -> Đúng 25 câu = 5.0 điểm
        self.app.answer_key = ["A"] * 50
        self.app.on_score()
        self.assertEqual(self.app.score_result["score"], 5.0)

        # Lần 2: Đổi sang key_2 (25 A + 25 B) -> Đúng 50 câu = 10.0 điểm
        self.app.answer_key = ["A"] * 25 + ["B"] * 25
        self.app.on_score()
        self.assertEqual(self.app.score_result["score"], 10.0)

        # Lần 3: Đổi sang key_3 (toàn C) -> Đúng 0 câu = 0.0 điểm
        self.app.answer_key = ["C"] * 50
        self.app.on_score()
        self.assertEqual(self.app.score_result["score"], 0.0)

    def test_treeview_row_tags_colored(self):
        """Kiểm tra Treeview gán đúng tag màu cho từng trạng thái: correct, wrong, blank, multiple."""
        # 1. Kiểm tra khi đã chấm điểm
        self.app.student_answers = ["A", "B", "BLANK", "MULTIPLE"] + ["A"] * 46
        self.app.answer_key = ["A"] * 50
        self.app.on_score()

        items = self.app.tree.get_children()
        # Câu 1: A vs A -> correct
        self.assertIn("correct", self.app.tree.item(items[0], "tags"))
        # Câu 2: B vs A -> wrong
        self.assertIn("wrong", self.app.tree.item(items[1], "tags"))
        # Câu 3: BLANK -> blank
        self.assertIn("blank", self.app.tree.item(items[2], "tags"))
        # Câu 4: MULTIPLE -> multiple
        self.assertIn("multiple", self.app.tree.item(items[3], "tags"))

        # 2. Kiểm tra khi chưa chấm điểm
        self.app.score_result = None
        self.app._update_table_unscored()
        items_unscored = self.app.tree.get_children()
        self.assertIn("normal", self.app.tree.item(items_unscored[0], "tags"))
        self.assertIn("blank", self.app.tree.item(items_unscored[2], "tags"))
        self.assertIn("multiple", self.app.tree.item(items_unscored[3], "tags"))

    # ═════════════════════════════════════════════════════════════════
    # KIỂM THỬ CHỨC NĂNG NHẬP THỦ CÔNG ĐÁP ÁN CHUẨN (10 YÊU CẦU BẮT BUỘC)
    # ═════════════════════════════════════════════════════════════════

    def test_manual_key_save_success(self):
        """1. Nhập đủ 50 đáp án A/B/C/D rồi lưu thành công."""
        dlg = self.app.on_manual_key()
        dlg.withdraw()
        dlg.fill_all("B")
        dlg.on_save()

        self.assertIsNotNone(self.app.answer_key)
        self.assertEqual(len(self.app.answer_key), 50)
        self.assertEqual(self.app.answer_key, ["B"] * 50)
        self.assertIn("Thủ công", self.app.lbl_key_status.cget("text"))
        self.assertEqual(str(self.app.btn_export_key["state"]), "normal")

    def test_manual_key_missing_question_10_rejected(self):
        """2. Thiếu đáp án ở câu 10 thì không cho lưu và thông báo rõ."""
        dlg = self.app.on_manual_key()
        dlg.withdraw()
        dlg.fill_all("A")
        # Để trống câu 10 (chỉ số 9)
        dlg.set_answer(9, "")

        with patch("tkinter.messagebox.showwarning") as mock_warn:
            dlg.on_save()
            mock_warn.assert_called_once()
            args, _ = mock_warn.call_args
            self.assertIn("10", str(args))  # Báo rõ thiếu câu 10

        # Đáp án chuẩn chưa được lưu vào app
        self.assertIsNone(self.app.answer_key)
        dlg.destroy()

    def test_manual_key_edit_question_25_only(self):
        """3. Sửa đáp án câu 25 không làm thay đổi các câu khác."""
        dlg = self.app.on_manual_key()
        dlg.withdraw()
        dlg.fill_all("A")
        # Sửa câu 25 (chỉ số 24) thành C
        dlg.set_answer(24, "C")

        answers = dlg.get_answers()
        self.assertEqual(answers[23], "A")  # Câu 24 vẫn là A
        self.assertEqual(answers[24], "C")  # Câu 25 là C
        self.assertEqual(answers[25], "A")  # Câu 26 vẫn là A

        dlg.on_save()
        self.assertEqual(self.app.answer_key[24], "C")
        self.assertEqual(self.app.answer_key[0], "A")
        self.assertEqual(self.app.answer_key[49], "A")

    def test_manual_key_cancel_preserves_current_key(self):
        """4. Nhấn Hủy không làm thay đổi bộ đáp án chuẩn đang sử dụng."""
        self.app.answer_key = ["D"] * 50
        dlg = self.app.on_manual_key()
        dlg.withdraw()
        dlg.fill_all("A")
        # Người dùng bấm hủy
        dlg.destroy()

        self.assertEqual(self.app.answer_key, ["D"] * 50)

    def test_manual_key_prefills_loaded_json(self):
        """5. Nạp JSON rồi mở cửa sổ thủ công thì hiện đúng các đáp án đã nạp."""
        key_file = ROOT / "answer_key" / "answer_key.json"
        expected = load_answer_key(key_file)
        self.app._apply_new_answer_key(expected, "test.json")

        dlg = self.app.on_manual_key()
        dlg.withdraw()
        dlg_answers = dlg.get_answers()

        self.assertEqual(dlg_answers, expected)
        dlg.destroy()

    def test_manual_key_export_json_and_reload(self):
        """6. Nhập thủ công, lưu vào app, rồi xuất JSON từ giao diện chính, nạp lại đối chiếu khớp 50 câu."""
        dlg = self.app.on_manual_key()
        dlg.withdraw()
        sample_answers = (["A", "B", "C", "D"] * 12) + ["A", "B"]
        for idx, val in enumerate(sample_answers):
            dlg.set_answer(idx, val)
        dlg.on_save()  # Lưu & sử dụng -> cập nhật vào self.app.answer_key

        with tempfile.TemporaryDirectory() as tmpdir:
            out_json = Path(tmpdir) / "exported_key.json"
            with patch("tkinter.filedialog.asksaveasfilename", return_value=str(out_json)):
                with patch("tkinter.messagebox.showinfo"):
                    self.app.on_export_key_json()

            self.assertTrue(out_json.exists())
            # Nạp lại bằng hàm lõi load_answer_key
            reloaded = load_answer_key(out_json)
            self.assertEqual(reloaded, sample_answers)

    def test_export_key_json_without_key_shows_warning(self):
        """Kiểm tra khi chưa có đáp án chuẩn, bấm Xuất JSON trên giao diện chính phải cảnh báo rõ."""
        self.app.answer_key = None
        with patch("tkinter.messagebox.showwarning") as mock_warn:
            with patch("tkinter.filedialog.asksaveasfilename") as mock_file:
                self.app.on_export_key_json()
                mock_warn.assert_called_once()
                mock_file.assert_not_called()

    def test_dialog_has_only_save_and_cancel_buttons(self):
        """Cửa sổ nhập thủ công chỉ có 2 nút hành động: 'Lưu & sử dụng' và 'Hủy', không có 'Xuất JSON'."""
        dlg = self.app.on_manual_key()
        dlg.withdraw()
        self.assertFalse(hasattr(dlg, "on_export_json"))
        self.assertFalse(hasattr(dlg, "btn_export"))
        dlg.destroy()

    def test_manual_and_json_scoring_identical(self):
        """7. Chấm điểm bằng đáp án thủ công và đáp án JSON giống nhau thì kết quả phải giống nhau."""
        student = (["A", "B", "C", "D"] * 12) + ["BLANK", "MULTIPLE"]
        key_list = ["A"] * 50

        # Chấm với đáp án từ hàm score_answers trực tiếp
        res_direct = score_answers(student, key_list)

        # Chấm trên GUI qua đáp án nạp thủ công
        self.app.student_answers = student
        self.app._apply_new_answer_key(key_list, "Thủ công (50 câu)")
        self.app.on_score()

        self.assertEqual(self.app.score_result["score"], res_direct["score"])
        self.assertEqual(self.app.score_result["correct_count"], res_direct["correct_count"])
        self.assertEqual(self.app.score_result["wrong_count"], res_direct["wrong_count"])
        self.assertEqual(self.app.score_result["blank_count"], res_direct["blank_count"])
        self.assertEqual(self.app.score_result["multiple_count"], res_direct["multiple_count"])

    def test_changing_answer_key_invalidates_old_score(self):
        """8. Đổi đáp án chuẩn sau khi chấm: Xóa điểm cũ, yêu cầu bấm chấm lại, không giữ điểm cũ."""
        self.app.student_answers = ["A"] * 50
        self.app.answer_key = ["A"] * 50
        self.app.on_score()
        self.assertEqual(self.app.score_result["score"], 10.0)

        # Đổi sang bộ đáp án mới qua _apply_new_answer_key
        self.app._apply_new_answer_key(["B"] * 50, "Bộ đáp án mới")

        # 1. Điểm cũ phải bị vô hiệu hóa / xóa
        self.assertIsNone(self.app.score_result)
        self.assertEqual(self.app.lbl_score.cget("text"), "Chưa chấm")
        self.assertEqual(self.app.chip_correct.cget("text"), "--")
        self.assertEqual(self.app.chip_wrong.cget("text"), "--")

        # 2. Học sinh vẫn giữ nguyên 50 câu đã đọc
        self.assertEqual(len(self.app.student_answers), 50)

        # 3. Nút chấm điểm được bật để chấm lại
        self.assertEqual(str(self.app.btn_score["state"]), "normal")

        # 4. Khi xuất Excel lúc này, không chứa điểm cũ (chế độ chưa chấm)
        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = Path(tmpdir) / "check_export.xlsx"
            with patch("tkinter.filedialog.asksaveasfilename", return_value=str(out_file)):
                with patch("tkinter.messagebox.showinfo"):
                    self.app.on_export_excel()
            wb = openpyxl.load_workbook(out_file)
            self.assertEqual(wb.active["B1"].value, "Đáp án nhận diện")

        # 5. Bấm chấm điểm lại -> Ra kết quả 0.0 điểm theo key mới
        self.app.on_score()
        self.assertIsNotNone(self.app.score_result)
        self.assertEqual(self.app.score_result["score"], 0.0)


if __name__ == "__main__":
    unittest.main()
