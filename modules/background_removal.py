"""Tách nền ảnh phiếu bằng tìm bốn góc và hiệu chỉnh phối cảnh OpenCV."""

import numpy as np

from .image_processing import resize_image
from .paper_detection import PaperConfig, detect_and_warp_paper


def remove_background(image: np.ndarray, config: PaperConfig | None = None) -> np.ndarray:
    """Bỏ phần ngoài tờ phiếu, trả ảnh đã căn thẳng (mặc định 1000 × 1400).

    Không thay đổi ảnh đầu vào, không ghi đè tệp và không đọc đáp án.
    Ảnh trả về cần được đọc với already_warped=True để không tìm lại viền
    sát mép ảnh. Không tìm được đủ bốn góc thì báo PaperDetectionError.
    """
    return detect_and_warp_paper(resize_image(image), config)
