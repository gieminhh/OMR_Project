from pathlib import Path

from .errors import OMRError
from .validation import QUESTION_COUNT

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
        raise ExportError("Thư viện openpyxl chưa cài. Chạy: pip install openpyxl")

    is_scored = isinstance(score_result, dict) and "score" in score_result
    if is_scored:
        required = {"score", "correct_count", "wrong_count", "blank_count",
                    "multiple_count", "total", "details"}
        if not required.issubset(score_result):
            raise ExportError("score_result thiếu trường; hãy dùng kết quả từ score_answers().")
    elif answers is not None:
        unscored_answers = list(answers)
    elif isinstance(score_result, list):
        unscored_answers = list(score_result)
    elif isinstance(score_result, dict) and "answers" in score_result and score_result["answers"] is not None:
        unscored_answers = list(score_result["answers"])
    else:
        raise ExportError("score_result thiếu trường; hãy dùng kết quả từ score_answers() hoặc cung cấp danh sách đáp án.")

    if not is_scored and len(unscored_answers) != QUESTION_COUNT:
        raise ExportError(f"Cần đúng {QUESTION_COUNT} đáp án để xuất Excel, nhận được {len(unscored_answers)}.")

    output_path = Path(output_path)
    if output_path.suffix.lower() != ".xlsx":
        output_path = output_path.with_suffix(".xlsx")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    wb = openpyxl.Workbook()
    ws = wb.active
    if ws is None:
        ws = wb.create_sheet()
    ws.title = "Kết quả"
    rows = []
    if is_scored:
        headers = ("Câu", "Đáp án HS", "Đáp án đúng", "Kết quả")
        col_widths = (8, 14, 16, 18)
        labels = {
            "correct": "✓ Đúng",
            "wrong": "✗ Sai",
            "blank": "— Bỏ trống",
            "multiple": "⚠ Nhiều đáp án",
        }
        colors = {
            "correct": _COLOR_CORRECT,
            "wrong": _COLOR_WRONG,
            "blank": _COLOR_BLANK,
            "multiple": _COLOR_MULTIPLE,
        }
        for detail in score_result["details"]:
            result = detail["result"]
            values = (detail["question"], detail["student"], detail["correct"], labels.get(result, result))
            rows.append((detail["question"] + 1, values, colors.get(result, "FFFFFF")))
        summary_row = score_result["total"] + 3
        summary = (
            ("Tổng số câu", score_result["total"]),
            ("Số câu đúng", score_result["correct_count"]),
            ("Số câu sai", score_result["wrong_count"]),
            ("Số câu bỏ trống", score_result["blank_count"]),
            ("Nhiều đáp án", score_result["multiple_count"]),
            ("Điểm (thang 10)", score_result["score"]),
        )
    else:
        headers = ("Câu", "Đáp án nhận diện", "Trạng thái")
        col_widths = (8, 18, 18)
        statuses = {
            "A": ("Đã chọn", None),
            "B": ("Đã chọn", None),
            "C": ("Đã chọn", None),
            "D": ("Đã chọn", None),
            "BLANK": ("— Bỏ trống", _COLOR_BLANK),
            "MULTIPLE": ("⚠ Nhiều đáp án", _COLOR_MULTIPLE),
        }
        counts = {"Đã chọn": 0, "— Bỏ trống": 0, "⚠ Nhiều đáp án": 0, "Không hợp lệ": 0}
        for question, answer in enumerate(unscored_answers, start=1):
            status, color = statuses.get(answer, ("Không hợp lệ", _COLOR_WRONG))
            counts[status] += 1
            rows.append((question + 1, (question, answer, status), color))
        summary_row = len(unscored_answers) + 3
        summary = (
            ("Tổng số câu", len(unscored_answers)),
            ("Số câu đã chọn", counts["Đã chọn"]),
            ("Số câu bỏ trống", counts["— Bỏ trống"]),
            ("Số câu tô nhiều", counts["⚠ Nhiều đáp án"]),
            ("Ghi chú", "Chưa có đáp án chuẩn để tính điểm"),
        )

    side = Side(style="thin", color="AAAAAA")
    border = Border(left=side, right=side, top=side, bottom=side)
    center = Alignment(horizontal="center", vertical="center")
    bold = Font(bold=True, name="Calibri", size=11)
    header_font = Font(bold=True, color="FFFFFF", name="Calibri", size=11)
    header_fill = PatternFill("solid", fgColor=_COLOR_HEADER)
    summary_fill = PatternFill("solid", fgColor=_COLOR_SUMMARY)

    ws.row_dimensions[1].height = 22
    for column, (header, width) in enumerate(zip(headers, col_widths), start=1):
        cell = ws.cell(row=1, column=column, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center
        cell.border = border
        ws.column_dimensions[get_column_letter(column)].width = width

    for row, values, color in rows:
        fill = PatternFill("solid", fgColor=color) if color is not None else None
        for column, value in enumerate(values, start=1):
            cell = ws.cell(row=row, column=column, value=value)
            cell.alignment = center
            cell.border = border
            if column >= 2 and fill is not None:
                cell.fill = fill

    for row, values in enumerate(summary, start=summary_row):
        for column, value in enumerate(values, start=1):
            cell = ws.cell(row=row, column=column, value=value)
            cell.font = bold
            cell.fill = summary_fill
            cell.border = border
            cell.alignment = center
    if is_scored:
        score_cell = ws.cell(row=summary_row + len(summary) - 1, column=2)
        score_cell.font = Font(bold=True, size=14, color="C00000", name="Calibri")

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
