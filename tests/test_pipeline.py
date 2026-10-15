"""Kiểm tra phối hợp các module và CLI phát triển, không chấm điểm giả."""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from main import main, process_omr
from modules.image_processing import save_image
from scripts.generate_samples import make_sheet, photograph


class PipelineTests(unittest.TestCase):
    def test_pipeline_and_six_debug_images(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            image = save_image(directory / "phiếu.png", photograph(make_sheet()))
            result = process_omr(image, debug=True, output_dir=directory / "output")
            self.assertEqual(result["answers"], ["ABCD"[i % 4] for i in range(50)])
            self.assertIsNone(result["score_result"])
            self.assertEqual(len(list((directory / "output" / "debug").glob("*.jpg"))), 6)

    def test_phase_stops_and_debug_false_no_writes(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            image = save_image(directory / "sample.png", photograph(make_sheet()))
            output = directory / "not-created"
            phase2 = process_omr(image, phase=2, output_dir=output)
            phase3 = process_omr(image, phase=3, output_dir=output)
            self.assertEqual(phase2["processed_image"].ndim, 2)
            self.assertEqual(phase3["processed_image"].shape, (1400, 1000, 3))
            self.assertIsNone(phase3["answers"])
            self.assertFalse(output.exists())

    def test_cli_no_image_and_missing_image(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main([]), 0)
        with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stderr(io.StringIO()) as error:
            self.assertEqual(main([str(Path(folder) / "missing.png")]), 1)
            self.assertIn("không tồn tại", error.getvalue())


if __name__ == "__main__":
    unittest.main()
