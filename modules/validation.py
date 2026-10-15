"""Kiểm tra danh sách 50 đáp án học sinh — Phase 6."""

from .errors import OMRError

VALID_VALUES = {"A", "B", "C", "D", "BLANK", "MULTIPLE"}
QUESTION_COUNT = 50


class ValidationError(OMRError):
    """Danh sách đáp án học sinh không hợp lệ."""


def validate_answers(answers: list[str]) -> dict:
    """Kiểm tra số câu và tập giá trị A/B/C/D/BLANK/MULTIPLE.

    Returns:
        {
          "valid": bool,
          "count": int,
          "blank_count": int,
          "multiple_count": int,
          "errors": list[str]
        }
    """
    errors = []
    blank_count = multiple_count = 0

    if not isinstance(answers, list):
        raise ValidationError("Đáp án phải là list.")
    if len(answers) != QUESTION_COUNT:
        errors.append(
            f"Cần đúng {QUESTION_COUNT} câu, nhận được {len(answers)}."
        )
    for i, val in enumerate(answers, start=1):
        if val not in VALID_VALUES:
            errors.append(f"Câu {i}: giá trị '{val}' không hợp lệ.")
        elif val == "BLANK":
            blank_count += 1
        elif val == "MULTIPLE":
            multiple_count += 1

    return {
        "valid": len(errors) == 0,
        "count": len(answers),
        "blank_count": blank_count,
        "multiple_count": multiple_count,
        "errors": errors,
    }
