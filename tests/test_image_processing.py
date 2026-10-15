"""Phase 2: đọc ảnh, giữ tỷ lệ, nhị phân hóa và thông báo lỗi."""

import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from modules.errors import ImageProcessingError
from modules.image_processing import (
    PreprocessConfig, apply_threshold, load_image, preprocess_image, resize_image, save_image,
)


class ImageProcessingTests(unittest.TestCase):
    def test_one_image_and_unicode_path(self) -> None:
        image = np.full((300, 200, 3), 245, np.uint8)
        cv2.circle(image, (100, 150), 12, (15, 15, 15), -1)
        with tempfile.TemporaryDirectory() as folder:
            path = save_image(Path(folder) / "phiếu thử.png", image)
            data = preprocess_image(load_image(path))
        self.assertEqual(data.binary.shape, (300, 200))
        self.assertEqual(int(data.binary[150, 100]), 255)
        self.assertEqual(int(data.binary[30, 30]), 0)
        self.assertTrue(set(np.unique(data.binary)) <= {0, 255})

    def test_resize_keeps_aspect_ratio(self) -> None:
        image = np.zeros((600, 400, 3), np.uint8)
        self.assertEqual(resize_image(image, 300).shape, (300, 200, 3))
        self.assertEqual(resize_image(image, 900).shape, image.shape)

    def test_missing_empty_and_non_image(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bad.png"
            with self.assertRaisesRegex(ImageProcessingError, "không tồn tại"):
                load_image(path)
            path.write_bytes(b"")
            with self.assertRaisesRegex(ImageProcessingError, "không phải ảnh"):
                load_image(path)
            path.write_text("not an image", encoding="utf-8")
            with self.assertRaises(ImageProcessingError):
                load_image(path)

    def test_bad_settings_and_otsu(self) -> None:
        image = np.zeros((100, 100), np.uint8)
        with self.assertRaises(ImageProcessingError):
            preprocess_image(image, PreprocessConfig(blur_kernel=4))
        with self.assertRaises(ImageProcessingError):
            apply_threshold(image, block_size=4)
        with self.assertRaises(ImageProcessingError):
            apply_threshold(image, method="unknown")
        self.assertEqual(apply_threshold(image, method="otsu").shape, image.shape)


if __name__ == "__main__":
    unittest.main()
