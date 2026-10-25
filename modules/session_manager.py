"""Quản lý nghiệp vụ Đợt thi, Lớp học, Học sinh, Mã đề và Bộ đáp án.

Đảm bảo:
- Mã đợt thi, mã đề, SBD là chuỗi giữ số 0 đầu ("01", "0023", "101").
- Cách ly hoàn toàn dữ liệu giữa các đợt thi.
- Hỗ trợ nhập danh sách học sinh & đáp án từ Excel / CSV.
- Tự động đối chiếu SBD, phát hiện trùng lặp, chuyển trạng thái NEEDS_REVIEW.
- Hỗ trợ chấm lại khi đáp án chuẩn thay đổi.
"""

import csv
from datetime import datetime
import json
from pathlib import Path
from typing import Any

from .db import get_connection, init_db, transaction
from .errors import OMRError
from .scoring import ScoringError, score_answers, VALID_ANSWERS

try:
    import openpyxl
    _HAS_OPENPYXL = True
except ImportError:
    _HAS_OPENPYXL = False

DEFAULT_GRADE_SCALE = {
    "gioi": 8.0,
    "kha": 6.5,
    "trung_binh": 5.0,
    "yeu": 3.5,
}


def classify_score(score: float, scale_config: dict[str, float] | None = None) -> str:
    """Xếp loại điểm số theo thang 10."""
    cfg = scale_config or DEFAULT_GRADE_SCALE
    if score >= cfg.get("gioi", 8.0):
        return "Giỏi"
    if score >= cfg.get("kha", 6.5):
        return "Khá"
    if score >= cfg.get("trung_binh", 5.0):
        return "Trung bình"
    if score >= cfg.get("yeu", 3.5):
        return "Yếu"
    return "Kém"


class SessionManager:
    """Lớp quản lý nghiệp vụ đợt thi, học sinh, mã đề và kết quả."""

    def __init__(self, db_path: Path | str | None = None):
        self.db_path = db_path
        init_db(self.db_path)

    # ── ĐỢT THI (EXAM SESSION) ────────────────────────────────────────────────

    def create_session(
        self,
        session_code: str,
        name: str,
        subject: str,
        exam_date: str,
        question_count: int = 50,
        max_score: float = 10.0,
        status: str = "ACTIVE",
        grade_scale_config: dict | None = None,
        class_codes: list[str] | None = None,
    ) -> dict:
        """Tạo đợt thi mới; session_code phải là chuỗi (bảo toàn số 0 đầu)."""
        session_code = str(session_code).strip()
        if not session_code:
            raise OMRError("Mã đợt thi không được để trống.")
        name = str(name).strip()
        if not name:
            raise OMRError("Tên đợt thi không được để trống.")
        now = datetime.now().isoformat()
        scale_json = json.dumps(grade_scale_config or DEFAULT_GRADE_SCALE)

        with transaction(self.db_path) as conn:
            # Kiểm tra trùng mã
            cur = conn.execute("SELECT id FROM exam_sessions WHERE session_code = ?", (session_code,))
            if cur.fetchone():
                raise OMRError(f"Mã đợt thi '{session_code}' đã tồn tại.")

            conn.execute(
                """
                INSERT INTO exam_sessions (session_code, name, subject, exam_date, question_count,
                                           max_score, status, grade_scale_config, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (session_code, name, subject, exam_date, question_count, max_score, status, scale_json, now, now),
            )
            if class_codes:
                for cc in class_codes:
                    cc = str(cc).strip()
                    if cc:
                        # Đảm bảo lớp tồn tại
                        conn.execute("INSERT OR IGNORE INTO classes (class_code, class_name) VALUES (?, ?)", (cc, f"Lớp {cc}"))
                        conn.execute(
                            "INSERT OR IGNORE INTO session_classes (session_code, class_code) VALUES (?, ?)",
                            (session_code, cc),
                        )

        return self.get_session(session_code)

    def update_session(self, session_code: str, **kwargs) -> dict:
        """Cập nhật thông tin đợt thi."""
        session_code = str(session_code).strip()
        allowed = {"name", "subject", "exam_date", "question_count", "max_score", "status", "grade_scale_config"}
        updates = []
        params = []
        for key, val in kwargs.items():
            if key in allowed:
                if key == "grade_scale_config" and isinstance(val, dict):
                    val = json.dumps(val)
                updates.append(f"{key} = ?")
                params.append(val)
        if not updates and "class_codes" not in kwargs:
            return self.get_session(session_code)

        now = datetime.now().isoformat()
        updates.append("updated_at = ?")
        params.append(now)
        params.append(session_code)

        with transaction(self.db_path) as conn:
            if updates:
                sql = f"UPDATE exam_sessions SET {', '.join(updates)} WHERE session_code = ?"
                conn.execute(sql, params)

            if "class_codes" in kwargs and kwargs["class_codes"] is not None:
                conn.execute("DELETE FROM session_classes WHERE session_code = ?", (session_code,))
                for cc in kwargs["class_codes"]:
                    cc = str(cc).strip()
                    if cc:
                        conn.execute("INSERT OR IGNORE INTO classes (class_code, class_name) VALUES (?, ?)", (cc, f"Lớp {cc}"))
                        conn.execute("INSERT INTO session_classes (session_code, class_code) VALUES (?, ?)", (session_code, cc))

        return self.get_session(session_code)

    def get_session(self, session_code: str) -> dict | None:
        """Lấy thông tin đợt thi theo mã."""
        session_code = str(session_code).strip()
        conn = get_connection(self.db_path)
        cur = conn.execute("SELECT * FROM exam_sessions WHERE session_code = ?", (session_code,))
        row = cur.fetchone()
        if not row:
            return None
        res = dict(row)
        if res.get("grade_scale_config"):
            try:
                res["grade_scale_config"] = json.loads(res["grade_scale_config"])
            except Exception:
                res["grade_scale_config"] = DEFAULT_GRADE_SCALE
        # Lấy danh sách lớp
        cur2 = conn.execute("SELECT class_code FROM session_classes WHERE session_code = ?", (session_code,))
        res["class_codes"] = [r["class_code"] for r in cur2.fetchall()]
        # Lấy danh sách mã đề
        cur3 = conn.execute("SELECT exam_code FROM exam_codes WHERE session_code = ?", (session_code,))
        res["exam_codes"] = [r["exam_code"] for r in cur3.fetchall()]
        return res

    def list_sessions(self, search: str | None = None, status: str | None = None) -> list[dict]:
        """Tìm kiếm và lọc danh sách đợt thi."""
        conn = get_connection(self.db_path)
        query = "SELECT * FROM exam_sessions WHERE 1=1"
        params: list[Any] = []
        if status:
            query += " AND status = ?"
            params.append(status)
        if search:
            query += " AND (session_code LIKE ? OR name LIKE ? OR subject LIKE ?)"
            s = f"%{search}%"
            params.extend([s, s, s])
        query += " ORDER BY session_code DESC"
        cur = conn.execute(query, params)
        rows = cur.fetchall()
        result = []
        for r in rows:
            d = dict(r)
            if d.get("grade_scale_config"):
                try:
                    d["grade_scale_config"] = json.loads(d["grade_scale_config"])
                except Exception:
                    d["grade_scale_config"] = DEFAULT_GRADE_SCALE
            result.append(d)
        return result

    # ── LỚP HỌC VÀ HỌC SINH ──────────────────────────────────────────────────

    def add_class(self, class_code: str, class_name: str | None = None) -> dict:
        """Thêm lớp học."""
        class_code = str(class_code).strip()
        class_name = str(class_name or f"Lớp {class_code}").strip()
        with transaction(self.db_path) as conn:
            conn.execute(
                "INSERT INTO classes (class_code, class_name) VALUES (?, ?) ON CONFLICT(class_code) DO UPDATE SET class_name=excluded.class_name",
                (class_code, class_name),
            )
        return {"class_code": class_code, "class_name": class_name}

    def list_classes(self) -> list[dict]:
        """Liệt kê danh sách lớp."""
        conn = get_connection(self.db_path)
        cur = conn.execute("SELECT * FROM classes ORDER BY class_code ASC")
        return [dict(r) for r in cur.fetchall()]

    def add_student(self, student_code: str, sbd: str, full_name: str, class_code: str) -> dict:
        """Thêm hoặc cập nhật học sinh."""
        student_code = str(student_code).strip()
        sbd = str(sbd).strip()
        full_name = str(full_name).strip()
        class_code = str(class_code).strip()
        if not student_code or not sbd or not full_name or not class_code:
            raise OMRError("Thông tin học sinh không được để trống trường nào.")

        with transaction(self.db_path) as conn:
            conn.execute("INSERT OR IGNORE INTO classes (class_code, class_name) VALUES (?, ?)", (class_code, f"Lớp {class_code}"))
            conn.execute(
                """
                INSERT INTO students (student_code, sbd, full_name, class_code)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(student_code) DO UPDATE SET
                    sbd=excluded.sbd,
                    full_name=excluded.full_name,
                    class_code=excluded.class_code
                """,
                (student_code, sbd, full_name, class_code),
            )
        return {"student_code": student_code, "sbd": sbd, "full_name": full_name, "class_code": class_code}

    def get_student_by_sbd(self, sbd: str, session_code: str | None = None) -> dict | None:
        """Tìm học sinh theo số báo danh (ưu tiên trong các lớp thuộc đợt thi nếu có)."""
        sbd = str(sbd).strip()
        conn = get_connection(self.db_path)
        if session_code:
            cur = conn.execute(
                """
                SELECT s.* FROM students s
                INNER JOIN session_classes sc ON s.class_code = sc.class_code
                WHERE s.sbd = ? AND sc.session_code = ?
                """,
                (sbd, session_code),
            )
            row = cur.fetchone()
            if row:
                return dict(row)

        cur = conn.execute("SELECT * FROM students WHERE sbd = ?", (sbd,))
        row = cur.fetchone()
        return dict(row) if row else None

    def list_students(self, class_code: str | None = None, search: str | None = None) -> list[dict]:
        """Liệt kê danh sách học sinh theo lớp hoặc tìm kiếm."""
        conn = get_connection(self.db_path)
        query = "SELECT * FROM students WHERE 1=1"
        params: list[Any] = []
        if class_code:
            query += " AND class_code = ?"
            params.append(class_code)
        if search:
            query += " AND (student_code LIKE ? OR sbd LIKE ? OR full_name LIKE ?)"
            s = f"%{search}%"
            params.extend([s, s, s])
        query += " ORDER BY class_code ASC, sbd ASC"
        cur = conn.execute(query, params)
        return [dict(r) for r in cur.fetchall()]

    def import_students_from_csv(self, file_path: str | Path, default_class: str | None = None) -> int:
        """Nhập danh sách học sinh từ file CSV.

        Header hỗ trợ: student_code, sbd, full_name, class_code
        (hoặc tiếng Việt: ma_hs, sbd, ho_ten, lop).
        """
        path = Path(file_path)
        if not path.is_file():
            raise OMRError(f"File CSV không tồn tại: {path}")

        count = 0
        with open(path, mode="r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Chuẩn hóa tên cột
                r = {k.strip().lower(): str(v).strip() for k, v in row.items() if k}
                code = r.get("student_code") or r.get("ma_hs") or r.get("mã hs") or r.get("mahs")
                sbd = r.get("sbd") or r.get("so_bao_danh") or r.get("số báo danh")
                name = r.get("full_name") or r.get("ho_ten") or r.get("họ và tên") or r.get("hoten")
                c_code = r.get("class_code") or r.get("lop") or r.get("lớp") or default_class

                if code and sbd and name and c_code:
                    self.add_student(code, sbd, name, c_code)
                    count += 1
        return count

    def import_students_from_excel(self, file_path: str | Path, default_class: str | None = None) -> int:
        """Nhập danh sách học sinh từ file Excel .xlsx."""
        if not _HAS_OPENPYXL:
            raise OMRError("Cần thư viện openpyxl để nhập file Excel.")
        path = Path(file_path)
        if not path.is_file():
            raise OMRError(f"File Excel không tồn tại: {path}")

        wb = openpyxl.load_workbook(path, data_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return 0

        header = [str(c).strip().lower() if c is not None else "" for c in rows[0]]
        # Tìm index các cột
        col_map = {}
        for idx, col in enumerate(header):
            if col in ("student_code", "ma_hs", "mã hs", "mahs", "mã học sinh"):
                col_map["code"] = idx
            elif col in ("sbd", "so_bao_danh", "số báo danh"):
                col_map["sbd"] = idx
            elif col in ("full_name", "ho_ten", "họ và tên", "hoten", "họ tên"):
                col_map["name"] = idx
            elif col in ("class_code", "lop", "lớp", "mã lớp"):
                col_map["class"] = idx

        count = 0
        for r in rows[1:]:
            if not any(r):
                continue
            code = str(r[col_map["code"]]).strip() if "code" in col_map and r[col_map["code"]] is not None else None
            sbd = str(r[col_map["sbd"]]).strip() if "sbd" in col_map and r[col_map["sbd"]] is not None else None
            name = str(r[col_map["name"]]).strip() if "name" in col_map and r[col_map["name"]] is not None else None
            c_code = str(r[col_map["class"]]).strip() if "class" in col_map and r[col_map["class"]] is not None else default_class

            # Chuyển đổi định dạng số sang chuỗi nguyên vẹn (ví dụ 101.0 -> 101)
            if code and code.endswith(".0"):
                code = code[:-2]
            if sbd and sbd.endswith(".0"):
                sbd = sbd[:-2]

            if code and sbd and name and c_code:
                self.add_student(code, sbd, name, c_code)
                count += 1
        return count

    # ── MÃ ĐỀ VÀ BỘ ĐÁP ÁN (EXAM CODES & ANSWER KEYS) ─────────────────────────

    def set_answer_key(
        self,
        session_code: str,
        exam_code: str,
        answers: list[str],
        source: str = "manual",
    ) -> dict:
        """Lưu hoặc cập nhật bộ đáp án cho mã đề trong đợt thi."""
        session_code = str(session_code).strip()
        exam_code = str(exam_code).strip()
        if not session_code or not exam_code:
            raise OMRError("Mã đợt thi và mã đề không được để trống.")

        # Lấy session để biết question_count
        sess = self.get_session(session_code)
        if not sess:
            raise OMRError(f"Đợt thi '{session_code}' không tồn tại.")
        expected_len = sess["question_count"]

        if len(answers) != expected_len:
            raise ScoringError(f"Đáp án mã đề {exam_code} cần đúng {expected_len} câu, nhận được {len(answers)}.")

        for i, ans in enumerate(answers, start=1):
            if ans not in VALID_ANSWERS:
                raise ScoringError(f"Câu {i}: đáp án '{ans}' không hợp lệ (chỉ nhận A, B, C, D).")

        now = datetime.now().isoformat()
        ans_json = json.dumps(answers)

        with transaction(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO exam_codes (session_code, exam_code, answers_json, source, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(session_code, exam_code) DO UPDATE SET
                    answers_json=excluded.answers_json,
                    source=excluded.source
                """,
                (session_code, exam_code, ans_json, source, now),
            )

        return {"session_code": session_code, "exam_code": exam_code, "answers": answers, "source": source}

    def get_answer_key(self, session_code: str, exam_code: str) -> list[str] | None:
        """Lấy bộ đáp án đúng theo Mã đợt thi + Mã đề."""
        session_code = str(session_code).strip()
        exam_code = str(exam_code).strip()
        conn = get_connection(self.db_path)
        cur = conn.execute(
            "SELECT answers_json FROM exam_codes WHERE session_code = ? AND exam_code = ?",
            (session_code, exam_code),
        )
        row = cur.fetchone()
        if not row:
            return None
        return json.loads(row["answers_json"])

    def list_exam_codes(self, session_code: str) -> list[dict]:
        """Liệt kê tất cả các mã đề trong một đợt thi."""
        session_code = str(session_code).strip()
        conn = get_connection(self.db_path)
        cur = conn.execute(
            "SELECT session_code, exam_code, source, created_at, answers_json FROM exam_codes WHERE session_code = ? ORDER BY exam_code ASC",
            (session_code,),
        )
        rows = cur.fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["answers"] = json.loads(d.pop("answers_json"))
            result.append(d)
        return result

    def import_answer_keys_from_csv(self, session_code: str, file_path: str | Path) -> int:
        """Nhập nhiều mã đề và đáp án từ file CSV.

        Định dạng CSV:
        Cột đầu là exam_code (hoặc ma_de). Các cột tiếp theo là 1, 2, ..., 50 hoặc câu 1, câu 2...
        hoặc format dòng: exam_code, question, answer.
        """
        path = Path(file_path)
        if not path.is_file():
            raise OMRError(f"File CSV không tồn tại: {path}")

        sess = self.get_session(session_code)
        if not sess:
            raise OMRError(f"Đợt thi '{session_code}' không tồn tại.")
        q_count = sess["question_count"]

        count = 0
        with open(path, mode="r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            header = [c.strip().lower() for c in next(reader, [])]
            if not header:
                return 0

            # Trường hợp 1: Dòng ngang (cột 1 là exam_code, 50 cột tiếp theo là đáp án)
            if len(header) >= q_count + 1:
                for row in reader:
                    if not row or not any(row):
                        continue
                    ecode = str(row[0]).strip()
                    if ecode.endswith(".0"):
                        ecode = ecode[:-2]
                    ans = [str(x).strip().upper() for x in row[1 : q_count + 1]]
                    if len(ans) == q_count and all(a in VALID_ANSWERS for a in ans):
                        self.set_answer_key(session_code, ecode, ans, source="csv")
                        count += 1
            else:
                # Trường hợp 2: Bảng dọc (exam_code, question, answer)
                rows = list(reader)
                grouped: dict[str, dict[int, str]] = {}
                for r in rows:
                    if len(r) >= 3:
                        ecode = str(r[0]).strip()
                        try:
                            q_idx = int(r[1])
                            ans = str(r[2]).strip().upper()
                            if ans in VALID_ANSWERS:
                                grouped.setdefault(ecode, {})[q_idx] = ans
                        except ValueError:
                            continue
                for ecode, ans_map in grouped.items():
                    if len(ans_map) == q_count and all(i in ans_map for i in range(1, q_count + 1)):
                        ans_list = [ans_map[i] for i in range(1, q_count + 1)]
                        self.set_answer_key(session_code, ecode, ans_list, source="csv")
                        count += 1
        return count

    def import_answer_keys_from_excel(self, session_code: str, file_path: str | Path) -> int:
        """Nhập nhiều mã đề và đáp án từ file Excel .xlsx."""
        if not _HAS_OPENPYXL:
            raise OMRError("Cần openpyxl để nhập file Excel.")
        path = Path(file_path)
        if not path.is_file():
            raise OMRError(f"File Excel không tồn tại: {path}")

        sess = self.get_session(session_code)
        if not sess:
            raise OMRError(f"Đợt thi '{session_code}' không tồn tại.")
        q_count = sess["question_count"]

        wb = openpyxl.load_workbook(path, data_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return 0

        count = 0
        header = rows[0]
        # Kiểm tra xem dạng ngang hay dọc
        if len(header) >= q_count + 1:
            for r in rows[1:]:
                if not any(r):
                    continue
                ecode = str(r[0]).strip()
                if ecode.endswith(".0"):
                    ecode = ecode[:-2]
                ans = [str(x).strip().upper() for x in r[1 : q_count + 1] if x is not None]
                if len(ans) == q_count and all(a in VALID_ANSWERS for a in ans):
                    self.set_answer_key(session_code, ecode, ans, source="excel")
                    count += 1
        return count

    # ── LƯU VÀ CHẤM LẠI KẾT QUẢ (RESULTS & RE-GRADING) ─────────────────────────

    def save_exam_result(
        self,
        session_code: str,
        image_path: str | Path,
        student_answers: list[str],
        sbd: str | None = None,
        exam_code: str | None = None,
        student_code: str | None = None,
        student_name: str | None = None,
        class_code: str | None = None,
    ) -> dict:
        """Lưu kết quả bài thi. Tự động kiểm tra trùng lặp và chấm điểm."""
        session_code = str(session_code).strip()
        sess = self.get_session(session_code)
        if not sess:
            raise OMRError(f"Đợt thi '{session_code}' không tồn tại.")

        sbd = str(sbd).strip() if sbd else None
        exam_code = str(exam_code).strip() if exam_code else None
        image_path = str(image_path)
        now = datetime.now().isoformat()

        # Đối chiếu học sinh nếu chưa có thông tin
        if sbd and (not student_name or not class_code):
            stu = self.get_student_by_sbd(sbd, session_code)
            if stu:
                student_code = student_code or stu["student_code"]
                student_name = student_name or stu["full_name"]
                class_code = class_code or stu["class_code"]

        # Kiểm tra trạng thái và các điều kiện
        review_reasons = []
        status = "SUCCESS"

        if not exam_code:
            status = "NEEDS_REVIEW"
            review_reasons.append("Thiếu mã đề thi.")

        if not sbd:
            status = "NEEDS_REVIEW"
            review_reasons.append("Thiếu số báo danh.")
        elif not student_name:
            status = "NEEDS_REVIEW"
            review_reasons.append(f"Không tìm thấy học sinh với SBD '{sbd}' trong danh sách.")

        # Kiểm tra trùng SBD trong đợt thi
        if sbd:
            conn = get_connection(self.db_path)
            cur = conn.execute(
                "SELECT id, image_path FROM exam_results WHERE session_code = ? AND sbd = ? AND status != 'FAILED'",
                (session_code, sbd),
            )
            existing = cur.fetchall()
            if existing:
                status = "NEEDS_REVIEW"
                review_reasons.append(f"Trùng số báo danh '{sbd}' trong đợt thi (đã có {len(existing)} bài khác).")

        # Lấy đáp án chuẩn và chấm điểm
        score_res = None
        classification = None
        if exam_code:
            key = self.get_answer_key(session_code, exam_code)
            if not key:
                status = "NEEDS_REVIEW"
                review_reasons.append(f"Chưa có đáp án chuẩn cho mã đề '{exam_code}'.")
            else:
                score_res = score_answers(student_answers, key)
                classification = classify_score(score_res["score"], sess.get("grade_scale_config"))

        review_reason_str = "; ".join(review_reasons) if review_reasons else None

        with transaction(self.db_path) as conn:
            cur = conn.execute(
                """
                INSERT INTO exam_results (
                    session_code, image_path, student_code, sbd, student_name, class_code,
                    exam_code, student_answers_json, score, correct_count, wrong_count,
                    blank_count, multiple_count, total_questions, details_json,
                    classification, status, review_reason, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_code,
                    image_path,
                    student_code,
                    sbd,
                    student_name,
                    class_code,
                    exam_code,
                    json.dumps(student_answers),
                    score_res["score"] if score_res else None,
                    score_res["correct_count"] if score_res else None,
                    score_res["wrong_count"] if score_res else None,
                    score_res["blank_count"] if score_res else None,
                    score_res["multiple_count"] if score_res else None,
                    sess["question_count"],
                    json.dumps(score_res["details"]) if score_res else None,
                    classification,
                    status,
                    review_reason_str,
                    now,
                    now,
                ),
            )
            result_id = cur.lastrowid

        return self.get_result_by_id(result_id)

    def get_result_by_id(self, result_id: int) -> dict | None:
        """Lấy một kết quả bài thi theo ID."""
        conn = get_connection(self.db_path)
        cur = conn.execute("SELECT * FROM exam_results WHERE id = ?", (result_id,))
        row = cur.fetchone()
        if not row:
            return None
        res = dict(row)
        res["student_answers"] = json.loads(res["student_answers_json"])
        if res.get("details_json"):
            res["details"] = json.loads(res["details_json"])
        return res

    def list_results(
        self,
        session_code: str,
        class_code: str | None = None,
        exam_code: str | None = None,
        status: str | None = None,
    ) -> list[dict]:
        """Lấy danh sách kết quả bài thi theo bộ lọc."""
        session_code = str(session_code).strip()
        conn = get_connection(self.db_path)
        query = "SELECT * FROM exam_results WHERE session_code = ?"
        params: list[Any] = [session_code]
        if class_code:
            query += " AND class_code = ?"
            params.append(class_code)
        if exam_code:
            query += " AND exam_code = ?"
            params.append(exam_code)
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY id ASC"

        cur = conn.execute(query, params)
        rows = cur.fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["student_answers"] = json.loads(d["student_answers_json"])
            if d.get("details_json"):
                d["details"] = json.loads(d["details_json"])
            result.append(d)
        return result

    def re_grade_session(self, session_code: str) -> int:
        """Chấm lại toàn bộ bài thi trong đợt thi khi đáp án chuẩn hoặc ngưỡng điểm thay đổi."""
        session_code = str(session_code).strip()
        sess = self.get_session(session_code)
        if not sess:
            raise OMRError(f"Đợt thi '{session_code}' không tồn tại.")

        results = self.list_results(session_code)
        now = datetime.now().isoformat()
        updated_count = 0

        with transaction(self.db_path) as conn:
            for item in results:
                # Nếu không có mã đề thì không thể chấm lại
                ecode = item.get("exam_code")
                if not ecode:
                    continue
                key = self.get_answer_key(session_code, ecode)
                if not key:
                    # Chuyển trạng thái sang NEEDS_REVIEW
                    conn.execute(
                        """
                        UPDATE exam_results
                        SET status = 'NEEDS_REVIEW', review_reason = 'Không tìm thấy đáp án chuẩn mã đề', updated_at = ?
                        WHERE id = ?
                        """,
                        (now, item["id"]),
                    )
                    continue

                student_answers = item["student_answers"]
                score_res = score_answers(student_answers, key)
                classification = classify_score(score_res["score"], sess.get("grade_scale_config"))

                # Kiểm tra xem có lý do review khác không
                review_reasons = []
                new_status = "SUCCESS"
                if not item.get("sbd"):
                    new_status = "NEEDS_REVIEW"
                    review_reasons.append("Thiếu số báo danh.")
                elif not item.get("student_name"):
                    new_status = "NEEDS_REVIEW"
                    review_reasons.append("Không tìm thấy học sinh trong danh sách.")

                conn.execute(
                    """
                    UPDATE exam_results
                    SET score = ?, correct_count = ?, wrong_count = ?, blank_count = ?,
                        multiple_count = ?, details_json = ?, classification = ?,
                        status = ?, review_reason = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        score_res["score"],
                        score_res["correct_count"],
                        score_res["wrong_count"],
                        score_res["blank_count"],
                        score_res["multiple_count"],
                        json.dumps(score_res["details"]),
                        classification,
                        new_status,
                        "; ".join(review_reasons) if review_reasons else None,
                        now,
                        item["id"],
                    ),
                )
                updated_count += 1

        return updated_count
