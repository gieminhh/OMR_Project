"""Các lỗi dự kiến để CLI/GUI hiển thị mà không mất ngữ cảnh."""


class OMRError(Exception):
    """Lỗi có thể trình bày trực tiếp cho người dùng."""


class ImageProcessingError(OMRError):
    """Không thể đọc, ghi hoặc tiền xử lý ảnh."""


class PaperDetectionError(OMRError):
    """Không xác định được bốn góc phiếu hợp lệ."""


class AnswerDetectionError(OMRError):
    """Layout hoặc vùng đáp án không hợp lệ."""
