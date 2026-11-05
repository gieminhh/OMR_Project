# OMR SCANNER — Hệ thống chấm trắc nghiệm 50 câu bằng Python & OpenCV

Đề tài: **Đọc kết quả từ phiếu trả lời trắc nghiệm bằng Computer Vision (OpenCV & Python)**.  
Chương trình ứng dụng các kỹ thuật thị giác máy tính truyền thống để tự động căn chỉnh phiếu thi, phát hiện và nhận diện 50 câu trắc nghiệm (A, B, C, D), xử lý các trường hợp bỏ trống (BLANK) hoặc tô nhiều đáp án (MULTIPLE), chấm điểm theo đáp án chuẩn và xuất kết quả ra tệp Excel trực quan.

---

## 1. Yêu cầu & Cài đặt môi trường

### Yêu cầu hệ thống:
- Python 3.10 trở lên (khuyến nghị Python 3.11, 3.12, 3.13 hoặc 3.14).
- Hệ điều hành: Windows, macOS hoặc Linux.

### Cài đặt thư viện:
Khởi tạo môi trường ảo và cài đặt các phụ thuộc từ `requirements.txt`:

```bash
# Tạo môi trường ảo (khuyến nghị)
python -m venv .venv

# Kích hoạt môi trường (Windows PowerShell):
.\.venv\Scripts\Activate.ps1
# Hoặc trên Linux/macOS:
# source .venv/bin/activate

# Cài đặt thư viện phụ thuộc:
pip install -r requirements.txt
```

Các thư viện chính được sử dụng:
- `opencv-python`: Tiền xử lý ảnh, phát hiện biên Canny, tìm contour, nắn phối cảnh (Warp Perspective) và đo mật độ pixel mực (`countNonZero`).
- `numpy`: Xử lý mảng ma trận điểm ảnh và tọa độ đa giác.
- `openpyxl`: Xuất dữ liệu bảng điểm và định dạng màu sắc báo cáo Excel.
- `Pillow`: Hiển thị hình ảnh mượt mà trên giao diện Tkinter.

---

## 2. Hướng dẫn chạy chương trình

### 2.1. Giao diện đồ họa (GUI)
Giao diện Tkinter hiện đại, dễ thao tác và hiển thị màu sắc trực quan:

```bash
python run_simple_gui.py
```

**Quy trình sử dụng trên giao diện:**
1. **Chọn ảnh:** Mở file ảnh chụp phiếu trắc nghiệm (`.jpg`, `.png`, `.jpeg`).
2. **Đọc phiếu:** OpenCV tự động tìm 4 góc, căn phẳng phiếu thi và nhận diện 50 câu. Bảng kết quả hiển thị 50 câu kèm trạng thái "Đã chọn", "Bỏ trống", hoặc "Nhiều đáp án". Khi chưa có đáp án chuẩn, nhãn "Đúng / Sai" hiển thị trạng thái `--` (không đoán mò).
3. **Quản lý đáp án chuẩn:**
   - **Nạp JSON:** Chọn tệp JSON đáp án chuẩn có sẵn (ví dụ: `answer_key/answer_key.json`).
   - **Nhập thủ công:** Mở cửa sổ "NHẬP ĐÁP ÁN CHUẨN – 50 CÂU" chia 2 cột × 25 câu, hỗ trợ chọn combobox hoặc gõ phím nhanh A/B/C/D, các tiện ích điền nhanh/xóa hết, điền sẵn đáp án đang dùng để chỉnh sửa từng câu, kiểm tra hợp lệ đủ 50 câu với 2 nút **"Lưu & sử dụng"** và **"Hủy"**.
   - **Xuất JSON:** Nút duy nhất trên thanh công cụ giao diện chính cho phép lưu bộ đáp án chuẩn hiện đang sử dụng ra tệp `.json` chuẩn (cấu trúc `{"answers": [...]}` tương thích `load_answer_key`).
4. **Chấm điểm:** Chấm điểm thang 10, hiển thị điểm số nổi bật và phân loại màu từng dòng:
   - 🟩 **Xanh lá:** Đúng đáp án.
   - 🟥 **Đỏ:** Sai đáp án.
   - 🟨 **Vàng:** Bỏ trống không tô (`BLANK`).
   - 🟧 **Cam:** Tô nhiều hơn một đáp án (`MULTIPLE`).
5. **Xuất Excel:** Xuất báo cáo bảng điểm ra file `.xlsx` (hỗ trợ cả **Chế độ 1**: chỉ xuất kết quả nhận diện khi chưa chấm, và **Chế độ 2**: bảng điểm chi tiết kèm màu sắc đồng bộ).
*(Lưu ý: Khi đổi bộ đáp án chuẩn sau khi đã chấm, chương trình tự động xóa kết quả điểm cũ, chuyển bảng về trạng thái chưa chấm và yêu cầu bấm "Chấm điểm" lại để tránh hiển thị điểm sai).*

---

### 2.2. Dòng lệnh (CLI)
Chương trình cung cấp giao diện dòng lệnh linh hoạt để tích hợp hoặc kiểm thử tự động qua `main.py`:

```bash
# 1. Nhận diện 50 câu từ ảnh (chế độ cơ bản):
python main.py Test_TGMT.jpg

# 2. Nhận diện và chấm điểm với đáp án chuẩn:
python main.py Test_TGMT.jpg --score answer_key/answer_key.json

# 3. Nhận diện, chấm điểm và xuất Excel:
python main.py Test_TGMT.jpg --score answer_key/answer_key.json --excel output/ket_qua.xlsx

# 4. Bật chế độ debug (lưu 6 ảnh trung gian vào output/debug/):
python main.py Test_TGMT.jpg --debug --output-dir output
```

Các tham số dòng lệnh hỗ trợ:
- `image`: Đường dẫn ảnh phiếu trắc nghiệm đầu vào (bắt buộc).
- `--score <path>`: Đường dẫn file JSON đáp án chuẩn để tính điểm.
- `--excel <path>`: Đường dẫn lưu file Excel kết quả.
- `--layout <path>`: Chỉ định file cấu hình layout mẫu (mặc định tự động nhận diện mốc in THPT hoặc layout mẫu).
- `--already-warped`: Bỏ qua bước phát hiện góc nếu ảnh đầu vào đã được căn phẳng trước đó.
- `--debug`: Lưu lại các ảnh trung gian qua từng bước xử lý.

---

### 2.3. Chạy các Demo học thuật toán OpenCV
Dành cho sinh viên và lập trình viên tìm hiểu chi tiết từng bước xử lý ảnh:

```bash
# Demo 1: Minh họa 7 bước tiền xử lý ảnh và căn phẳng phiếu thi
python demos/demo_preprocessing.py test_images/sample_photo.png

# Demo 2: Minh họa đo mật độ pixel mực trong ô tô và nhận diện 50 câu
python demos/demo_detect_answers.py test_images/printed_50_real.png

# Demo 3: Minh họa quy trình xác thực dữ liệu, tính điểm và xuất Excel 2 chế độ
python demos/demo_scoring.py
```

---

### 2.4. Chạy kiểm thử tự động (Unit Tests)
Dự án được bảo vệ bởi bộ kiểm thử tự động toàn diện bao phủ từ tiền xử lý, thuật toán nhận diện, logic chấm điểm cho đến xuất Excel và giao diện:

```bash
# Chạy toàn bộ 53 bài kiểm thử:
python -m unittest discover -s tests -v

# Hoặc chạy kiểm thử riêng từng thành phần:
python -m unittest tests.test_scoring -v
python -m unittest tests.test_simple_gui -v
python -m unittest tests.test_export_excel -v
```

---

## 3. Cấu trúc thư mục hiện tại

```text
OMR_Project/
├── main.py                      # CLI nhận diện 50 câu & API lõi (process_omr)
├── run_simple_gui.py            # Launcher khởi chạy giao diện Tkinter
├── requirements.txt             # Danh sách thư viện phụ thuộc
├── README.md                    # Tài liệu hướng dẫn sử dụng và triển khai
├── Test_TGMT.jpg                # Ảnh chụp phiếu thi thực tế dùng kiểm thử trực quan
│
├── config/                      # Cấu hình tọa độ và tham số layout
│   ├── layout.json              # Cấu hình lưới chuẩn 50 câu
│   └── printed_50.json          # Tham số nhận diện mốc đen phiếu in THPT
│
├── modules/                     # Các module thuật toán cốt lõi
│   ├── __init__.py
│   ├── image_processing.py      # Đọc ảnh Unicode, resize, grayscale, Gaussian blur, Canny
│   ├── paper_detection.py       # Tìm contour 4 góc và biến đổi phối cảnh (Perspective Transform)
│   ├── background_removal.py    # Tách nền và căn phẳng phiếu về kích thước chuẩn 1000×1400
│   ├── printed_form.py          # Quét mốc định vị mẫu in thực tế
│   ├── answer_detection.py      # Đo mật độ pixel mực (countNonZero), phân loại đáp án
│   ├── validation.py            # Kiểm tra tính hợp lệ dữ liệu 50 câu
│   ├── scoring.py               # Kiểm tra đáp án chuẩn và tính điểm thang 10
│   ├── export_excel.py          # Xuất báo cáo Excel định dạng màu sắc (2 chế độ)
│   └── errors.py                # Định nghĩa cây ngoại lệ chuẩn của hệ thống (OMRError)
│
├── gui/
│   ├── __init__.py
│   └── simple_app.py            # Giao diện Tkinter + ttk (bảng màu, score card, ảnh preview)
│
├── demos/                       # Các kịch bản demo thuật toán độc lập phục vụ học tập
│   ├── demo_preprocessing.py    # Demo trực quan hóa tiền xử lý và căn phẳng
│   ├── demo_detect_answers.py   # Demo trích xuất vùng câu hỏi và phân loại đáp án
│   └── demo_scoring.py          # Demo quy trình xác thực, chấm điểm và xuất Excel
│
├── answer_key/                  # Tệp đáp án chuẩn JSON phục vụ chấm điểm
│   ├── answer_key.json          # Đáp án chuẩn 50 câu mẫu
│   └── test_key.json            # Đáp án kiểm thử
│
├── test_images/                 # Tập dữ liệu ảnh kiểm thử đa dạng
│   ├── .gitkeep
│   ├── expected_answers.json    # Kết quả kỳ vọng của mẫu phát triển
│   ├── printed_50_real.png      # Ảnh chụp phiếu thi thật có mốc định vị
│   ├── sample_photo.png         # Ảnh chụp góc nghiêng có phối cảnh
│   ├── sample_shadow.jpg        # Ảnh có bóng đổ phức tạp
│   └── sample_sheet.png         # Phiếu chuẩn scan thẳng
│
├── scripts/
│   ├── __init__.py
│   └── generate_samples.py      # Script sinh dữ liệu kiểm thử tổng hợp
│
├── tests/                       # Bộ kiểm thử tự động (53 test cases)
│   ├── __init__.py
│   ├── test_image_processing.py
│   ├── test_paper_detection.py
│   ├── test_background_removal.py
│   ├── test_printed_form.py
│   ├── test_answer_detection.py
│   ├── test_pipeline.py
│   ├── test_scoring.py
│   ├── test_export_excel.py
│   └── test_simple_gui.py
│
└── output/                      # Thư mục lưu kết quả ảnh debug và file Excel (tự tạo lại)
    └── .gitkeep
```

---

## 4. Tính năng nâng cao (Chấm hàng loạt & Quản lý đợt thi)

Ngoài giao diện và API xử lý phiếu 50 câu đơn lẻ cốt lõi, project còn tích hợp các module mở rộng hỗ trợ quản lý đợt thi và chấm hàng loạt:
- Quản lý đợt thi, lớp học và học sinh bảo toàn số 0 ở đầu SBD (`modules/session_manager.py`).
- Động cơ xử lý hàng loạt đa luồng (`modules/batch_processor.py`).
- Cơ sở dữ liệu SQLite cục bộ (`modules/db.py`).
- Nạp dữ liệu mẫu và benchmark (`modules/demo_loader.py`, `scripts/load_demo_data.py`).

Xem tài liệu hướng dẫn chi tiết dành cho các tính năng nâng cao này tại file: [`HUONG_DAN_SU_DUNG.md`](HUONG_DAN_SU_DUNG.md).

---

## 5. Giới hạn & Lưu ý vận hành

Để hệ thống đạt độ chính xác cao nhất, cần lưu ý các điều kiện sau:

1. **Điều kiện ánh sáng:**
   - Cần chụp trong điều kiện ánh sáng đồng đều, tránh bóng đổ quá gắt cắt ngang vùng các ô trả lời hoặc ánh đèn flash gây lóa sáng cục bộ (cháy sáng làm mất nét in).
2. **Biên và góc phiếu thi:**
   - Ảnh chụp phải bao gồm trọn vẹn 4 góc của tờ giấy thi trên một mặt nền có độ tương phản (ví dụ: đặt phiếu trắng trên bàn màu sẫm hoặc mặt bàn tối màu) để thuật toán tìm contour có thể xấp xỉ chính xác 4 đỉnh góc tứ giác.
3. **Góc chụp:**
   - Khuyến nghị chụp từ góc thẳng đứng xuống (Top-down) hoặc góc nghiêng không vượt quá $45^\circ$ so với mặt phẳng giấy để tránh suy biến biến đổi phối cảnh.
4. **Độ phẳng của giấy:**
   - Phiếu thi cần tương đối phẳng, không bị quăn góc nặng, gấp nếp sâu hoặc rách mất các ô trả lời.
5. **Chất lượng tô đáp án:**
   - Thí sinh nên dùng bút chì 2B hoặc đậm hơn để tô kín ô tròn. Các vết tẩy xóa cần được tẩy kỹ; nếu vết chì tẩy chưa sạch vượt quá ngưỡng mật độ mực, hệ thống có thể nhận diện thành câu tô nhiều đáp án (`MULTIPLE`).
