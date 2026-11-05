"""Kiểm tra tính hợp lệ của danh sách đáp án học sinh và đáp án chuẩn."""

from .errors import OMRError

VALID_VALUES = {"A", "B", "C", "D", "BLANK", "MULTIPLE"}
VALID_KEY_VALUES = {"A", "B", "C", "D"}
QUESTION_COUNT = 50


class ValidationError(OMRError):
    """Danh sách đáp án không hợp lệ."""


def validate_answers(answers: list[str]) -> dict:
    """Kiểm tra số câu và tập giá trị A/B/C/D/BLANK/MULTIPLE của học sinh.

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


def validate_answer_key(key: list[str]) -> dict:
    """Kiểm tra tính hợp lệ của bộ đáp án chuẩn (đúng 50 câu, chỉ gồm A, B, C, D).

    Returns:
        {
          "valid": bool,
          "count": int,
          "missing_indices": list[int],
          "errors": list[str]
        }
    """
    errors = []
    missing_indices = []

    if not isinstance(key, list):
        raise ValidationError("Đáp án chuẩn phải là list.")
    if len(key) != QUESTION_COUNT:
        errors.append(f"Cần đúng {QUESTION_COUNT} câu, nhận được {len(key)}.")

    for i, val in enumerate(key, start=1):
        if not isinstance(val, str) or val.strip().upper() not in VALID_KEY_VALUES:
            errors.append(f"Câu {i}: giá trị '{val}' không hợp lệ (chỉ nhận A, B, C, D).")
            missing_indices.append(i)

    return {
        "valid": len(errors) == 0,
        "count": len(key),
        "missing_indices": missing_indices,
        "errors": errors,
    }
