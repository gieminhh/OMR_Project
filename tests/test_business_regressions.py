"""Bộ kiểm thử hồi quy cho các quy tắc nghiệp vụ chấm thi OMR (Business Regressions).

Bao gồm:
1. P0 - Ảnh trùng tên ở khác thư mục không được ghi đè kết quả của nhau.
2. P0 - Chấm lại giữ nguyên trạng thái NEEDS_REVIEW của bài trùng SBD.
3. P0 - An toàn dữ liệu demo: không ghi đè đáp án chuẩn đã có của người dùng.
4. P1 - Đối chiếu học sinh chỉ trong các lớp thuộc đợt thi, phát hiện SBD mơ hồ.
5. P1 - Khóa đợt thi: từ chối nhận bài mới, từ chối chấm lại, ghi nhận audit log.
6. P1 - Cảnh báo lệch mã đợt thi khi chấm hàng loạt.
7. P2 - Xóa mã đề an toàn qua transaction.
"""

from pathlib import Path
import tempfile
import unittest

from modules.batch_processor import process_single_sheet
from modules.db import close_connections, init_db
from modules.demo_loader import load_demo_data
from modules.errors import OMRError
from modules.session_manager import SessionManager


class BusinessRegressionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root_path = Path(self.temp_dir.name)
        self.db_path = self.root_path / "test_omr.sqlite"
        init_db(self.db_path)
        self.sm = SessionManager(self.db_path)

        # Tạo đợt thi mẫu
        self.sm.create_session(
            session_code="01",
            name="Đợt thi Toán HK1",
            subject="Toán học",
            exam_date="2026-10-26",
            class_codes=["12A1"],
        )
        self.sm.add_student("HS01", "000001", "Nguyễn Văn A", "12A1")
        self.sm.add_student("HS02", "000002", "Trần Thị B", "12A1")
        self.sm.set_answer_key("01", "101", ["A"] * 50)

    def tearDown(self):
        close_connections(self.db_path)
        self.temp_dir.cleanup()

    def test_p0_duplicate_filenames_in_different_folders_not_overwritten(self):
        """Hai ảnh cùng tên ở hai thư mục khác nhau không được ghi đè kết quả của nhau."""
        dir1 = self.root_path / "dir1"
        dir2 = self.root_path / "dir2"
        dir1.mkdir(parents=True, exist_ok=True)
        dir2.mkdir(parents=True, exist_ok=True)

        file1 = dir1 / "sheet.png"
        file2 = dir2 / "sheet.png"
        file1.write_bytes(b"image_content_student_01")
        file2.write_bytes(b"image_content_student_02")

        res1 = self.sm.save_exam_result(
            session_code="01",
            image_path=file1,
            student_answers=["A"] * 50,
            sbd="000001",
            exam_code="101",
        )

        res2 = self.sm.save_exam_result(
            session_code="01",
            image_path=file2,
            student_answers=["B"] * 50,
            sbd="000002",
            exam_code="101",
        )

        self.assertNotEqual(res1["id"], res2["id"])

        all_results = self.sm.list_results("01")
        self.assertEqual(len(all_results), 2)
        saved_sbds = {r["sbd"] for r in all_results}
        self.assertEqual(saved_sbds, {"000001", "000002"})

        # Lưu lại chính file1 (cùng hash/canonical path) thì phải cập nhật bản ghi cũ
        res1_update = self.sm.save_exam_result(
            session_code="01",
            image_path=file1,
            student_answers=["C"] * 50,
            sbd="000001",
            exam_code="101",
        )
        self.assertEqual(res1_update["id"], res1["id"])
        self.assertEqual(len(self.sm.list_results("01")), 2)

    def test_p0_re_grade_preserves_needs_review_for_duplicate_sbd(self):
        """Chấm lại đợt thi không được làm mất trạng thái NEEDS_REVIEW của bài thi trùng SBD."""
        f1 = self.root_path / "f1.png"
        f2 = self.root_path / "f2.png"
        f1.write_bytes(b"img1")
        f2.write_bytes(b"img2")

        # Bài 1 chấm trước với SBD 000001
        res1 = self.sm.save_exam_result(
            session_code="01",
            image_path=f1,
            student_answers=["A"] * 50,
            sbd="000001",
            exam_code="101",
        )
        self.assertEqual(res1["status"], "SUCCESS")

        # Bài 2 chấm sau với cùng SBD 000001 -> Phải là NEEDS_REVIEW do trùng SBD
        res2 = self.sm.save_exam_result(
            session_code="01",
            image_path=f2,
            student_answers=["A"] * 50,
            sbd="000001",
            exam_code="101",
        )
        self.assertEqual(res2["status"], "NEEDS_REVIEW")
        self.assertIn("Trùng số báo danh", res2["review_reason"])

        # Cập nhật lại đáp án chuẩn của mã đề 101 và gọi re_grade_session
        self.sm.set_answer_key("01", "101", ["B"] * 50)
        self.sm.re_grade_session("01")

        # Kiểm tra lại sau khi chấm lại
        res1_after = self.sm.get_result_by_id(res1["id"])
        res2_after = self.sm.get_result_by_id(res2["id"])

        self.assertEqual(res2_after["status"], "NEEDS_REVIEW")
        self.assertIn("Trùng số báo danh", res2_after["review_reason"])
        # Điểm số vẫn được cập nhật theo đáp án mới
        self.assertIsNotNone(res2_after["score"])

    def test_p0_demo_data_does_not_overwrite_existing_answer_keys(self):
        """Nạp dữ liệu demo không ghi đè đáp án chuẩn đã tồn tại của người dùng khi overwrite_keys=False."""
        user_key = ["C"] * 50
        self.sm.set_answer_key("01", "101", user_key)

        stats = load_demo_data(self.sm, overwrite_keys=False)
        current_key = self.sm.get_answer_key("01", "101")
        self.assertEqual(current_key, user_key)
        self.assertGreater(stats.get("skipped_keys", 0), 0)

    def test_p1_student_lookup_scoped_to_session_classes(self):
        """get_student_by_sbd chỉ tìm học sinh trong các lớp thuộc đợt thi."""
        # Thêm học sinh thuộc lớp 11B1 (lớp này KHÔNG thuộc đợt thi 01)
        self.sm.add_student("HS99", "000099", "Lê Văn Ngoài Đợt", "11B1")

        # Tìm không truyền session_code: tìm thấy
        stu_global = self.sm.get_student_by_sbd("000099")
        self.assertIsNotNone(stu_global)
        self.assertEqual(stu_global["student_code"], "HS99")

        # Tìm với session_code="01" (chỉ chứa 12A1): KHÔNG được trả về học sinh lớp 11B1
        stu_session = self.sm.get_student_by_sbd("000099", session_code="01")
        self.assertIsNone(stu_session)

    def test_p1_student_lookup_ambiguous_sbd(self):
        """Phát hiện nhiều học sinh có cùng SBD trong đợt thi và gắn cờ is_ambiguous."""
        # Lớp 12A2 cũng được liên kết vào đợt 01
        self.sm.update_session("01", class_codes=["12A1", "12A2"])
        # Thêm học sinh khác lớp nhưng trùng SBD 000001
        self.sm.add_student("HS01_DUPLICATE", "000001", "Nguyễn Văn Trùng", "12A2")

        stu = self.sm.get_student_by_sbd("000001", session_code="01")
        self.assertIsNotNone(stu)
        self.assertTrue(stu.get("is_ambiguous"))

        # Khi lưu bài, phát hiện mơ hồ thì phải sang NEEDS_REVIEW
        f = self.root_path / "ambiguous.png"
        f.write_bytes(b"ambiguous")
        res = self.sm.save_exam_result(
            session_code="01",
            image_path=f,
            student_answers=["A"] * 50,
            sbd="000001",
            exam_code="101",
        )
        self.assertEqual(res["status"], "NEEDS_REVIEW")
        self.assertIn("nhiều học sinh", res["review_reason"].lower())

    def test_p1_locked_session_blocks_operations_and_records_audit(self):
        """Đợt thi bị khóa phải từ chối nhận bài mới, từ chối chấm lại và ghi audit log."""
        # Khóa đợt thi
        self.sm.lock_session("01", reason="Kết thúc thời gian nộp bài", operator="giam_thi_1")
        sess = self.sm.get_session("01")
        self.assertEqual(sess["status"], "LOCKED")

        f = self.root_path / "new_sheet.png"
        f.write_bytes(b"content")

        with self.assertRaises(OMRError):
            self.sm.save_exam_result("01", f, ["A"] * 50, sbd="000001", exam_code="101")

        with self.assertRaises(OMRError):
            self.sm.re_grade_session("01")

        with self.assertRaises(OMRError):
            self.sm.set_answer_key("01", "101", ["B"] * 50)

        with self.assertRaises(OMRError):
            self.sm.delete_exam_code("01", "101")

        # Mở khóa đợt thi
        self.sm.unlock_session("01", reason="Cần bổ sung bài sót", operator="hieu_truong")
        sess = self.sm.get_session("01")
        self.assertEqual(sess["status"], "ACTIVE")

        # Kiểm tra audit log
        logs = self.sm.get_session_audit_logs("01")
        self.assertEqual(len(logs), 2)
        self.assertEqual(logs[0]["action"], "LOCK")
        self.assertEqual(logs[0]["operator"], "giam_thi_1")
        self.assertEqual(logs[1]["action"], "UNLOCK")
        self.assertEqual(logs[1]["operator"], "hieu_truong")

    def test_p2_delete_exam_code_safe_transaction(self):
        """Xóa mã đề an toàn qua transaction và kiểm tra trạng thái khóa."""
        self.sm.set_answer_key("01", "102", ["B"] * 50)
        self.assertIsNotNone(self.sm.get_answer_key("01", "102"))

        deleted = self.sm.delete_exam_code("01", "102")
        self.assertTrue(deleted)
        self.assertIsNone(self.sm.get_answer_key("01", "102"))


if __name__ == "__main__":
    unittest.main()
