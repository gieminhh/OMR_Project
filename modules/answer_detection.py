"""Đọc 2 cột × 25 hàng × 4 ô theo vị trí và tỷ lệ mực, không OCR.

Tọa độ config là pixel trên ảnh đã warp; các hộp dùng [x0, y0, x1, y1].
Mặc định trả đúng 50 phần tử. question_count chỉ dành cho kiểm thử 5/10 câu.
"""

import json
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from .errors import AnswerDetectionError, ImageProcessingError
from .image_processing import apply_blur, apply_threshold, to_grayscale, validate_image

CHOICES = ("A", "B", "C", "D")
QUESTION_COUNT = 50
DEBUG_FONT_SCALE = 0.32
COLOR_MARKED = (30, 150, 30)
COLOR_EMPTY = (180, 100, 0)
COLOR_AMBIGUOUS = (0, 100, 240)


@dataclass(frozen=True)
class AnswerConfig:
    """Layout mẫu; thay bằng config phù hợp trước khi dùng phiếu thật."""

    paper_size: tuple[int, int] = (1000, 1400)
    answer_region: tuple[int, int, int, int] = (120, 250, 930, 1330)
    columns: tuple[tuple[int, int, int, int], ...] = ((200, 300, 440, 1300), (630, 300, 870, 1300))
    rows_per_column: int = 25
    column_margin: tuple[int, int] = (0, 0)
    bubble_radius: int = 12
    sample_radius_ratio: float = 0.65
    fill_threshold: float = 0.45
    threshold_block_size: int = 51
    threshold_c: float = 12.0
    ring_inner_ratio: float = 0.8
    ring_outer_ratio: float = 1.2
    min_ring_ink_ratio: float = 0.25
    min_visible_bubble_fraction: float = 0.85
    centers: tuple | None = None
    center_search_radius: int = 0
    ring_threshold_c: float | None = None


@dataclass
class AnswerDetectionResult:
    """Đáp án cùng số đo thô và ảnh đánh dấu để hiệu chỉnh layout."""

    answers: list[str]
    fill_ratios: list[list[float]]
    ring_ratios: list[list[float]]
    answer_region_image: np.ndarray
    annotated_image: np.ndarray


def validate_config(config: AnswerConfig) -> None:
    """Từ chối layout sai hoặc bubble tràn khỏi ô trước khi xử lý."""
    try:
        width, height = config.paper_size
        if any(type(n) is not int or n < 3 for n in (width, height)):
            raise ValueError("paper_size phải gồm hai số nguyên >= 3")
        if type(config.rows_per_column) is not int or config.rows_per_column != 25 or len(config.columns) != 2:
            raise ValueError("layout phải có hai cột, mỗi cột 25 hàng")
        mx, my = config.column_margin
        if any(type(n) is not int or n < 0 for n in (mx, my)):
            raise ValueError("column_margin phải là hai số nguyên không âm")
        if type(config.bubble_radius) is not int or config.bubble_radius < 3:
            raise ValueError("bubble_radius phải là số nguyên >= 3")
        for name in ("sample_radius_ratio", "fill_threshold", "min_ring_ink_ratio", "min_visible_bubble_fraction"):
            value = getattr(config, name)
            if not isinstance(value, (int, float)) or not 0 < value <= 1:
                raise ValueError(f"{name} phải nằm trong (0, 1]")
        if not 0 < config.sample_radius_ratio < config.ring_inner_ratio < 1 < config.ring_outer_ratio <= 2:
            raise ValueError("bán kính lấy mẫu phải nhỏ hơn vành kiểm tra viền ô")
        block = config.threshold_block_size
        if type(block) is not int or block < 3 or block % 2 == 0 or block > min(width, height):
            raise ValueError("threshold_block_size phải lẻ, >= 3 và không lớn hơn ảnh")
        if not np.isfinite(config.threshold_c):
            raise ValueError("threshold_c phải hữu hạn")
        if type(config.center_search_radius) is not int or not 0 <= config.center_search_radius <= config.bubble_radius:
            raise ValueError("center_search_radius phải là số nguyên từ 0 đến bubble_radius")
        if config.ring_threshold_c is not None and not np.isfinite(config.ring_threshold_c):
            raise ValueError("ring_threshold_c phải hữu hạn")
        boxes = [config.answer_region, *config.columns]
        for box in boxes:
            x0, y0, x1, y1 = box
            if any(type(n) is not int for n in box) or not (0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height):
                raise ValueError("hộp tọa độ phải là số nguyên và nằm trong ảnh chuẩn")
        rx0, ry0, rx1, ry1 = config.answer_region
        for x0, y0, x1, y1 in config.columns:
            if not (rx0 <= x0 < x1 <= rx1 and ry0 <= y0 < y1 <= ry1):
                raise ValueError("hai cột phải nằm trong answer_region")
            cell_width = (x1 - x0 - 2 * mx) / len(CHOICES)
            cell_height = (y1 - y0 - 2 * my) / config.rows_per_column
            if min(cell_width, cell_height) <= 2 * np.ceil(config.bubble_radius * config.ring_outer_ratio):
                raise ValueError("ô quá nhỏ so với bubble_radius hoặc margin")
        left, right = config.columns
        if left[2] > right[0]:
            raise ValueError("cột 1–25 phải nằm bên trái và không chồng cột 26–50")
        if config.centers is not None:
            centers = np.asarray(config.centers, dtype=float)
            if centers.shape != (50, 4, 2) or not np.isfinite(centers).all():
                raise ValueError("centers cần đúng 50 hàng × 4 ô × 2 tọa độ hữu hạn")
            padding = np.ceil(config.bubble_radius * config.ring_outer_ratio) + config.center_search_radius
            if (centers[..., 0] < rx0 + padding).any() or (centers[..., 0] >= rx1 - padding).any() or (
                centers[..., 1] < ry0 + padding).any() or (centers[..., 1] >= ry1 - padding).any():
                raise ValueError("centers và vùng tìm kiếm phải nằm trong answer_region")
    except (TypeError, ValueError, OverflowError) as exc:
        raise AnswerDetectionError(f"Cấu hình layout không hợp lệ: {exc}") from exc


def load_layout(path: str | Path) -> AnswerConfig:
    """Đọc JSON; cấm khóa lạ để phát hiện lỗi gõ tên cấu hình."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("nội dung layout phải là JSON object")
        config = AnswerConfig(**data)
        validate_config(config)
        return config
    except (OSError, ValueError, TypeError) as exc:
        raise AnswerDetectionError(f"Không đọc được layout {path}: {exc}") from exc


def bubble_centers(config: AnswerConfig) -> list[list[tuple[int, int]]]:
    """Lần lượt từ trên xuống cột trái (1–25), rồi cột phải (26–50)."""
    validate_config(config)
    if config.centers is not None:
        return [[(round(x), round(y)) for x, y in row] for row in config.centers]
    mx, my = config.column_margin
    centers = []
    for x0, y0, x1, y1 in config.columns:
        cell_width = (x1 - x0 - 2 * mx) / len(CHOICES)
        cell_height = (y1 - y0 - 2 * my) / config.rows_per_column
        for row in range(config.rows_per_column):
            y = round(y0 + my + (row + 0.5) * cell_height)
            centers.append([(round(x0 + mx + (choice + 0.5) * cell_width), y) for choice in range(4)])
    return centers


def classify_ratios(ratios: list[float], fill_threshold: float) -> str:
    """Không ép chọn đáp án khi chưa tô hoặc có nhiều ô vượt ngưỡng."""
    selected = [label for label, ratio in zip(CHOICES, ratios) if ratio >= fill_threshold]
    if not selected:
        return "BLANK"
    return selected[0] if len(selected) == 1 else "MULTIPLE"


def analyze_answers(
    warped_image: np.ndarray, config: AnswerConfig | None = None, *, question_count: int = QUESTION_COUNT
) -> AnswerDetectionResult:
    """Đo mực trong lòng ô; kiểm tra viền bubble để từ chối layout lệch.

    Việc kiểm tra viền giúp phân biệt phiếu trắng với giấy không có mẫu OMR.
    Đây không phải bộ tự tìm layout; config phải khớp mẫu phiếu đã warp.
    """
    config = config or AnswerConfig()
    validate_config(config)
    validate_image(warped_image)
    if tuple(warped_image.shape[:2][::-1]) != tuple(config.paper_size):
        raise AnswerDetectionError(f"Ảnh phải được warp về kích thước {config.paper_size} trước khi đọc.")
    if type(question_count) is not int or question_count not in (5, 10, QUESTION_COUNT):
        raise AnswerDetectionError("question_count chỉ nhận 5, 10 hoặc 50; mặc định là 50.")
    gray = to_grayscale(warped_image)
    try:
        binary = apply_threshold(apply_blur(gray), block_size=config.threshold_block_size, c=config.threshold_c)
    except ImageProcessingError as exc:
        raise AnswerDetectionError(f"Không nhị phân hóa được vùng đáp án: {exc}") from exc
    x0, y0, x1, y1 = config.answer_region
    cropped = warped_image[y0:y1, x0:x1].copy()
    binary_region = binary[y0:y1, x0:x1]
    ring_binary = binary if config.ring_threshold_c is None else apply_threshold(
        apply_blur(gray), block_size=config.threshold_block_size, c=config.ring_threshold_c
    )
    ring_region = ring_binary[y0:y1, x0:x1]
    annotated = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    radius = config.bubble_radius
    outer_radius = int(np.ceil(radius * config.ring_outer_ratio))
    yy, xx = np.ogrid[-outer_radius:outer_radius + 1, -outer_radius:outer_radius + 1]
    distance_squared = xx * xx + yy * yy
    sample_mask = distance_squared <= (radius * config.sample_radius_ratio) ** 2
    ring_mask = (distance_squared >= (radius * config.ring_inner_ratio) ** 2) & (
        distance_squared <= (radius * config.ring_outer_ratio) ** 2
    )
    fill_ratios, ring_ratios, answers = [], [], []
    centers = bubble_centers(config)[:question_count]
    for question, row in enumerate(centers, start=1):
        if config.center_search_radius:
            row = [_refine_center(center, ring_binary, ring_mask, outer_radius, config.center_search_radius) for center in row]
        fills, rings = [], []
        for x, y in row:
            cx, cy = x - x0, y - y0
            patch = binary_region[cy - outer_radius:cy + outer_radius + 1, cx - outer_radius:cx + outer_radius + 1]
            if patch.shape != sample_mask.shape:
                raise AnswerDetectionError(f"Vùng bubble câu {question} bị cắt; kiểm tra answer_region.")
            fills.append(float(np.count_nonzero(patch[sample_mask]) / sample_mask.sum()))
            ring_patch = ring_region[cy - outer_radius:cy + outer_radius + 1, cx - outer_radius:cx + outer_radius + 1]
            rings.append(float(np.count_nonzero(ring_patch[ring_mask]) / ring_mask.sum()))
        answer = classify_ratios(fills, config.fill_threshold)
        answers.append(answer)
        fill_ratios.append(fills)
        ring_ratios.append(rings)
        for label, center, ratio in zip(CHOICES, row, fills):
            marked = ratio >= config.fill_threshold
            color = COLOR_AMBIGUOUS if answer == "MULTIPLE" and marked else COLOR_MARKED if marked else COLOR_EMPTY
            cv2.circle(annotated, center, radius, color, 2)
            cv2.putText(annotated, f"{label}:{ratio:.2f}", (center[0] - radius, center[1] - radius - 3),
                        cv2.FONT_HERSHEY_SIMPLEX, DEBUG_FONT_SCALE, color, 1, cv2.LINE_AA)
        cv2.putText(annotated, f"{question:02} {answer}", (row[-1][0] + radius + 12, row[-1][1] + 5),
                    cv2.FONT_HERSHEY_SIMPLEX, DEBUG_FONT_SCALE, (0, 0, 180), 1, cv2.LINE_AA)
    visibility = np.asarray(ring_ratios) >= config.min_ring_ink_ratio
    if float(visibility.mean()) < config.min_visible_bubble_fraction:
        raise AnswerDetectionError(
            f"Không xác định được vùng đáp án: chỉ {visibility.mean():.0%} viền ô khớp layout. "
            "Kiểm tra chiều phiếu, tọa độ columns, bubble_radius và ảnh đã warp."
        )
    cv2.rectangle(annotated, (x0, y0), (x1 - 1, y1 - 1), (180, 0, 180), 1)
    return AnswerDetectionResult(answers, fill_ratios, ring_ratios, cropped, annotated)


def _refine_center(
    center: tuple[int, int], binary: np.ndarray, ring_mask: np.ndarray, radius: int, search: int
) -> tuple[int, int]:
    """Tìm viền ô gần vị trí marker dự đoán; phạt dịch xa để tránh nhảy hàng."""
    x, y = center
    best_score, best_center = -float("inf"), center
    distance_penalty = 0.004
    for dy in range(-search, search + 1):
        for dx in range(-search, search + 1):
            cx, cy = x + dx, y + dy
            patch = binary[cy - radius:cy + radius + 1, cx - radius:cx + radius + 1]
            if patch.shape != ring_mask.shape:
                continue
            ratio = np.count_nonzero(patch[ring_mask]) / ring_mask.sum()
            score = ratio - distance_penalty * (dx * dx + dy * dy)
            if score > best_score:
                best_score, best_center = score, (cx, cy)
    return best_center


def detect_answers(
    warped_image: np.ndarray, config: AnswerConfig | None = None, *, question_count: int = QUESTION_COUNT
) -> list[str]:
    """API trả list A/B/C/D/BLANK/MULTIPLE, mặc định đúng 50 phần tử."""
    return analyze_answers(warped_image, config, question_count=question_count).answers
