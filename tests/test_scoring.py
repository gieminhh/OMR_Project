"""Kiểm tra đọc đáp án chuẩn, xác thực đáp án và tính điểm."""

import json
import tempfile
import unittest
from pathlib import Path

from modules.errors import OMRError
from modules.scoring import ScoringError, load_answer_key, score_answers
from modules.validation import validate_answers

ROOT = Path(__file__).resolve().parents[1]


class ScoringTests(unittest.TestCase):
    def test_loads_bundled_answer_key(self) -> None:
        answers = load_answer_key(ROOT / "answer_key" / "answer_key.json")
        self.assertEqual(answers, ["ABCD"[i % 4] for i in range(50)])

    def test_loads_supported_json_shapes(self) -> None:
        answers = ["A"] * 50
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "answers.json"
            for data in (answers, {"answers": answers}):
                path.write_text(json.dumps(data), encoding="utf-8")
                self.assertEqual(load_answer_key(path), answers)

    def test_rejects_incorrect_answer_key(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "answers.json"
            path.write_text(json.dumps(["A"] * 49), encoding="utf-8")
            with self.assertRaises(ScoringError):
                load_answer_key(path)

    def test_validates_answers_and_scores_each_result(self) -> None:
        correct = ["A"] * 50
        student = correct.copy()
        student[1] = "B"
        student[2] = "BLANK"
        student[3] = "MULTIPLE"

        validation = validate_answers(student)
        self.assertTrue(validation["valid"])
        self.assertEqual(validation["blank_count"], 1)
        self.assertEqual(validation["multiple_count"], 1)

        result = score_answers(student, correct)
        self.assertEqual(result["correct_count"], 47)
        self.assertEqual(result["wrong_count"], 1)
        self.assertEqual(result["blank_count"], 1)
        self.assertEqual(result["multiple_count"], 1)
        self.assertEqual(result["score"], 9.4)
        self.assertEqual(result["total"], 50)

    def test_rejects_invalid_answer_count(self) -> None:
        self.assertFalse(validate_answers(["A"])["valid"])
        with self.assertRaises(OMRError):
            score_answers(["A"], ["A"])


if __name__ == "__main__":
    unittest.main()
