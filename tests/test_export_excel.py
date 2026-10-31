"""Kiểm tra tệp Excel được tạo từ kết quả chấm điểm."""

import tempfile
import unittest
from pathlib import Path

import openpyxl

from modules.errors import OMRError
from modules.export_excel import export_excel
from modules.scoring import score_answers


class ExportExcelTests(unittest.TestCase):
    def test_exports_question_rows_and_summary(self) -> None:
        result = score_answers(["A"] * 50, ["A"] * 50)
        with tempfile.TemporaryDirectory() as folder:
            output = export_excel(result, Path(folder) / "result")
            workbook = openpyxl.load_workbook(output, data_only=True)

        sheet = workbook.active
        assert sheet is not None
        self.assertEqual(output.suffix, ".xlsx")
        self.assertEqual(sheet.title, "Kết quả")
        self.assertEqual(sheet["A1"].value, "Câu")
        self.assertEqual(sheet["D2"].value, "✓ Đúng")
        self.assertEqual(sheet["A53"].value, "Tổng số câu")
        self.assertEqual(sheet["B58"].value, 10)

    def test_rejects_incomplete_score_result(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(OMRError):
                export_excel({}, Path(folder) / "result.xlsx")

    def test_exports_unscored_mode_1_without_answer_key(self) -> None:
        """Chế độ 1: Xuất Excel khi chưa chấm điểm, không tự sinh điểm số."""
        answers = ["A"] * 48 + ["BLANK", "MULTIPLE"]
        with tempfile.TemporaryDirectory() as folder:
            output = export_excel(None, Path(folder) / "unscored.xlsx", answers=answers)
            workbook = openpyxl.load_workbook(output, data_only=True)

        sheet = workbook.active
        assert sheet is not None
        self.assertEqual(sheet["A1"].value, "Câu")
        self.assertEqual(sheet["B1"].value, "Đáp án nhận diện")
        self.assertEqual(sheet["C1"].value, "Trạng thái")
        self.assertIsNone(sheet["D1"].value)  # Không có cột đáp án đúng

        # Kiểm tra câu bình thường, blank, multiple
        self.assertEqual(sheet["B2"].value, "A")
        self.assertEqual(sheet["C2"].value, "Đã chọn")
        self.assertEqual(sheet["B50"].value, "BLANK")
        self.assertEqual(sheet["C50"].value, "— Bỏ trống")
        self.assertEqual(sheet["B51"].value, "MULTIPLE")
        self.assertEqual(sheet["C51"].value, "⚠ Nhiều đáp án")

        # Kiểm tra phần tổng kết (không có điểm số)
        self.assertEqual(sheet["A53"].value, "Tổng số câu")
        self.assertEqual(sheet["B53"].value, 50)
        self.assertEqual(sheet["A54"].value, "Số câu đã chọn")
        self.assertEqual(sheet["B54"].value, 48)
        self.assertEqual(sheet["A55"].value, "Số câu bỏ trống")
        self.assertEqual(sheet["B55"].value, 1)
        self.assertEqual(sheet["A56"].value, "Số câu tô nhiều")
        self.assertEqual(sheet["B56"].value, 1)

    def test_exports_unscored_from_dict_and_list(self) -> None:
        """Xuất từ dict (process_omr format) hoặc list thuần."""
        answers = ["B"] * 50
        with tempfile.TemporaryDirectory() as folder:
            # Truyền dict từ process_omr
            p1 = export_excel({"answers": answers, "score_result": None}, Path(folder) / "res1.xlsx")
            wb1 = openpyxl.load_workbook(p1)
            self.assertEqual(wb1.active["B2"].value, "B")

            # Truyền list thuần
            p2 = export_excel(answers, Path(folder) / "res2.xlsx")
            wb2 = openpyxl.load_workbook(p2)
            self.assertEqual(wb2.active["B2"].value, "B")

    def test_rejects_invalid_answer_count_for_unscored(self) -> None:
        """Chế độ 1 từ chối dữ liệu không đủ 50 câu."""
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(OMRError):
                export_excel(["A"] * 25, Path(folder) / "bad.xlsx")


if __name__ == "__main__":
    unittest.main()
