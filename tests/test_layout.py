"""Kiểm tra bố cục thật của Tk, giữ cửa sổ trong suốt để không làm phiền người dùng."""

import gc
import unittest
from unittest.mock import patch

import numpy as np

from gui.app import CameraDialog, OMRApp, _fit_window


class LayoutTests(unittest.TestCase):
    def setUp(self):
        gc.collect()
        with patch.object(OMRApp, "_restore_state"):
            self.app = OMRApp()
        self.app.attributes("-alpha", 0)
        self.addCleanup(self.app.destroy)

    def assert_visible(self, widget, window):
        self.assertTrue(widget.winfo_ismapped())
        x = widget.winfo_rootx() - window.winfo_rootx()
        y = widget.winfo_rooty() - window.winfo_rooty()
        self.assertGreaterEqual(x, 0)
        self.assertGreaterEqual(y, 0)
        self.assertLessEqual(x + widget.winfo_width(), window.winfo_width())
        self.assertLessEqual(y + widget.winfo_height(), window.winfo_height())
        self.assertGreaterEqual(widget.winfo_height(), widget.winfo_reqheight())

    def test_main_buttons_stay_visible_at_default_and_small_sizes(self):
        self.app._lbl_info.configure(text="ten_anh_rat_dai_" * 30)
        self.app._set_status("Không tìm được đủ bốn góc phiếu. Vui lòng chọn ảnh khác hoặc chụp lại.")
        for width, height in ((1140, 740), (900, 600), (780, 500)):
            with self.subTest(size=(width, height)):
                self.app.geometry(f"{width}x{height}")
                self.app.update()
                for button in (self.app._btn_img, self.app._btn_camera, self.app._btn_scan,
                               self.app._btn_key_edit, self.app._btn_key_file,
                               self.app._btn_background, self.app._btn_original, self.app._btn_excel):
                    self.assert_visible(button, self.app)
                footer_y = self.app._btn_excel.master.winfo_rooty()
                self.assertLessEqual(self.app._canvas.winfo_rooty() + self.app._canvas.winfo_height(), footer_y)
                self.assertGreater(self.app._tree.winfo_height(), 100)

    def test_preview_fits_when_window_shrinks(self):
        self.app.geometry("1140x740")
        self.app.update()
        self.app._show_image(np.full((1400, 1000, 3), 255, np.uint8))
        self.app.geometry("780x500")
        self.app.update()
        self.assertLessEqual(self.app._photo.width(), self.app._canvas.winfo_width())
        self.assertLessEqual(self.app._photo.height(), self.app._canvas.winfo_height())
        self.assert_visible(self.app._btn_excel, self.app)

    def test_camera_actions_stay_visible_at_small_height(self):
        with patch.object(CameraDialog, "_start_camera"), patch.object(CameraDialog, "wait_window"):
            dialog = CameraDialog(self.app)
        dialog.attributes("-alpha", 0)
        try:
            dialog._show_frame(np.full((1400, 1000, 3), 255, np.uint8))
            for width, height in ((760, 620), (600, 460)):
                with self.subTest(size=(width, height)):
                    dialog.geometry(f"{width}x{height}")
                    dialog.update()
                    for button in (dialog._btn_capture, dialog._btn_retake, dialog._btn_use,
                                   dialog._btn_cancel, dialog._btn_background, dialog._btn_original):
                        self.assert_visible(button, dialog)
                        self.assertGreaterEqual(button.winfo_width(), button.winfo_reqwidth())
                    self.assertLessEqual(dialog._photo.height(), dialog._canvas.winfo_height())
                    self.assertLessEqual(dialog._photo.width(), dialog._canvas.winfo_width())
        finally:
            dialog._on_close()

    def test_initial_size_leaves_room_on_laptop_screen(self):
        with patch.object(self.app, "winfo_screenheight", return_value=768), \
             patch.object(self.app, "winfo_screenwidth", return_value=1366):
            _fit_window(self.app, (1140, 740), (780, 500))
        self.app.update()
        self.assertLessEqual(self.app.winfo_height(), 656)
        self.assert_visible(self.app._btn_excel, self.app)


if __name__ == "__main__":
    unittest.main()
