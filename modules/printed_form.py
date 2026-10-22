"""Định vị mẫu in 50 câu có hai dãy ô vuông đen giữa hai cột.

Chỉ nhận mẫu có 6 cặp mốc (5 nhóm, mỗi nhóm 5 câu) và hai mốc ngoài
ở đầu bảng. Không dùng ô đã tô để suy ra layout hoặc đáp án.
"""

from dataclasses import replace
import json
from pathlib import Path

import cv2
import numpy as np

from .answer_detection import AnswerConfig, validate_config
from .errors import AnswerDetectionError
from .image_processing import to_grayscale

PROFILE_PATH = Path(__file__).resolve().parents[1] / "config" / "printed_50.json"


def detect_printed_layout(image: np.ndarray) -> AnswerConfig | None:
    """Trả layout theo mốc in hoặc None khi không có dấu hiệu mẫu này.

    Nếu đã thấy hai dãy mốc nhưng thiếu/lệch mốc, báo lỗi thay vì đoán vị trí.
    Tọa độ và tỷ lệ riêng của mẫu được đặt trong config/printed_50.json.
    """
    try:
        profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise AnswerDetectionError(f"Không đọc được cấu hình mẫu phiếu in: {exc}") from exc
    gray = to_grayscale(image)
    height, width = gray.shape
    scale = width / profile["reference_width"]
    otsu, _ = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    cutoff = float(np.clip(otsu * profile["marker_threshold_ratio"], 40, 120))
    mask = cv2.threshold(gray, cutoff, 255, cv2.THRESH_BINARY_INV)[1]
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    markers = []
    low, high = np.asarray(profile["marker_size_range"]) * scale
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if low <= w <= high and low <= h <= high and 0.8 <= w / h <= 1.25:
            if cv2.contourArea(contour) / (w * h) >= profile["marker_min_extent"]:
                markers.append((x + w / 2, y + h / 2))
    bands = profile["middle_marker_x_bands"]
    ymin, ymax = np.array(profile["marker_y_band"]) * height
    groups = []
    for xmin, xmax in bands:
        group = [point for point in markers if xmin * width < point[0] < xmax * width and ymin < point[1] < ymax]
        groups.append(np.array(sorted(group, key=lambda point: point[1])))
    if min(map(len, groups)) < 3:
        return None
    if any(len(group) != 6 for group in groups):
        raise AnswerDetectionError("Nhận ra mẫu phiếu in nhưng thiếu mốc đen giữa hai cột; cần đủ 6 cặp mốc.")
    left, right = groups
    tolerance = profile["marker_alignment_tolerance"] * scale
    if np.max(np.abs(left[:, 1] - right[:, 1])) > tolerance:
        raise AnswerDetectionError("Các mốc đen hai cột không thẳng hàng; kiểm tra phiếu cong hoặc góc chụp.")
    for group in groups:
        gaps = np.diff(group[:, 1])
        if gaps.min() < height * .07 or gaps.max() / gaps.min() > 1.3:
            raise AnswerDetectionError("Khoảng cách mốc đen không phù hợp mẫu 50 câu.")
    outer = []
    for (xmin, xmax), group in zip(profile["outer_marker_x_bands"], groups):
        matches = [p for p in markers if xmin * width < p[0] < xmax * width and abs(p[1] - group[0, 1]) < tolerance]
        if len(matches) != 1:
            raise AnswerDetectionError("Không tìm đủ hai mốc đen ngoài ở đầu vùng trả lời.")
        outer.append(matches[0])
    spans = (left[0, 0] - outer[0][0], outer[1][0] - right[0, 0])
    if min(spans) < width * .25 or max(spans) / min(spans) > 1.15:
        raise AnswerDetectionError("Bề rộng hai cột đáp án không phù hợp mẫu phiếu in.")
    centers = []
    for column, group in enumerate(groups):
        for row in range(25):
            block, offset = divmod(row, 5)
            fraction = (offset + .5) / 5
            anchor = group[block] * (1 - fraction) + group[block + 1] * fraction
            row_centers = []
            for position in profile["choice_fractions"]:
                x = round(anchor[0] + (position - (1 if column == 0 else 0)) * spans[column])
                row_centers.append((x, round(anchor[1])))
            centers.append(tuple(row_centers))
    radius = round(profile["bubble_radius"] * scale)
    search = round(profile["center_search_radius"] * scale)
    points = np.asarray(centers)
    padding = radius * 2 + search + 2
    min_x, min_y = points.reshape(-1, 2).min(axis=0) - padding
    max_x, max_y = points.reshape(-1, 2).max(axis=0) + padding + 1
    region = (max(0, int(min_x)), max(0, int(min_y)), min(width, int(max_x)), min(height, int(max_y)))
    columns = []
    for block in (points[:25], points[25:]):
        xs = block[..., 0]
        columns.append((int(xs.min() - 20 * scale), region[1], int(xs.max() + 20 * scale), region[3]))
    config = replace(
        AnswerConfig(), paper_size=(width, height), answer_region=region, columns=tuple(columns),
        bubble_radius=radius, centers=tuple(centers), center_search_radius=search,
        ring_threshold_c=profile["ring_threshold_c"], fill_threshold=profile["fill_threshold"],
    )
    validate_config(config)
    return config
