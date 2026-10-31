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

    def test_rescore_when_answer_key_changes(self) -> None:
        """Thay đổi đáp án chuẩn sau khi chấm phải tính lại điểm chính xác."""
        student = ["A"] * 25 + ["B"] * 25
        key_1 = ["A"] * 50  # Đúng 25 câu -> 5.0 điểm
        key_2 = ["B"] * 50  # Đúng 25 câu -> 5.0 điểm
        key_3 = ["A"] * 25 + ["B"] * 25  # Đúng 50 câu -> 10.0 điểm
        key_4 = ["C"] * 50  # Đúng 0 câu -> 0.0 điểm

        res_1 = score_answers(student, key_1)
        self.assertEqual(res_1["score"], 5.0)
        self.assertEqual(res_1["correct_count"], 25)

        # Đổi sang key_3 (khớp hoàn toàn)
        res_3 = score_answers(student, key_3)
        self.assertEqual(res_3["score"], 10.0)
        self.assertEqual(res_3["correct_count"], 50)

        # Đổi sang key_4 (sai hoàn toàn)
        res_4 = score_answers(student, key_4)
        self.assertEqual(res_4["score"], 0.0)
        self.assertEqual(res_4["correct_count"], 0)
        self.assertEqual(res_4["wrong_count"], 50)

    def test_all_blank_and_all_multiple_scoring(self) -> None:
        """Phiếu toàn BLANK hoặc toàn MULTIPLE đạt 0 điểm."""
        key = ["A"] * 50
        blanks = ["BLANK"] * 50
        multiples = ["MULTIPLE"] * 50

        res_blank = score_answers(blanks, key)
        self.assertEqual(res_blank["score"], 0.0)
        self.assertEqual(res_blank["blank_count"], 50)
        self.assertEqual(res_blank["correct_count"], 0)

        res_multi = score_answers(multiples, key)
        self.assertEqual(res_multi["score"], 0.0)
        self.assertEqual(res_multi["multiple_count"], 50)
        self.assertEqual(res_multi["correct_count"], 0)

    def test_missing_answer_key_file(self) -> None:
        """Thiếu file đáp án chuẩn báo ScoringError."""
        with self.assertRaises(ScoringError):
            load_answer_key("non_existent_key_path.json")

    def test_invalid_character_in_answer_key(self) -> None:
        """Đáp án chuẩn chứa ký tự lạ (E, X...) bị từ chối."""
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bad_key.json"
            bad_key = ["A"] * 49 + ["E"]
            path.write_text(json.dumps(bad_key), encoding="utf-8")
            with self.assertRaises(ScoringError):
                load_answer_key(path)


if __name__ == "__main__":
    unittest.main()
