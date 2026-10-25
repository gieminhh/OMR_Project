"""Tạo mẫu phiếu trắc nghiệm A4/PDF chuẩn in ấn OMR.

Hỗ trợ:
- Template V1: 50 câu 2 cột có mốc định vị, bảng Số báo danh và Mã đề.
- Template V2: Có thêm bảng Đợt thi (2 hoặc 3 cột 0..9).
- Xuất ảnh PNG/JPG hoặc PDF A4 chất lượng cao.
- Có thể tạo phiếu trắng hoặc phiếu đã tô (cho dữ liệu test).
- Tương thích 100% với thuật toán OMR của hệ thống.
"""

from pathlib import Path
from typing import Literal
import cv2
import numpy as np
from PIL import Image

from .bubble_id_detection import (
    DEFAULT_BUBBLE_RADIUS,
    DIGIT_Y_ROWS,
    EXAM_CODE_X_COLS,
    SBD_X_COLS,
    SESSION_X_COLS_2,
    SESSION_X_COLS_3,
)

SHEET_WIDTH = 1000
SHEET_HEIGHT = 1400

# Mốc định vị chuẩn cho mẫu printed_50
# 6 cặp mốc đen ở giữa (cột trái x ~ 455, cột phải x ~ 545)
# 2 mốc đen ngoài ở đầu vùng trả lời (x ~ 125 và x ~ 875)
MARKER_SIZE = 18
MIDDLE_MARKER_X_LEFT = 458
MIDDLE_MARKER_X_RIGHT = 542
OUTER_MARKER_X_LEFT = 125
OUTER_MARKER_X_RIGHT = 875
MARKER_Y_POSITIONS = [535, 690, 845, 1000, 1155, 1310]


def _draw_marker(image: np.ndarray, cx: int, cy: int, size: int = MARKER_SIZE) -> None:
    """Vẽ mốc đen vuông định vị."""
    half = size // 2
    cv2.rectangle(image, (cx - half, cy - half), (cx + half, cy + half), (0, 0, 0), -1)


def _draw_number_grid(
    sheet: np.ndarray,
    col_xs: list[int],
    y_rows: list[int],
    title: str,
    box_rect: tuple[int, int, int, int],
    filled_digits: str | None = None,
    bubble_radius: int = DEFAULT_BUBBLE_RADIUS,
) -> None:
    """Vẽ bảng tô số (Đợt thi, SBD, Mã đề) gồm ô chữ số viết tay và 10 hàng ô tròn 0..9."""
    bx, by, bw, bh = box_rect
    # Khung ngoài
    cv2.rectangle(sheet, (bx, by), (bx + bw, by + bh), (0, 0, 0), 2)
    # Tiêu đề
    cv2.rectangle(sheet, (bx, by), (bx + bw, by + 22), (235, 235, 235), -1)
    cv2.line(sheet, (bx, by + 22), (bx + bw, by + 22), (0, 0, 0), 2)
    t_size = cv2.getTextSize(title, cv2.FONT_HERSHEY_SIMPLEX, 0.40, 1)[0]
    tx = bx + (bw - t_size[0]) // 2
    cv2.putText(sheet, title, (tx, by + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (0, 0, 0), 1, cv2.LINE_AA)

    # Ô viết tay
    cell_w = bw // len(col_xs)
    hand_y = by + 22
    hand_h = 26
    cv2.line(sheet, (bx, hand_y + hand_h), (bx + bw, hand_y + hand_h), (0, 0, 0), 2)

    filled_chars = list(filled_digits) if filled_digits else []
    while len(filled_chars) < len(col_xs):
        filled_chars.append("")

    for i, cx in enumerate(col_xs):
        left_x = bx + i * cell_w
        if i > 0:
            cv2.line(sheet, (left_x, hand_y), (left_x, hand_y + hand_h), (0, 0, 0), 1)
        # Nếu có chữ số viết tay mẫu
        ch = filled_chars[i]
        if ch.isdigit():
            cv2.putText(sheet, ch, (cx - 5, hand_y + 19), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 2)

    # Các ô tròn 0..9
    for r_idx, cy in enumerate(y_rows):
        for c_idx, cx in enumerate(col_xs):
            cv2.circle(sheet, (cx, cy), bubble_radius, (0, 0, 0), 1, cv2.LINE_AA)
            cv2.putText(sheet, str(r_idx), (cx - 4, cy + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (160, 160, 160), 1, cv2.LINE_AA)
            # Nếu tô ô này
            if filled_chars[c_idx] == str(r_idx):
                cv2.circle(sheet, (cx, cy), bubble_radius - 1, (20, 20, 20), -1, cv2.LINE_AA)


def generate_sheet(
    template_version: Literal["V1", "V2"] = "V2",
    session_col_count: int = 2,
    exam_title: str = "PHIẾU TRẢ LỜI TRẮC NGHIỆM",
    subject: str = "BÀI THI TỔNG HỢP",
    session_code: str | None = None,
    sbd: str | None = None,
    exam_code: str | None = None,
    answers: list[str] | None = None,
) -> np.ndarray:
    """Tạo ảnh phiếu OMR kích thước chuẩn 1000x1400."""
    sheet = np.full((SHEET_HEIGHT, SHEET_WIDTH, 3), 255, dtype=np.uint8)

    # 1. Tiêu đề phiếu (không vẽ khung chữ nhật bao kín toàn tờ giấy để không cản trở OMR markers)
    cv2.putText(sheet, "BỘ GIÁO DỤC VÀ ĐÀO TẠO", (70, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2, cv2.LINE_AA)
    cv2.putText(sheet, exam_title, (70, 95), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2, cv2.LINE_AA)
    cv2.putText(sheet, f"Môn thi: {subject}", (70, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 1, cv2.LINE_AA)

    # Khung thông tin thí sinh (bên trái)
    cv2.rectangle(sheet, (70, 105), (550, 425), (0, 0, 0), 1)
    fields = [
        "1. Họ và tên thí sinh: ................................................................",
        "2. Ngày sinh: ........ / ........ / ................   Giới tính: ....................",
        "3. Lớp: ........................ Trường: .............................................",
        "4. Phòng thi số: ................... Số CMND/CCCD: .........................",
        "5. Chữ ký thí sinh: .................... Chữ ký GT 1: .........................",
        "HƯỚNG DẪN TÔ:",
        "[X] Đúng: Tô kín ô tròn   [ ] Sai: Không gạch chéo, không đánh dấu v",
    ]
    # Giới hạn chữ trong khung thông tin; chữ dài không được đè lên ô tô số.
    info_region = sheet[106:425, 71:550]
    for idx, fld in enumerate(fields):
        y_pos = 135 + idx * 38
        if idx >= 5:
            cv2.putText(info_region, fld, (14, y_pos - 106), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (60, 60, 60), 1, cv2.LINE_AA)
        else:
            cv2.putText(info_region, fld, (14, y_pos - 106), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1, cv2.LINE_AA)

    # 2. Bảng Mã đề (3 cột)
    _draw_number_grid(sheet, EXAM_CODE_X_COLS, DIGIT_Y_ROWS, "MÃ ĐỀ THI", (855, 105, 75, 320), exam_code)

    # 3. Bảng Số báo danh (6 cột)
    _draw_number_grid(sheet, SBD_X_COLS, DIGIT_Y_ROWS, "SỐ BÁO DANH", (710, 105, 135, 320), sbd)

    # 4. Bảng Đợt thi nếu là Template V2 (2 hoặc 3 cột)
    if template_version == "V2":
        sess_cols = SESSION_X_COLS_3 if session_col_count == 3 else SESSION_X_COLS_2
        bw = 85 if session_col_count == 3 else 65
        bx = 615 if session_col_count == 3 else 635
        _draw_number_grid(sheet, sess_cols, DIGIT_Y_ROWS, "ĐỢT THI", (bx, 105, bw, 320), session_code)

    # 5. Mốc định vị OMR
    # Mốc ngoài ở đầu bảng
    _draw_marker(sheet, OUTER_MARKER_X_LEFT, MARKER_Y_POSITIONS[0])
    _draw_marker(sheet, OUTER_MARKER_X_RIGHT, MARKER_Y_POSITIONS[0])

    # 6 cặp mốc giữa hai cột
    for y_mark in MARKER_Y_POSITIONS:
        _draw_marker(sheet, MIDDLE_MARKER_X_LEFT, y_mark)
        _draw_marker(sheet, MIDDLE_MARKER_X_RIGHT, y_mark)

    # 6. Vùng 50 câu trả lời OMR
    cv2.putText(sheet, "PHẦN TRẢ LỜI CÂU HỎI TRẮC NGHIỆM", (280, 480), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 0), 2, cv2.LINE_AA)

    ans_list = answers or []
    while len(ans_list) < 50:
        ans_list.append("BLANK")

    # Tính toán tọa độ tâm ô tròn khớp 100% với profile printed_50
    left_span = MIDDLE_MARKER_X_LEFT - OUTER_MARKER_X_LEFT
    right_span = OUTER_MARKER_X_RIGHT - MIDDLE_MARKER_X_RIGHT
    choice_fractions = [0.32, 0.505, 0.69, 0.875]

    for column, (marker_x, span) in enumerate([(MIDDLE_MARKER_X_LEFT, left_span), (MIDDLE_MARKER_X_RIGHT, right_span)]):
        for row in range(25):
            q_num = column * 25 + row + 1
            block, offset = divmod(row, 5)
            frac = (offset + 0.5) / 5.0
            y_center = int(round(MARKER_Y_POSITIONS[block] * (1 - frac) + MARKER_Y_POSITIONS[block + 1] * frac))

            row_centers = []
            for position in choice_fractions:
                shift = (position - 1) * span if column == 0 else position * span
                row_centers.append((int(round(marker_x + shift)), y_center))

            # Số thứ tự câu hỏi
            first_cx = row_centers[0][0]
            cv2.putText(sheet, f"{q_num:02d}", (first_cx - 45, y_center + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 0, 0), 1, cv2.LINE_AA)

            # Tiêu đề cột A, B, C, D (vẽ ở hàng đầu tiên)
            if row == 0:
                for c_idx, letter in enumerate("ABCD"):
                    cv2.putText(sheet, letter, (row_centers[c_idx][0] - 5, y_center - 25), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1, cv2.LINE_AA)

            ans_val = ans_list[q_num - 1]
            for c_idx, (cx, cy) in enumerate(row_centers):
                cv2.circle(sheet, (cx, cy), 10, (0, 0, 0), 2, cv2.LINE_AA)
                letter = "ABCD"[c_idx]
                cv2.putText(sheet, letter, (cx - 4, cy + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (180, 180, 180), 1)

                # Tô đáp án nếu có
                if ans_val != "BLANK" and letter in ans_val:
                    cv2.circle(sheet, (cx, cy), 8, (20, 20, 20), -1, cv2.LINE_AA)

    return sheet


def export_sheet_to_image(sheet: np.ndarray, output_path: str | Path) -> Path:
    """Lưu phiếu thành file ảnh PNG / JPG."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), sheet)
    return path


def export_sheet_to_pdf(sheets: list[np.ndarray] | np.ndarray, output_path: str | Path) -> Path:
    """Xuất một hoặc nhiều phiếu thành file PDF kích thước chuẩn A4."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(sheets, np.ndarray):
        sheets = [sheets]

    pil_images = []
    for s in sheets:
        rgb = cv2.cvtColor(s, cv2.COLOR_BGR2RGB)
        pil_images.append(Image.fromarray(rgb))

    if pil_images:
        pil_images[0].save(str(path), save_all=True, append_images=pil_images[1:], resolution=150.0)
    return path
