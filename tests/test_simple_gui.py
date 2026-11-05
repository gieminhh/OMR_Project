"""Kiểm thử tự động cho Giao diện OMR Tkinter."""

import tempfile
import unittest
from pathlib import Path

import openpyxl

from gui.simple_app import SimpleOMRApp

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


if __name__ == "__main__":
    unittest.main()
