# OMR SCANNER — Python/OpenCV 

Thank you for the collaboration and support from Ngatran2784

[VIE]
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

[ENG]
The CLI `main.py` remains a standalone recognition tool; `score_result` from the CLI is `None`.

## Fixes for recognizing real answer sheets — 15/10/2026

The image `test_images/printed_50_real.png` was previously incorrectly reported as having a cropped corner, even though the entire sheet was visible. Two causes were confirmed:

- The patterned blanket background contained bright details that connected to the paper region at the Otsu threshold. The sheet-detection step now tries additional brightness thresholds and removes thin bridges based on image dimensions. It fills in concavities only when the contour is nearly convex. Regions touching the image edge are still rejected; crop validation has not been removed.
- `config/layout.json` is a development sample layout and does not match the actual printed answer sheet. The program now automatically recognizes a template with 6 pairs of black markers between the two columns, plus two outer markers at the top of the table. The `printed_form.py` module uses these markers to divide the sheet into 5 groups × 5 questions, then makes small adjustments to the bubble centers. Faint printed outlines are checked using a separate threshold; the fill threshold is not lowered to force an answer, and ink color is not used to infer the selected choice.

The template settings are in `config/printed_50.json`. Omit `--layout` to detect the template automatically; if `--layout` is provided, the program respects that configuration. The result includes `layout_name`, which can be `printed_50`, `sample_grid`, or `custom`.

Open the GUI (after closing any currently running instance):

```powershell
.\.venv\Scripts\python.exe run_gui.py
```

Re-test using the actual image and save the debugging outputs:

```powershell
.\.venv\Scripts\python.exe main.py test_images/printed_50_real.png --debug --output-dir output/real_sheet_after
.\.venv\Scripts\python.exe -m unittest tests.test_printed_form -v
```

The image can be read as 50 questions: 49 have one selected bubble, and question 44 is `BLANK`. The test is compared against the answers **read visually from the image**, rather than using the program's output as the expected result. Resized variants at 960 × 1280, brighter and darker variants, and JPEG variants were also tested; images with missing corners and templates with missing markers are rejected. The GUI test covers the workflow: select a real image → preview → read the answer sheet → display the 50-question table.

Limitations: the system has only been calibrated against one real answer-sheet template and variants of that image. It is not guaranteed to work with every printed template, degree of paper curvature, rotation, or complex background. The older image `anh11.jpg`, showing a sheet on a desk, still cannot be separated from its background. If markers are missing, the program reports an error instead of guessing. The Phase 1–4 descriptions below are a history of the initial implementation; the current status and instructions for opening the GUI are provided above.

## Installation and running on Windows

Python 3.11 or later is required. Open a terminal in the `OMR_Project` directory:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

The last command displays the CLI instructions; it does not open the GUI. The `.venv` environment in the project directory has already been installed and tested with Python 3.14.4 on Windows. You do not need to activate the virtual environment or change the PowerShell execution policy when using the paths shown above.

Run the included examples:

```powershell
.\.venv\Scripts\python.exe -m scripts.generate_samples
.\.venv\Scripts\python.exe main.py test_images/sample_photo.png --debug
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Result: reads 50 answers using the repeating A/B/C/D pattern in the sample, and saves `output/answers.json`, `output/detected_bubbles.png`, and six images in `output/debug`.
`test_images/expected_answers.json` contains the expected results for the development sample.
`answer_key/answer_key.json` is also an **illustrative answer key**, not the actual answer key for an exam.

On macOS/Linux, use `.venv/bin/python` instead of `\.venv\Scripts\python.exe`.
The program's default paths are calculated from `__file__` using pathlib, rather than being tied to a drive or Windows username.

## Project structure

```text
OMR_Project/
├── main.py                      # Development CLI and module orchestration
├── requirements.txt
├── config/layout.json           # Adjustable sample layout
├── modules/
│   ├── __init__.py
│   ├── errors.py                # Errors with specific messages
│   ├── image_processing.py
│   ├── paper_detection.py
│   ├── answer_detection.py
│   ├── validation.py            # Phase 6 skeleton
│   ├── scoring.py               # Phase 6 skeleton
│   └── export_excel.py          # Phase 7 skeleton
├── gui/
│   ├── __init__.py
│   └── app.py                   # Phase 9 skeleton
├── answer_key/answer_key.json
├── scripts/generate_samples.py
├── tests/
├── test_images/
└── output/
```

## Phase-by-phase report

### Phase 1 — Structure and skeleton

- Created all required directories and files, the requirements file, and a shared error module.
- `validation.py`, `scoring.py`, `export_excel.py`, and `gui/app.py` only define function interfaces and messages describing the implementation phase; they do not return fabricated results.
- Test: `python main.py` exits normally after displaying the CLI instructions.
- Remaining work: the full product acceptance criteria have not yet been met, especially for the GUI, answer-key validation, scoring, and Excel export.

### Phase 2 — Preprocessing

- Main file: `modules/image_processing.py`; test: `tests/test_image_processing.py`.
- Supports reading and writing filenames containing Unicode characters; validates missing, empty, or corrupted images; resizes while preserving aspect ratio; and supports grayscale conversion, Gaussian blur, adaptive/Otsu thresholding, and optional morphology.
- Inverted binary image: ink = 255, paper = 0. Morphology is disabled by default to preserve thin strokes.
- Tested with an image containing a filled bubble accessed through a Vietnamese-language path, resize ratios, and configuration errors.

```powershell
python -m unittest tests.test_image_processing -v
python main.py test_images/sample_photo.png --phase 2 --debug --output-dir output/phase2
```

- Remaining work: default parameters need further calibration for noise, pencil marks, and real-world lighting.

### Phase 3 — Detection and alignment

- Main file: `modules/paper_detection.py`; test: `tests/test_paper_detection.py`;
  test data: `scripts/generate_samples.py`.
- Finds outer contours using Canny edges and bright regions, examines candidates from largest to smallest, checks convex quadrilaterals, area, edge lengths, and image borders, orders the corners TL–TR–BR–BL, and applies a perspective warp.
- The default output size is 1000 × 1400. `detect_and_warp_paper()` returns the image directly.
- Tested corner coordinates against fixtures, image dimensions, bubble-mark positions after warping, cases with no sheet, and cropped/missing-corner cases.

```powershell
python -m unittest tests.test_paper_detection -v
python main.py test_images/sample_photo.png --phase 3 --debug --output-dir output/phase3
```

- Remaining work: the method requires a contrasting background and all four corners to be visible. Text orientation is not detected yet, and automatic 90°/180° rotation, curved paper, and multiple overlapping sheets are not handled.
- Scanned images or images cropped tightly to the sheet edges are not treated as photographs with a complete background. Use `--already-warped` to skip corner detection only when the image has already been correctly aligned to the layout's required dimensions.

### Phase 4 — Reading 5 → 10 → 50 questions

- Main files: `modules/answer_detection.py`, `config/layout.json`;
  tests: `tests/test_answer_detection.py`, `tests/test_pipeline.py`.
- Crops the answer area; divides it into two columns × 25 rows × 4 choices according to the configuration. Measures the ink-pixel ratio inside a small circle within each bubble to avoid counting the printed outline.
- The left column contains questions 1–25; the right column contains questions 26–50. It does not use OCR to read letters or question numbers.
- The default API returns exactly 50 values; `question_count=5/10` is for testing. The CLI can export those smaller question counts, so keep the default of 50 when reading a complete sheet.
- Basic `BLANK` handling is implemented when no bubble reaches the threshold, and `MULTIPLE` handling when at least two bubbles reach it. Advanced calibration for faint pencil marks and erasures was not completed in Phase 5 at that stage.
- Bubble-outline checks help detect layout misalignment and blank sheets. These checks are supplementary and do not prove that the template matches in every situation.
- `main.py` temporarily combines the existing steps for trial runs; the complete pipeline with validation, answer keys, and scoring was planned for Phase 8.

```powershell
python -m unittest tests.test_answer_detection.AnswerDetectionTests.test_01_five_questions -v
python -m unittest tests.test_answer_detection.AnswerDetectionTests.test_02_ten_questions -v
python -m unittest tests.test_answer_detection -v
python main.py test_images/sample_photo.png --questions 5 --output-dir output/first5
python main.py test_images/sample_photo.png --questions 10 --output-dir output/first10
python main.py test_images/sample_photo.png --debug
python main.py test_images/sample_shadow.jpg --debug --output-dir output/shadow
```

A total of **20 tests passed**: reading images through Unicode paths, perspective geometry, 5/10/50-question markers, the boundary between questions 25 and 26, blank/multiple answers, images without an OMR region, invalid configuration, uneven lighting + slight blur + JPEG, the pipeline, and six debug images.

**Limitation:** this uses synthetic fixtures generated independently of the detector; it is not an accuracy evaluation on real answer sheets. A real template with a different layout may be rejected or read incorrectly unless calibrated. Cases involving faint marks, erasures, harsh shadows, incomplete strokes, folds, and strong rotation require additional data in later phases.

## Configuring for a real answer sheet

1. Photograph the sheet from nearly directly above, keeping all four corners visible and including a contrasting background around it.
2. Run Phase 3 and open `warped.png`. All coordinates below refer to pixels **in the warped image**, not the original photograph.
3. Copy `config/layout.json` to a separate layout file and adjust:
   - `paper_size`: `[width, height]`, kept consistent with the warp dimensions.
   - `answer_region`: `[x0, y0, x1, y1]`, enclosing both answer columns.
   - `columns`: two boxes for the left and right columns, ordered as questions 1–25 and then 26–50. The boxes should enclose the **answer bubbles**, not the question numbers or heading.
   - `column_margin`: the horizontal/vertical margins to exclude inside each box before dividing it into cells.
   - `bubble_radius`: the radius of the printed bubble outline in the reference image.
   - `sample_radius_ratio`: the proportion of the bubble radius used for measuring ink inside it (default 0.65).
   - `fill_threshold`: the ink ratio inside the bubble, from 0 to 1 (default 0.45).
   - `threshold_block_size`, `threshold_c`: adaptive thresholding parameters used when reading bubbles.
   - `ring_inner_ratio`, `ring_outer_ratio`: the sampling ring used to check bubble outlines;
     `min_ring_ink_ratio`, `min_visible_bubble_fraction`: minimum required layout-match values.
4. Each column box is divided evenly into four horizontal choices and 25 vertical rows. The box edges must be **half a cell-step away from the centers of the first and last bubbles**; do not place the box edges directly at bubble centers. For example, the sample left column `[200, 300, 440, 1300]` has x-centers of 230/290/350/410 and y-centers of 320…1280.
5. Run again with `--layout config/my_layout.json --debug`. Check that the colored circles align with the actual bubbles in the first and last rows of both columns before adjusting the fill threshold.

```powershell
python main.py "test_images/phieu_that.jpg" --layout config/my_layout.json --debug
python main.py test_images/sample_sheet.png --already-warped --debug --output-dir output/scan
```

If a different layout is required—for example, unequal spacing between rows, or unevenly spaced bubbles—the layout model must be extended; simply lowering the outline-check threshold is not enough.

## API for integration

```python
from main import process_omr

result = process_omr("test_images/sample_photo.png", debug=True)
answers = result["answers"]             # list[str], 50 elements by default
warped = result["processed_image"]      # numpy.ndarray BGR, warped
ratios = result["fill_ratios"]          # 50 rows × 4 ratios
score_result = result["score_result"]   # None, scoring not implemented
```

You can call `load_image`, `preprocess_image`, `detect_and_warp_paper`, and `detect_answers` individually to develop each stage. The API raises `OMRError` or a subclass; the CLI catches errors and exits with code 1. The GUI only needs to call the pipeline and display any errors.

## Debugging

Enable `--debug` in the CLI, set `debug=True` when calling the API, or change the `DEBUG` constant in `main.py`. A successful Phase 4 run creates:

```text
output/debug/
  01_original.jpg
  02_threshold.jpg
  03_detected_paper.jpg
  04_warped.jpg
  05_answer_region.jpg
  06_detected_bubbles.jpg
```

The final image shows the locations of A/B/C/D, ink ratios, question numbers, and selected answers: green marks the selected bubble, blue marks unselected bubbles, and orange marks bubbles in a question with multiple selections. `02_threshold` is the binary image from preprocessing; bubble ratios are recalculated on the warped image in the answer-detection module. Paper edges are detected using grayscale and edge information to preserve geometry.

The API does not write files when `debug=False`; the CLI still saves the final results. Runs using the same output directory overwrite files with matching names; an early-stopped run does not delete images left from an earlier run. Use different `--output-dir` values when comparing images/phases or investigating failed cases.

## Subsequent phases

- Phase 5: calibrate `BLANK`/`MULTIPLE` handling using real images, faint pencil marks, erasures, and incomplete fills.
- Phase 6: validate all 50 questions, load/check the answer key, and score correct/incorrect/blank/multiple answers.
- Phase 7: export to Excel using openpyxl and handle write errors or files that are already open.
- Phase 8: complete the pipeline, calculate scores on a 10-point scale, handle answer-key errors, and handle incomplete results.
- Phase 9: Tkinter interface for selecting an image, previewing it, reading the answer sheet, displaying all 50 questions, and exporting to Excel.
- Phase 10: build a real-image test set, measure recognition accuracy, and tune thresholds; the full product should be accepted only after the functions above have been implemented and tested.
