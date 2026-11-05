"""Nhận diện các trường số dạng lưới OMR: Số báo danh (SBD), Mã đề, và Đợt thi.

Mỗi trường số gồm N cột (mỗi cột là 1 chữ số), mỗi cột có 10 hàng ô tròn (tương ứng 0..9).
Hỗ trợ:
- Template V1: SBD (6 số) + Mã đề (3 số).
- Template V2: Đợt thi (2 hoặc 3 số) + SBD (6 số) + Mã đề (3 số).
- Tự động xác định phiên bản Template V1 hoặc V2.
- Kiểm tra tô thiếu, tô trùng, không tự suy đoán.
"""

from dataclasses import dataclass
from typing import Literal
import cv2
import numpy as np

from .errors import OMRError
from .image_processing import apply_blur, apply_threshold, to_grayscale

# ── TỌA ĐỘ CHUẨN TRÊN ẢNH ĐÃ CĂN THẲNG (1000 x 1400) ─────────────────────────

# Mã đề: 3 cột, 10 hàng (0..9)
EXAM_CODE_X_COLS = [872, 892, 912]
DIGIT_Y_ROWS = [173, 199, 225, 251, 277, 303, 329, 355, 381, 407]

# Số báo danh: 6 cột, 10 hàng (0..9)
SBD_X_COLS = [728, 748, 768, 788, 808, 828]

# Đợt thi (Template V2): 2 hoặc 3 cột, 10 hàng (0..9)
SESSION_X_COLS_2 = [640, 665]        # 2 số (01, 02...)
SESSION_X_COLS_3 = [620, 645, 670]   # 3 số (001, 002...)

DEFAULT_BUBBLE_RADIUS = 9
DEFAULT_FILL_THRESHOLD = 0.40


@dataclass
class IdentifierFieldResult:
    value: str                   # Chuỗi số đọc được (vd: "001234", "101")
    is_valid: bool               # True nếu tất cả các cột đều đọc được duy nhất 1 số
    fill_ratios: list[list[float]]  # [cột][hàng]
    detected_digits: list[str]   # từng cột: '0'..'9', 'BLANK', 'MULTIPLE'
    error_message: str | None = None


@dataclass
class SheetIdentifiers:
    template_version: str        # "V1" hoặc "V2"
    sbd: str | None              # Số báo danh
    exam_code: str | None        # Mã đề
    session_code: str | None     # Đợt thi
    is_valid: bool               # Cả SBD và Mã đề (và Đợt thi nếu V2) hợp lệ
    review_reasons: list[str]    # Lý do nếu có vấn đề
    annotated_image: np.ndarray  # Ảnh đã vẽ đánh dấu nhận diện


def read_digit_column(
    binary: np.ndarray,
    col_x: int,
    y_rows: list[int],
    radius: int = DEFAULT_BUBBLE_RADIUS,
    fill_threshold: float = DEFAULT_FILL_THRESHOLD,
) -> tuple[str, list[float]]:
    """Đọc 1 cột chữ số (10 hàng 0..9)."""
    h, w = binary.shape
    sample_radius = int(radius * 0.7)
    yy, xx = np.ogrid[-sample_radius : sample_radius + 1, -sample_radius : sample_radius + 1]
    mask = (xx * xx + yy * yy) <= (sample_radius * sample_radius)
    mask_sum = mask.sum()

    ratios = []
    marked_digits = []

    for digit, cy in enumerate(y_rows):
        cx = col_x
        if cx - sample_radius < 0 or cx + sample_radius + 1 > w or cy - sample_radius < 0 or cy + sample_radius + 1 > h:
            ratios.append(0.0)
            continue
        patch = binary[cy - sample_radius : cy + sample_radius + 1, cx - sample_radius : cx + sample_radius + 1]
        ratio = float(np.count_nonzero(patch[mask]) / mask_sum)
        ratios.append(ratio)
        if ratio >= fill_threshold:
            marked_digits.append(str(digit))

    if not marked_digits:
        return "BLANK", ratios
    if len(marked_digits) == 1:
        return marked_digits[0], ratios
    return "MULTIPLE", ratios


def read_number_field(
    binary: np.ndarray,
    col_xs: list[int],
    y_rows: list[int],
    field_name: str = "Trường số",
    radius: int = DEFAULT_BUBBLE_RADIUS,
    fill_threshold: float = DEFAULT_FILL_THRESHOLD,
) -> IdentifierFieldResult:
    """Đọc 1 trường số gồm nhiều cột."""
    digits = []
    all_ratios = []
    is_valid = True
    errors = []

    for idx, cx in enumerate(col_xs, start=1):
        digit, ratios = read_digit_column(binary, cx, y_rows, radius, fill_threshold)
        digits.append(digit)
        all_ratios.append(ratios)
        if digit == "BLANK":
            is_valid = False
            errors.append(f"Cột {idx} bỏ trống")
        elif digit == "MULTIPLE":
            is_valid = False
            errors.append(f"Cột {idx} tô nhiều ô")

    value_str = "".join(d if d.isdigit() else "?" for d in digits)
    err_msg = f"{field_name}: {', '.join(errors)}" if errors else None
    return IdentifierFieldResult(
        value=value_str,
        is_valid=is_valid,
        fill_ratios=all_ratios,
        detected_digits=digits,
        error_message=err_msg,
    )


def check_presence_of_session_field(binary: np.ndarray, col_xs: list[int], y_rows: list[int]) -> bool:
    """Kiểm tra xem trên phiếu có trường Đợt thi (Template V2) hay không.

    Đo độ nét viền hoặc mốc bảng quanh vùng đợt thi.
    """
    h, w = binary.shape
    x_min, x_max = min(col_xs) - 25, max(col_xs) + 25
    y_min, y_max = min(y_rows) - 30, max(y_rows) + 30
    if x_min < 0 or x_max > w or y_min < 0 or y_max > h:
        return False
    patch = binary[y_min:y_max, x_min:x_max]
    # Nếu có bảng hoặc các đường kẻ bảng, số lượng pixel đen sẽ đáng kể
    edge_count = np.count_nonzero(patch)
    area = patch.shape[0] * patch.shape[1]
    # Kiểm tra tỷ lệ nét vẽ trong vùng
    ratio = edge_count / area
    return ratio > 0.04  # Có bảng và các ô


def _session_grid_score(binary: np.ndarray, col_xs: list[int], radius: int) -> float:
    """Đối chiếu viền ô in, không chọn bố cục dựa trên chữ số đã tô."""
    extent = radius + 2
    yy, xx = np.ogrid[-extent:extent + 1, -extent:extent + 1]
    ring = ((xx * xx + yy * yy) >= (radius - 1) ** 2) & (
        (xx * xx + yy * yy) <= (radius + 1) ** 2
    )
    column_scores = []
    for x in col_xs:
        scores = []
        for y in DIGIT_Y_ROWS:
            if x - extent < 0 or y - extent < 0 or x + extent >= binary.shape[1] or y + extent >= binary.shape[0]:
                return 0.0
            patch = binary[y - extent:y + extent + 1, x - extent:x + extent + 1]
            scores.append(float(np.mean(patch[ring] > 0)))
        column_scores.append(float(np.median(scores)))
    return min(column_scores)


def detect_sheet_identifiers(
    warped_image: np.ndarray,
    template_version: Literal["auto", "V1", "V2"] = "auto",
    session_col_count: int | None = None,
    bubble_radius: int = DEFAULT_BUBBLE_RADIUS,
    fill_threshold: float = DEFAULT_FILL_THRESHOLD,
) -> SheetIdentifiers:
    """Nhận diện SBD, Mã đề và Đợt thi trên ảnh phiếu đã căn thẳng."""
    if session_col_count not in (None, 2, 3):
        raise OMRError("Số cột đợt thi chỉ nhận 2, 3 hoặc tự động (None).")
    gray = to_grayscale(warped_image)
    binary = apply_threshold(apply_blur(gray), block_size=51, c=10.0)
    annotated = warped_image.copy()

    # 1. Nhận diện Mã đề (3 số)
    exam_res = read_number_field(binary, EXAM_CODE_X_COLS, DIGIT_Y_ROWS, "Mã đề", bubble_radius, fill_threshold)

    # 2. Nhận diện Số báo danh (6 số)
    sbd_res = read_number_field(binary, SBD_X_COLS, DIGIT_Y_ROWS, "Số báo danh", bubble_radius, fill_threshold)

    # 3. Xác định phiên bản Template V1 hoặc V2
    grids = [SESSION_X_COLS_2, SESSION_X_COLS_3]
    has_session_field = any(check_presence_of_session_field(binary, cols, DIGIT_Y_ROWS) for cols in grids)

    detected_version = template_version
    if template_version == "auto":
        detected_version = "V2" if has_session_field else "V1"

    session_res = None
    session_layout_error = None
    sess_cols = []
    if detected_version == "V2":
        if session_col_count is not None:
            sess_cols = grids[session_col_count - 2]
        else:
            scores = [_session_grid_score(binary, cols, bubble_radius) for cols in grids]
            best = int(np.argmax(scores))
            if scores[best] >= 0.45 and abs(scores[0] - scores[1]) >= 0.15:
                sess_cols = grids[best]
            else:
                session_layout_error = "Đợt thi: không xác định chắc chắn bố cục 2 hay 3 cột."
        if sess_cols:
            session_res = read_number_field(binary, sess_cols, DIGIT_Y_ROWS, "Đợt thi", bubble_radius, fill_threshold)

    # Đánh dấu lên ảnh annotated
    def draw_field(col_xs, field_res, color_ok=(0, 200, 0), color_err=(0, 0, 240)):
        for col_idx, (cx, digit) in enumerate(zip(col_xs, field_res.detected_digits)):
            for r_idx, cy in enumerate(DIGIT_Y_ROWS):
                is_marked = (r_idx < len(field_res.fill_ratios[col_idx]) and
                             field_res.fill_ratios[col_idx][r_idx] >= fill_threshold)
                if is_marked:
                    col = color_ok if digit.isdigit() else color_err
                    cv2.circle(annotated, (cx, cy), bubble_radius + 2, col, 2)
            # Viết số đã nhận diện lên đầu cột
            top_y = DIGIT_Y_ROWS[0] - 20
            txt = digit if digit.isdigit() else "!"
            cv2.putText(annotated, txt, (cx - 5, top_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                        (0, 150, 0) if digit.isdigit() else (0, 0, 220), 2)

    draw_field(EXAM_CODE_X_COLS, exam_res)
    draw_field(SBD_X_COLS, sbd_res)
    if session_res:
        draw_field(sess_cols, session_res)

    # Tổng hợp review reasons
    review_reasons = []
    if session_layout_error:
        review_reasons.append(session_layout_error)
    if not exam_res.is_valid:
        review_reasons.append(exam_res.error_message or "Lỗi đọc mã đề")
    if not sbd_res.is_valid:
        review_reasons.append(sbd_res.error_message or "Lỗi đọc số báo danh")
    if detected_version == "V2" and session_res and not session_res.is_valid:
        review_reasons.append(session_res.error_message or "Lỗi đọc đợt thi")

    is_overall_valid = exam_res.is_valid and sbd_res.is_valid and session_layout_error is None
    if detected_version == "V2" and session_res:
        is_overall_valid = is_overall_valid and session_res.is_valid

    return SheetIdentifiers(
        template_version=detected_version,
        sbd=sbd_res.value if sbd_res.is_valid else None,
        exam_code=exam_res.value if exam_res.is_valid else None,
        session_code=session_res.value if (session_res and session_res.is_valid) else None,
        is_valid=is_overall_valid,
        review_reasons=review_reasons,
        annotated_image=annotated,
    )
