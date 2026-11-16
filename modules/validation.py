

from .errors import OMRError

VALID_VALUES = {"A", "B", "C", "D", "BLANK", "MULTIPLE"}
VALID_KEY_VALUES = {"A", "B", "C", "D"}
QUESTION_COUNT = 50


class ValidationError(OMRError):
    pass


def validate_answers(answers: list[str]) -> dict:











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
