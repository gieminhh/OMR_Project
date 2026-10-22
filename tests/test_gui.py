"""Hồi quy chọn ảnh/nhận kết quả: chạy Tk ẩn, không sửa state người dùng."""

import os
import subprocess
import sys
import tempfile
import threading
import gc
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from gui.app import OMRApp, ROOT
from modules.errors import ImageProcessingError


class GuiTests(unittest.TestCase):
    def run(self, result=None):
        if os.environ.get("OMR_GUI_TEST_SUBPROCESS") == "1":
            return super().run(result)

        if result is None:
            result = self.defaultTestResult()
        result.startTest(self)

        env = os.environ.copy()
        env["OMR_GUI_TEST_SUBPROCESS"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        try:
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "unittest",
                    "discover",
                    "-s",
                    "tests",
                    "-p",
                    "test_gui.py",
                    "-k",
                    self._testMethodName,
                    "-v",
                ],
                cwd=Path(__file__).resolve().parents[1],
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
                check=False,
            )
            if completed.returncode == 0:
                result.addSuccess(self)
            else:
                error = AssertionError(completed.stdout + completed.stderr)
                try:
                    raise error
                except AssertionError:
                    result.addFailure(self, sys.exc_info())
        except subprocess.TimeoutExpired:
            error = AssertionError("GUI test timed out after 120 seconds")
            try:
                raise error
            except AssertionError:
                result.addFailure(self, sys.exc_info())
        finally:
            result.stopTest(self)
        return result

    def setUp(self):
        # Mỗi test tạo Tcl interpreter riêng; thu hồi interpreter cũ trên main thread.
        gc.collect()
        for target in ("_restore_state", "_save_state"):
            mock = patch.object(OMRApp, target)
            mock.start()
            self.addCleanup(mock.stop)
        dialog = patch("gui.app.messagebox.showerror")
        self.showerror = dialog.start()
        self.addCleanup(dialog.stop)
        self.app = OMRApp()
        self.app.withdraw()
        self.addCleanup(self.close_app)
        self.callback_errors = []
        self.app.report_callback_exception = lambda *error: self.callback_errors.append(error)

    def close_app(self):
        if not self.app._closed:
            self.app.destroy()

    def pump_until(self, predicate, timeout=5):
        deadline = time.monotonic() + timeout
        while not predicate():
            if time.monotonic() >= deadline:
                self.fail("GUI không hoàn tất trong thời gian kiểm thử")
            self.app.update()
            time.sleep(.005)
        self.assertEqual(self.callback_errors, [])

    def test_selection_displays_preview_and_enables_scan(self):
        path = ROOT / "test_images" / "sample_photo.png"
        with patch("gui.app.filedialog.askopenfilename", return_value=str(path)) as picker:
            self.app._pick_image()
        self.assertIs(picker.call_args.kwargs["parent"], self.app)
        self.pump_until(lambda: not self.app._busy)
        self.assertEqual(self.app._image_path, path)
        self.assertIsNotNone(self.app._photo)
        self.assertEqual(str(self.app._btn_scan["state"]), "normal")
        self.showerror.assert_not_called()

    def test_slow_image_load_does_not_block_event_loop(self):
        gate = threading.Event()
        self.addCleanup(gate.set)
        image = np.full((1200, 900, 3), 255, np.uint8)
        def slow_load(_):
            gate.wait(5)
            return image
        heartbeat = []
        with patch("gui.app.load_image", side_effect=slow_load):
            self.app._load_image_path(Path("slow.png"))
            self.app.after(10, lambda: heartbeat.append(True))
            self.pump_until(lambda: bool(heartbeat))
            self.assertTrue(self.app._busy)
            self.assertEqual(str(self.app._btn_scan["state"]), "disabled")
            gate.set()
            self.pump_until(lambda: not self.app._busy)
        self.assertIsNotNone(self.app._photo)

    def test_bad_image_reports_error_and_allows_retry(self):
        with patch("gui.app.load_image", side_effect=ImageProcessingError("Ảnh hỏng")):
            self.app._load_image_path(Path("bad.png"))
            self.pump_until(lambda: not self.app._busy)
        self.showerror.assert_called_once()
        self.assertIn("Ảnh hỏng", self.showerror.call_args.args[1])
        self.assertEqual(str(self.app._btn_img["state"]), "normal")
        self.assertEqual(str(self.app._btn_scan["state"]), "disabled")
        self.assertIsNone(self.app._image_path)

    def test_scan_result_with_numpy_image_populates_50_rows(self):
        self.app._image_path = ROOT / "test_images" / "sample_photo.png"
        self.app._answer_key = ["ABCD"[i % 4] for i in range(50)]
        self.app._run_scan()
        self.pump_until(lambda: not self.app._busy)
        self.assertEqual(len(self.app._tree.get_children()), 50)
        assert self.app._score_result is not None
        self.assertEqual(self.app._score_result["score"], 10)
        self.assertEqual(str(self.app._btn_scan["state"]), "normal")
        self.assertEqual(str(self.app._btn_excel["state"]), "normal")
        self.showerror.assert_not_called()

    def test_scan_error_survives_worker_and_buttons_recover(self):
        self.app._image_path = Path("sample.png")
        with patch("main.process_omr", side_effect=RuntimeError("Không tìm thấy phiếu")):
            self.app._run_scan()
            self.pump_until(lambda: not self.app._busy)
        self.assertIn("Không tìm thấy phiếu", self.showerror.call_args.args[1])
        self.assertEqual(str(self.app._btn_scan["state"]), "normal")
        self.assertEqual(str(self.app._btn_img["state"]), "normal")
        self.assertEqual(str(self.app._btn_excel["state"]), "disabled")

    def test_select_and_scan_real_printed_form(self):
        self.app._load_image_path(ROOT / "test_images" / "printed_50_real.png")
        self.pump_until(lambda: not self.app._busy)
        self.app._run_scan()
        self.pump_until(lambda: not self.app._busy)
        rows = self.app._tree.get_children()
        self.assertEqual(len(rows), 50)
        self.assertEqual(self.app._tree.item(rows[43], "values")[1], "BLANK")
        assert self.app._result is not None
        self.assertEqual(self.app._result["layout_name"], "printed_50")
        self.showerror.assert_not_called()

    def test_display_error_also_restores_buttons(self):
        self.app._image_path = Path("sample.png")
        result = {"annotated_image": np.zeros((20, 20, 3), np.uint8), "answers": ["A"] * 50}
        with patch("main.process_omr", return_value=result), patch.object(self.app, "_show_image", side_effect=ValueError("Preview error")):
            self.app._run_scan()
            self.pump_until(lambda: not self.app._busy)
        self.showerror.assert_called_once()
        self.assertEqual(str(self.app._btn_scan["state"]), "normal")
        self.assertIsNone(self.app._result)

    def test_processed_image_fallback(self):
        self.app._on_scan_done({"processed_image": np.zeros((40, 40, 3), np.uint8), "answers": ["A"] * 50}, None)
        self.assertIsNotNone(self.app._photo)
        self.assertEqual(len(self.app._tree.get_children()), 50)

    def test_cancel_preserves_current_selection(self):
        self.app._image_path = Path("previous.png")
        with patch("gui.app.filedialog.askopenfilename", return_value=""):
            self.app._pick_image()
        self.assertEqual(self.app._image_path, Path("previous.png"))
        self.assertFalse(self.app._busy)

    def test_workers_never_call_tk_even_after_close(self):
        self.app.destroy()
        with patch.object(self.app, "after", side_effect=AssertionError("Worker called Tk")):
            with patch("main.process_omr", side_effect=RuntimeError("late error")):
                worker = threading.Thread(target=self.app._scan_worker, args=(Path("late.png"),))
                worker.start()
                worker.join(timeout=3)
                self.assertFalse(worker.is_alive())
            kind, result, error = self.app._worker_results.get_nowait()
        self.assertEqual(kind, "scan")
        self.assertIsNone(result)
        self.assertEqual(str(error), "late error")


if __name__ == "__main__":
    unittest.main()
