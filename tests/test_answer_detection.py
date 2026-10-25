"""Phase 4: tăng dần 5 → 10 → 50 câu với dữ liệu kỳ vọng độc lập."""

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import cv2
import numpy as np

from modules.answer_detection import AnswerConfig, analyze_answers, detect_answers, load_layout
from modules.errors import AnswerDetectionError
from modules.paper_detection import detect_and_warp_paper
from scripts.generate_samples import make_sheet, photograph


class AnswerDetectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.expected = ["ABCD"[i % 4] for i in range(50)]
        cls.sheet = make_sheet(cls.expected)
        cls.warped = detect_and_warp_paper(photograph(cls.sheet))

    def test_01_five_questions(self) -> None:
        self.assertEqual(detect_answers(self.warped, question_count=5), self.expected[:5])

    def test_02_ten_questions(self) -> None:
        self.assertEqual(detect_answers(self.warped, question_count=10), self.expected[:10])

    def test_03_fifty_questions_and_column_boundary(self) -> None:
        answers = detect_answers(self.warped)
        self.assertEqual(len(answers), 50)
        self.assertEqual(answers, self.expected)
        self.assertEqual(answers[24:27], ["A", "B", "C"])

    def test_unmarked_and_ambiguous_are_not_forced_to_a_choice(self) -> None:
        marks = self.expected.copy()
        marks[0], marks[24], marks[25], marks[49] = "BLANK", "AC", "BD", "BLANK"
        expected = self.expected.copy()
        expected[0], expected[24], expected[25], expected[49] = "BLANK", "MULTIPLE", "MULTIPLE", "BLANK"
        result = detect_answers(detect_and_warp_paper(photograph(make_sheet(marks))))
        self.assertEqual(result, expected)

    def test_empty_form_is_blank_but_plain_paper_is_rejected(self) -> None:
        self.assertEqual(detect_answers(make_sheet(["BLANK"] * 50)), ["BLANK"] * 50)
        with self.assertRaisesRegex(AnswerDetectionError, "vùng đáp án"):
            detect_answers(np.full_like(self.sheet, 255))

    def test_uneven_light_blur_and_jpeg(self) -> None:
        photo = photograph(self.sheet)
        shading = np.linspace(.60, 1, photo.shape[1])[None, :, None]
        shaded = np.clip(photo * shading, 0, 255).astype(np.uint8)
        blurred = cv2.GaussianBlur(shaded, (3, 3), 0)
        success, encoded = cv2.imencode(".jpg", blurred, [cv2.IMWRITE_JPEG_QUALITY, 80])
        self.assertTrue(success)
        decoded = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
        assert decoded is not None
        self.assertEqual(detect_answers(detect_and_warp_paper(decoded)), self.expected)

    def test_layout_shift_is_rejected(self) -> None:
        shifted = replace(AnswerConfig(), columns=((215, 300, 455, 1300), (645, 300, 885, 1300)))
        with self.assertRaisesRegex(AnswerDetectionError, "layout"):
            detect_answers(self.sheet, shifted)

    def test_invalid_config_and_image_size(self) -> None:
        for config in (
            replace(AnswerConfig(), fill_threshold=2),
            replace(AnswerConfig(), columns=((200, 300, 440, 1300),)),
            replace(AnswerConfig(), bubble_radius=100),
            replace(AnswerConfig(), answer_region=(-1, 0, 1000, 1400)),
        ):
            with self.subTest(config=config), self.assertRaises(AnswerDetectionError):
                detect_answers(self.sheet, config)
        with self.assertRaises(AnswerDetectionError):
            detect_answers(self.sheet[:300])
        with self.assertRaises(AnswerDetectionError):
            detect_answers(self.sheet, question_count=49)

    def test_json_layout_and_diagnostics(self) -> None:
        config = load_layout(Path(__file__).resolve().parents[1] / "config" / "layout.json")
        result = analyze_answers(self.warped, config)
        self.assertEqual(result.answers, self.expected)
        self.assertEqual(np.asarray(result.fill_ratios).shape, (50, 4))
        self.assertEqual(result.annotated_image.shape, self.sheet.shape)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "layout.json"
            for content in ('{"typo": 123}', '[]', '{', '{"columns": null}'):
                path.write_text(content, encoding="utf-8")
                with self.assertRaises(AnswerDetectionError):
                    load_layout(path)


if __name__ == "__main__":
    unittest.main()
