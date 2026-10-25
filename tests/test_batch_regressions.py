"""Hồi quy giao diện batch, hướng phiếu và định tuyến đúng đợt thi."""

import gc
from pathlib import Path
import random
import tempfile
import tkinter as tk
import unittest
from unittest.mock import patch

import cv2

from gui.dialogs import BatchProcessorDialog
from modules.batch_processor import BatchProcessor, process_single_sheet
from modules.bubble_id_detection import detect_sheet_identifiers, SESSION_X_COLS_3, DIGIT_Y_ROWS
from modules.db import close_connections
from modules.image_processing import save_image
from modules.session_manager import SessionManager
from modules.sheet_generator import generate_sheet, MARKER_Y_POSITIONS, MIDDLE_MARKER_X_LEFT
from modules.test_dataset_generator import simulate_realistic_photo


class BatchRegressionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.db_path = self.base / "test.sqlite"
        self.mgr = SessionManager(self.db_path)
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(close_connections, self.db_path)
        for code in ("01", "001"):
            self.mgr.create_session(code, "Test", "Math", "2026-10-25")
            # Khác đáp án để phát hiện ngay nếu lưu/chấm nhầm đợt thi.
            self.mgr.set_answer_key(code, "101", ["A" if code == "001" else "B"] * 50)
        self.mgr.add_student("HS1", "000001", "Student", "12A1")

    def sheet(self, version="V2", columns=3, session="001"):
        return generate_sheet(version, session_col_count=columns, session_code=session,
                              sbd="000001", exam_code="101", answers=["A"] * 50)

    def process(self, sheet, name="sheet.png", **kwargs):
        path = save_image(self.base / name, sheet)
        return process_single_sheet(path, self.mgr, "01", self.base / "out", **kwargs)

    def test_batch_dialog_opens_and_has_start_button(self):
        gc.collect()
        root = tk.Tk()
        root.withdraw()
        try:
            dialog = BatchProcessorDialog(root, self.mgr, "01")
            dialog.withdraw()
            self.assertTrue(dialog.btn_run.winfo_exists())
            self.assertEqual(str(dialog.btn_run["state"]), "normal")
        finally:
            root.destroy()

    def test_auto_detects_v1_and_both_session_widths(self):
        for version, count, code in (("V1", 2, None), ("V2", 2, "01"), ("V2", 3, "001"), ("V2", 3, "987")):
            with self.subTest(version=version, code=code):
                ids = detect_sheet_identifiers(self.sheet(version, count, code))
                self.assertTrue(ids.is_valid, ids.review_reasons)
                self.assertEqual(ids.template_version, version)
                self.assertEqual(ids.session_code, code)
                self.assertEqual(ids.sbd, "000001")
                self.assertEqual(ids.exam_code, "101")

    def test_three_digit_session_saved_and_scored_in_correct_session(self):
        item = self.process(self.sheet())
        self.assertEqual(item.status, "SUCCESS", item.error_message)
        self.assertEqual((item.session_code, item.score), ("001", 10.0))
        self.assertEqual(self.mgr.list_results("01"), [])
        self.assertEqual(len(self.mgr.list_results("001")), 1)

    def test_rotated_sheet_scan_resized_and_photo(self):
        rotated = cv2.rotate(self.sheet(), cv2.ROTATE_180)
        photo = simulate_realistic_photo(rotated, random.Random(42), add_shadow=False, add_noise=False)
        for name, sheet in (("scan", rotated), ("resized", cv2.resize(rotated, (800, 1120))), ("photo", photo)):
            with self.subTest(name=name):
                item = self.process(sheet, name + ".png")
                self.assertNotEqual(item.status, "FAILED", item.error_message)
                self.assertEqual((item.session_code, item.sbd, item.exam_code), ("001", "000001", "101"))
                self.assertEqual(item.answers, ["A"] * 50)
                self.assertEqual(item.score, 10.0)

    def test_rotation_disabled_does_not_accept_upside_down_sheet(self):
        item = self.process(cv2.rotate(self.sheet(), cv2.ROTATE_180), allow_rotation_correction=False)
        self.assertEqual(item.status, "FAILED")
        self.assertEqual(self.mgr.list_results("001"), [])

    def test_missing_marker_still_rejected(self):
        sheet = self.sheet()
        x, y = MIDDLE_MARKER_X_LEFT, MARKER_Y_POSITIONS[2]
        cv2.rectangle(sheet, (x - 15, y - 15), (x + 15, y + 15), (255, 255, 255), -1)
        item = self.process(sheet)
        self.assertEqual(item.status, "FAILED")
        self.assertEqual(self.mgr.list_results("001"), [])

    def test_blank_or_multiple_session_never_saved_to_default(self):
        for mode in ("blank", "multiple"):
            with self.subTest(mode=mode):
                sheet = self.sheet(session=None if mode == "blank" else "001")
                if mode == "multiple":
                    cv2.circle(sheet, (SESSION_X_COLS_3[0], DIGIT_Y_ROWS[1]), 8, (20, 20, 20), -1)
                item = self.process(sheet, mode + ".png")
                self.assertEqual(item.status, "NEEDS_REVIEW", item.error_message)
                self.assertIsNone(item.session_code)
                self.assertIsNone(item.result_id)
                self.assertIsNone(item.score)
                self.assertTrue(item.review_reasons)
                self.assertEqual(self.mgr.list_results("01"), [])
                self.assertEqual(self.mgr.list_results("001"), [])

    def test_unknown_session_never_saved_to_default(self):
        item = self.process(self.sheet(session="999"))
        self.assertEqual(item.status, "FAILED")
        self.assertEqual(item.session_code, "999")
        self.assertEqual(self.mgr.list_results("01"), [])

    def test_batch_continues_after_bad_file(self):
        bad = self.base / "broken.png"
        bad.write_bytes(b"not an image")
        good = save_image(self.base / "good.png", self.sheet())
        batch = BatchProcessor(self.mgr, "01", self.base / "out")
        batch.add_files([bad, good])
        results = batch.process_all()
        self.assertEqual([item.status for item in results], ["FAILED", "SUCCESS"])
        self.assertEqual(results[1].score, 10.0)

    def test_single_scan_uses_printed_session_and_rejects_unreadable_session(self):
        from gui.app import OMRApp
        gc.collect()
        with patch("gui.app.SessionManager", return_value=self.mgr), \
             patch.object(OMRApp, "_restore_state"), patch.object(OMRApp, "_save_state"):
            app = OMRApp()
            app.withdraw()
            try:
                app.current_session_code = "01"
                app._image_path = self.base / "scan.png"
                app._on_scan_done({"processed_image": self.sheet(), "answers": ["A"] * 50}, None)
                self.assertEqual(self.mgr.list_results("01"), [])
                self.assertEqual(len(self.mgr.list_results("001")), 1)
                app._on_scan_done({"processed_image": self.sheet(session=None), "answers": ["A"] * 50}, None)
                self.assertEqual(self.mgr.list_results("01"), [])
                self.assertEqual(len(self.mgr.list_results("001")), 1)
                self.assertIn("Chưa lưu", app._lbl_status["text"])
            finally:
                app.destroy()


if __name__ == "__main__":
    unittest.main()
