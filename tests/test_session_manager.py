"""Kiểm thử tính năng quản lý đợt thi, học sinh, mã đề và cơ sở dữ liệu SQLite."""

import json
from pathlib import Path
import tempfile
import unittest

from modules.session_manager import SessionManager, classify_score
from modules.db import close_connections
from modules.errors import OMRError
from modules.scoring import ScoringError


class SessionManagerTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp_dir.name) / "test_omr.sqlite"
        self.manager = SessionManager(self.db_path)

    def tearDown(self):
        close_connections(self.db_path)
        self.tmp_dir.cleanup()

    def test_create_and_get_session(self):
        sess = self.manager.create_session(
            session_code="01",
            name="Kiểm tra học kỳ 1",
            subject="Toán",
            exam_date="2026-10-25",
            class_codes=["12A1", "12A2"],
        )
        self.assertEqual(sess["session_code"], "01")
        self.assertEqual(sess["name"], "Kiểm tra học kỳ 1")
        self.assertEqual(sess["subject"], "Toán")
        self.assertEqual(sess["question_count"], 50)
        self.assertIn("12A1", sess["class_codes"])
        self.assertIn("12A2", sess["class_codes"])

        # Không cho phép trùng mã đợt thi
        with self.assertRaises(OMRError):
            self.manager.create_session(session_code="01", name="Trùng", subject="Lý", exam_date="2026-10-26")

    def test_list_and_search_sessions(self):
        self.manager.create_session("01", "Thi Học kỳ 1 Toán", "Toán", "2026-10-25")
        self.manager.create_session("02", "Thi Học kỳ 1 Lý", "Vật lý", "2026-10-26")

        all_sess = self.manager.list_sessions()
        self.assertEqual(len(all_sess), 2)

        search_res = self.manager.list_sessions(search="Vật lý")
        self.assertEqual(len(search_res), 1)
        self.assertEqual(search_res[0]["session_code"], "02")

    def test_update_missing_session_raises(self):
        with self.assertRaises(OMRError):
            self.manager.update_session("missing", name="Không tồn tại")

    def test_student_management_and_matching(self):
        self.manager.add_class("12A1", "Lớp 12A1 Tự nhiên")
        self.manager.add_student("HS001", "001234", "Nguyễn Văn A", "12A1")

        stu = self.manager.get_student_by_sbd("001234")
        self.assertIsNotNone(stu)
        self.assertEqual(stu["full_name"], "Nguyễn Văn A")
        self.assertEqual(stu["student_code"], "HS001")

        # Tìm SBD không tồn tại
        self.assertIsNone(self.manager.get_student_by_sbd("999999"))

    def test_exam_codes_and_answer_keys(self):
        self.manager.create_session("01", "Giữa kỳ", "Hóa", "2026-10-25")
        answers_101 = ["A"] * 50
        answers_102 = ["B"] * 50

        self.manager.set_answer_key("01", "101", answers_101)
        self.manager.set_answer_key("01", "102", answers_102)

        key_101 = self.manager.get_answer_key("01", "101")
        self.assertEqual(key_101, answers_101)
        key_102 = self.manager.get_answer_key("01", "102")
        self.assertEqual(key_102, answers_102)

        # Cách ly giữa các đợt thi: Đợt 02 chưa có đề 101
        self.manager.create_session("02", "Đợt 2", "Hóa", "2026-10-26")
        self.assertIsNone(self.manager.get_answer_key("02", "101"))

        # Kiểm tra số lượng câu sai
        with self.assertRaises(ScoringError):
            self.manager.set_answer_key("01", "103", ["A"] * 20)

    def test_save_result_and_duplicate_sbd(self):
        self.manager.create_session("01", "Kiểm tra", "Sử", "2026-10-25", class_codes=["12A1"])
        self.manager.add_student("HS001", "000123", "Trần Thị B", "12A1")
        self.manager.set_answer_key("01", "201", ["A"] * 50)

        # Bài làm thứ nhất của SBD 000123 -> SUCCESS
        res1 = self.manager.save_exam_result(
            session_code="01",
            image_path="test1.png",
            student_answers=["A"] * 50,
            sbd="000123",
            exam_code="201",
        )
        self.assertEqual(res1["status"], "SUCCESS")
        self.assertEqual(res1["score"], 10.0)
        self.assertEqual(res1["student_name"], "Trần Thị B")

        # Bài làm thứ hai cùng SBD 000123 trong cùng đợt thi -> Phải cảnh báo NEEDS_REVIEW
        res2 = self.manager.save_exam_result(
            session_code="01",
            image_path="test2.png",
            student_answers=["A"] * 50,
            sbd="000123",
            exam_code="201",
        )
        self.assertEqual(res2["status"], "NEEDS_REVIEW")
        self.assertIn("Trùng số báo danh", res2["review_reason"])

    def test_re_grading(self):
        self.manager.create_session("01", "Kiểm tra", "Địa", "2026-10-25", class_codes=["12A1"])
        self.manager.add_student("HS001", "000111", "Lê Văn C", "12A1")
        # Ban đầu đáp án là B
        self.manager.set_answer_key("01", "301", ["B"] * 50)

        # Học sinh tô toàn A -> Điểm 0
        res = self.manager.save_exam_result(
            session_code="01",
            image_path="test.png",
            student_answers=["A"] * 50,
            sbd="000111",
            exam_code="301",
        )
        self.assertEqual(res["score"], 0.0)

        # Cập nhật đáp án thành toàn A và gọi re_grade_session
        self.manager.set_answer_key("01", "301", ["A"] * 50)
        count = self.manager.re_grade_session("01")
        self.assertEqual(count, 1)

        # Kiểm tra lại điểm đã thành 10
        updated = self.manager.get_result_by_id(res["id"])
        self.assertEqual(updated["score"], 10.0)
        self.assertEqual(updated["classification"], "Giỏi")


if __name__ == "__main__":
    unittest.main()
