"""Kiểm thử toàn diện chức năng Quản lý Đáp án chuẩn và Nạp Dữ liệu Demo."""

import json
from pathlib import Path
import tempfile
import unittest

from modules.batch_processor import read_answer_key_from_image
from modules.db import close_connections, init_db
from modules.demo_loader import load_demo_data
from modules.errors import OMRError
from modules.scoring import ScoringError
from modules.session_manager import SessionManager

ROOT = Path(__file__).resolve().parents[1]


class AnswerKeyManagementTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_omr.sqlite"
        init_db(self.db_path)
        self.mgr = SessionManager(self.db_path)
        self.mgr.create_session("01", "Kỳ thi thử", "Toán", "2026-10-26")

    def tearDown(self):
        close_connections(self.db_path)
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_import_answer_keys_from_json_nested(self):
        self.mgr.create_session("02", "Kỳ thi 2", "Lý", "2026-10-26")
        data = {
            "01": {
                "101": ["A"] * 50,
                "102": ["B"] * 50,
            },
            "02": {
                "201": ["C"] * 50,
            },
        }
        json_file = Path(self.temp_dir.name) / "multi_keys.json"
        json_file.write_text(json.dumps(data), encoding="utf-8")

        count = self.mgr.import_answer_keys_from_json(json_file)
        self.assertEqual(count, 3)

        self.assertEqual(self.mgr.get_answer_key("01", "101"), ["A"] * 50)
        self.assertEqual(self.mgr.get_answer_key("01", "102"), ["B"] * 50)
        self.assertEqual(self.mgr.get_answer_key("02", "201"), ["C"] * 50)

    def test_import_answer_keys_from_csv_vertical_4_cols(self):
        csv_file = Path(self.temp_dir.name) / "keys_4cols.csv"
        lines = ["session_code,exam_code,question,answer"]
        for q in range(1, 51):
            lines.append(f"01,101,{q},A")
            lines.append(f"01,102,{q},B")
        csv_file.write_text("\n".join(lines), encoding="utf-8")

        count = self.mgr.import_answer_keys_from_csv("01", csv_file)
        self.assertEqual(count, 2)
        self.assertEqual(self.mgr.get_answer_key("01", "101"), ["A"] * 50)
        self.assertEqual(self.mgr.get_answer_key("01", "102"), ["B"] * 50)

    def test_import_answer_keys_from_csv_inferred_filename(self):
        # Tên file dap_an_dot_01_ma_103.csv với 2 cột question,answer
        csv_file = Path(self.temp_dir.name) / "dap_an_dot_01_ma_103.csv"
        lines = ["cau,dap_an"]
        for q in range(1, 51):
            lines.append(f"{q},C")
        csv_file.write_text("\n".join(lines), encoding="utf-8")

        count = self.mgr.import_answer_keys_from_csv("01", csv_file)
        self.assertEqual(count, 1)
        self.assertEqual(self.mgr.get_answer_key("01", "103"), ["C"] * 50)

    def test_read_answer_key_from_image_independent_and_no_exam_results(self):
        perfect_img = ROOT / "test_images" / "benchmark_dataset" / "images" / "perfect_01.png"
        if not perfect_img.is_file():
            self.skipTest("Ảnh perfect_01.png không tồn tại")

        # Đọc đáp án từ ảnh
        res = read_answer_key_from_image(perfect_img)
        self.assertTrue(res["is_valid"])
        self.assertEqual(res["exam_code"], "103")
        self.assertEqual(res["session_code"], "01")
        self.assertEqual(len(res["answers"]), 50)
        self.assertEqual(res["blank_questions"], [])
        self.assertEqual(res["multiple_questions"], [])

        # Kiểm tra tuyệt đối KHÔNG có bản ghi kết quả học sinh nào phát sinh
        results = self.mgr.list_results("01")
        self.assertEqual(len(results), 0)

    def test_read_answer_key_from_blank_image(self):
        blank_img = ROOT / "test_images" / "benchmark_dataset" / "images" / "blank_01.png"
        if not blank_img.is_file():
            self.skipTest("Ảnh blank_01.png không tồn tại")

        res = read_answer_key_from_image(blank_img)
        self.assertFalse(res["is_valid"])
        self.assertEqual(len(res["blank_questions"]), 50)
        self.assertIn("Có 50 câu chưa tô", "; ".join(res["review_reasons"]))

    def test_load_demo_data_complete(self):
        stats = load_demo_data(self.mgr)
        self.assertGreaterEqual(stats["sessions"], 1)  # Đợt 02 mới tạo
        self.assertGreaterEqual(stats["classes"], 4)   # 10A1, 10A2, 12A1, 12A2
        self.assertGreaterEqual(stats["students"], 39)
        self.assertGreaterEqual(stats["exam_codes"], 8)

        # Kiểm tra đọc lại cả 2 đợt thi
        s1 = self.mgr.get_session("01")
        s2 = self.mgr.get_session("02")
        self.assertIsNotNone(s1)
        self.assertIsNotNone(s2)

        codes1 = [c["exam_code"] for c in self.mgr.list_exam_codes("01")]
        codes2 = [c["exam_code"] for c in self.mgr.list_exam_codes("02")]
        self.assertEqual(sorted(codes1), ["101", "102", "103", "104"])
        self.assertEqual(sorted(codes2), ["101", "102", "103", "104"])

        # Kiểm tra học sinh có SBD số 0 ở đầu
        stu = self.mgr.get_student_by_sbd("000001", "01")
        self.assertIsNotNone(stu)
        self.assertEqual(stu["sbd"], "000001")

    def test_rescoring_same_image_updates_instead_of_duplicates(self):
        self.mgr.add_class("12A1", "Lớp 12A1")
        self.mgr.add_student("HS001", "000001", "Nguyễn Văn A", "12A1")
        self.mgr.set_answer_key("01", "101", ["A"] * 50)

        # Lần 1: Lưu bài thi
        r1 = self.mgr.save_exam_result(
            session_code="01",
            image_path=str(ROOT / "test_images" / "sheet.png"),
            student_answers=["A"] * 50,
            sbd="000001",
            exam_code="101",
        )
        self.assertEqual(r1["status"], "SUCCESS")
        self.assertEqual(r1["score"], 10.0)

        # Lần 2: Chấm lại chính bài đó với câu 1 đổi sang B
        new_ans = ["A"] * 50
        new_ans[0] = "B"
        r2 = self.mgr.save_exam_result(
            session_code="01",
            image_path=str(ROOT / "test_images" / "sheet.png"),
            student_answers=new_ans,
            sbd="000001",
            exam_code="101",
        )
        # ID phải giữ nguyên (update)
        self.assertEqual(r2["id"], r1["id"])
        self.assertEqual(r2["status"], "SUCCESS")
        self.assertEqual(r2["score"], 9.8)

        # Tổng số bài thi trong đợt thi vẫn là 1 bài (không bị duplicate)
        all_res = self.mgr.list_results("01")
        self.assertEqual(len(all_res), 1)
