

import numpy as np

from .image_processing import resize_image
from .paper_detection import PaperConfig, detect_and_warp_paper


def remove_background(image: np.ndarray, config: PaperConfig | None = None) -> np.ndarray:






    return detect_and_warp_paper(resize_image(image), config)
