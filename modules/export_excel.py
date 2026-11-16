

from pathlib import Path

from .errors import OMRError

try:
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill, Border, Side
    from openpyxl.utils import get_column_letter
    _HAS_OPENPYXL = True
except ImportError:
    _HAS_OPENPYXL = False


class ExportError(OMRError):
    pass



_COLOR_CORRECT  = "C6EFCE"
_COLOR_WRONG    = "FFC7CE"
_COLOR_BLANK    = "FFEB9C"
_COLOR_MULTIPLE = "FFE5D0"
_COLOR_HEADER   = "4472C4"
_COLOR_SUMMARY  = "D9E1F2"


def export_excel(
    score_result: dict | list[str] | None,
    output_path: str | Path,
    *,
    answers: list[str] | None = None,
) -> Path:


















    if not _HAS_OPENPYXL:
        raise ExportError(
            "Thư viện openpyxl chưa cài. Chạy: pip install openpyxl"
        )


    is_scored = False
    unscored_answers = None

    if isinstance(score_result, dict) and "score" in score_result:
        required = {"score", "correct_count", "wrong_count", "blank_count",
                    "multiple_count", "total", "details"}
        if not required.issubset(score_result):
            raise ExportError("score_result thiếu trường; hãy dùng kết quả từ score_answers().")
        is_scored = True
    elif answers is not None:
        unscored_answers = list(answers)
    elif isinstance(score_result, list):
        unscored_answers = list(score_result)
    elif isinstance(score_result, dict) and "answers" in score_result and score_result["answers"] is not None:
        unscored_answers = list(score_result["answers"])
    else:
        raise ExportError("score_result thiếu trường; hãy dùng kết quả từ score_answers() hoặc cung cấp danh sách đáp án.")

    if not is_scored:
        if len(unscored_answers) != 50:
            raise ExportError(f"Cần đúng 50 đáp án để xuất Excel, nhận được {len(unscored_answers)}.")

    output_path = Path(output_path)
    if output_path.suffix.lower() != ".xlsx":
        output_path = output_path.with_suffix(".xlsx")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    wb = openpyxl.Workbook()
    ws = wb.active
    if ws is None:
        ws = wb.create_sheet()
    ws.title = "Kết quả"
    side = Side(style="thin", color="AAAAAA")
    thin_border = Border(left=side, right=side, top=side, bottom=side)

    header_font = Font(bold=True, color="FFFFFF", name="Calibri", size=11)
    header_fill = PatternFill("solid", fgColor=_COLOR_HEADER)
    header_align = Alignment(horizontal="center", vertical="center")
    center = Alignment(horizontal="center", vertical="center")
    bold = Font(bold=True, name="Calibri", size=11)
    summary_fill = PatternFill("solid", fgColor=_COLOR_SUMMARY)
    summary_align = Alignment(horizontal="center", vertical="center")

    if is_scored:



        headers = ["Câu", "Đáp án HS", "Đáp án đúng", "Kết quả"]
        for col_idx, header in enumerate(headers, start=1):
            cell = ws.cell(row=1, column=col_idx, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_align
            cell.border = thin_border
        ws.row_dimensions[1].height = 22

        result_label = {
            "correct":  "✓ Đúng",
            "wrong":    "✗ Sai",
            "blank":    "— Bỏ trống",
            "multiple": "⚠ Nhiều đáp án",
        }
        result_color = {
            "correct":  _COLOR_CORRECT,
            "wrong":    _COLOR_WRONG,
            "blank":    _COLOR_BLANK,
            "multiple": _COLOR_MULTIPLE,
        }

        for detail in score_result["details"]:
            row = detail["question"] + 1
            result = detail["result"]
            fill = PatternFill("solid", fgColor=result_color.get(result, "FFFFFF"))

            values = [
                detail["question"],
                detail["student"],
                detail["correct"],
                result_label.get(result, result),
            ]
            for col_idx, val in enumerate(values, start=1):
                cell = ws.cell(row=row, column=col_idx, value=val)
                cell.alignment = center
                cell.border = thin_border
                if col_idx >= 2:
                    cell.fill = fill

        summary_row = score_result["total"] + 3
        summary_data = [
            ("Tổng số câu",      score_result["total"]),
            ("Số câu đúng",      score_result["correct_count"]),
            ("Số câu sai",       score_result["wrong_count"]),
            ("Số câu bỏ trống",  score_result["blank_count"]),
            ("Nhiều đáp án",     score_result["multiple_count"]),
            ("Điểm (thang 10)",  score_result["score"]),
        ]
        for offset, (label, value) in enumerate(summary_data):
            label_cell = ws.cell(row=summary_row + offset, column=1, value=label)
            value_cell = ws.cell(row=summary_row + offset, column=2, value=value)
            for cell in (label_cell, value_cell):
                cell.font = bold
                cell.fill = summary_fill
                cell.border = thin_border
                cell.alignment = summary_align


        score_cell = ws.cell(row=summary_row + 5, column=2)
        score_cell.font = Font(bold=True, size=14, color="C00000", name="Calibri")

        col_widths = [8, 14, 16, 18]
        for col_idx, width in enumerate(col_widths, start=1):
            ws.column_dimensions[get_column_letter(col_idx)].width = width

    else:



        headers = ["Câu", "Đáp án nhận diện", "Trạng thái"]
        for col_idx, header in enumerate(headers, start=1):
            cell = ws.cell(row=1, column=col_idx, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_align
            cell.border = thin_border
        ws.row_dimensions[1].height = 22

        blank_cnt = 0
        multiple_cnt = 0
        valid_cnt = 0

        for idx, ans in enumerate(unscored_answers, start=1):
            row = idx + 1
            if ans == "BLANK":
                status = "— Bỏ trống"
                fill_color = _COLOR_BLANK
                blank_cnt += 1
            elif ans == "MULTIPLE":
                status = "⚠ Nhiều đáp án"
                fill_color = _COLOR_MULTIPLE
                multiple_cnt += 1
            elif ans in {"A", "B", "C", "D"}:
                status = "Đã chọn"
                fill_color = "FFFFFF"
                valid_cnt += 1
            else:
                status = "Không hợp lệ"
                fill_color = _COLOR_WRONG

            fill = PatternFill("solid", fgColor=fill_color)
            values = [idx, ans, status]
            for col_idx, val in enumerate(values, start=1):
                cell = ws.cell(row=row, column=col_idx, value=val)
                cell.alignment = center
                cell.border = thin_border
                if col_idx >= 2 and fill_color != "FFFFFF":
                    cell.fill = fill

        summary_row = len(unscored_answers) + 3
        summary_data = [
            ("Tổng số câu",       len(unscored_answers)),
            ("Số câu đã chọn",    valid_cnt),
            ("Số câu bỏ trống",   blank_cnt),
            ("Số câu tô nhiều",   multiple_cnt),
            ("Ghi chú",           "Chưa có đáp án chuẩn để tính điểm"),
        ]
        for offset, (label, value) in enumerate(summary_data):
            label_cell = ws.cell(row=summary_row + offset, column=1, value=label)
            value_cell = ws.cell(row=summary_row + offset, column=2, value=value)
            for cell in (label_cell, value_cell):
                cell.font = bold
                cell.fill = summary_fill
                cell.border = thin_border
                cell.alignment = summary_align

        col_widths = [8, 18, 18]
        for col_idx, width in enumerate(col_widths, start=1):
            ws.column_dimensions[get_column_letter(col_idx)].width = width


    try:

        wb.save(output_path)
    except PermissionError as exc:
        raise ExportError(
            f"Không ghi được file Excel (có thể đang mở trong Excel): {output_path}\n{exc}"
        ) from exc
    except OSError as exc:
        raise ExportError(f"Lỗi ghi file Excel {output_path}: {exc}") from exc

    return output_path


def export_unscored_excel(answers: list[str], output_path: str | Path) -> Path:

    return export_excel(None, output_path, answers=answers)
