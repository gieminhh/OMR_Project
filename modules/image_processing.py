"""Đọc/ghi đường dẫn Unicode và tiền xử lý bằng OpenCV (Phase 2)."""

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from .errors import ImageProcessingError

DEFAULT_MAX_DIMENSION = 2200
DEFAULT_BLUR_KERNEL = 3
DEFAULT_BLOCK_SIZE = 51
DEFAULT_THRESHOLD_C = 12.0


@dataclass(frozen=True)
class PreprocessConfig:
    """Các tham số có thể hiệu chỉnh mà không thay thuật toán."""

    max_dimension: int = DEFAULT_MAX_DIMENSION
    blur_kernel: int = DEFAULT_BLUR_KERNEL
    threshold_method: str = "adaptive"
    block_size: int = DEFAULT_BLOCK_SIZE
    threshold_c: float = DEFAULT_THRESHOLD_C
    morphology_kernel: int = 0


@dataclass
class PreprocessedImage:
    """Ảnh trung gian cùng hệ tọa độ; binary dùng mực trắng, nền đen."""

    original: np.ndarray
    resized: np.ndarray
    gray: np.ndarray
    blurred: np.ndarray
    binary: np.ndarray


def validate_image(image: np.ndarray) -> None:
    """Yêu cầu ảnh uint8 không rỗng, grayscale/BGR/BGRA."""
    if not isinstance(image, np.ndarray) or image.size == 0:
        raise ImageProcessingError("Ảnh rỗng hoặc dữ liệu không phải numpy array.")
    if image.dtype != np.uint8 or image.ndim not in (2, 3):
        raise ImageProcessingError("Ảnh phải có kiểu uint8 và 2 hoặc 3 chiều.")
    if image.ndim == 3 and image.shape[2] not in (3, 4):
        raise ImageProcessingError("Ảnh màu phải có 3 hoặc 4 kênh.")
    if min(image.shape[:2]) < 3:
        raise ImageProcessingError("Ảnh quá nhỏ để xử lý.")


def load_image(path: str | Path) -> np.ndarray:
    """Đọc ảnh BGR, hỗ trợ tên tệp tiếng Việt trên Windows."""
    path = Path(path)
    if not path.is_file():
        raise ImageProcessingError(f"Ảnh không tồn tại hoặc không phải tệp: {path}")
    try:
        data = np.fromfile(path, dtype=np.uint8)
        image = cv2.imdecode(data, cv2.IMREAD_COLOR) if data.size else None
    except (OSError, cv2.error) as exc:
        raise ImageProcessingError(f"Không đọc được ảnh {path}: {exc}") from exc
    if image is None:
        raise ImageProcessingError(f"Tệp không phải ảnh hợp lệ hoặc định dạng chưa hỗ trợ: {path}")
    validate_image(image)
    return image


def save_image(path: str | Path, image: np.ndarray) -> Path:
    """Lưu ảnh Unicode, tạo thư mục cha và báo rõ lỗi ghi."""
    validate_image(image)
    path = Path(path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        success, encoded = cv2.imencode(path.suffix or ".png", image)
        if not success:
            raise ImageProcessingError(f"Không mã hóa được ảnh: {path}")
        encoded.tofile(path)
    except (OSError, cv2.error) as exc:
        raise ImageProcessingError(f"Không ghi được ảnh {path}: {exc}") from exc
    return path


def resize_image(image: np.ndarray, max_dimension: int = DEFAULT_MAX_DIMENSION) -> np.ndarray:
    """Giảm kích thước khi cần, giữ tỷ lệ và không phóng lớn ảnh."""
    validate_image(image)
    if not isinstance(max_dimension, int) or max_dimension < 3:
        raise ImageProcessingError("max_dimension phải là số nguyên >= 3.")
    height, width = image.shape[:2]
    largest_dimension = max(height, width)
    if largest_dimension <= max_dimension:
        return image.copy()
    scale = max_dimension / largest_dimension
    size = (max(3, round(width * scale)), max(3, round(height * scale)))
    return cv2.resize(image, size, interpolation=cv2.INTER_AREA)


def to_grayscale(image: np.ndarray) -> np.ndarray:
    """Chuyển grayscale/BGR/BGRA thành một kênh."""
    validate_image(image)
    if image.ndim == 2:
        return image.copy()
    conversion = cv2.COLOR_BGRA2GRAY if image.shape[2] == 4 else cv2.COLOR_BGR2GRAY
    return cv2.cvtColor(image, conversion)


def apply_blur(gray: np.ndarray, kernel_size: int = DEFAULT_BLUR_KERNEL) -> np.ndarray:
    """Gaussian blur nhẹ để giảm nhiễu trước khi nhị phân hóa."""
    gray = to_grayscale(gray)
    if not isinstance(kernel_size, int) or kernel_size < 1 or kernel_size % 2 == 0:
        raise ImageProcessingError("Kích thước Gaussian kernel phải là số lẻ dương.")
    return cv2.GaussianBlur(gray, (kernel_size, kernel_size), 0)


def apply_threshold(
    gray: np.ndarray,
    method: str = "adaptive",
    block_size: int = DEFAULT_BLOCK_SIZE,
    c: float = DEFAULT_THRESHOLD_C,
) -> np.ndarray:
    """Nhị phân đảo: pixel mực là 255, nền giấy là 0."""
    gray = to_grayscale(gray)
    if method == "otsu":
        return cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]
    if method != "adaptive":
        raise ImageProcessingError("threshold_method chỉ nhận 'adaptive' hoặc 'otsu'.")
    if not isinstance(block_size, int) or block_size < 3 or block_size % 2 == 0:
        raise ImageProcessingError("block_size phải là số lẻ >= 3.")
    if block_size > min(gray.shape) or not np.isfinite(c):
        raise ImageProcessingError("Ảnh nhỏ hơn block_size hoặc threshold_c không hữu hạn.")
    return cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, block_size, c
    )


def preprocess_image(
    image: np.ndarray, config: PreprocessConfig | None = None
) -> PreprocessedImage:
    """Resize → grayscale → Gaussian blur → threshold → mở hình thái tùy chọn."""
    config = config or PreprocessConfig()
    resized = resize_image(image, config.max_dimension)
    gray = to_grayscale(resized)
    blurred = apply_blur(gray, config.blur_kernel)
    binary = apply_threshold(blurred, config.threshold_method, config.block_size, config.threshold_c)
    kernel = config.morphology_kernel
    if not isinstance(kernel, int) or kernel < 0 or (kernel > 0 and kernel % 2 == 0):
        raise ImageProcessingError("morphology_kernel phải bằng 0 (tắt) hoặc số lẻ dương.")
    if kernel:
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, np.ones((kernel, kernel), np.uint8))
    return PreprocessedImage(image.copy(), resized, gray, blurred, binary)
