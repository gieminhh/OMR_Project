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


if __name__ == "__main__":
    unittest.main()
