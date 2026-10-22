"""Kiểm tra tách nền và màn hình xem lại camera, không cần webcam vật lý."""

import tempfile
import gc
import threading
import time
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np

from gui.app import CameraDialog, OMRApp, ROOT
from main import process_omr
from modules.background_removal import remove_background
from modules.errors import PaperDetectionError
from modules.image_processing import load_image
from tests.test_printed_form import EXPECTED


class BackgroundRemovalTests(unittest.TestCase):
    def test_paper_only_and_original_unchanged(self):
        image = load_image(ROOT / "test_images" / "sample_photo.png")
        original = image.copy()
        cleaned = remove_background(image)
        self.assertEqual(cleaned.shape, (1400, 1000, 3))
        self.assertGreater(float(cleaned[:10].mean()), 230)
        np.testing.assert_array_equal(original, image)

    def test_no_paper_reports_error(self):
        with self.assertRaises(PaperDetectionError):
            remove_background(np.zeros((500, 500, 3), np.uint8))


class CameraBackgroundTests(unittest.TestCase):
    def setUp(self):
        gc.collect()
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.errors = []
        self.root.report_callback_exception = lambda *args: self.errors.append(args)
        self.dialog_patch = patch("gui.app.messagebox.showerror")
        self.showerror = self.dialog_patch.start()
        self.addCleanup(self.dialog_patch.stop)
        with patch.object(CameraDialog, "_start_camera"), patch.object(CameraDialog, "wait_window"):
            self.dialog = CameraDialog(self.root)
        self.dialog.withdraw()
        self.addCleanup(self.close_dialog)
        self.frame = load_image(ROOT / "test_images" / "printed_50_real.png")
        self.dialog._cap = Mock()
        self.dialog._cap.isOpened.return_value = True
        self.dialog._cap.read.return_value = (True, self.frame.copy())
        self.dialog._capture()

    def close_dialog(self):
        if not self.dialog._closed:
            self.dialog._on_close()

    def pump_until(self, predicate):
        deadline = time.monotonic() + 8
        while not predicate():
            if time.monotonic() > deadline:
                self.fail("Camera preview timeout")
            self.root.update()
            time.sleep(.005)
        self.assertEqual(self.errors, [])

    def test_capture_remove_background_use_and_read(self):
        self.assertEqual(str(self.dialog._btn_background["state"]), "normal")
        self.dialog._remove_background()
        self.pump_until(lambda: not self.dialog._background_busy)
        self.assertTrue(self.dialog.background_removed)
        self.assertEqual(self.dialog._frozen_frame.shape, (1400, 1000, 3))
        with tempfile.TemporaryDirectory() as folder, patch("gui.app.CAMERA_DIR", Path(folder)):
            self.dialog._use_image()
            self.assertTrue(self.dialog._closed)
            np.testing.assert_array_equal(load_image(self.dialog.original_path), self.frame)
            result = process_omr(self.dialog.captured_path, already_warped=self.dialog.background_removed)
            self.assertEqual(result["answers"], EXPECTED)
        self.showerror.assert_not_called()

    def test_restore_original_and_retake_reset_mode(self):
        self.dialog._remove_background()
        self.pump_until(lambda: not self.dialog._background_busy)
        self.dialog._restore_original()
        np.testing.assert_array_equal(self.dialog._frozen_frame, self.frame)
        self.assertFalse(self.dialog.background_removed)
        self.dialog._retake()
        self.assertIsNone(self.dialog._frozen_frame)
        self.assertEqual(str(self.dialog._btn_background["state"]), "disabled")

    def test_error_keeps_captured_frame(self):
        with patch("gui.app.remove_background", side_effect=PaperDetectionError("test error")):
            self.dialog._remove_background()
            self.pump_until(lambda: not self.dialog._background_busy)
        np.testing.assert_array_equal(self.dialog._frozen_frame, self.frame)
        self.assertFalse(self.dialog.background_removed)
        self.assertEqual(str(self.dialog._btn_use["state"]), "normal")
        self.showerror.assert_called_once()

    def test_close_during_processing_never_updates_destroyed_widgets(self):
        gate = threading.Event()
        self.addCleanup(gate.set)
        def delayed(image):
            gate.wait(5)
            return image
        with patch("gui.app.remove_background", side_effect=delayed):
            self.dialog._remove_background()
            self.dialog._on_close()
            gate.set()
            self.pump_until(lambda: not self.dialog._background_queue.empty())
        self.assertIsNone(self.dialog._background_poll_id)


class BackgroundStateTests(unittest.TestCase):
    def test_restart_preserves_prepared_mode_and_original_path(self):
        gc.collect()
        source = ROOT / "test_images" / "sample_photo.png"
        def wait(app):
            deadline = time.monotonic() + 8
            while app._busy:
                if time.monotonic() > deadline:
                    self.fail("State restore timeout")
                app.update()
                time.sleep(.005)
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            with patch("gui.app.APP_STATE_PATH", directory / "state.json"), \
                 patch("gui.app.LAST_KEY_PATH", directory / "key.json"), \
                 patch("gui.app.BACKGROUND_DIR", directory / "background"), \
                 patch("gui.app.messagebox.showerror") as error:
                app = OMRApp()
                app.withdraw()
                try:
                    app._load_image_path(source)
                    wait(app)
                    app._remove_background()
                    wait(app)
                    saved_path = app._image_path
                finally:
                    app.destroy()
                reopened = OMRApp()
                reopened.withdraw()
                try:
                    wait(reopened)
                    self.assertTrue(reopened._already_warped)
                    self.assertEqual(reopened._image_path, saved_path)
                    self.assertEqual(reopened._original_image_path, source)
                    reopened._run_scan()
                    wait(reopened)
                    self.assertEqual(reopened._result["answers"], ["ABCD"[i % 4] for i in range(50)])
                finally:
                    reopened.destroy()
                error.assert_not_called()


if __name__ == "__main__":
    unittest.main()
