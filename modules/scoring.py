"""Đọc đáp án chuẩn và chấm điểm 50 câu trắc nghiệm — Phase 6."""

import json
from pathlib import Path

from .errors import OMRError

VALID_ANSWERS = {"A", "B", "C", "D"}
QUESTION_COUNT = 50


class ScoringError(OMRError):
    """Đáp án chuẩn không hợp lệ hoặc không khớp số câu."""


def load_answer_key(path: str | Path) -> list[str]:
    """Đọc file JSON đáp án chuẩn; từ chối nếu thiếu câu hoặc giá trị lạ.

    Định dạng file:
        {"answers": ["A", "B", "C", ...]}   # đúng 50 phần tử
    hoặc đơn giản hơn:
        ["A", "B", "C", ...]                # list thuần
    """
    path = Path(path)
    if not path.is_file():
        raise ScoringError(f"File đáp án chuẩn không tồn tại: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ScoringError(f"Không đọc được file đáp án chuẩn: {exc}") from exc

    if isinstance(data, dict):
        if "answers" not in data:
            raise ScoringError("File JSON đáp án chuẩn phải có khóa 'answers'.")
        answers = data["answers"]
    elif isinstance(data, list):
        answers = data
    else:
        raise ScoringError("File đáp án chuẩn phải là JSON array hoặc object có khóa 'answers'.")

    if not isinstance(answers, list) or len(answers) != QUESTION_COUNT:
        raise ScoringError(
            f"Đáp án chuẩn phải có đúng {QUESTION_COUNT} phần tử, "
            f"nhận được {len(answers) if isinstance(answers, list) else 'không phải list'}."
        )
    for i, val in enumerate(answers, start=1):
        if val not in VALID_ANSWERS:
            raise ScoringError(
                f"Câu {i}: giá trị đáp án chuẩn '{val}' không hợp lệ; "
                f"chỉ chấp nhận {sorted(VALID_ANSWERS)}."
            )
    return answers


def score_answers(student_answers: list[str], correct_answers: list[str]) -> dict:
    """So sánh từng câu và trả thống kê + điểm thang 10.

    Returns:
        {
          "score": float,          # thang 10, làm tròn 2 chữ số
          "correct_count": int,
          "wrong_count": int,
          "blank_count": int,
          "multiple_count": int,
          "total": int,
          "details": [             # list 50 phần tử
            {
              "question": int,
              "student": str,      # A/B/C/D/BLANK/MULTIPLE
              "correct": str,      # A/B/C/D
              "result": str        # "correct" | "wrong" | "blank" | "multiple"
            }, ...
          ]
        }
    """
    if len(student_answers) != QUESTION_COUNT or len(correct_answers) != QUESTION_COUNT:
        raise ScoringError(
            f"Cần đúng {QUESTION_COUNT} câu học sinh và {QUESTION_COUNT} câu đáp án chuẩn."
        )

    details = []
    correct_count = wrong_count = blank_count = multiple_count = 0

    for i, (student, correct) in enumerate(zip(student_answers, correct_answers), start=1):
        if student == "BLANK":
            result = "blank"
            blank_count += 1
        elif student == "MULTIPLE":
            result = "multiple"
            multiple_count += 1
        elif student == correct:
            result = "correct"
            correct_count += 1
        else:
            result = "wrong"
            wrong_count += 1
        details.append({"question": i, "student": student, "correct": correct, "result": result})

    score = round(correct_count / QUESTION_COUNT * 10, 2)
    return {
        "score": score,
        "correct_count": correct_count,
        "wrong_count": wrong_count,
        "blank_count": blank_count,
        "multiple_count": multiple_count,
        "total": QUESTION_COUNT,
        "details": details,
    }
