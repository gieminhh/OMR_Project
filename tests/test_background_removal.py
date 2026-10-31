"""Kiểm tra chức năng tách nền và nắn phẳng phiếu OMR."""

import unittest
from pathlib import Path

import numpy as np

from modules.background_removal import remove_background
from modules.errors import PaperDetectionError
from modules.image_processing import load_image

ROOT = Path(__file__).resolve().parents[1]


class BackgroundRemovalTests(unittest.TestCase):
    def test_paper_only_and_original_unchanged(self):
        """Tách nền thành công trả về ảnh kích thước chuẩn 1400x1000 và không đổi ảnh gốc."""
        image = load_image(ROOT / "test_images" / "sample_photo.png")
        original = image.copy()
        cleaned = remove_background(image)
        self.assertEqual(cleaned.shape, (1400, 1000, 3))
        self.assertGreater(float(cleaned[:10].mean()), 230)
        np.testing.assert_array_equal(original, image)

    def test_no_paper_reports_error(self):
        """Ảnh đen toàn bộ không có giấy phải báo PaperDetectionError."""
        with self.assertRaises(PaperDetectionError):
            remove_background(np.zeros((500, 500, 3), np.uint8))


if __name__ == "__main__":
    unittest.main()
