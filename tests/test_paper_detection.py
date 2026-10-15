"""Phase 3: hình học phối cảnh, ảnh không có phiếu, phiếu mất góc."""

import unittest

import numpy as np

from modules.errors import PaperDetectionError
from modules.paper_detection import detect_and_warp_paper, find_paper_contour, order_points
from scripts.generate_samples import SAMPLE_CORNERS, make_sheet, photograph


class PaperDetectionTests(unittest.TestCase):
    def test_orders_shuffled_points(self) -> None:
        expected = np.array([[10, 10], [90, 20], [95, 120], [5, 110]], np.float32)
        np.testing.assert_array_equal(order_points(expected[[2, 0, 3, 1]]), expected)

    def test_rejects_degenerate_points(self) -> None:
        with self.assertRaises(PaperDetectionError):
            order_points(np.zeros((4, 2)))

    def test_photo_warps_to_standard_and_preserves_marks(self) -> None:
        sheet = make_sheet()
        photo = photograph(sheet)
        corners = find_paper_contour(photo)
        self.assertLess(float(np.max(np.linalg.norm(corners - SAMPLE_CORNERS, axis=1))), 5)
        warped = detect_and_warp_paper(photo)
        self.assertEqual(warped.shape, (1400, 1000, 3))
        self.assertLess(float(warped[320, 230].mean()), 50)
        self.assertGreater(float(warped[320, 290].mean()), 200)

    def test_no_paper_and_cropped_paper(self) -> None:
        with self.assertRaises(PaperDetectionError):
            detect_and_warp_paper(np.full((500, 500, 3), 45, np.uint8))
        cropped = photograph(make_sheet())[200:, :]
        with self.assertRaisesRegex(PaperDetectionError, "crop|góc"):
            detect_and_warp_paper(cropped)


if __name__ == "__main__":
    unittest.main()
