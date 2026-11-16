# Hướng dẫn bảo vệ code OMR 50 câu

## 1. Luồng xử lý

```text
Ảnh đầu vào
  ↓
Đọc ảnh Unicode → resize giữ tỷ lệ → ảnh xám → Gaussian Blur → nhị phân
  ├─ Phase 2 trả ảnh nhị phân
  ↓
Tìm contour và bốn góc trên ảnh đã resize → căn phối cảnh
  ├─ --already-warped kiểm tra kích thước và dùng ảnh đã căn
  ├─ Phase 3 trả ảnh đã căn
  ↓
Chọn layout JSON hoặc nhận mẫu có mốc đen → xác định tâm 50 × 4 ô
  ↓
Đo mực ở tâm và viền → phân loại A/B/C/D, BLANK, MULTIPLE
  ├─ Phase 4 trả đáp án, tỷ lệ mực và ảnh đánh dấu
  ↓
Tkinter hiển thị kết quả → chấm theo đáp án chuẩn → xuất Excel
                          ↘ xuất Excel ngay khi chưa chấm
```

Phase 2 phục vụ quan sát tiền xử lý. Khi tìm giấy, chương trình lấy **ảnh màu đã resize** từ bước đó và tự tạo các mặt nạ chuyên dùng cho biên giấy. Sau khi căn phẳng, chương trình nhị phân hóa lại để đọc ô tô trong hệ tọa độ của layout.

## 2. Thứ tự mở file

1. [main.py, dòng 21](../main.py#L21) — `process_omr` cho thấy thứ tự xử lý. [Dòng 85](../main.py#L85) là hàm `main` đọc tham số và ghi kết quả CLI.
2. [modules/image_processing.py, dòng 45](../modules/image_processing.py#L45) — đọc ảnh, resize và tiền xử lý.
3. [modules/paper_detection.py, dòng 41](../modules/paper_detection.py#L41) — tìm giấy, sắp bốn góc và biến đổi phối cảnh. Sau đó mở [modules/background_removal.py, dòng 7](../modules/background_removal.py#L7) để xem cách ghép resize với căn phẳng.
4. [config/layout.json](../config/layout.json), [config/printed_50.json](../config/printed_50.json) và [modules/printed_form.py, dòng 15](../modules/printed_form.py#L15) — cấu hình lưới và cách tìm mốc đen.
5. [modules/answer_detection.py, dòng 140](../modules/answer_detection.py#L140) — vòng lặp đọc ô, tô chú thích và kiểm tra layout.
6. [gui/simple_app.py, dòng 666](../gui/simple_app.py#L666) — nút Đọc phiếu gọi pipeline thật. Mở tiếp [modules/scoring.py, dòng 47](../modules/scoring.py#L47) và [modules/export_excel.py, dòng 27](../modules/export_excel.py#L27) để giải thích chấm điểm và xuất kết quả.

## 3. Đọc ảnh và tiền xử lý

- [`load_image`, dòng 45](../modules/image_processing.py#L45) kiểm tra đường dẫn rồi dùng `np.fromfile` đọc byte. `cv2.imdecode` giải mã byte thành ảnh màu BGR. Bước giải mã nhận mảng byte nên tên ảnh có dấu hoặc ký tự Unicode được xử lý ở bước đọc file. Tệp rỗng, sai định dạng hoặc ảnh không hợp lệ có thông báo lỗi. [`save_image`, dòng 60](../modules/image_processing.py#L60) thực hiện chiều ngược lại qua `imencode` và `tofile`.
- [`resize_image`, dòng 74](../modules/image_processing.py#L74) tính hệ số bằng kích thước tối đa chia cho cạnh dài nhất. Cả ngang và dọc cùng nhân hệ số này. Mặc định chỉ thu nhỏ ảnh vượt 2.200 pixel ở cạnh dài, dùng `INTER_AREA` để giảm mất chi tiết khi thu nhỏ. Ảnh quá hẹp được chặn ở mức tối thiểu 3 pixel mỗi chiều để các bước sau có dữ liệu hợp lệ.
- [`to_grayscale`, dòng 87](../modules/image_processing.py#L87) chuyển BGR hoặc BGRA thành một kênh. Với ảnh đã xám, các bước đọc dữ liệu có thể truyền `copy=False` để dùng lại mảng; lời gọi mặc định vẫn trả bản sao.
- [`apply_blur`, dòng 95](../modules/image_processing.py#L95) dùng trung bình có trọng số Gaussian để giảm nhiễu. Kernel phải lẻ và dương để có một pixel ở tâm. [`apply_threshold`, dòng 102](../modules/image_processing.py#L102) dùng ngưỡng thích nghi Gaussian theo vùng lân cận, hoặc Otsu để chọn một ngưỡng chung cho toàn ảnh. Chế độ đảo khiến nét tối có giá trị 255, thuận tiện cho đếm mực.
- [`preprocess_image`, dòng 122](../modules/image_processing.py#L122) gọi tuần tự resize, grayscale, blur và threshold. Morphological opening chỉ được áp dụng ở bước này nếu cấu hình bật, để bỏ các cụm nhiễu nhỏ.

**Giảng viên có thể hỏi**

- **Vì sao đọc byte rồi giải mã?** Python/NumPy xử lý đường dẫn, còn OpenCV giải mã nội dung ảnh. Hai trách nhiệm tách rời nên có thể đọc tệp tên tiếng Việt.
- **Khi nào ngưỡng thích nghi có lợi?** Một vùng bị bóng đổ và một vùng sáng có mức nền khác nhau. Ngưỡng cục bộ được tính quanh từng pixel nên vẫn có thể tách nét mực ở cả hai vùng.
- **Ảnh nhị phân dùng để căn phẳng luôn được không?** Phép căn thực hiện trên ảnh màu đã resize để giữ sắc độ và chi tiết ô tô. Ảnh sau căn được nhị phân hóa theo layout dùng để đo mực.

## 4. Tìm contour, lấy bốn góc và căn giấy

1. [`find_paper_contour`, dòng 41](../modules/paper_detection.py#L41) chuyển xám một lần. Ở [dòng 54](../modules/paper_detection.py#L54), Gaussian Blur 5 × 5 làm mượt ảnh trước Canny. Canny phát hiện nơi cường độ sáng thay đổi mạnh. Morphological closing nối các khe nhỏ trên biên. Otsu tạo thêm mặt nạ vùng sáng.
2. [Dòng 60](../modules/paper_detection.py#L60) tạo ba mặt nạ bổ sung trên ảnh làm mượt theo kích thước. Ngưỡng lần lượt là `Otsu + f × (255 − Otsu)`, với `f` bằng 0,20, 0,35 và 0,50. Opening giúp bỏ cụm nhỏ. Các mức sáng bổ sung có ích khi mặt nền và giấy gần nhau về độ sáng.
3. [Dòng 72](../modules/paper_detection.py#L72) gom contour ngoài từ các mặt nạ. Loại contour nhỏ hơn diện tích tối thiểu, mặc định 15% diện tích ảnh. Riêng contour từ ba mặt nạ sáng bổ sung được chuyển sang bao lồi khi **diện tích contour / diện tích bao lồi ≥ 0,95**. Điều kiện này hạn chế việc kéo một vùng lõm hoặc dính nền thành hình có vẻ giống tờ giấy.
4. [Dòng 86](../modules/paper_detection.py#L86) xét contour lớn trước. Hộp bao cho biết contour có đi vào vùng sát mép ảnh hay không. Contour chạm mép bị loại, sau đó thử xấp xỉ đa giác với ba mức sai số theo chu vi tại [dòng 93](../modules/paper_detection.py#L93). Kết quả cần đúng bốn đỉnh, lồi, đủ diện tích và có cạnh ngắn nhất đạt ngưỡng mặc định 60 pixel.
5. [`order_points`, dòng 26](../modules/paper_detection.py#L26) xác nhận bốn điểm hữu hạn tạo được tứ giác lồi. Tính tâm, sắp theo góc quanh tâm rồi xoay dãy để điểm có tổng `x + y` nhỏ nhất đứng đầu. Thứ tự quy ước là trên trái → trên phải → dưới phải → dưới trái.
6. [`four_point_transform`, dòng 109](../modules/paper_detection.py#L109) kiểm tra kích thước đích và tọa độ nguồn, ghép bốn góc phiếu với bốn góc hình chữ nhật. `getPerspectiveTransform` tính ma trận 3 × 3. `warpPerspective` dùng ma trận và nội suy tuyến tính để tạo ảnh nhìn thẳng. Kích thước chuẩn mặc định là 1.000 × 1.400 pixel. Lưới đáp án trong JSON và kết quả warp cùng dùng kích thước đã khai báo.
7. [`remove_background`, dòng 7](../modules/background_removal.py#L7) resize rồi gọi [`detect_and_warp_paper`, dòng 128](../modules/paper_detection.py#L128). Ảnh đầu ra chỉ chứa vùng giấy vì phép warp ánh xạ tứ giác giấy vào toàn khung. Demo nhận diện dùng lại hàm này. Pipeline chính lấy bốn góc trực tiếp để còn vẽ lên ảnh debug.

**Giảng viên có thể hỏi**

- **Vì sao dùng cả biên Canny và mặt nạ sáng?** Canny bắt đường chuyển sáng tối. Mặt nạ sáng xem tờ giấy như một vùng. Khi biên mờ hoặc đứt, vùng sáng vẫn có thể tạo contour đủ tốt.
- **Vì sao không chọn luôn contour lớn nhất?** Mặt bàn sáng có thể phủ phần lớn ảnh. Các điều kiện về mép, diện tích, độ lồi, số đỉnh và chiều dài cạnh giúp loại ứng viên sai. Một ứng viên bị loại thì thuật toán xét ứng viên tiếp theo.
- **Sai số của `approxPolyDP` có tác dụng gì?** Sai số lớn hơn cho phép bỏ thêm chi tiết nhỏ trên đường bao. Dùng ba tỷ lệ theo chu vi giúp thử từ xấp xỉ sát đến xấp xỉ rộng hơn trên các ảnh khác kích thước.
- **Điểm nào được ghép khi tính ma trận?** Bốn góc nguồn và bốn góc đích ghép cùng thứ tự. Ghép sai thứ tự có thể xoay hoặc lật phiếu, làm lưới đọc trật vị trí.
- **Chạm mép ảnh có luôn là mất góc không?** Vùng nền sáng dính tới mép cũng tạo dấu hiệu này. Chương trình loại ứng viên và báo kiểm tra nền, ánh sáng và bốn góc nếu các ứng viên còn lại đều không đạt.
- **Khi nào dùng `already_warped`?** Khi ảnh đã thẳng và đúng kích thước của layout. Bước đọc đáp án vẫn kiểm tra viền ô nên một ảnh đúng kích thước nhưng sai lưới vẫn có thể bị từ chối.

## 5. Nhận diện đáp án

- [`detect_printed_layout`, dòng 15](../modules/printed_form.py#L15) lọc các khối tối gần vuông theo kích thước và độ đặc. Từ [dòng 35](../modules/printed_form.py#L35) kiểm tra sáu cặp mốc giữa hai cột, độ thẳng hàng, khoảng cách và hai mốc ngoài khi đã có dấu hiệu của mẫu in. Từ [dòng 62](../modules/printed_form.py#L62) chia mỗi khoảng giữa hai mốc liên tiếp thành năm hàng, rồi nội suy bốn vị trí theo bề rộng mỗi cột.
- [`load_layout`, dòng 104](../modules/answer_detection.py#L104) đọc JSON và kiểm tra hình học, tham số, và các tâm được cung cấp. [`bubble_centers`, dòng 116](../modules/answer_detection.py#L116) lấy tâm cấu hình hoặc tính tâm từ ô chữ nhật của lưới. Cột trái là câu 1–25, cột phải là 26–50. Khi truyền `--layout`, pipeline dùng cấu hình đó.
- [`analyze_answers`, dòng 140](../modules/answer_detection.py#L140) tạo ảnh nhị phân để đo mực. Tại [dòng 170](../modules/answer_detection.py#L170), một mặt nạ tròn lấy mực trong lòng ô, một vành khuyên lấy mực ở viền. Tỷ lệ mực bằng số pixel khác 0 chia cho số pixel của mặt nạ. [`_refine_center`, dòng 215](../modules/answer_detection.py#L215) thử các vị trí gần tâm nếu cấu hình bật, ưu tiên vành có nhiều mực và trừ điểm khi dịch xa.
- [`classify_ratios`, dòng 131](../modules/answer_detection.py#L131) lấy các ô đạt ngưỡng mực. Không có ô nào là `BLANK`, một ô là A/B/C/D, từ hai ô trở lên là `MULTIPLE`. Ở [dòng 205](../modules/answer_detection.py#L205), chương trình báo lỗi nếu quá ít viền khớp layout.

**Giảng viên có thể hỏi**

- **Tại sao đo vòng viền riêng?** Viền in cho biết tại tọa độ dự kiến có một ô. Lòng ô cho biết thí sinh tô bao nhiêu. Một phiếu thật bỏ trống vẫn có viền, còn tờ giấy trắng hoặc lưới lệch thường không đủ viền khớp.
- **Nếu thiếu mốc thì sao?** Khi có dấu hiệu mẫu in nhưng số lượng, khoảng cách hoặc độ thẳng hàng sai, chương trình báo lỗi. Với ảnh không đủ dấu hiệu mẫu in, chương trình thử lưới mặc định và tiếp tục kiểm tra viền.
- **Vì sao không chọn ô đậm nhất?** Chọn theo ngưỡng giúp giữ đúng hai trường hợp có ý nghĩa là bỏ trống và tô nhiều.

## 6. Tkinter, chấm điểm và Excel

- [`on_scan_sheet`, dòng 666](../gui/simple_app.py#L666) đọc đáp án và ảnh đánh dấu. [`on_load_key`, dòng 702](../gui/simple_app.py#L702) nạp JSON, [`on_manual_key`, dòng 717](../gui/simple_app.py#L717) mở hộp thoại nhập tay, và [`on_export_key_json`, dòng 724](../gui/simple_app.py#L724) lưu đáp án chuẩn.
- [`_apply_new_answer_key`, dòng 770](../gui/simple_app.py#L770) áp dụng bộ đáp án mới. [`_show_unscored`, dòng 789](../gui/simple_app.py#L789) xóa điểm cũ và đưa bảng về trạng thái chưa chấm sau khi đổi đáp án hoặc đọc lại thành công. [`on_open_image`, dòng 624](../gui/simple_app.py#L624) chỉ đổi ảnh đang dùng sau khi đọc và hiển thị ảnh mới thành công.
- [`score_answers`, dòng 47](../modules/scoring.py#L47) kiểm tra hai danh sách 50 câu, xác định trạng thái từng câu và cộng bộ đếm tương ứng. Điểm bằng số câu đúng chia 50 rồi nhân 10. [`on_score`, dòng 797](../gui/simple_app.py#L797) đưa điểm và thống kê lên giao diện.
- [`on_export_excel`, dòng 829](../gui/simple_app.py#L829) chuyển trạng thái hiện tại cho [`export_excel`, dòng 27](../modules/export_excel.py#L27). Hàm Excel chuẩn bị dữ liệu theo chế độ đã chấm hoặc chưa chấm, rồi dùng chung các vòng ghi tiêu đề, dòng kết quả và tổng hợp. Màu xanh lá là đúng, đỏ là sai, vàng là bỏ trống và cam là tô nhiều.

**Giảng viên có thể hỏi**

- **Đổi đáp án chuẩn cần nhận diện lại không?** Danh sách đã đọc là kết quả từ ảnh nên vẫn dùng được. Điểm trước đó phụ thuộc bộ đáp án cũ nên bị hủy và người dùng bấm Chấm điểm để tính lại.
- **Xuất Excel ngay sau khi đổi đáp án chuẩn sẽ ra gì?** Bảng nhận diện chưa chấm. Sau khi chấm lại, Excel có đáp án đúng, trạng thái và điểm tính theo bộ mới.

## 7. So sánh trước và sau

Mốc trước là source trong thư mục làm việc ban đầu, gồm các chỉnh sửa khoảng trắng đã có sẵn. Số dưới đây tính cả dòng trống. Tổng cho 10 file chương trình có chỉnh sửa giảm từ **2.326 xuống 2.020 dòng**, và số dòng có nội dung giảm từ **1.771 xuống 1.699**.

- `modules/image_processing.py` — 144 → 135. Dùng lại ảnh xám khi blur và threshold chỉ đọc dữ liệu. Giữ các hàm xử lý độc lập để demo, test và phần tìm giấy gọi trực tiếp.
- `modules/paper_detection.py` — 147 → 132. Một lần chuyển xám, một vòng thu contour cho các mặt nạ, một ngưỡng diện tích tính sẵn và dùng hộp bao để kiểm tra mép. Giữ lọc bao lồi, tứ giác và cạnh ngắn.
- `modules/background_removal.py` — 16 → 9. API tách nền có hai bước rõ ràng và được gọi từ demo nhận diện.
- `main.py` — 126 → 125. Rút nhánh căn phiếu và chỉ sao chép ảnh để vẽ contour khi bật debug. Giữ các điểm dừng theo phase và thứ tự xử lý lỗi.
- `modules/answer_detection.py` — 271 → 238. Kiểm tra cấu hình qua bước lấy tâm, dùng chung lát cắt cho lòng và viền ô, tính sẵn kích thước các mặt nạ. Giữ hiệu chỉnh tâm và kiểm tra viền.
- `modules/printed_form.py` — 100 → 93. Kiểm tra ứng viên mốc bằng nhánh loại sớm và dùng lại tọa độ đã tính. Giữ các kiểm tra về đủ mốc, thẳng hàng, khoảng cách và bề rộng.
- `modules/scoring.py` — 124 → 92. Mỗi nhánh xác định một trạng thái. Vòng lặp dùng chung một lệnh cộng bộ đếm theo trạng thái đó.
- `modules/export_excel.py` — 253 → 168. Gộp định dạng và cách ghi ô của hai chế độ Excel.
- `gui/simple_app.py` — 1.025 → 926. Gộp thao tác trở về trạng thái chưa chấm trong `_show_unscored`, gộp `_export_key_to_json_file` vào nút xuất JSON, dùng chung cấu hình bảng và cập nhật các ô thống kê bằng vòng lặp.
- `demos/demo_detect_answers.py` — 120 → 102. Dùng lại API tách nền khi ảnh cần căn.
- `tests/test_simple_gui.py` — 306 → 338. Thêm kiểm thử đọc lại sau khi chấm và chọn ảnh lỗi sau khi đã có kết quả.

Phần lọc hình học và kiểm tra mốc cần giữ vì chúng quyết định khi nào một ảnh đủ tin cậy để đọc. Viền ô và tâm tự hiệu chỉnh cần thiết với ảnh chụp lệch nhẹ. Các cấu hình widget còn dài vì mỗi vùng giao diện có nhãn, kích thước, màu và vị trí riêng.

## 8. Chạy khi bảo vệ

Chạy từ thư mục gốc dự án với môi trường đã cài `requirements.txt`.

```powershell
python run_simple_gui.py
python main.py test_images/sample_photo.png --phase 2 --debug
python main.py test_images/sample_photo.png --phase 3 --debug
python main.py test_images/printed_50_real.png --phase 4 --debug
python main.py test_images/sample_sheet.png --already-warped --layout config/layout.json
python demos/demo_preprocessing.py test_images/sample_photo.png
python demos/demo_detect_answers.py test_images/printed_50_real.png
python demos/demo_scoring.py
python -m unittest discover -s tests -v
```

Phase 2, 3 và 4 ghi lần lượt `threshold.png`, `warped.png` và `detected_bubbles.png`. Phase 4 còn ghi `answers.json`. Bật debug để xem lần lượt 2, 4 hoặc 6 ảnh trung gian theo phase. CLI trong checkout này phục vụ nhận diện. Chấm điểm và xuất Excel có trong Tkinter và demo chấm điểm.

Kết quả trên Windows, Python 3.14 và OpenCV 4.14 theo `requirements.txt`:

- 65/65 bài kiểm thử qua, gồm 17 bài Tkinter. Đã mở và hiển thị cửa sổ chính, hộp thoại nhập đáp án, đọc ảnh thật và chấm điểm qua các nút.
- Đối chiếu trước và sau trên 21 ca gồm ảnh chuẩn, ảnh nghiêng, bóng đổ, ảnh phiếu in thật và biến thể sáng/tối/thu nhỏ, câu trống/nhiều ô, phiếu mất góc/thiếu mốc, các phase và tiền xử lý. Đáp án, tỷ lệ mực, lỗi và ảnh đầu ra/debug trùng khớp cho các ca tương ứng. [Bài kiểm tra phiếu in thật](../tests/test_printed_form.py#L36) khớp đủ 50 câu với kết quả đọc tay, gồm câu 44 bỏ trống.
- Ba demo và các lệnh CLI ở phase 2/3/4 chạy thành công. Đã đọc lại cả hai loại Excel và đối chiếu giá trị ô, màu, căn lề, viền và kích thước cột.
