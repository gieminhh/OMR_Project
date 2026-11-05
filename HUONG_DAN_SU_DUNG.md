# HƯỚNG DẪN SỬ DỤNG VÀ KIỂM THỬ OMR_PROJECT TRÊN WINDOWS

## 1. Giới thiệu tổng quan
Hệ thống OMR_Project là phần mềm nhận diện và chấm bài thi trắc nghiệm 50 câu (mẫu phiếu A4 V1 và V2), hỗ trợ:
- Quản lý đợt thi, lớp học, học sinh (SBD giữ nguyên số 0 ở đầu).
- Quản lý mã đề và đáp án chuẩn theo từng đợt thi độc lập.
- Nhập đáp án chuẩn từ:
  + Nhập thủ công (gõ chuỗi hoặc chỉnh sửa từng câu).
  + File Excel (.xlsx).
  + File CSV (4 cột, 3 cột, 2 cột hoặc dòng ngang).
  + File JSON tổng hợp (`answer_keys.json`).
  + Quét trực tiếp từ **nhiều ảnh phiếu đáp án** (không lưu bài học sinh, không phát sinh điểm).
- Chấm bài thi hàng loạt (Batch Processing) đa luồng, tự động căn chỉnh phối cảnh (4-point warp), tự động xoay 180 độ.
- Cơ chế chống trùng lặp: Chấm lại cùng một ảnh sẽ cập nhật kết quả thay vì nhân đôi bản ghi.
- Xuất báo cáo Excel 6 sheet chuyên nghiệp với SBD dạng chuỗi không mất số 0 đầu.
- Bộ nạp dữ liệu mẫu (Demo Loader) an toàn, idempotent.

---

## 2. Cài đặt môi trường trên Windows

### Yêu cầu:
- Python 3.11+ (Khuyến nghị Python 3.12 hoặc 3.13)
- Các thư viện cần thiết trong file `.venv` hoặc môi trường Python:
  ```powershell
  pip install opencv-python numpy pillow openpyxl pytest
  ```

---

## 3. Cách nạp dữ liệu mẫu (Demo)

Bạn có thể nạp dữ liệu mẫu qua **giao diện** hoặc **dòng lệnh**.

### Cách 1: Qua dòng lệnh (Terminal)
Chạy script:
```powershell
.\.venv\Scripts\python.exe scripts/load_demo_data.py
```
Dữ liệu được nạp gồm:
- **2 Đợt thi**: `01` (Khảo sát chất lượng) và `02` (Kiểm tra định kỳ).
- **4 Lớp học**: `10A1`, `10A2`, `12A1`, `12A2`.
- **43 Học sinh**: Đồng bộ với bộ ảnh benchmark (SBD từ `000001` đến `000039` và các SBD lớp 10).
- **8 Bộ đáp án chuẩn**: Mã đề `101`, `102`, `103`, `104` cho cả đợt `01` và `02`.

### Cách 2: Qua giao diện đồ họa (GUI)
1. Mở phần mềm OMR (`python main.py`).
2. Nhấn nút **"📋 Đáp án chuẩn"** hoặc vào menu **Mã đề & Đáp án -> Nạp bộ dữ liệu mẫu (Demo)...**
3. Trong cửa sổ **Chấm hàng loạt**, cũng có nút **"🎯 Nạp Demo"** để nạp dữ liệu ngay lập tức.

---

## 4. Quản lý Đáp án chuẩn

Mở cửa sổ bằng cách nhấn **"📋 Đáp án chuẩn"** trên thanh công cụ hoặc menu **Mã đề & Đáp án -> Quản lý mã đề & Đáp án...**:
- **Chọn đợt thi**: Dropdown chọn đợt `01`, `02`... để xem các mã đề tương ứng.
- **Thêm mã đề**: Nhập mã đề (vd: `101`), nhập chuỗi 50 đáp án (vd: `ABCD...`), phần mềm tự đếm số câu và cảnh báo nếu mã đề đã tồn tại trước khi ghi đè.
- **Nhập từ CSV**: Hỗ trợ 8 file CSV trong thư mục `answer_key/` (`dap_an_dot_01_ma_101.csv`...).
- **Nhập từ JSON**: Chọn file `answer_key/answer_keys.json` để đăng ký toàn bộ 8 mã đề cùng lúc.
- **Quét từ nhiều ảnh**: Chọn nhiều ảnh phiếu đáp án đã tô -> Phần mềm tự đọc mã đề và 50 câu -> Mở hộp thoại xác nhận cho phép sửa trước khi lưu (hoàn toàn không ghi nhận điểm số học sinh).

---

## 5. Chấm bài hàng loạt (Batch Processing)

1. Nhấn nút **"📑 Chấm hàng loạt"** trên giao diện chính.
2. Chọn đợt thi mong muốn.
3. Nhấn **"➕ Chọn ảnh..."** hoặc **"📁 Chọn cả thư mục..."** (chọn thư mục `test_images/benchmark_dataset/images`).
4. Nhấn **"▶️ BẮT ĐẦU CHẤM"**:
   - Nếu đợt thi chưa có đáp án chuẩn, phần mềm sẽ hiển thị cảnh báo cụ thể.
   - Thanh tiến trình hiển thị % thực tế và tên file đang xử lý.
   - Bảng kết quả hiển thị rõ ràng: Tên file, Trạng thái, SBD, Họ tên, Lớp, Mã đề, Điểm (thang 10), Số câu đúng (/50), Ghi chú.
5. Nếu có bài báo `⚠️ Cần kiểm tra` hoặc `✗ Thất bại`, bạn có thể nhấn **"🔁 Chấm lại bài lỗi"** sau khi kiểm tra/sửa đáp án chuẩn.
6. Nhấn **"📊 Xuất Excel 6 sheet"** để lưu toàn bộ báo cáo đợt thi ra file `.xlsx`.

---

## 6. Chạy kiểm thử tự động (Automated Tests & Benchmark)

### Chạy kiểm tra bộ 26 ảnh Benchmark đối chiếu Ground Truth:
```powershell
.\.venv\Scripts\python.exe scripts/verify_benchmark.py
```
Kết quả kiểm tra chi tiết từng ảnh (Đợt thi, SBD, Mã đề, Trạng thái kỳ vọng, Thực tế, Điểm số, Thời gian xử lý) và tự động xuất file Excel báo cáo.

### Chạy toàn bộ test suite (86 bài test unit & integration):
```powershell
.\.venv\Scripts\python.exe -m unittest discover tests
```
Tất cả 86/86 bài kiểm thử đều PASS (0 lỗi, 0 thất bại).
