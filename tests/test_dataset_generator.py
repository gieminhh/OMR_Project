import csv
import json
from pathlib import Path
import random
import tempfile
import unittest

import numpy as np

from modules.sheet_generator import generate_sheet
from modules.test_dataset_generator import generate_benchmark_dataset, simulate_realistic_photo


class DatasetGeneratorTests(unittest.TestCase):
    def test_realistic_photo_respects_angle_and_seed(self):
        sheet = generate_sheet(session_code="01", sbd="000001", exam_code="101")
        angle_zero = simulate_realistic_photo(
            sheet, random.Random(42), max_angle_deg=0, add_shadow=False, add_noise=True
        )
        repeated = simulate_realistic_photo(
            sheet, random.Random(42), max_angle_deg=0, add_shadow=False, add_noise=True
        )
        rotated = simulate_realistic_photo(
            sheet, random.Random(42), max_angle_deg=2.5, add_shadow=False, add_noise=False
        )

        np.testing.assert_array_equal(angle_zero, repeated)
        self.assertFalse(np.array_equal(angle_zero, rotated))
        with self.assertRaises(ValueError):
            simulate_realistic_photo(sheet, random.Random(42), max_angle_deg=-1)

    def test_num_special_limits_outputs_and_custom_codes_are_used(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            result = generate_benchmark_dataset(
                output_dir,
                num_perfect=0,
                num_realistic=0,
                num_special=5,
                session_codes=["007"],
                exam_codes=["901"],
            )
            limited_result = generate_benchmark_dataset(
                output_dir,
                num_perfect=0,
                num_realistic=0,
                num_special=2,
                session_codes=["007"],
                exam_codes=["901"],
            )

            ground_truth = json.loads(Path(limited_result["ground_truth_json"]).read_text(encoding="utf-8"))
            image_files = list((output_dir / "images").glob("*.png"))
            self.assertEqual(result["total_images"], 6)
            self.assertEqual(limited_result["total_images"], 3)
            self.assertEqual(len(image_files), 3)
            self.assertEqual([item["session_code"] for item in ground_truth[1:]], ["007", "007"])
            self.assertEqual(ground_truth[2]["exam_code"], "901")

    def test_student_list_scales_to_requested_dataset_size(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            result = generate_benchmark_dataset(
                temp_dir,
                num_perfect=40,
                num_realistic=0,
                num_special=0,
            )

            with open(result["students_csv"], encoding="utf-8-sig", newline="") as csv_file:
                students = list(csv.DictReader(csv_file))
            self.assertEqual(len(students), 40)
            self.assertEqual(result["total_images"], 41)


if __name__ == "__main__":
    unittest.main()
