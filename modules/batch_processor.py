"""Xử lý chấm bài thi trắc nghiệm hàng loạt (Batch Processing).

Đặc điểm:
- Xử lý nền (Background Worker / Thread-safe), không khóa giao diện.
- Không tải tất cả ảnh cùng lúc vào RAM; đọc và giải phóng từng ảnh tuần tự.
- Tự động nhận diện template (V1/V2), đọc SBD, Mã đề, Đợt thi, 50 câu.
- Hỗ trợ tự động xoay nếu ảnh chụp bị lộn 180 độ.
- Một ảnh lỗi (FAILED) không bao giờ làm dừng cả lô.
- Tự động phân loại trạng thái: QUEUED, PROCESSING, SUCCESS, NEEDS_REVIEW, FAILED.
- Báo cáo tiến độ (progress callback) sau mỗi ảnh.
"""

from dataclasses import dataclass, field
from datetime import datetime
import os
from pathlib import Path
import threading
import time
from typing import Callable, Literal

import cv2
import numpy as np

from .answer_detection import analyze_answers, load_layout, AnswerConfig
from .bubble_id_detection import detect_sheet_identifiers, SheetIdentifiers
from .errors import OMRError, AnswerDetectionError, PaperDetectionError
from .image_processing import load_image, preprocess_image, save_image
from .paper_detection import PaperConfig, find_paper_contour, four_point_transform
from .printed_form import detect_printed_layout
from .session_manager import SessionManager

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LAYOUT_PATH = ROOT / "config" / "layout.json"


def _orient_printed_sheet(image: np.ndarray, allow_rotation: bool) -> tuple[np.ndarray, AnswerConfig | None]:
    """Thử cả hai hướng trước khi kết luận thiếu mốc; không bỏ qua mốc hỏng."""
    first_error = None
    candidates = [image]
    if allow_rotation:
        candidates.append(cv2.rotate(image, cv2.ROTATE_180))
    for candidate in candidates:
        try:
            layout = detect_printed_layout(candidate)
        except AnswerDetectionError as exc:
            if first_error is None:
                first_error = exc
            continue
        if layout is not None:
            return candidate, layout
    if first_error is not None:
        raise first_error
    return image, None


@dataclass
class BatchItem:
    """Đại diện cho 1 ảnh trong danh sách chấm hàng loạt."""
    image_path: Path
    status: Literal["QUEUED", "PROCESSING", "SUCCESS", "NEEDS_REVIEW", "FAILED"] = "QUEUED"
    result_id: int | None = None
    session_code: str | None = None
    exam_code: str | None = None
    sbd: str | None = None
    student_name: str | None = None
    class_code: str | None = None
    score: float | None = None
    correct_count: int | None = None
    total_questions: int = 50
    review_reasons: list[str] = field(default_factory=list)
    error_message: str | None = None
    annotated_image_path: Path | None = None
    answers: list[str] = field(default_factory=list)


def process_single_sheet(
    image_path: str | Path,
    session_manager: SessionManager,
    default_session_code: str,
    output_dir: Path | str | None = None,
    allow_rotation_correction: bool = True,
) -> BatchItem:
    """Quy trình chấm hoàn chỉnh cho 1 ảnh đơn lẻ."""
    path = Path(image_path)
    item = BatchItem(image_path=path, session_code=default_session_code)
    item.status = "PROCESSING"

    try:
        # 1. Tải ảnh và tiền xử lý
        original = load_image(path)
        prepared = preprocess_image(original)

        # 2. Căn chỉnh phiếu (paper detection & 4-point warp)
        # Hỗ trợ cả 2 trường hợp:
        # a) Ảnh scan từ máy quét phẳng (đã đúng kích thước hoặc không có nền bàn)
        # b) Ảnh chụp điện thoại / camera (có nền bàn bao quanh)
        warped = None
        if original.shape[:2] == (1400, 1000):
            warped = original.copy()
        else:
            paper_cfg = PaperConfig(output_size=(1000, 1400))
            try:
                corners = find_paper_contour(prepared.resized, paper_cfg)
                warped = four_point_transform(prepared.resized, corners, paper_cfg.output_size)
            except PaperDetectionError:
                # Nếu không tách được nền, thử kiểm tra nếu ảnh resize về (1000, 1400) khớp layout
                resized_direct = cv2.resize(original, (1000, 1400))
                oriented, direct_layout = _orient_printed_sheet(resized_direct, allow_rotation_correction)
                if direct_layout is not None:
                    warped = oriented
                else:
                    raise

        # 3. Xác định layout và tự động xoay nếu ảnh bị lộn 180 độ
        warped, layout_cfg = _orient_printed_sheet(warped, allow_rotation_correction)

        if layout_cfg is None:
            # Fallback dùng layout mặc định nếu có
            try:
                layout_cfg = load_layout(DEFAULT_LAYOUT_PATH)
            except Exception:
                raise OMRError("Không nhận diện được mẫu phiếu in hoặc mốc OMR trên ảnh.")

        # 4. Nhận diện SBD, Mã đề và Đợt thi
        identifiers = detect_sheet_identifiers(warped)
        item.sbd = identifiers.sbd
        item.exam_code = identifiers.exam_code

        # Nếu Template V2 có đợt thi, ưu tiên đợt thi đọc được từ phiếu
        session_mismatch = False
        if identifiers.template_version == "V2":
            item.session_code = identifiers.session_code
            if identifiers.session_code is not None and default_session_code is not None:
                id_s = str(identifiers.session_code).strip()
                def_s = str(default_session_code).strip()
                # Khác đợt thi nếu mã không bằng nhau và không cùng biểu diễn số (vd: 01 vs 001 là cùng đợt, 01 vs 02 là khác đợt)
                is_different = False
                if id_s.isdigit() and def_s.isdigit():
                    is_different = (int(id_s) != int(def_s))
                else:
                    is_different = (id_s != def_s)

                if is_different:
                    session_mismatch = True
                    mismatch_reason = f"Mã đợt thi trên phiếu ('{identifiers.session_code}') khác với đợt thi đang chọn ('{default_session_code}')."
                    if mismatch_reason not in item.review_reasons:
                        item.review_reasons.append(mismatch_reason)
        else:
            item.session_code = default_session_code

        for r in identifiers.review_reasons:
            if r not in item.review_reasons:
                item.review_reasons.append(r)

        # 5. Nhận diện 50 câu trả lời
        ans_detection = analyze_answers(warped, layout_cfg, question_count=50)
        item.answers = ans_detection.answers

        # 6. Lưu kết quả vào cơ sở dữ liệu và chấm điểm
        out_dir = Path(output_dir or (ROOT / "output" / "batch"))
        out_dir.mkdir(parents=True, exist_ok=True)
        annotated_path = out_dir / f"annotated_{path.stem}.png"
        save_image(annotated_path, identifiers.annotated_image)
        item.annotated_image_path = annotated_path

        # Phiếu V2 phải xác định được đợt thi trước khi ghi vào dữ liệu đợt thi.
        if item.session_code is None:
            item.status = "NEEDS_REVIEW"
            item.review_reasons.append("Chưa lưu bài: cần xác định mã đợt thi trên phiếu.")
            return item

        extra_reasons = list(item.review_reasons)
        db_res = session_manager.save_exam_result(
            session_code=item.session_code,
            image_path=str(path),
            student_answers=item.answers,
            sbd=item.sbd,
            exam_code=item.exam_code,
            extra_review_reasons=extra_reasons if extra_reasons else None,
        )

        item.result_id = db_res["id"]
        item.status = db_res["status"]
        item.student_name = db_res.get("student_name")
        item.class_code = db_res.get("class_code")
        item.score = db_res.get("score")
        item.correct_count = db_res.get("correct_count")
        if db_res.get("review_reason"):
            item.review_reasons.append(db_res["review_reason"])

    except Exception as exc:
        item.status = "FAILED"
        item.error_message = str(exc)

    return item


def read_answer_key_from_image(
    image_path: str | Path,
    allow_rotation_correction: bool = True,
) -> dict:
    """Đọc mã đề và 50 đáp án chuẩn từ ảnh phiếu đáp án OMR.

    Hoàn toàn độc lập:
    - KHÔNG lưu kết quả bài thi của học sinh.
    - KHÔNG phát sinh bản ghi điểm nào trong database.
    - Phát hiện đáp án bỏ trống hoặc tô nhiều ô.
    """
    path = Path(image_path)
    res = {
        "image_path": path,
        "filename": path.name,
        "exam_code": None,
        "session_code": None,
        "template_version": "V2",
        "answers": [],
        "is_valid": False,
        "blank_questions": [],
        "multiple_questions": [],
        "review_reasons": [],
        "error_message": None,
        "annotated_image": None,
    }

    try:
        original = load_image(path)
        prepared = preprocess_image(original)

        warped = None
        if original.shape[:2] == (1400, 1000):
            warped = original.copy()
        else:
            paper_cfg = PaperConfig(output_size=(1000, 1400))
            try:
                corners = find_paper_contour(prepared.resized, paper_cfg)
                warped = four_point_transform(prepared.resized, corners, paper_cfg.output_size)
            except PaperDetectionError:
                resized_direct = cv2.resize(original, (1000, 1400))
                oriented, direct_layout = _orient_printed_sheet(resized_direct, allow_rotation_correction)
                if direct_layout is not None:
                    warped = oriented
                else:
                    raise

        warped, layout_cfg = _orient_printed_sheet(warped, allow_rotation_correction)
        if layout_cfg is None:
            try:
                layout_cfg = load_layout(DEFAULT_LAYOUT_PATH)
            except Exception:
                raise OMRError("Không nhận diện được mẫu phiếu in hoặc mốc OMR trên ảnh.")

        identifiers = detect_sheet_identifiers(warped)
        res["exam_code"] = identifiers.exam_code
        res["session_code"] = identifiers.session_code
        res["template_version"] = identifiers.template_version
        res["annotated_image"] = identifiers.annotated_image

        ans_detection = analyze_answers(warped, layout_cfg, question_count=50)
        res["answers"] = ans_detection.answers

        for q_idx, ans in enumerate(ans_detection.answers, start=1):
            if ans == "BLANK":
                res["blank_questions"].append(q_idx)
            elif ans == "MULTIPLE":
                res["multiple_questions"].append(q_idx)

        review_reasons = []
        if not identifiers.exam_code:
            review_reasons.append("Chưa nhận diện được mã đề trên phiếu.")
        if res["blank_questions"]:
            review_reasons.append(f"Có {len(res['blank_questions'])} câu chưa tô ({', '.join(map(str, res['blank_questions'][:10]))})")
        if res["multiple_questions"]:
            review_reasons.append(f"Có {len(res['multiple_questions'])} câu tô nhiều ô ({', '.join(map(str, res['multiple_questions'][:10]))})")

        res["review_reasons"] = review_reasons
        res["is_valid"] = (
            bool(identifiers.exam_code)
            and len(res["answers"]) == 50
            and not res["blank_questions"]
            and not res["multiple_questions"]
        )

    except Exception as exc:
        res["error_message"] = str(exc)
        res["is_valid"] = False

    return res


class BatchProcessor:
    """Quản lý hàng đợi và tiến trình chấm hàng loạt."""

    def __init__(
        self,
        session_manager: SessionManager,
        default_session_code: str,
        output_dir: Path | str | None = None,
    ):
        self.session_manager = session_manager
        self.default_session_code = default_session_code
        self.output_dir = Path(output_dir or (ROOT / "output" / "batch"))
        self.items: list[BatchItem] = []
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._is_running = False

    def add_files(self, paths: list[str | Path]) -> int:
        """Thêm các file ảnh vào hàng đợi."""
        added = 0
        with self._lock:
            existing = {str(item.image_path.resolve()) for item in self.items}
            for p in paths:
                p = Path(p)
                if p.is_file() and p.suffix.lower() in (".png", ".jpg", ".jpeg", ".bmp") and str(p.resolve()) not in existing:
                    self.items.append(BatchItem(image_path=p, session_code=self.default_session_code))
                    existing.add(str(p.resolve()))
                    added += 1
        return added

    def add_directory(self, dir_path: str | Path, recursive: bool = False) -> int:
        """Thêm toàn bộ ảnh trong thư mục vào hàng đợi."""
        folder = Path(dir_path)
        if not folder.is_dir():
            raise OMRError(f"Thư mục không tồn tại: {folder}")
        files = []
        pattern = "**/*" if recursive else "*"
        for ext in (".png", ".jpg", ".jpeg", ".bmp"):
            files.extend(folder.glob(f"{pattern}{ext}"))
        return self.add_files(files)

    def remove_item(self, index: int) -> bool:
        """Loại bỏ một ảnh khỏi hàng đợi (khi chưa hoặc đã chấm)."""
        with self._lock:
            if 0 <= index < len(self.items):
                del self.items[index]
                return True
        return False

    def clear(self) -> None:
        """Xóa sạch hàng đợi."""
        with self._lock:
            if not self._is_running:
                self.items.clear()

    def reset_for_retry(self, include_needs_review: bool = True) -> int:
        """Đặt lại trạng thái QUEUED cho các bài lỗi hoặc cần kiểm tra để chấm lại."""
        count = 0
        targets = ("FAILED", "NEEDS_REVIEW") if include_needs_review else ("FAILED",)
        with self._lock:
            for item in self.items:
                if item.status in targets:
                    item.status = "QUEUED"
                    item.error_message = None
                    item.review_reasons = []
                    count += 1
        return count

    def stop(self) -> None:
        """Yêu cầu dừng tiến trình chấm hàng loạt."""
        self._stop_event.set()

    def process_all(
        self,
        on_progress: Callable[[int, int, BatchItem], None] | None = None,
        on_complete: Callable[[list[BatchItem]], None] | None = None,
    ) -> list[BatchItem]:
        """Chạy chấm hàng loạt đồng bộ (hoặc gọi trong thread riêng)."""
        self._is_running = True
        self._stop_event.clear()

        total = len(self.items)
        for idx, item in enumerate(self.items):
            if self._stop_event.is_set():
                break
            if item.status in ("SUCCESS", "NEEDS_REVIEW"):
                # Đã chấm xong trước đó, bỏ qua trừ khi yêu cầu chấm lại
                if on_progress:
                    on_progress(idx + 1, total, item)
                continue

            processed_item = process_single_sheet(
                item.image_path,
                self.session_manager,
                self.default_session_code,
                self.output_dir,
            )
            # Cập nhật thông tin vào item
            with self._lock:
                self.items[idx] = processed_item

            if on_progress:
                on_progress(idx + 1, total, processed_item)

        self._is_running = False
        if on_complete:
            on_complete(self.items)
        return self.items

    def process_all_async(
        self,
        on_progress: Callable[[int, int, BatchItem], None] | None = None,
        on_complete: Callable[[list[BatchItem]], None] | None = None,
    ) -> threading.Thread:
        """Khởi chạy chấm hàng loạt trong background thread."""
        thread = threading.Thread(
            target=self.process_all,
            args=(on_progress, on_complete),
            daemon=True,
        )
        thread.start()
        return thread
