"""Phát hiện tứ giác lớn và hiệu chỉnh phối cảnh (Phase 3)."""

from dataclasses import dataclass

import cv2
import numpy as np

from .errors import PaperDetectionError
from .image_processing import apply_blur, validate_image

STANDARD_SIZE = (1000, 1400)  # width, height
APPROXIMATION_RATIOS = (0.015, 0.025, 0.04)
BACKGROUND_THRESHOLD_FRACTIONS = (0.20, 0.35, 0.50)
MIN_PAPER_SOLIDITY = 0.95


@dataclass(frozen=True)
class PaperConfig:
    """Giới hạn hình học; yêu cầu thấy trọn bốn góc và có nền quanh phiếu."""

    output_size: tuple[int, int] = STANDARD_SIZE
    min_area_ratio: float = 0.15
    border_margin: int = 4
    min_edge_length: float = 60.0
    canny_low: int = 40
    canny_high: int = 140
    close_kernel: int = 5


def order_points(points: np.ndarray) -> np.ndarray:
    """Sắp xếp bốn đỉnh lồi thành TL, TR, BR, BL cho phiếu gần thẳng đứng."""
    points = np.asarray(points, dtype=np.float32)
    if points.size != 8 or not np.isfinite(points).all():
        raise PaperDetectionError("Cần đúng bốn điểm hữu hạn để căn chỉnh phiếu.")
    points = points.reshape(4, 2)
    hull = cv2.convexHull(points).reshape(-1, 2)
    if len(hull) != 4 or cv2.contourArea(hull) < 1:
        raise PaperDetectionError("Bốn góc bị trùng, thẳng hàng hoặc không tạo tứ giác lồi.")
    center = points.mean(axis=0)
    angles = np.arctan2(points[:, 1] - center[1], points[:, 0] - center[0])
    ordered = points[np.argsort(angles)]
    return np.roll(ordered, -int(np.argmin(ordered.sum(axis=1))), axis=0)


def find_paper_contour(
    image: np.ndarray, config: PaperConfig | None = None
) -> np.ndarray:
    """Chọn tứ giác lồi lớn nhất hợp lệ từ cạnh và vùng giấy sáng."""
    config = config or PaperConfig()
    if not 0 < config.min_area_ratio < 1 or config.border_margin < 0:
        raise PaperDetectionError("Cấu hình diện tích/biên phiếu không hợp lệ.")
    if config.close_kernel < 1 or config.close_kernel % 2 == 0:
        raise PaperDetectionError("close_kernel phải là số lẻ dương.")
    gray = apply_blur(image, 5)
    height, width = gray.shape
    edges = cv2.Canny(gray, config.canny_low, config.canny_high)
    edges = cv2.morphologyEx(
        edges, cv2.MORPH_CLOSE, np.ones((config.close_kernel, config.close_kernel), np.uint8)
    )
    bright = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
    candidates = []
    for mask in (edges, bright):
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        candidates.extend(contours)
    # Vải có họa tiết nối với giấy ở ngưỡng Otsu. Tách các cầu nối mảnh
    # ở nhiều mức sáng; chỉ bù các vết lõm nhỏ khi contour gần lồi.
    smooth_kernel = max(3, round(min(width, height) * 0.009) | 1)
    smooth = apply_blur(image, smooth_kernel)
    otsu, _ = cv2.threshold(smooth, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    kernel_size = max(3, round(min(width, height) * 0.013) | 1)
    for fraction in BACKGROUND_THRESHOLD_FRACTIONS:
        cutoff = otsu + fraction * (255 - otsu)
        mask = cv2.threshold(smooth, cutoff, 255, cv2.THRESH_BINARY)[1]
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((kernel_size, kernel_size), np.uint8))
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < config.min_area_ratio * width * height:
                continue
            hull = cv2.convexHull(contour)
            if area / max(cv2.contourArea(hull), 1) >= MIN_PAPER_SOLIDITY:
                candidates.append(hull)
    candidates.sort(key=cv2.contourArea, reverse=True)
    touches_border = False
    for contour in candidates:
        if cv2.contourArea(contour) < config.min_area_ratio * width * height:
            continue
        vertices = contour.reshape(-1, 2)
        margin = config.border_margin
        if (
            (vertices[:, 0] <= margin).any() or (vertices[:, 0] >= width - 1 - margin).any()
            or (vertices[:, 1] <= margin).any() or (vertices[:, 1] >= height - 1 - margin).any()
        ):
            touches_border = True
            continue
        perimeter = cv2.arcLength(contour, True)
        for ratio in APPROXIMATION_RATIOS:
            polygon = cv2.approxPolyDP(contour, ratio * perimeter, True)
            if len(polygon) != 4 or not cv2.isContourConvex(polygon):
                continue
            if cv2.contourArea(polygon) < config.min_area_ratio * width * height:
                continue
            points = order_points(polygon)
            lengths = np.linalg.norm(points - np.roll(points, -1, axis=0), axis=1)
            if lengths.min() >= config.min_edge_length:
                return points
    if touches_border:
        raise PaperDetectionError(
            "Chưa tách được bốn góc phiếu khỏi nền. Có vùng sáng nối tới mép ảnh; "
            "điều này không nhất thiết nghĩa là phiếu bị crop. "
            "Hãy kiểm tra nền, ánh sáng và bốn góc phiếu."
        )
    raise PaperDetectionError("Không tìm được contour phiếu dạng tứ giác đủ lớn và rõ bốn góc.")


def four_point_transform(
    image: np.ndarray, points: np.ndarray, output_size: tuple[int, int] = STANDARD_SIZE
) -> np.ndarray:
    """Warp ảnh về kích thước (width, height) cố định."""
    validate_image(image)
    if len(output_size) != 2 or any(not isinstance(n, int) or n < 3 for n in output_size):
        raise PaperDetectionError("Kích thước ảnh chuẩn phải gồm hai số nguyên >= 3.")
    ordered = order_points(points)
    height, width = image.shape[:2]
    if (ordered < 0).any() or (ordered[:, 0] >= width).any() or (ordered[:, 1] >= height).any():
        raise PaperDetectionError("Góc phiếu nằm ngoài ảnh; ảnh có thể bị crop.")
    target_width, target_height = output_size
    destination = np.array(
        [[0, 0], [target_width - 1, 0], [target_width - 1, target_height - 1], [0, target_height - 1]],
        dtype=np.float32,
    )
    matrix = cv2.getPerspectiveTransform(ordered, destination)
    return cv2.warpPerspective(image, matrix, output_size, flags=cv2.INTER_LINEAR)


def detect_and_warp_paper(
    image: np.ndarray, config: PaperConfig | None = None
) -> np.ndarray:
    """Trả ảnh phiếu đã căn thẳng hoặc PaperDetectionError có thông báo."""
    config = config or PaperConfig()
    return four_point_transform(image, find_paper_contour(image, config), config.output_size)
