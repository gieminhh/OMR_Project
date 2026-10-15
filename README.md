# OMR SCANNER — Python/OpenCV, 50 câu

Đã có tiền xử lý, phát hiện phiếu, căn thẳng, đọc đáp án, giao diện Tkinter,
chấm điểm và xuất Excel qua GUI. Không dùng AI, YOLO hay OCR.
CLI `main.py` vẫn là công cụ nhận diện riêng; `score_result` từ CLI là `None`.

## Sửa nhận diện phiếu thật — 15/10/2026

Ảnh `test_images/printed_50_real.png` từng bị báo nhầm là crop mất góc dù thấy
đủ tờ phiếu. Có hai nguyên nhân đã được xác minh:

- Nền chăn có họa tiết sáng nối với vùng giấy ở ngưỡng Otsu. Bước tìm phiếu
  nay thử thêm các ngưỡng sáng và loại cầu nối mảnh theo kích thước ảnh, chỉ
  bù vết lõm khi contour gần lồi. Vẫn từ chối vùng chạm mép, không bỏ kiểm tra crop.
- `config/layout.json` là layout mẫu phát triển, không khớp phiếu in thực tế.
  Nay tự nhận mẫu có 6 cặp mốc đen giữa hai cột, cộng hai mốc ngoài ở đầu bảng.
  Module `printed_form.py` dùng các mốc để chia 5 nhóm × 5 câu, rồi tinh chỉnh
  tâm bubble trong phạm vi nhỏ. Viền in mờ được kiểm tra bằng ngưỡng riêng;
  không giảm ngưỡng tô để cố lấy đáp án và không dùng màu mực để suy ra lựa chọn.

Thông số mẫu ở `config/printed_50.json`. Không truyền `--layout` để tự nhận mẫu;
nếu truyền `--layout`, chương trình tôn trọng cấu hình đó. Kết quả có
`layout_name`: `printed_50`, `sample_grid` hoặc `custom`.

Mở GUI (sau khi đóng phiên bản đang chạy):

```powershell
.\.venv\Scripts\python.exe run_gui.py
```

Kiểm tra lại đúng ảnh thật và lưu các bước debug:

```powershell
.\.venv\Scripts\python.exe main.py test_images/printed_50_real.png --debug --output-dir output/real_sheet_after
.\.venv\Scripts\python.exe -m unittest tests.test_printed_form -v
```

Ảnh này đọc được 50 câu: 49 câu chọn một ô, câu 44 `BLANK`. Kiểm thử đối chiếu
với đáp án **đọc bằng mắt từ ảnh**, không phải lấy output của chương trình làm
kết quả kỳ vọng. Các biến thể thu nhỏ 960 × 1280, tăng/giảm sáng và JPEG cũng
được kiểm tra; ảnh mất góc và mẫu thiếu mốc bị từ chối. Test GUI có luồng chọn
ảnh thật → preview → đọc phiếu → bảng 50 câu.

Giới hạn: mới hiệu chỉnh trên một mẫu phiếu thật và các biến thể của ảnh đó;
không đảm bảo mọi mẫu in, mức cong giấy, hướng xoay hay nền phức tạp. Ảnh cũ
`anh11.jpg` trên bàn vẫn chưa tách được viền. Khi thiếu mốc, chương trình báo
lỗi thay vì tự đoán. Các mô tả Phase 1–4 dưới đây là lịch sử triển khai ban đầu;
trạng thái hiện tại và cách mở GUI nằm ở phần trên.

## Cài đặt và chạy trên Windows

Yêu cầu Python 3.11 trở lên. Mở terminal tại thư mục `OMR_Project`:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

Lệnh cuối hiển thị hướng dẫn, chưa mở GUI. Môi trường `.venv` trong thư mục
đã được cài và kiểm thử với Python 3.14.4 trên Windows. Không cần kích hoạt
venv hay đổi PowerShell execution policy khi dùng đường dẫn trên.

Chạy ví dụ có sẵn:

```powershell
.\.venv\Scripts\python.exe -m scripts.generate_samples
.\.venv\Scripts\python.exe main.py test_images/sample_photo.png --debug
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Kết quả: đọc 50 đáp án A/B/C/D theo chu kỳ trong mẫu, lưu `output/answers.json`,
`output/detected_bubbles.png` và sáu ảnh trong `output/debug`.
`test_images/expected_answers.json` là kết quả kỳ vọng của mẫu phát triển.
`answer_key/answer_key.json` cũng là **đáp án minh họa**, không phải đáp án đề thi thật.

Trên macOS/Linux dùng `.venv/bin/python` thay `.\.venv\Scripts\python.exe`.
Các đường dẫn mặc định trong chương trình được tính từ `__file__` bằng pathlib,
không gắn với ổ đĩa hay tên người dùng Windows.

## Cấu trúc

```text
OMR_Project/
├── main.py                      # CLI phát triển và phối hợp các module
├── requirements.txt
├── config/layout.json           # Layout mẫu có thể hiệu chỉnh
├── modules/
│   ├── __init__.py
│   ├── errors.py                # Các lỗi có thông báo cụ thể
│   ├── image_processing.py
│   ├── paper_detection.py
│   ├── answer_detection.py
│   ├── validation.py            # Skeleton Phase 6
│   ├── scoring.py               # Skeleton Phase 6
│   └── export_excel.py          # Skeleton Phase 7
├── gui/
│   ├── __init__.py
│   └── app.py                   # Skeleton Phase 9
├── answer_key/answer_key.json
├── scripts/generate_samples.py
├── tests/
├── test_images/
└── output/
```

## Báo cáo từng phase

### Phase 1 — Cấu trúc và skeleton

- Đã tạo các thư mục và toàn bộ file bắt buộc, requirements, module lỗi chung.
- `validation.py`, `scoring.py`, `export_excel.py`, `gui/app.py` chỉ khai báo
  hợp đồng hàm và thông báo phase triển khai; không trả kết quả giả.
- Test: `python main.py` kết thúc bình thường với hướng dẫn CLI.
- Còn lại: chưa đạt các tiêu chí nghiệm thu của toàn bộ sản phẩm, đặc biệt GUI,
  kiểm tra đáp án chuẩn, chấm điểm và Excel.

### Phase 2 — Tiền xử lý

- File chính: `modules/image_processing.py`; test: `tests/test_image_processing.py`.
- Đọc/ghi tên tệp Unicode; kiểm tra ảnh thiếu, rỗng, hỏng; resize giữ tỷ lệ;
  grayscale, Gaussian blur, adaptive/Otsu threshold và morphology tùy chọn.
- Ảnh nhị phân đảo: mực = 255, giấy = 0. Mặc định tắt morphology để giữ nét mảnh.
- Đã kiểm thử một ảnh có ô tô qua đường dẫn tiếng Việt, tỷ lệ resize và lỗi cấu hình.

```powershell
python -m unittest tests.test_image_processing -v
python main.py test_images/sample_photo.png --phase 2 --debug --output-dir output/phase2
```

- Còn lại: tham số mặc định cần hiệu chỉnh với nhiễu, nét chì và ánh sáng thực tế.

### Phase 3 — Phát hiện và căn thẳng

- File chính: `modules/paper_detection.py`; test: `tests/test_paper_detection.py`;
  dữ liệu thử: `scripts/generate_samples.py`.
- Tìm contour ngoài từ Canny và vùng sáng; xét từ lớn xuống nhỏ, kiểm tra
  tứ giác lồi/diện tích/độ dài cạnh/mép ảnh, sắp xếp TL–TR–BR–BL rồi warp.
- Kích thước mặc định 1000 × 1400. `detect_and_warp_paper()` trả trực tiếp ảnh.
- Đã kiểm tra tọa độ góc so với fixture, kích thước ảnh, vị trí nét tô sau warp,
  trường hợp không có phiếu và mất góc do crop.

```powershell
python -m unittest tests.test_paper_detection -v
python main.py test_images/sample_photo.png --phase 3 --debug --output-dir output/phase3
```

- Còn lại: cần nền tương phản và đủ bốn góc. Chưa xác định hướng chữ, chưa tự
  xoay phiếu 90°/180°, chưa xử lý giấy cong hoặc nhiều tờ chồng nhau.
- Ảnh scan/crop sát mép không được coi là ảnh chụp đủ nền. Chỉ bỏ phát hiện góc
  bằng `--already-warped` khi ảnh thực sự đã căn thẳng đúng kích thước layout.

### Phase 4 — Đọc 5 → 10 → 50 câu

- File chính: `modules/answer_detection.py`, `config/layout.json`;
  test: `tests/test_answer_detection.py`, `tests/test_pipeline.py`.
- Crop vùng đáp án; chia hai cột × 25 hàng × 4 lựa chọn theo config. Đo tỷ lệ
  pixel mực trong hình tròn nhỏ hơn bubble để tránh tính viền in.
- Cột trái là câu 1–25, cột phải 26–50. Không OCR chữ cái hay số câu.
- API mặc định trả đúng 50 giá trị; `question_count=5/10` là chế độ kiểm thử.
  CLI có thể xuất số câu này, vì vậy cần giữ mặc định 50 khi đọc toàn phiếu.
- Có xử lý cơ bản `BLANK` khi không ô nào đạt ngưỡng, `MULTIPLE` khi ít nhất
  hai ô đạt ngưỡng; chưa làm hiệu chỉnh chuyên sâu cho gôm tẩy/nét chì mờ ở Phase 5.
- Kiểm tra viền bubble để phát hiện nhiều trường hợp layout lệch/giấy trống.
  Đây là kiểm tra hỗ trợ, không chứng minh mẫu phiếu khớp trong mọi trường hợp.
- `main.py` ghép tạm các bước hiện có để chạy thử; pipeline đầy đủ có validation,
  đáp án chuẩn, scoring sẽ được hoàn thiện ở Phase 8.

```powershell
python -m unittest tests.test_answer_detection.AnswerDetectionTests.test_01_five_questions -v
python -m unittest tests.test_answer_detection.AnswerDetectionTests.test_02_ten_questions -v
python -m unittest tests.test_answer_detection -v
python main.py test_images/sample_photo.png --questions 5 --output-dir output/first5
python main.py test_images/sample_photo.png --questions 10 --output-dir output/first10
python main.py test_images/sample_photo.png --debug
python main.py test_images/sample_shadow.jpg --debug --output-dir output/shadow
```

Tổng cộng **20 kiểm thử đã đạt**: ảnh đọc qua đường dẫn Unicode, hình học phối
cảnh, mốc 5/10/50 câu, ranh giới 25/26, blank/multiple, ảnh không có vùng OMR,
config sai, ánh sáng không đều + blur nhẹ + JPEG, pipeline và sáu ảnh debug.

**Giới hạn:** đây là fixture tổng hợp được vẽ độc lập với detector, chưa phải
đánh giá độ chính xác trên phiếu thật. Mẫu thật khác layout có thể bị từ chối
hoặc đọc sai nếu không hiệu chỉnh. Các ca tô nhạt, tẩy xóa, bóng gắt, mất nét,
nếp gấp và xoay mạnh cần bổ sung dữ liệu ở các phase tiếp theo.

## Cấu hình theo phiếu thật

1. Chụp phiếu gần thẳng đứng, trọn bốn góc, có nền tương phản xung quanh.
2. Chạy Phase 3 và mở ảnh `warped.png`. Mọi tọa độ bên dưới đều là pixel
   **trên ảnh đã warp**, không phải ảnh chụp gốc.
3. Sao chép `config/layout.json` thành layout riêng rồi chỉnh:
   - `paper_size`: `[width, height]`, giữ đồng nhất với kích thước warp.
   - `answer_region`: `[x0, y0, x1, y1]` bao trọn hai cột đáp án.
   - `columns`: hai hộp cho cột trái/phải, theo thứ tự câu 1–25 rồi 26–50.
     Các hộp bao các **ô đáp án**, không bao số câu hoặc tiêu đề.
   - `column_margin`: lề ngang/dọc bỏ qua bên trong mỗi hộp trước khi chia ô.
   - `bubble_radius`: bán kính viền bubble in trên ảnh chuẩn.
   - `sample_radius_ratio`: tỷ lệ bán kính lòng ô dùng đo mực (mặc định 0.65).
   - `fill_threshold`: tỷ lệ mực trong lòng ô từ 0 đến 1 (mặc định 0.45).
   - `threshold_block_size`, `threshold_c`: ngưỡng adaptive khi đọc bubble.
   - `ring_inner_ratio`, `ring_outer_ratio`: vành lấy mẫu kiểm tra viền ô;
     `min_ring_ink_ratio`, `min_visible_bubble_fraction`: độ khớp layout tối thiểu.
4. Hộp cột chia đều bốn ô ngang và 25 hàng dọc. Mép hộp phải cách tâm ô đầu/cuối
   **nửa bước ô**, không đặt mép hộp ngay tại tâm bubble. Ví dụ cột trái mẫu
   `[200, 300, 440, 1300]` có tâm x = 230/290/350/410, tâm y = 320…1280.
5. Chạy lại với `--layout config/my_layout.json --debug`. Kiểm tra vòng tròn màu
   có trùng bubble thật ở cả hàng đầu/cuối và cả hai cột trước khi chỉnh ngưỡng tô.

```powershell
python main.py "test_images/phieu_that.jpg" --layout config/my_layout.json --debug
python main.py test_images/sample_sheet.png --already-warped --debug --output-dir output/scan
```

Nếu cần bố cục khác hai cột đều, hàng không đều hoặc bubble không đều khoảng cách,
cần mở rộng mô hình layout; không chỉ giảm ngưỡng kiểm tra viền để cố đọc.

## API cho giai đoạn tích hợp

```python
from main import process_omr

result = process_omr("test_images/sample_photo.png", debug=True)
answers = result["answers"]             # list[str], 50 phần tử mặc định
warped = result["processed_image"]      # numpy.ndarray BGR, đã warp
ratios = result["fill_ratios"]          # 50 hàng × 4 tỷ lệ
score_result = result["score_result"]   # None, chưa chấm điểm
```

Có thể gọi riêng `load_image`, `preprocess_image`, `detect_and_warp_paper`,
`detect_answers` để phát triển từng bước. API ném `OMRError` hoặc lớp con;
CLI bắt lỗi và trả mã thoát 1. GUI về sau chỉ cần gọi pipeline và hiển thị lỗi.

## Debug

Bật `--debug` trên CLI, `debug=True` khi gọi API hoặc sửa constant `DEBUG` trong
`main.py`. Phase 4 thành công tạo:

```text
output/debug/
  01_original.jpg
  02_threshold.jpg
  03_detected_paper.jpg
  04_warped.jpg
  05_answer_region.jpg
  06_detected_bubbles.jpg
```

Ảnh cuối vẽ vị trí A/B/C/D, tỷ lệ mực, số câu và kết quả chọn; xanh lá là ô tô,
xanh lam là ô không chọn, cam là các ô trong câu tô nhiều đáp án.
`02_threshold` là nhị phân ở bước tiền xử lý; tỷ lệ bubble được tính lại trên ảnh
warp trong module đáp án. Đọc theo viền giấy dùng grayscale/cạnh để giữ hình học.
API không ghi tệp khi `debug=False`; CLI vẫn lưu kết quả cuối. Các lần chạy cùng
thư mục ghi đè tệp cùng tên; bước dừng sớm không xóa ảnh từ lần cũ. Dùng
`--output-dir` khác nhau khi so sánh các ảnh/phase hoặc kiểm tra ca thất bại.

## Các phase tiếp theo

- Phase 5: hiệu chỉnh BLANK/MULTIPLE với ảnh thật, nét chì mờ, tẩy xóa và tô thiếu.
- Phase 6: validation đủ 50 câu, đọc/kiểm tra answer key, chấm đúng/sai/blank/multiple.
- Phase 7: xuất Excel bằng openpyxl và xử lý lỗi ghi/đang mở file.
- Phase 8: pipeline đầy đủ, chấm điểm thang 10, lỗi answer key và kết quả không đủ câu.
- Phase 9: Tkinter chọn ảnh, preview, đọc phiếu, bảng 50 câu và xuất Excel.
- Phase 10: bộ ảnh thật, đo tỷ lệ nhận diện và chỉnh ngưỡng; chỉ nghiệm thu toàn bộ
  sản phẩm sau khi các chức năng trên được triển khai và kiểm thử.
