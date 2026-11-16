import json
from pathlib import Path

from .errors import OMRError

VALID_ANSWERS = {"A", "B", "C", "D"}
VALID_STUDENT_ANSWERS = {"A", "B", "C", "D", "BLANK", "MULTIPLE"}
QUESTION_COUNT = 50


class ScoringError(OMRError):
    pass


def load_answer_key(path: str | Path) -> list[str]:
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
    if not isinstance(student_answers, list) or not isinstance(correct_answers, list):
        raise ScoringError("Danh sách đáp án học sinh và đáp án chuẩn phải là dạng list.")
    if len(student_answers) != QUESTION_COUNT or len(correct_answers) != QUESTION_COUNT:
        raise ScoringError(
            f"Cần đúng {QUESTION_COUNT} câu học sinh và {QUESTION_COUNT} câu đáp án chuẩn."
        )

    for i, correct in enumerate(correct_answers, start=1):
        if not isinstance(correct, str) or correct not in VALID_ANSWERS:
            raise ScoringError(
                f"Câu {i}: đáp án chuẩn '{correct}' không hợp lệ; chỉ chấp nhận {sorted(VALID_ANSWERS)}."
            )

    for i, student in enumerate(student_answers, start=1):
        if not isinstance(student, str) or student not in VALID_STUDENT_ANSWERS:
            raise ScoringError(
                f"Câu {i}: đáp án học sinh '{student}' không hợp lệ; chỉ chấp nhận {sorted(VALID_STUDENT_ANSWERS)}."
            )

    details = []
    counts = dict.fromkeys(("correct", "wrong", "blank", "multiple"), 0)

    for i, (student, correct) in enumerate(zip(student_answers, correct_answers), start=1):
        if student == "BLANK":
            result = "blank"
        elif student == "MULTIPLE":
            result = "multiple"
        elif student == correct:
            result = "correct"
        else:
            result = "wrong"
        counts[result] += 1
        details.append({"question": i, "student": student, "correct": correct, "result": result})


    score = round(counts["correct"] / QUESTION_COUNT * 10, 2)
    return {
        "score": score,
        "correct_count": counts["correct"],
        "wrong_count": counts["wrong"],
        "blank_count": counts["blank"],
        "multiple_count": counts["multiple"],
        "total": QUESTION_COUNT,
        "details": details,
    }
