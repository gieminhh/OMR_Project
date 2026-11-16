

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import openpyxl

from gui.simple_app import ManualAnswerKeyDialog, SimpleOMRApp
from modules.scoring import load_answer_key, score_answers

ROOT = Path(__file__).resolve().parents[1]


class SimpleGuiTests(unittest.TestCase):
    def setUp(self):
        try:
            self.app = SimpleOMRApp()
            self.app.withdraw()
        except Exception as exc:
            self.skipTest(f"Môi trường không có Tkinter/Display: {exc}")

    def tearDown(self):
        if hasattr(self, "app"):
            self.app.destroy()

    def test_initial_state(self):

        self.assertIsNone(self.app.image_path)
        self.assertIsNone(self.app.student_answers)
        self.assertIsNone(self.app.answer_key)
        self.assertIsNone(self.app.score_result)
        self.assertEqual(str(self.app.btn_scan["state"]), "disabled")
        self.assertEqual(str(self.app.btn_score["state"]), "disabled")
        self.assertEqual(str(self.app.btn_excel["state"]), "disabled")
        self.assertEqual(str(self.app.btn_export_key["state"]), "normal")
        self.assertEqual(self.app.chip_correct.cget("text"), "--")
        self.assertEqual(self.app.chip_wrong.cget("text"), "--")
        self.assertEqual(self.app.chip_blank.cget("text"), "--")
        self.assertEqual(self.app.chip_multi.cget("text"), "--")

    def test_scan_and_unscored_table_and_export(self):

        sample_img = ROOT / "test_images" / "sample_photo.png"
        self.app.image_path = sample_img
        self.app.on_scan_sheet()

        self.assertIsNotNone(self.app.student_answers)
        self.assertEqual(len(self.app.student_answers), 50)

        children = self.app.tree.get_children()
        self.assertEqual(len(children), 50)

        self.assertEqual(str(self.app.btn_excel["state"]), "normal")


        self.assertEqual(self.app.chip_correct.cget("text"), "--")
        self.assertEqual(self.app.chip_wrong.cget("text"), "--")
        self.assertEqual(self.app.chip_blank.cget("text"), "0")
        self.assertEqual(self.app.chip_multi.cget("text"), "0")


        with tempfile.TemporaryDirectory() as folder:
            out_file = Path(folder) / "unscored.xlsx"
            self.app.score_result = None
            from modules.export_excel import export_excel
            export_excel(None, out_file, answers=self.app.student_answers)
            wb = openpyxl.load_workbook(out_file)
            self.assertEqual(wb.active["B1"].value, "Đáp án nhận diện")

    def test_load_key_and_scoring(self):

        self.app.student_answers = ["A"] * 50
        self.app.answer_key = ["A"] * 50

        self.app.on_score()

        self.assertIsNotNone(self.app.score_result)
        self.assertEqual(self.app.score_result["score"], 10.0)
        self.assertEqual(self.app.score_result["correct_count"], 50)
        self.assertEqual(str(self.app.btn_excel["state"]), "normal")


        self.assertEqual(self.app.chip_correct.cget("text"), "50")
        self.assertEqual(self.app.chip_wrong.cget("text"), "0")
        self.assertEqual(self.app.chip_blank.cget("text"), "0")
        self.assertEqual(self.app.chip_multi.cget("text"), "0")

    def test_changing_answer_key_updates_score(self):

        self.app.student_answers = ["A"] * 25 + ["B"] * 25


        self.app.answer_key = ["A"] * 50
        self.app.on_score()
        self.assertEqual(self.app.score_result["score"], 5.0)


        self.app.answer_key = ["A"] * 25 + ["B"] * 25
        self.app.on_score()
        self.assertEqual(self.app.score_result["score"], 10.0)


        self.app.answer_key = ["C"] * 50
        self.app.on_score()
        self.assertEqual(self.app.score_result["score"], 0.0)

    def test_treeview_row_tags_colored(self):


        self.app.student_answers = ["A", "B", "BLANK", "MULTIPLE"] + ["A"] * 46
        self.app.answer_key = ["A"] * 50
        self.app.on_score()

        items = self.app.tree.get_children()

        self.assertIn("correct", self.app.tree.item(items[0], "tags"))

        self.assertIn("wrong", self.app.tree.item(items[1], "tags"))

        self.assertIn("blank", self.app.tree.item(items[2], "tags"))

        self.assertIn("multiple", self.app.tree.item(items[3], "tags"))


        self.app.score_result = None
        self.app._update_table_unscored()
        items_unscored = self.app.tree.get_children()
        self.assertIn("normal", self.app.tree.item(items_unscored[0], "tags"))
        self.assertIn("blank", self.app.tree.item(items_unscored[2], "tags"))
        self.assertIn("multiple", self.app.tree.item(items_unscored[3], "tags"))





    def test_manual_key_save_success(self):

        dlg = self.app.on_manual_key()
        dlg.withdraw()
        dlg.fill_all("B")
        dlg.on_save()

        self.assertIsNotNone(self.app.answer_key)
        self.assertEqual(len(self.app.answer_key), 50)
        self.assertEqual(self.app.answer_key, ["B"] * 50)
        self.assertIn("Thủ công", self.app.lbl_key_status.cget("text"))
        self.assertEqual(str(self.app.btn_export_key["state"]), "normal")

    def test_manual_key_missing_question_10_rejected(self):

        dlg = self.app.on_manual_key()
        dlg.withdraw()
        dlg.fill_all("A")

        dlg.set_answer(9, "")

        with patch("tkinter.messagebox.showwarning") as mock_warn:
            dlg.on_save()
            mock_warn.assert_called_once()
            args, _ = mock_warn.call_args
            self.assertIn("10", str(args))


        self.assertIsNone(self.app.answer_key)
        dlg.destroy()

    def test_manual_key_edit_question_25_only(self):

        dlg = self.app.on_manual_key()
        dlg.withdraw()
        dlg.fill_all("A")

        dlg.set_answer(24, "C")

        answers = dlg.get_answers()
        self.assertEqual(answers[23], "A")
        self.assertEqual(answers[24], "C")
        self.assertEqual(answers[25], "A")

        dlg.on_save()
        self.assertEqual(self.app.answer_key[24], "C")
        self.assertEqual(self.app.answer_key[0], "A")
        self.assertEqual(self.app.answer_key[49], "A")

    def test_manual_key_cancel_preserves_current_key(self):

        self.app.answer_key = ["D"] * 50
        dlg = self.app.on_manual_key()
        dlg.withdraw()
        dlg.fill_all("A")

        dlg.destroy()

        self.assertEqual(self.app.answer_key, ["D"] * 50)

    def test_manual_key_prefills_loaded_json(self):

        key_file = ROOT / "answer_key" / "answer_key.json"
        expected = load_answer_key(key_file)
        self.app._apply_new_answer_key(expected, "test.json")

        dlg = self.app.on_manual_key()
        dlg.withdraw()
        dlg_answers = dlg.get_answers()

        self.assertEqual(dlg_answers, expected)
        dlg.destroy()

    def test_manual_key_export_json_and_reload(self):

        dlg = self.app.on_manual_key()
        dlg.withdraw()
        sample_answers = (["A", "B", "C", "D"] * 12) + ["A", "B"]
        for idx, val in enumerate(sample_answers):
            dlg.set_answer(idx, val)
        dlg.on_save()

        with tempfile.TemporaryDirectory() as tmpdir:
            out_json = Path(tmpdir) / "exported_key.json"
            with patch("tkinter.filedialog.asksaveasfilename", return_value=str(out_json)):
                with patch("tkinter.messagebox.showinfo"):
                    self.app.on_export_key_json()

            self.assertTrue(out_json.exists())

            reloaded = load_answer_key(out_json)
            self.assertEqual(reloaded, sample_answers)

    def test_export_key_json_without_key_shows_warning(self):

        self.app.answer_key = None
        with patch("tkinter.messagebox.showwarning") as mock_warn:
            with patch("tkinter.filedialog.asksaveasfilename") as mock_file:
                self.app.on_export_key_json()
                mock_warn.assert_called_once()
                mock_file.assert_not_called()

    def test_dialog_has_only_save_and_cancel_buttons(self):

        dlg = self.app.on_manual_key()
        dlg.withdraw()
        self.assertFalse(hasattr(dlg, "on_export_json"))
        self.assertFalse(hasattr(dlg, "btn_export"))
        dlg.destroy()

    def test_manual_and_json_scoring_identical(self):

        student = (["A", "B", "C", "D"] * 12) + ["BLANK", "MULTIPLE"]
        key_list = ["A"] * 50


        res_direct = score_answers(student, key_list)


        self.app.student_answers = student
        self.app._apply_new_answer_key(key_list, "Thủ công (50 câu)")
        self.app.on_score()

        self.assertEqual(self.app.score_result["score"], res_direct["score"])
        self.assertEqual(self.app.score_result["correct_count"], res_direct["correct_count"])
        self.assertEqual(self.app.score_result["wrong_count"], res_direct["wrong_count"])
        self.assertEqual(self.app.score_result["blank_count"], res_direct["blank_count"])
        self.assertEqual(self.app.score_result["multiple_count"], res_direct["multiple_count"])

    def test_rescanning_invalidates_old_score(self):
        self.app.image_path = ROOT / "test_images" / "sample_photo.png"
        self.app.student_answers = self.app.answer_key = ["A"] * 50
        self.app.on_score()
        self.assertEqual(self.app.score_result["score"], 10.0)

        self.app.on_scan_sheet()

        self.assertIsNone(self.app.score_result)
        self.assertEqual(self.app.lbl_score.cget("text"), "Chưa chấm")
        self.assertEqual(str(self.app.btn_score["state"]), "normal")
        self.assertEqual(len(self.app.tree.get_children()), 50)

    def test_failed_image_selection_preserves_previous_sheet(self):
        path = ROOT / "test_images" / "sample_photo.png"
        with patch("tkinter.filedialog.askopenfilename", return_value=str(path)):
            self.app.on_open_image()
        self.app.student_answers = self.app.answer_key = ["A"] * 50
        self.app.on_score()
        score = self.app.score_result
        self.assertEqual(self.app.image_path, path)
        self.assertIsNotNone(score)

        with patch("tkinter.filedialog.askopenfilename", return_value=str(path.with_name("missing.png"))):
            with patch("tkinter.messagebox.showerror") as error:
                self.app.on_open_image()
                error.assert_called_once()

        self.assertEqual(self.app.image_path, path)
        self.assertIs(self.app.score_result, score)
        self.assertEqual(str(self.app.btn_scan["state"]), "normal")

    def test_changing_answer_key_invalidates_old_score(self):

        self.app.student_answers = ["A"] * 50
        self.app.answer_key = ["A"] * 50
        self.app.on_score()
        self.assertEqual(self.app.score_result["score"], 10.0)


        self.app._apply_new_answer_key(["B"] * 50, "Bộ đáp án mới")


        self.assertIsNone(self.app.score_result)
        self.assertEqual(self.app.lbl_score.cget("text"), "Chưa chấm")
        self.assertEqual(self.app.chip_correct.cget("text"), "--")
        self.assertEqual(self.app.chip_wrong.cget("text"), "--")


        self.assertEqual(len(self.app.student_answers), 50)


        self.assertEqual(str(self.app.btn_score["state"]), "normal")


        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = Path(tmpdir) / "check_export.xlsx"
            with patch("tkinter.filedialog.asksaveasfilename", return_value=str(out_file)):
                with patch("tkinter.messagebox.showinfo"):
                    self.app.on_export_excel()
            wb = openpyxl.load_workbook(out_file)
            self.assertEqual(wb.active["B1"].value, "Đáp án nhận diện")


        self.app.on_score()
        self.assertIsNotNone(self.app.score_result)
        self.assertEqual(self.app.score_result["score"], 0.0)


if __name__ == "__main__":
    unittest.main()
