


class OMRError(Exception):
    pass


class ImageProcessingError(OMRError):
    pass


class PaperDetectionError(OMRError):
    pass


class AnswerDetectionError(OMRError):
    pass
