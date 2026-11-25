# CP6 — Triển khai agent

Agent từ `06-lab-complete/` chạy trên Railway trong project `k5-day14-cp6`, môi trường `production`. Service web là `day14-agent`, build bằng Dockerfile và dùng Redis cùng project qua mạng nội bộ.

**URL gốc của API** `https://day14-agent-production-b49979a0.up.railway.app` · [Mở endpoint `/health`](https://day14-agent-production-b49979a0.up.railway.app/health)

## Cách triển khai

Từ gốc repo đã liên kết với project Railway:

```bash
railway up ./06-lab-complete --path-as-root --service day14-agent
```

Các biến được cấu hình trên service `day14-agent`:

| Biến | Cấu hình |
| --- | --- |
| `ENVIRONMENT` | `production` |
| `PORT` | `8000` |
| `REDIS_URL` | Tham chiếu `${{Redis.REDIS_URL}}` |
| `AGENT_API_KEY` | Secret cấu hình trên Railway |
| `RATE_LIMIT_PER_MINUTE` | `10` |
| `DAILY_BUDGET_USD` | `1.0` |

## Tự kiểm tra

Đặt `AGENT_API_KEY` trong môi trường local bằng key của dịch vụ trước khi chạy phép thử cuối.

```bash
BASE=https://day14-agent-production-b49979a0.up.railway.app
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H 'Content-Type: application/json' -d '{"question":"Hello"}'
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H 'Content-Type: application/json' -H "X-API-Key: $AGENT_API_KEY" \
  -d '{"question":"Hello"}'
```

Kết quả đo trên URL public ngày 25/11/2026 lúc 16:10 GMT+7:

| Kiểm tra | HTTP |
| --- | --- |
| `GET /health` | 200 |
| `GET /ready` | 200 |
| `POST /ask` thiếu API key | 401 |
| `POST /ask` có API key hợp lệ | 200 |

## Ảnh bằng chứng

- [Dashboard có agent và Redis online](screenshots/dashboard.png)
- [Deployment agent đang hoạt động](screenshots/running.png)
- [Transcript bốn kiểm tra HTTP](screenshots/test.png)
