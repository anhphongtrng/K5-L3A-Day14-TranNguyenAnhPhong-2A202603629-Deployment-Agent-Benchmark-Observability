# Benchmark & Observability Report — Day 14

**Họ tên:** Trần Nguyễn Anh Phong

**Ngày chạy CP7:** 25/11/2026

**Môi trường CP7:** Ubuntu WSL2 trên Windows, Python 3.11.18, chạy agent và bộ tạo tải trên cùng máy.

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | ≤ 500 ms | Dùng ngưỡng mặc định của `load_test.py` để kiểm soát thời gian chờ ở nhóm request chậm. |
| Error rate `/ask` | ≤ 2% | Dùng ngưỡng mặc định của `load_test.py` để giới hạn tỷ lệ request thất bại. |
| Accuracy trên golden dataset | ≥ 85% | Ngưỡng dùng cho quality gate của CI theo Exercise 7.3. Kiểm tra sau khi sửa KB của CP7 yêu cầu 100% và không có regression so với baseline v2. |

### Metrics của agent

Output `GET /metrics` của v2 sau khi gửi một câu hỏi dài 40 ký tự (trích):

```text
# TYPE http_requests_total counter
http_requests_total{method="POST",route="/ask",status="200"} 1.0
# TYPE agent_in_flight_requests gauge
agent_in_flight_requests 0.0
# TYPE agent_question_length_chars histogram
agent_question_length_chars_count 1.0
agent_question_length_chars_sum 40.0
```

Counter đếm tổng request và tăng dần trong vòng đời tiến trình. Gauge tăng khi có request vào và giảm khi xử lý xong. Histogram mới ghi phân bố độ dài câu hỏi vào các bucket, kèm tổng số mẫu và tổng số ký tự.

Label `route` dùng mẫu route, với `unmatched` cho URL không khớp. Nếu dùng URL thật, hàng nghìn đường dẫn khác nhau sẽ tạo hàng nghìn chuỗi theo thời gian. Histogram còn tạo nhiều chuỗi cho từng tổ hợp label vì có các bucket, `_sum` và `_count`. Điều đó làm tăng bộ nhớ của agent, dung lượng lưu trữ và chi phí truy vấn của Prometheus.

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

Mỗi lượt gửi 300 request vào agent v2. RPS tính trên toàn bộ request đã gửi. Latency chỉ thống kê các phản hồi HTTP 200. Bản mock giữ `MOCK_ERROR_RATE=0.01` ở cả hai thí nghiệm tải. Bảng concurrency dùng `MOCK_SLOW_RATE=0.03`. Bảng tail latency giữ concurrency ở 20 và khởi động lại agent với từng mức `MOCK_SLOW_RATE`.

### 2.1 Concurrency vs latency (agent v2)

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|
| 1 | 4,40 | 189,3 | 219,0 | 1.692,1 | 0,33% | PASS |
| 10 | 37,13 | 188,6 | 218,4 | 1.696,3 | 0,33% | PASS |
| 50 | 107,98 | 195,5 | 241,6 | 1.693,3 | 1,00% | PASS |
| 100 | 133,97 | 206,2 | 297,5 | 1.716,2 | 0,33% | PASS |

RPS tăng dưới tuyến tính. Từ concurrency 50 lên 100, RPS chỉ tăng từ 107,98 lên 133,97, đồng thời p95 tăng từ 241,6 lên 297,5 ms. Các request song song có thể chồng lấp thời gian chờ LLM giả lập, nhưng vẫn chia sẻ tài nguyên của agent và bộ tạo tải. Lượt đo có 300 request nên vài request chậm cũng có thể kéo dài thời gian hoàn thành cả lượt. [JSON c1](reports/load_v2_c1.json) · [c10](reports/load_v2_c10.json) · [c50](reports/load_v2_c50.json) · [c100](reports/load_v2_c100.json)

### 2.2 Tail latency

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| 0 | 188,5 | 216,5 | 223,2 |
| 0.03 (mặc định) | 263,8 | 584,1 | 1.710,6 |
| 0.1 | 303,9 | 1.675,0 | 1.708,8 |

Ở mức 0,03, p99 đã tăng từ 223,2 lên 1.710,6 ms, trong khi average chỉ tăng từ 188,5 lên 263,8 ms. Average dàn phần chờ thêm của nhóm nhỏ lên toàn bộ mẫu. Ở mức 0,1, request chậm xuất hiện đủ thường xuyên để p95 tăng lên 1.675,0 ms. Hai lượt có request chậm đều vượt SLO p95 500 ms. p95 phù hợp làm SLO cho phần lớn request, còn p99 giúp phát hiện nhóm chậm hiếm hơn. Kết quả giữa các lượt có thể dao động vì mock chọn request chậm ngẫu nhiên. [JSON slow 0](reports/load_v2_slow_0.json) · [0.03](reports/load_v2_slow_0.03.json) · [0.1](reports/load_v2_slow_0.1.json)

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

Ba lượt eval dùng cùng golden dataset. `MOCK_ERROR_RATE=0` và `MOCK_SLOW_RATE=0` cố định để so sánh chất lượng câu trả lời và latency khi không có lỗi giả lập hoặc độ trễ bất thường.

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4,3% (1/23) | 91,3% (21/23) | 100% (23/23) |
| Avg tokens / câu | 57,1 | 109,0 | 114,9 |
| Latency p95 (ms) | 181,4 | 215,6 | 215,3 |
| Tổng cost (USD) | 0,000404 | 0,000760 | 0,000801 |
| Cost / câu đúng (USD) | 0,00040395 | 0,00003619 | 0,00003482 |
| Quality gate | FAIL (≥ 80%) | PASS (≥ 80%, 0 regression) | PASS (100%, 0 regression) |

**Những câu v2 trả lời sai ban đầu và cách bạn sửa:**

| ID | Keyword bị thiếu | Bạn đã sửa gì |
|---|---|---|
| `security-02` | `token`, `hết hạn`, `chữ ký` | Bổ sung tài liệu phân biệt API key với JWT, gồm cơ chế kiểm tra chữ ký và thời hạn. |
| `scaling-03` | `cpu`, `memory`, `custom metrics` | Bổ sung tài liệu về HPA và các nhóm chỉ số dùng để điều chỉnh số pod. |

**Quality gate trong CI.** Khởi động v2 với `MOCK_ERROR_RATE=0` và `MOCK_SLOW_RATE=0`, đợi `/health` trả 200, rồi chạy `python eval/run_eval.py --url http://localhost:8002 --min-accuracy 0.85`. Có thể thêm `--baseline` trỏ tới báo cáo của bản chuẩn để kiểm tra từng câu từng đạt. Script thoát với mã 1 khi accuracy dưới ngưỡng hoặc có regression so với baseline được cung cấp. Cấu hình job eval thành required status check của nhánh đích để CI lỗi thì PR bị chặn merge.

Retrieval tăng lượng token và p95 từ v1 sang v2. Tổng chi phí cũng tăng, nhưng số câu đúng tăng nhanh hơn, nên chi phí cho mỗi câu đúng giảm từ 0,00040395 xuống 0,00003619 USD. Sau khi bổ sung hai tài liệu, chi phí cho mỗi câu đúng giảm tiếp xuống 0,00003482 USD. P95 ở hai lượt v2 gần nhau (215,6 và 215,3 ms). [Eval v1](reports/eval_v1.json) · [Eval v2](reports/eval_v2.json) · [Eval v2 sau sửa](reports/eval_v2_fixed.json)

Tự kiểm tra CP7 bằng `python eval/run_eval.py --url http://localhost:8002 --min-accuracy 1.0 --baseline reports/eval_v2.json --out reports/eval_v2_fixed.json`. Kết quả thực tế (trích):

```text
Accuracy      : 100.0%  (23/23)
Câu được cải thiện : 2
Câu bị regression : 0
Quality gate (accuracy ≥ 100%, không regression): ✅ PASS
```

---

## 4. Observability stack (production)

CP8 chạy trong Docker Desktop trên cùng máy Windows/WSL2. Dockerfile của bản observability được sửa để cài dependency vào stage runtime đúng vị trí Python tìm kiếm. Trước khi sửa, agent thiếu module Uvicorn và Nginx trả 502. Các số đo dưới đây lấy từ stack đã build lại thành công.

### 4.1 Screenshot

- [x] Dashboard Grafana hiển thị Golden Signals khi có tải và đang bật lỗi giả lập A/B. Tại thời điểm chụp, traffic là **15,1 req/s**, error rate **19,01%** và p95 **1,90 giây**. [Ảnh Grafana](screenshots/grafana-dashboard.png)
- [x] Trace chậm trong Jaeger cho thấy span `chat mock-llm-small` chiếm phần lớn thời gian. [Ảnh trace chậm](screenshots/jaeger-slow-trace.png)
- [x] Trace lỗi trong Jaeger hiển thị HTTP 503 và event `exception` trong span `chat mock-llm-small`. [Ảnh trace lỗi](screenshots/jaeger-error-trace.png)
- [x] `AgentHighErrorRate` và `AgentHighLatencyP95` cùng **firing** trên trang Alerts. [Ảnh Prometheus](screenshots/prometheus-alert-firing.png)

**Exercise 7.4.** Locust chạy 30 user, tăng 5 user/giây, trên stack hai replica. Truy vấn trực tiếp Prometheus theo các biểu thức dùng trong Grafana cho thấy p95 **293,1 ms** và avg **233,1 ms**. Khoảng cách **60,0 ms** cho thấy nhóm request chậm có độ trễ cao hơn trung bình. Nginx phân khoảng **9,44 và 9,60 request/giây** vào hai replica tại thời điểm đo.

Input đạt **1.393,73 token/giây**, còn output đạt **738,04 token/giây**. Prompt v2 gồm câu hỏi, hướng dẫn hệ thống và tài liệu retrieval. Output chỉ gồm câu trả lời. `GET /metrics` qua Nginx trả **HTTP 404** vì cấu hình chặn route này. Prometheus scrape trực tiếp các agent qua mạng Docker.

### 4.2 Thí nghiệm lỗi giả lập

`promtool test rules` chạy thành công với bộ test alert đi kèm. Trong lần chạy thực tế, A và B được bật cùng lúc trên hai replica, giữ Locust ở 30 user. Thời gian bên dưới tính từ lúc bắt đầu áp dụng cấu hình đến lần đầu API Prometheus trả trạng thái `firing`, thăm dò mỗi hai giây.

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | `AgentHighErrorRate` | 89,2 giây | Error rate đạt 19,44% ở lần đầu quan sát firing. |
| B | `MOCK_SLOW_RATE=0.3` | `AgentHighLatencyP95` | 145,2 giây | Latency p95 đạt 1,893 giây ở lần đầu quan sát firing. |

Khi cả hai alert cùng firing, Prometheus báo error rate **21,63%** và p95 **1,893 giây**.

**Phát hiện suy giảm chất lượng khi đổi sang agent v1.** Chạy eval trên golden dataset trước khi deploy và định kỳ sau deploy. So sánh accuracy và kết quả từng câu với baseline đang chạy. Chặn phát hành nếu vi phạm quality gate và cảnh báo nếu accuracy giảm. Kết quả CP7 cho thấy v1 chỉ đúng 1/23 câu dù không có lỗi HTTP trong lượt eval.

### 4.3 Debug bằng trace

- Trace chậm nhất trong tập kết quả đã truy vấn từ Jaeger có ID `256fa97050d5512c343d9a44b133e6e2`. Span gốc `POST /ask` mất **1.761,384 ms**.
- Trong `agent.run`, span `chat mock-llm-small` mất **1.682,834 ms**, tức khoảng **95,54%** của cả request. Span retrieval mất **21,364 ms**. Phần lớn thời gian nằm ở lần gọi mock LLM.
- Trace lỗi `01cd71f12436e207355feb76d314c41f` có span `chat mock-llm-small` ở trạng thái ERROR và event `exception` loại `utils.mock_llm.LLMError`. Dòng `llm_error` trong log có cùng trace ID. [Trace chậm trong Jaeger](http://localhost:16686/trace/256fa97050d5512c343d9a44b133e6e2) · [Trace lỗi trong Jaeger](http://localhost:16686/trace/01cd71f12436e207355feb76d314c41f)

Hai dòng log độc lập đối chiếu theo `trace_id`:

```jsonl
{"ts":"2026-11-25T09:49:15.294190+00:00","level":"INFO","service":"observable-agent","instance":"ca3c6a24d34f","event":"llm_call","trace_id":"256fa97050d5512c343d9a44b133e6e2","span_id":"bd9370a71b0194b9","request_id":"6cad175e8c6a","model":"mock-llm-small","agent_version":"v2","input_tokens":73,"output_tokens":35,"cost_usd":3.2e-05,"llm_ms":1683.1}
{"ts":"2026-11-25T09:50:07.919188+00:00","level":"INFO","service":"observable-agent","instance":"ca3c6a24d34f","event":"llm_error","trace_id":"01cd71f12436e207355feb76d314c41f","span_id":"9ddf726036d0e623","request_id":"4c4a03988c10","error":"Upstream LLM error: 503 Service Unavailable (mock)"}
```

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

Mỗi lượt tăng 10 user/giây lên 100 user, chạy 120 giây và giữ cùng model cùng cấu hình mock. Bảng dùng dòng `POST /ask` trong CSV vì Locust cũng gọi `GET /health`.

Cả hai lượt dùng project Compose `k5-day14-observability`. Mỗi lần scale xong, stack có thời gian cập nhật DNS trước khi Locust bắt đầu. Locust chạy với `--headless -u 100 -r 10 -t 2m` và trỏ vào `http://nginx` trên mạng Docker.

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | 60,03 | 190 | 220 | 1.700 | 80/7.165 (1,12%) |
| 3 | 59,76 | 190 | 220 | 1.700 | 63/7.110 (0,89%) |

P95 giữ nguyên ở 220 ms và RPS gần như không đổi. Với mức tải này, thời gian chờ của mỗi người dùng giả lập và latency được chèn trong mock LLM vẫn chi phối kết quả. Nginx có phân tải, nhưng thêm replica không rút ngắn lần gọi mock LLM của một request. Chênh lệch tỷ lệ lỗi giữa hai lượt phù hợp với lỗi upstream được mô phỏng ngẫu nhiên. [CSV 1 replica](benchmark-results/scale_1_stats.csv) · [CSV 3 replica](benchmark-results/scale_3_stats.csv)

---

## 6. Kết luận

1. Đo cả p95 và p99 giúp thấy nhóm request rất chậm dù p50 và average còn thấp.
2. Số liệu phân tải theo replica cho biết Nginx chia tải ra sao. Trace cho biết thêm replica có tác động được đến bước gây chậm hay không.
3. Eval theo từng câu bắt được regression chất lượng và cost trên mỗi câu đúng phản ánh giá trị của mỗi lần gọi LLM.

Trong production, theo dõi thêm tỷ lệ 502/504 ở Nginx và chạy probe từ bên ngoài để phát hiện lỗi xảy ra trước khi request tới agent. Chạy eval định kỳ để phát hiện chất lượng suy giảm dù latency và tỷ lệ lỗi HTTP vẫn trong ngưỡng.
