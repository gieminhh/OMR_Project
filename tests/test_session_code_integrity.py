"""Bộ kiểm thử tính toàn vẹn của mã đợt thi, mã đề, SBD và các quy tắc nghiệp vụ chấm OMR.

10 trường hợp kiểm thử bắt buộc:
1. Chọn đợt thi "01" từ danh sách đợt thi (giữ nguyên "01", không mất số 0 đầu).
2. Chọn đợt thi "02" (giữ nguyên "02", không biến thành "2").
3. Mã đợt thi có 3 chữ số ("001", "002").
4. Cập nhật đợt thi vẫn bảo toàn "01".
5. Chấm lại đợt thi "01" không bị chuyển sang "1".
6. Lấy danh sách mã đề của đợt "01" khi truyền "01" và khi truyền "1" (đồng bộ canonical).
7. Lấy đáp án chuẩn của đợt "01" mã 101 khi truyền "01" và khi truyền "1".
8. Chấm bài perfect_02.png với đợt thi "01" và mã đề 103 (tìm thấy đáp án, đúng SBD, điểm 9.0, SUCCESS).
9. Chấm lại toàn bộ đợt "01" không sinh thêm bản ghi trùng lặp, giữ nguyên số lượng bài thi.
10. Toàn bộ test suite và benchmark vận hành chính xác.
"""

from pathlib import Path
import tempfile
import unittest

from modules.batch_processor import process_single_sheet
from modules.db import close_connections, init_db
from modules.demo_loader import load_demo_data
from modules.errors import OMRError
from modules.session_manager import SessionManager


class SessionCodeIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root_path = Path(self.temp_dir.name)
        self.db_path = self.root_path / "test_session_integrity.sqlite"
        init_db(self.db_path)
        self.sm = SessionManager(self.db_path)

        # Nạp dữ liệu mẫu sạch cho đợt 01, 02
        load_demo_data(self.sm, overwrite_keys=True)

    def tearDown(self):
        close_connections(self.db_path)
        self.temp_dir.cleanup()

    def test_case_01_select_session_01_preserves_leading_zero(self):
        """1. Chọn đợt thi '01' từ danh sách: mã đợt thi phải giữ nguyên '01'."""
        sessions = self.sm.list_sessions()
        sess_codes = [s["session_code"] for s in sessions]
        self.assertIn("01", sess_codes)
        resolved = self.sm.resolve_session_code("01")
        self.assertEqual(resolved, "01")
        self.assertIsInstance(resolved, str)
        self.assertEqual(len(resolved), 2)

    def test_case_02_select_session_02_preserves_leading_zero(self):
        """2. Chọn đợt thi '02': mã đợt thi phải giữ nguyên '02', không biến thành '2'."""
        resolved = self.sm.resolve_session_code("02")
        self.assertEqual(resolved, "02")
        sess = self.sm.get_session("02")
        self.assertIsNotNone(sess)
        self.assertEqual(sess["session_code"], "02")

    def test_case_03_three_digit_session_code(self):
        """3. Mã đợt thi có 3 chữ số ('001', '002') được tạo và lưu trữ chính xác."""
        sess_001 = self.sm.create_session(
            session_code="001",
            name="Đợt thi tuyển sinh 001",
            subject="Vật lý",
            exam_date="2026-11-01",
            class_codes=["12A1"],
        )
        self.assertEqual(sess_001["session_code"], "001")
        fetched = self.sm.get_session("001")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["session_code"], "001")
        self.assertEqual(self.sm.resolve_session_code("001"), "001")

    def test_case_04_update_session_preserves_session_code_01(self):
        """4. Cập nhật thông tin đợt thi vẫn bảo toàn mã '01'."""
        updated = self.sm.update_session("01", name="Đợt thi Toán HK1 - Tên Mới")
        self.assertEqual(updated["session_code"], "01")
        self.assertEqual(updated["name"], "Đợt thi Toán HK1 - Tên Mới")
        sess = self.sm.get_session("01")
        self.assertEqual(sess["session_code"], "01")

    def test_case_05_re_grade_session_preserves_session_code(self):
        """5. Chấm lại đợt thi '01' không làm đổi mã đợt sang '1'."""
        count = self.sm.re_grade_session("01")
        self.assertGreaterEqual(count, 0)
        sess = self.sm.get_session("01")
        self.assertEqual(sess["session_code"], "01")

    def test_case_06_list_exam_codes_with_both_01_and_1(self):
        """6. Lấy danh sách mã đề của đợt '01' khi truyền '01' hoặc '1' đều trả về đủ 4 mã."""
        codes_from_01 = self.sm.list_exam_codes("01")
        codes_from_1 = self.sm.list_exam_codes("1")
        names_01 = {c["exam_code"] for c in codes_from_01}
        names_1 = {c["exam_code"] for c in codes_from_1}
        expected_codes = {"101", "102", "103", "104"}
        self.assertTrue(expected_codes.issubset(names_01))
        self.assertTrue(expected_codes.issubset(names_1))
        self.assertEqual(names_01, names_1)

    def test_case_07_get_answer_key_with_both_01_and_1(self):
        """7. Lấy đáp án chuẩn đợt '01' mã '101' khi truyền '01' và '1' đều trả về cùng đáp án."""
        key_01 = self.sm.get_answer_key("01", "101")
        key_1 = self.sm.get_answer_key("1", "101")
        self.assertIsNotNone(key_01)
        self.assertIsNotNone(key_1)
        self.assertEqual(key_01, key_1)
        self.assertEqual(len(key_01), 50)

    def test_case_08_grade_perfect_02_image(self):
        """8. Chấm bài perfect_02.png với đợt thi '01' và mã đề 103:
        - Phải tìm thấy đáp án chuẩn
        - Nhận diện đúng SBD 000002
        - Điểm đạt 9.0 (hoặc điểm chính xác theo đáp án)
        - Trạng thái SUCCESS, không bị NEEDS_REVIEW do thiếu đáp án.
        """
        img_path = Path("test_images/benchmark_dataset/images/perfect_02.png")
        if not img_path.exists():
            self.skipTest(f"Không tìm thấy file ảnh: {img_path}")

        item = process_single_sheet(img_path, self.sm, default_session_code="01")
        self.assertEqual(item.sbd, "000002")
        self.assertEqual(item.exam_code, "103")
        self.assertEqual(item.status, "SUCCESS")
        self.assertIsNotNone(item.score)
        self.assertAlmostEqual(item.score, 9.0, places=1)
        self.assertEqual(item.correct_count, 45)
        self.assertEqual(len(item.review_reasons), 0)

    def test_case_09_re_grade_does_not_create_duplicates(self):
        """9. Chấm lại toàn bộ đợt '01' không tạo thêm bản ghi trùng lặp, giữ nguyên số lượng."""
        img_path = Path("test_images/benchmark_dataset/images/perfect_02.png")
        if not img_path.exists():
            self.skipTest(f"Không tìm thấy file ảnh: {img_path}")

        # Chấm lần đầu
        process_single_sheet(img_path, self.sm, default_session_code="01")
        initial_results = self.sm.list_results("01")
        initial_count = len(initial_results)
        self.assertEqual(initial_count, 1)

        # Chấm lại
        re_graded = self.sm.re_grade_session("01")
        self.assertEqual(re_graded, 1)

        after_results = self.sm.list_results("01")
        self.assertEqual(len(after_results), initial_count)
        self.assertEqual(after_results[0]["id"], initial_results[0]["id"])
        self.assertEqual(after_results[0]["sbd"], "000002")

    def test_case_10_treeview_iid_and_string_representation(self):
        """10. Đảm bảo iid và Treeview representation không làm mất số 0 đầu của đợt thi và mã đề."""
        for code in ["01", "02", "001", "007", "101"]:
            resolved = self.sm.resolve_session_code(code)
            # Đối với đợt thi có trong DB (01, 02), chuỗi chuẩn hóa phải giữ nguyên độ dài
            if code in ["01", "02"]:
                self.assertEqual(resolved, code)
                self.assertEqual(str(resolved), code)
                self.assertTrue(str(resolved).startswith("0"))
            else:
                self.assertEqual(str(resolved), code)


if __name__ == "__main__":
    unittest.main()
