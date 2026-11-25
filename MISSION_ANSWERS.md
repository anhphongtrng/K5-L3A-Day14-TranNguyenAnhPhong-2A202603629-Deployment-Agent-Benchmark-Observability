# Day 14 — Mission Answers

## CP1 — Phần 1 · Localhost vs Production

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

## CP2 — Phần 2 · Docker

### Exercise 2.1 — Dockerfile cơ bản

1. **Base image.** `FROM python:3.11` dùng image Python chính thức với Python 3.11 làm nền cho image của agent.
2. **Working directory.** `WORKDIR /app` đặt thư mục làm việc bên trong container là `/app`. Đích tương đối `.` trong các lệnh `COPY` trỏ đến thư mục này. Khi container khởi động, `python app.py` cũng chạy từ đây.
3. **Thứ tự copy.** Docker copy `requirements.txt` rồi chạy `pip install` trước khi copy mã nguồn. Nếu chỉ sửa `app.py` và các bước trước đó vẫn có cache, Docker có thể dùng lại lớp đã cài dependencies. Khi `requirements.txt` thay đổi, bước cài dependencies sẽ chạy lại.
4. **`CMD` và `ENTRYPOINT`.** `CMD ["python", "app.py"]` cung cấp lệnh mặc định. Dockerfile này dùng `CMD` để khởi động agent. Lệnh đặt sau tên image trong `docker run` có thể thay thế giá trị `CMD`. Nếu cấu hình `ENTRYPOINT` ở dạng exec, nó xác định chương trình chính và `CMD` có thể cung cấp đối số mặc định cho chương trình đó. Dùng `--entrypoint` để ghi đè `ENTRYPOINT`.

### Exercise 2.2 — Build và chạy container

Các lệnh được chạy từ gốc repo trong Ubuntu WSL2:

```bash
docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .
docker run --rm -d -p 127.0.0.1:8000:8000 my-agent:develop
curl -i -X POST 'http://localhost:8000/ask?question=What%20is%20Docker%3F'
docker images my-agent:develop
```

Kết quả gọi agent (trích):

```http
HTTP/1.1 200 OK
content-type: application/json

{"answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}
```

Kết quả `docker images my-agent:develop` (trích):

```text
IMAGE              ID             DISK USAGE   CONTENT SIZE   EXTRA
my-agent:develop   d4ffcc414c99       1.15GB             0B   U
```

Dung lượng ghi nhận ở cột `DISK USAGE` là **1.15 GB**. Container được dừng và tự xóa sau khi kiểm tra.

### Exercise 2.3 — Multi-stage build

1. **Stage 1 · Builder.** Dùng `python:3.11-slim`, cài `gcc` và `libpq-dev` để hỗ trợ build dependency khi cần. Sau đó, `pip install --user` cài các gói Python từ `requirements.txt` vào `/root/.local`.
2. **Stage 2 · Runtime.** Bắt đầu từ một image `python:3.11-slim` mới, copy các gói Python đã cài sang `/home/appuser/.local` và thêm mã nguồn. Uvicorn chạy dưới tài khoản `appuser`.
3. **Vì sao image nhỏ hơn?** Runtime dùng base image `slim` và chỉ lấy gói Python cần để chạy từ builder. Các công cụ build như `gcc` và gói header `libpq-dev` nằm ở stage builder.

Các lệnh build và đo dung lượng được chạy từ gốc repo:

```bash
docker build -f 02-docker/production/Dockerfile -t my-agent:advanced .
docker images my-agent
docker image inspect --format '{{.RepoTags}} {{.Size}}' my-agent:develop my-agent:advanced
```

Kết quả `docker images` (trích):

```text
IMAGE               ID             DISK USAGE   CONTENT SIZE   EXTRA
my-agent:advanced   306087538fa9        163MB             0B
my-agent:develop    d4ffcc414c99       1.15GB             0B   U
```

`docker image inspect` ghi nhận **1.154.311.927 byte** cho bản `develop` và **162.892.338 byte** cho bản `advanced`. Tính theo số byte trước khi làm tròn, dung lượng giảm **85,89%** theo công thức `(1 − 162892338 / 1154311927) × 100`.

### Exercise 2.4 — Docker Compose stack

```mermaid
flowchart LR
    Client["Client · localhost:80"]
    subgraph Internal["Mạng bridge internal"]
        Nginx["nginx:80 · reverse proxy"]
        Agent["agent:8000 · FastAPI"]
        Redis["redis:6379 · cache"]
        Qdrant["qdrant:6333 · vector database"]
        Nginx -->|HTTP proxy| Agent
        Agent -.->|REDIS_URL| Redis
        Agent -.->|QDRANT_URL| Qdrant
    end
    Client -->|HTTP| Nginx
```

Compose chạy bốn service trên cùng mạng bridge. Nginx nhận HTTP từ cổng 80 của host và chuyển tiếp đến `agent:8000` theo tên service. Compose chờ Redis và Qdrant đạt trạng thái healthy trước khi khởi động agent. Các mũi tên nét đứt thể hiện URL được cấu hình cho agent. Endpoint `/ask` trong mẫu gọi mock LLM trực tiếp.

Các lệnh chạy trong `02-docker/production/`:

```bash
touch .env.local
docker compose -p k5-day14-docker up -d --build --wait --wait-timeout 120
docker compose -p k5-day14-docker ps
curl -i http://localhost/health
curl -i -X POST http://localhost/ask \
  -H 'Content-Type: application/json' \
  -d '{"question":"Explain microservices"}'
docker compose -p k5-day14-docker down
```

Kết quả `docker compose ps` xác nhận `agent`, `redis` và `qdrant` đều `Up (healthy)`, còn `nginx` ở trạng thái `Up`.

`GET /health` qua Nginx (trích):

```http
HTTP/1.1 200 OK
Server: nginx
Content-Type: application/json

{"status":"ok","uptime_seconds":4.5,"version":"2.0.0","timestamp":"2026-11-25T08:12:00.563693"}
```

`POST /ask` qua Nginx (trích):

```http
HTTP/1.1 200 OK
Server: nginx
Content-Type: application/json

{"answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}
```

## CP3 — Phần 3 · API Security

### Exercise 4.1 — API Key authentication

- **Vị trí kiểm tra.** Trong [`04-api-gateway/develop/app.py`](04-api-gateway/develop/app.py), `APIKeyHeader` đọc header `X-API-Key`, còn `verify_api_key()` đối chiếu giá trị với `AGENT_API_KEY` (dòng 35–54). `POST /ask` khai báo `Depends(verify_api_key)` ở dòng 70 nên việc xác thực diễn ra trước khi xử lý câu hỏi.
- **Key sai hoặc thiếu.** Mẫu trả `403 Forbidden` cho key sai và `401 Unauthorized` khi thiếu key. Key hợp lệ cho phép xử lý request.
- **Đổi key.** Cập nhật `AGENT_API_KEY` trong nơi cấu hình môi trường, khởi động lại hoặc triển khai lại agent để nạp giá trị mới, rồi cập nhật key phía client. Bản mẫu chỉ chấp nhận một key tại một thời điểm và đọc giá trị khi khởi động.

Bản `develop` được chạy trên `127.0.0.1:8041` trong Ubuntu WSL2 vì cổng 8000 đang bận. Ba request đều gửi JSON `{"question":"Hello"}` đến `POST /ask`. Header được bỏ qua, gửi key sai hoặc gửi key hợp lệ tương ứng với ba kết quả sau.

```http
HTTP/1.1 401 Unauthorized

{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}
```

```http
HTTP/1.1 403 Forbidden

{"detail":"Invalid API key."}
```

```http
HTTP/1.1 200 OK

{"question":"Hello","answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic."}
```

### Exercise 4.2 — JWT authentication

1. Trên bản `production` của Part 4, `POST /auth/token` kiểm tra thông tin đăng nhập của tài khoản mẫu `student`. Khi xác thực thành công, server ký JWT có thời hạn 60 phút.
2. Client gửi JWT trong header `Authorization: Bearer <token>` khi gọi `POST /ask`. Dependency `verify_token()` trong [`auth.py`](04-api-gateway/production/auth.py) kiểm tra chữ ký và thời hạn trước khi endpoint xử lý câu hỏi.

Bản mẫu chạy trên `127.0.0.1:8042` trong Ubuntu WSL2. Kết quả thực tế của `POST /auth/token` (trích, token đã được che):

```http
HTTP/1.1 200 OK

{"access_token":"[đã che]","token_type":"bearer","expires_in_minutes":60}
```

Kết quả `POST /ask` với JWT vừa cấp và body `{"question":"Explain JWT"}` (trích):

```http
HTTP/1.1 200 OK

{"question":"Explain JWT","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé.","usage":{"requests_remaining":9,"budget_remaining_usd":1.6e-05}}
```

### Exercise 4.3 — Rate limiting

- **Thuật toán.** [`rate_limiter.py`](04-api-gateway/production/rate_limiter.py) dùng cửa sổ trượt 60 giây. Mỗi lần gọi, limiter loại bỏ timestamp đã ra khỏi cửa sổ rồi đếm request còn lại theo username. Nếu đã đạt ngưỡng, request mới nhận HTTP 429.
- **Ngưỡng theo vai trò.** Tài khoản `student` dùng ngưỡng **10 request/phút**. Vai trò `admin` được xác thực dùng bộ giới hạn riêng ở mức **100 request/phút**.

Thử nghiệm gửi 20 request tuần tự đến `POST /ask` trên agent local vừa khởi động, dùng JWT hợp lệ của tài khoản `student`. Request **1–10** trả **200**, request **11–20** trả **429**. Phản hồi của request thứ 11 (trích):

```http
HTTP/1.1 429 Too Many Requests
x-ratelimit-limit: 10
x-ratelimit-remaining: 0
retry-after: 59
content-type: application/json

{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":59}}
```

Header `Retry-After: 59` cho biết số giây cần đợi trước khi thử lại tại thời điểm đo.

### Exercise 4.4 — Cost guard

Trong [cost guard mẫu](04-api-gateway/production/cost_guard.py), `POST /ask` kiểm tra ngân sách trước khi gọi mock LLM. Sau khi có phản hồi, `record_usage()` cộng token đầu vào và đầu ra vào bộ đếm của tài khoản. Chi phí được tính theo công thức `(input_tokens / 1000 × giá input mỗi 1000 token) + (output_tokens / 1000 × giá output mỗi 1000 token)`. Mẫu lưu bộ đếm trong bộ nhớ và trả **402 Payment Required** khi mức sử dụng của tài khoản chạm ngân sách ngày.

**Thiết kế ngân sách 10 USD/người/tháng.** Dùng Redis để các replica chia sẻ số đã chi theo khóa `budget:{user_id}:{YYYY-MM}`, với tháng tính theo UTC. Trước khi gọi LLM, ước tính chi phí của request, gồm chi phí đầu vào và mức đầu ra tối đa được cấp. Dùng một thao tác nguyên tử trong Redis để đọc số đã chi, kiểm tra tổng sau khi giữ trước khoản ước tính và chỉ cộng khoản giữ trước nếu tổng không vượt **10 USD**. Nếu vượt, `check_budget()` trả `False` và API trả **402**. Khi có số token thực tế, cập nhật bộ đếm với phần chênh lệch so với khoản đã giữ. Tháng mới dùng khóa mới và TTL dọn các khóa cũ.

**Kiểm tra trên code mẫu.** Gọi trực tiếp `CostGuard.check_budget()` với ngân sách ngày 1 USD và nạp số token giả lập tương ứng 1,20 USD. Kết quả chương trình trước và sau khi nạp:

```text
Before usage: accepted
After simulated usage: 402 {'error': 'Daily budget exceeded', 'used_usd': 1.2, 'budget_usd': 1.0, 'resets_at': 'midnight UTC'}
```

## CP4 — Phần 4 · Scaling & Reliability

### Exercise 5.1 — Health checks

`GET /health` là liveness probe, dùng để kiểm tra agent còn chạy. `GET /ready` là readiness probe, dùng để quyết định có chuyển traffic đến agent hay không. Trong bản `production` của CP4, readiness kiểm tra Redis bằng `PING`. Khi Redis mất kết nối, tiến trình vẫn sống nhưng không sẵn sàng phục vụ các request cần dữ liệu phiên.

Kết quả gọi qua Nginx tại `localhost:8080`:

| Trạng thái | `GET /health` | `GET /ready` |
| --- | --- | --- |
| Redis đang chạy | HTTP 200, `"status":"ok"`, `"redis_connected":true` | HTTP 200, `"ready":true` |
| Dừng Redis của stack thử nghiệm | HTTP 200, `"status":"degraded"`, `"redis_connected":false` | HTTP 503, `{"detail":"Redis not available"}` |

### Exercise 5.2 — Graceful shutdown

Uvicorn xử lý SIGTERM, dừng nhận kết nối mới và chờ request đang xử lý. Bản `develop` đặt thời gian chờ tối đa 30 giây. Khi chạy hook shutdown của FastAPI, ứng dụng hạ cờ readiness và ghi log. Hook này cũng là nơi có thể đóng các kết nối do ứng dụng quản lý.

Trong Ubuntu WSL2, bản `develop` được chạy trên cổng 8052. SIGTERM được gửi khoảng 0,5 giây sau khi bắt đầu `POST /ask?question=Long%20task`, khi request mock vẫn đang xử lý. Kết quả thực tế (trích):

```text
INFO:     Shutting down
INFO:     127.0.0.1:55494 - "POST /ask?question=Long%20task HTTP/1.1" 200 OK
INFO:     Waiting for application shutdown.
INFO:     Application shutdown complete.
```

Client nhận **HTTP 200** và tiến trình thoát với mã **0**.

### Exercise 5.3 — Stateless design

Mỗi replica có bộ nhớ riêng. Nếu lịch sử nằm trong RAM của agent, request sau có thể đến một replica không có dữ liệu của phiên, và việc restart replica có thể làm mất lịch sử. Bản `production` lưu phiên theo khóa `session:{session_id}` trong Redis dùng chung, với TTL mặc định 3.600 giây. Khi client gửi lại cùng `session_id`, bất kỳ replica nào cũng có thể đọc và ghi lịch sử của phiên qua Redis.

### Exercise 5.4 — Load balancing

Các lệnh được chạy trong `05-scaling-reliability/production/`:

```bash
touch .env.local
docker compose -p k5-day14-scaling up -d --build --scale agent=3 --wait
docker compose -p k5-day14-scaling ps
python3 test_stateless.py
```

`docker compose ps` cho thấy cả ba container `agent-1`, `agent-2`, `agent-3` ở trạng thái `Up (healthy)`. Nginx nhận HTTP ở cổng host 8080 và phân phối request tới các replica của `agent:8000`. Trường `served_by` cho biết instance đã xử lý từng request. Năm request trong lần kiểm tra lần lượt đến `instance-48dd7e`, `instance-a779d1`, `instance-16acdc`, `instance-48dd7e` và `instance-a779d1`.

### Exercise 5.5 — Tự kiểm tra stateless

`test_stateless.py` gửi năm câu hỏi qua `POST /chat`, tái sử dụng cùng một `session_id`, rồi đọc lịch sử qua `GET /chat/{session_id}/history`. Kết quả thực tế (trích):

```text
Total requests: 5
Instances used: {'instance-48dd7e', 'instance-16acdc', 'instance-a779d1'}
✅ All requests served despite different instances!

--- Conversation History ---
Total messages: 10
```

Ba replica đã xử lý request của cùng phiên và lịch sử đọc được đủ năm cặp câu hỏi–trả lời, vì các replica dùng chung Redis. Phép thử xác nhận lịch sử xuyên replica. Sau các phép thử, stack được dừng bằng `docker compose -p k5-day14-scaling down`.

Endpoint nhận `question` qua query string và trả JSON chứa câu trả lời của mock LLM. HTTP 200 xác nhận luồng hỏi đáp hoạt động trên máy local. Trước khi đưa app lên production, cần xử lý các vấn đề ở Exercise 1.1.
