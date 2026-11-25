# Day 14 — Mission Answers

## Part 1 — Localhost vs Production

### Exercise 1.1 — Anti-patterns

Nguồn: [`01-localhost-vs-production/develop/app.py`](01-localhost-vs-production/develop/app.py).

| Vị trí | Vấn đề | Hậu quả khi đưa lên production |
| --- | --- | --- |
| Dòng 17–18 | API key và chuỗi kết nối có mật khẩu được ghi thẳng trong mã nguồn. | Nếu dùng thông tin thật, người có quyền đọc repo hoặc lịch sử commit có thể lấy được credential. Đổi key hoặc mật khẩu cũng phải sửa mã nguồn và triển khai lại. |
| Dòng 33–38 | App dùng `print()` để ghi câu hỏi, API key và câu trả lời. | Dữ liệu người dùng và key có thể bị lưu vào log. Log dạng văn bản rời cũng khó lọc theo trường hoặc mức độ khi điều tra lỗi. |
| Dòng 25–39 | App chỉ khai báo `GET /` và `POST /ask`, thiếu endpoint health check riêng. | Nền tảng không có endpoint chuyên dụng để kiểm tra liveness. Route `GET /` chỉ trả lời chào nên cũng không cho biết agent đã sẵn sàng xử lý request hay chưa. |
| Dòng 51–52 | Uvicorn bind vào `localhost` và dùng cổng cố định 8000. | Proxy ở ngoài container không thể kết nối vào địa chỉ loopback của app. Nếu nền tảng cấp cổng qua `PORT`, app vẫn nghe ở 8000 nên có thể không nhận được traffic. |
| Dòng 53 | Uvicorn bật `reload=True`, tùy chọn tự nạp lại dành cho phát triển. | App chạy thêm tiến trình theo dõi file. Nếu mã nguồn thay đổi, worker có thể khởi động lại ngoài quy trình triển khai, gây gián đoạn dịch vụ. |

### Exercise 1.2 — Chạy bản develop

`app.py` được chạy từ thư mục `01-localhost-vs-production/develop/` trong Ubuntu WSL2, với các gói từ `requirements.txt` được cài trong môi trường Python riêng.

```bash
curl -i -X POST 'http://localhost:8000/ask?question=Hello'
```

Kết quả thực tế (trích):

```http
HTTP/1.1 200 OK
content-type: application/json

{"answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}
```

Endpoint nhận `question` qua query string và trả JSON chứa câu trả lời của mock LLM. HTTP 200 xác nhận luồng hỏi đáp hoạt động trên máy local. Trước khi đưa app lên production, cần xử lý các vấn đề ở Exercise 1.1.

### Exercise 1.3 — So sánh develop và production

| Tiêu chí | Develop | Production | Vì sao quan trọng? |
| --- | --- | --- | --- |
| Cấu hình | Ghi API key và chuỗi kết nối trong code, bind vào `localhost:8000`, luôn bật reload (`app.py`, dòng 17–22 và 47–54). | `config.py` đọc `HOST`, `PORT`, `DEBUG` và các key từ biến môi trường. Mặc định bind `0.0.0.0` và tắt reload. | Cùng một bản build có thể chạy ở nhiều môi trường. Nền tảng có thể cấp cổng và cấu hình secret bên ngoài mã nguồn. |
| Health check | Có `GET /` trả lời chào. | `GET /health` trả trạng thái và uptime. `GET /ready` trả 200 khi cờ readiness được bật, 503 khi chưa sẵn sàng (`app.py`, dòng 135–161). | Liveness giúp nền tảng phát hiện tiến trình có vấn đề. Readiness giúp bộ cân bằng tải chọn instance đã sẵn sàng nhận request. |
| Logging | Dùng `print()` và ghi cả API key, nội dung câu hỏi và câu trả lời (`app.py`, dòng 33–38). | Dùng `logging` với định dạng hướng đến JSON. Log hỏi đáp ghi tên sự kiện, độ dài câu hỏi hoặc câu trả lời và IP ở sự kiện request (`app.py`, dòng 27–32 và 110–122). | Tên sự kiện và mức log giúp lọc khi điều tra lỗi. Việc bỏ key và nội dung hỏi đáp khỏi log giảm nguy cơ lộ dữ liệu. |
| Graceful shutdown | Không có hook shutdown riêng của ứng dụng. | Uvicorn xử lý quá trình dừng server. Hook `lifespan` chuyển cờ readiness về `False` và ghi log shutdown (`app.py`, dòng 39–74 và 180–189). | Hook tạo điểm để dọn tài nguyên khi dừng app. Graceful shutdown giúp các request đang xử lý có thời gian hoàn tất trước khi tiến trình thoát. |

Kiểm tra bản `production` trong Ubuntu WSL2 bằng cấu hình mặc định. `GET /health`, `GET /ready` và `POST /ask` với JSON `{"question":"Hello"}` đều trả HTTP 200. Sau khi gửi SIGTERM lúc server đang rảnh, Uvicorn ghi `Application shutdown complete.` và tiến trình thoát với mã 0.

