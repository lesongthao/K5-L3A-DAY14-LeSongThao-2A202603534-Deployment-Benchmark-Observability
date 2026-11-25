# Day 14 Lab — Mission Answers

## Part 1: Localhost vs Production

### Exercise 1.1: Các anti-patterns phát hiện trong `01-localhost-vs-production/develop/app.py`

1. **Hardcode thông tin nhạy cảm trong mã nguồn (dòng 17–18):** Khai báo trực tiếp `OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"` và `DATABASE_URL = "postgresql://admin:password123@localhost:5432/mydb"`. Nếu push lên GitHub, bí mật bị lộ ngay lập tức và nằm vĩnh viễn trong lịch sử commit.
2. **Không quản lý cấu hình theo môi trường (dòng 21–22):** `DEBUG = True` và `MAX_TOKENS = 500` được gán cứng trong code thay vì đọc từ biến môi trường (12-Factor Config).
3. **Dùng `print()` và làm lộ secret ra log (dòng 33–38):** Dùng `print(f"[DEBUG] Using key: {OPENAI_API_KEY}")` vừa xuất plain-text khó lọc/phân tích trên hệ thống log tập trung, vừa ghi trực tiếp API key vào stdout.
4. **Thiếu endpoint kiểm tra sức khỏe (`/health`, `/ready`) (dòng 42–43):** Platform (Docker, Railway, Render, Kubernetes) không thể kiểm tra tiến trình còn sống hay sẵn sàng nhận traffic để tự khởi động lại hoặc điều phối tải.
5. **Gắn cứng `host="localhost"` và `port=8000` (dòng 51–52):** `localhost` chỉ lắng nghe loopback nên bên ngoài container không truy cập được; cổng cố định `8000` không nhận biến `PORT` do cloud platform cấp phát động.
6. **Bật `reload=True` ở entrypoint chính (dòng 53) và không xử lý graceful shutdown:** `reload=True` tốn tài nguyên theo dõi tệp và có thể gây rò rỉ hoặc khởi động lại bất ngờ trên production; tiến trình tắt đột ngột sẽ cắt ngang các request đang xử lý.
7. **Nhận tham số qua query string thay vì JSON body (dòng 31):** `def ask_agent(question: str)` buộc client truyền `?question=...` trên URL (dễ lộ nội dung câu hỏi trong access log và giới hạn độ dài URL).

### Exercise 1.2: Kết quả chạy bản develop và bản production

**Bản develop (`01-localhost-vs-production/develop/app.py`):**

```http
$ curl -X POST "http://127.0.0.1:8000/ask?question=Hello"
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 15:03:17 GMT
server: uvicorn
content-length: 126
content-type: application/json

{"answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic."}
```

**Bản production (`01-localhost-vs-production/production/app.py`):**

```http
$ curl http://127.0.0.1:8000/health
HTTP/1.1 200 OK
content-type: application/json

{"status":"ok","uptime_seconds":0.6,"version":"1.0.0","environment":"development","timestamp":"2026-11-25T15:03:19.569144+00:00"}

$ curl http://127.0.0.1:8000/ready
HTTP/1.1 200 OK
content-type: application/json

{"ready":true}

$ curl -X POST http://127.0.0.1:8000/ask -H "Content-Type: application/json" -d '{"question":"Hello"}'
HTTP/1.1 200 OK
content-type: application/json

{"question":"Hello","answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic.","model":"gpt-4o-mini"}
```

### Exercise 1.3: Bảng so sánh Develop vs Production

| Feature | Develop (`develop/app.py`) | Production (`production/app.py` & `config.py`) | Tại sao quan trọng? |
| --- | --- | --- | --- |
| **Config & Secrets** | Hardcode `OPENAI_API_KEY`, `DATABASE_URL`, `DEBUG = True` (dòng 17–22) | Đọc từ `os.getenv(...)` trong `Settings` (`config.py` dòng 14–46), kiểm tra fail-fast ở `validate()` | Đóng gói một image dùng cho nhiều môi trường (dev/staging/prod), không lộ bí mật trong Git. |
| **Health & Readiness** | Không có `/health` và `/ready` | Có `GET /health` (dòng 135–149) và `GET /ready` (dòng 152–161) kiểm tra cờ `is_ready` | Cloud/orchestrator biết khi nào container chết để restart (`/health`) và khi nào sẵn sàng nhận traffic (`/ready`). |
| **Logging** | `print("[DEBUG] ...")` kèm lộ `OPENAI_API_KEY` (dòng 33–38) | `logging.basicConfig` xuất JSON (`{"time":...,"level":...,"msg":...}`) + `json.dumps` không log secret (dòng 28–31, 111–122) | Structured JSON log cho phép hệ thống log (Loki, Datadog) parse, lọc theo trường và bảo vệ dữ liệu nhạy cảm. |
| **Network & Binding** | `host="localhost"`, `port=8000`, `reload=True` (dòng 50–53) | `host=settings.host` (`0.0.0.0`), `port=settings.port` (`PORT` env), `reload=settings.debug` (dòng 194–199) | `0.0.0.0` cho phép nhận kết nối từ ngoài container; đọc `PORT` động giúp deploy được trên Railway/Render/Cloud Run. |
| **Shutdown** | Tắt đột ngột | `lifespan` hạ `is_ready = False` (dòng 39–67) và `signal.signal(signal.SIGTERM, handle_sigterm)` (dòng 180–189) | Cho phép request đang xử lý hoàn tất trước khi tắt container, tránh lỗi 502/cắt ngang người dùng khi deploy. |

---

## Part 2: Docker Containerization

### Exercise 2.1: Trả lời các câu hỏi về `02-docker/develop/Dockerfile`

1. **Base image là gì?** `python:3.11` (dòng 8) — image Debian đầy đủ kèm trình biên dịch và công cụ hệ thống, nên kích thước gốc rất lớn (~1 GB).
2. **Working directory là gì?** `/app` (dòng 11, lệnh `WORKDIR /app`) — mọi lệnh `COPY`, `RUN`, `CMD` sau đó đều chạy tương đối trong `/app`.
3. **Tại sao `COPY 02-docker/develop/requirements.txt .` đứng trước `COPY 02-docker/develop/app.py .`?** Để tận dụng cơ chế **Docker layer cache**. `requirements.txt` ít thay đổi hơn mã nguồn ứng dụng; nếu chỉ sửa `app.py`, Docker tái sử dụng lại layer `pip install` đã cache thay vì tải và cài lại toàn bộ thư viện.
4. **`CMD` vs `ENTRYPOINT` khác nhau thế nào?** `ENTRYPOINT` định nghĩa tiến trình chính cố định của container (khó bị thay thế khi `docker run`), còn `CMD` cung cấp lệnh hoặc tham số mặc định có thể bị ghi đè dễ dàng bằng đối số truyền thêm sau tên image lúc `docker run`.

### Exercise 2.2 & 2.3: Build, chạy container và so sánh kích thước image (Multi-stage build)

**Kết quả test container `my-agent:develop`:**

```http
$ curl -sS -i -X POST "http://localhost:8000/ask?question=What%20is%20Docker?"
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 15:12:46 GMT
server: uvicorn
content-length: 103
content-type: application/json

{"answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}
```

**Phân tích `02-docker/production/Dockerfile`:**
- **Stage 1 (`builder` từ `python:3.11-slim`):** Cài `gcc`, `libpq-dev` và chạy `pip install --no-cache-dir --user -r requirements.txt` để biên dịch toàn bộ dependencies vào `/root/.local`.
- **Stage 2 (`runtime` từ `python:3.11-slim`):** Tạo user non-root `appuser`, chỉ copy `/root/.local` từ stage `builder` sang `/home/appuser/.local` cùng `main.py` và `utils/mock_llm.py`, thiết lập `USER appuser` và `HEALTHCHECK`.
- **Tại sao image nhỏ hơn?** Stage cuối loại bỏ hoàn toàn bản phân phối Debian nặng của `python:3.11`, cũng như trình biên dịch `gcc`, `libpq-dev`, header files và cache cài đặt ở stage `builder`.

**So sánh kích thước image đo thực tế (`docker images` & `docker image inspect`):**

| Image | `docker images` (disk/virtual size) | `docker image inspect .Size` (compressed/content) | Ghi chú |
| --- | ---: | ---: | --- |
| `my-agent:develop` | **1.67 GB** (1,670 MB) | 426,320,322 bytes (**406.6 MB**) | Single-stage `python:3.11` |
| `my-agent:advanced` | **240 MB** | 57,408,961 bytes (**54.7 MB**) | Multi-stage `python:3.11-slim` |
| **Chênh lệch giảm** | **-85.6%** (-1,430 MB) | **-86.5%** (-351.8 MB) | Giảm > 85% dung lượng |

### Exercise 2.4: Docker Compose stack

**Sơ đồ kiến trúc stack (`02-docker/production/docker-compose.yml`):**

```text
Client (:80 / :443)
   │
   ▼
[nginx] (nginx:alpine, reverse proxy + rate limit 10r/s)
   │  mạng internal (bridge)
   ▼
[agent] (my-agent:advanced, FastAPI :8000, depends_on redis & qdrant healthy)
   ├──▶ [redis]  (redis:7-alpine :6379, volume redis_data)
   └──▶ [qdrant] (qdrant/qdrant:v1.9.0 :6333, volume qdrant_data)
```

Các service giao tiếp qua mạng Docker bridge nội bộ `internal` theo tên service (`redis:6379`, `http://qdrant:6333`, `agent:8000`), chỉ duy nhất `nginx` mở cổng `80`/`443` ra host.

**Kết quả test qua Nginx:**

```http
$ curl -sS -i http://localhost/health
HTTP/1.1 200 OK
Server: nginx
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
X-XSS-Protection: 1; mode=block

{"status":"ok","uptime_seconds":1.2,"version":"2.0.0","timestamp":"2026-11-25T15:13:04.352343"}

$ curl -sS -i -X POST http://localhost/ask -H "Content-Type: application/json" -d '{"question":"Explain microservices"}'
HTTP/1.1 200 OK
Server: nginx

{"answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}
```

---

## Part 3: Cloud Deployment

### Exercise 3.1 / 3.2: Deploy Agent Part 6 và so sánh `railway.toml` vs `render.yaml`

- **Public URL đang chạy thực tế trên Railway:** https://k5-l3a-day14-lesongthao-2a202603534-deployment-b-production.up.railway.app (project `protective-energy` / `production`, service `day14-agent` kết nối `Redis` Online, Root Directory `06-lab-complete`; xem chi tiết tại [DEPLOYMENT.md](DEPLOYMENT.md)).
- **Kết quả kiểm thử 4 lệnh CP6 trên Public URL (đã che `AGENT_API_KEY`):**
  - `GET /health` -> **`200 OK`**: `{"status":"ok","environment":"production","uptime_seconds":196.0}`
  - `GET /ready` -> **`200 OK`**: `{"ready":true,"redis":"ok"}`
  - `POST /ask` (không gửi `X-API-Key`) -> **`401 Unauthorized`**: `{"detail":"Invalid or missing X-API-Key"}`
  - `POST /ask` (gửi kèm `X-API-Key: $AGENT_API_KEY`) -> **`200 OK`**: `{"question":"What is Docker?","answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!","user_id":null,"usage":{"input_tokens":3,"output_tokens":18,"cost_usd":1.125e-05}}`
- **Ảnh chụp minh chứng triển khai:** [screenshots/dashboard.png](screenshots/dashboard.png), [screenshots/running.png](screenshots/running.png), [screenshots/test.png](screenshots/test.png).

**So sánh `06-lab-complete/railway.toml` và `06-lab-complete/render.yaml`:**

| Tiêu chí | `railway.toml` | `render.yaml` (Blueprint) |
| --- | --- | --- |
| **Định dạng & phạm vi** | TOML ngắn gọn, cấu hình **một service duy nhất** (build & deploy policy). | YAML (IaC Blueprint), mô tả **toàn bộ stack** gồm Web Service, Redis, region, plan và env vars. |
| **Khai báo biến môi trường & secret** | Không khai báo env vars trong file; biến được đặt qua Railway Dashboard hoặc `railway variables set`. | Khai báo trực tiếp danh sách `envVars` trong file; secret dùng `generateValue: true` (tự sinh) hoặc `sync: false` (nhập trên dashboard). |
| **Build & Health check** | `[build] builder = "DOCKERFILE"`, `[deploy] healthcheckPath = "/health"`, có `restartPolicyType`. | `runtime: docker`, `dockerfilePath: ./Dockerfile`, `healthCheckPath: /health`, có `autoDeploy: true` và `plan: free`. |
| **Vì sao khác nhau?** | Railway thiết kế theo hướng convention-over-configuration cho từng service tách biệt trong project. | Render Blueprint hướng tới Infrastructure-as-Code đồng bộ tự động từ Git repo cho cả service lẫn add-on liên kết. |

### Exercise 3.3: Mô tả pipeline CI/CD Cloud Run (`cloudbuild.yaml` & `service.yaml`)

Pipeline trong `03-cloud-deployment/production-cloud-run/cloudbuild.yaml` chạy tự động qua 4 bước tuần tự (`waitFor`):
1. **`test` (`python:3.11-slim`):** Cài dependencies từ `requirements.txt` cùng `pytest` và chạy toàn bộ unit test `pytest tests/ -v --tb=short` trước khi build.
2. **`build` (`gcr.io/cloud-builders/docker`):** Build Docker image gắn tag theo `$COMMIT_SHA` và `latest`, tận dụng `--cache-from` từ image `latest`.
3. **`push` (`gcr.io/cloud-builders/docker`):** Đẩy cả hai tag image lên Google Container Registry (`gcr.io/$PROJECT_ID/ai-agent`).
4. **`deploy` (`gcr.io/cloud-builders/gcloud`):** Triển khai image theo `$COMMIT_SHA` lên Cloud Run khu vực `asia-southeast1`, cấu hình autoscale (`min-instances=1`, `max-instances=10`, 512Mi RAM, 1 CPU), tiêm biến `ENVIRONMENT=production` và nạp bí mật `OPENAI_API_KEY` từ Secret Manager (khớp định nghĩa Knative Service trong `service.yaml` với `livenessProbe: /health` và `startupProbe: /ready`).

---

## Part 4: API Security

### Exercise 4.1–4.3: Kết quả kiểm thử Authentication & Rate Limiting

**1. Bản develop (`04-api-gateway/develop/app.py`, chạy với `AGENT_API_KEY=secret-key-123`):**

```http
# Thiếu header X-API-Key -> 401
HTTP/1.1 401 Unauthorized
content-type: application/json

{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}

# Sai key -> 403
HTTP/1.1 403 Forbidden
content-type: application/json

{"detail":"Invalid API key."}

# Đúng key -> 200
HTTP/1.1 200 OK
content-type: application/json

{"question":"Hello","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
```

**2. Bản production (`04-api-gateway/production/app.py`, JWT với tài khoản `student` / `demo123`, giới hạn 10 req/phút):**

```http
# Không gửi Authorization Bearer token -> 401
HTTP/1.1 401 Unauthorized
www-authenticate: Bearer
x-content-type-options: nosniff
x-frame-options: DENY

{"detail":"Authentication required. Include: Authorization: Bearer <token>"}

# Lấy token từ POST /auth/token (đã che token)
POST /auth/token -> token_type=bearer, expires_in_minutes=60 (token: <JWT_TOKEN_REDACTED>)

# Request thứ 1 với Authorization: Bearer <JWT_TOKEN_REDACTED> -> 200
HTTP/1.1 200 OK
content-type: application/json

{"question":"Test 1","answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic.","usage":{"requests_remaining":9,"budget_remaining_usd":2.1e-05}}

# ... (Request #2 đến #10 đều trả 200 OK; request #10 có requests_remaining: 0)

# Request thứ 11 trong vòng 60 giây -> 429 Too Many Requests
HTTP/1.1 429 Too Many Requests
x-ratelimit-limit: 10
x-ratelimit-remaining: 0
x-ratelimit-reset: 1795619066
retry-after: 59
content-type: application/json

{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":59}}
```

**Phân tích `04-api-gateway/production/rate_limiter.py`:**
- **Thuật toán sử dụng:** Sliding Window Counter (lưu `deque` chứa timestamp các request gần nhất của từng `user_id`, loại bỏ timestamp cũ hơn `now - window_seconds`).
- **Giới hạn mặc định:** `rate_limiter_user` cho phép **10 requests / 60 giây**; `rate_limiter_admin` cho phép **100 requests / 60 giây**.
- **Cách phân biệt/bypass giới hạn cho admin:** Trong `app.py` (dòng 141), khi `user["role"] == "admin"` (ví dụ tài khoản `teacher`), hệ thống chọn `rate_limiter_admin` thay vì `rate_limiter_user` (hoặc có thể kiểm `if role == "admin":` bỏ qua bước `limiter.check()` nếu cần bypass hoàn toàn).

**Trả lời 3 câu hỏi bổ sung Exercise 4.1 (`04-api-gateway/develop/app.py`):**
1. **Cách kiểm tra API key trong code:** Middleware/dependency `verify_api_key` dùng `APIKeyHeader(name="X-API-Key", auto_error=False)` đọc header `X-API-Key` từ request và đối chiếu với `VALID_API_KEY` nạp từ biến môi trường `AGENT_API_KEY`.
2. **Response khi gửi sai key:** Trả về **`403 Forbidden`** với nội dung `{"detail":"Invalid API key."}` (khác với khi thiếu hoàn toàn header trả **`401 Unauthorized`**).
3. **Cách rotate API key không downtime:** Hỗ trợ danh sách nhiều key hợp lệ trong giai đoạn chuyển tiếp (ví dụ đọc `AGENT_API_KEYS` phân tách dấu phẩy và so sánh constant-time qua `hmac.compare_digest` với từng key còn hiệu lực), cấp key mới cho toàn bộ client cập nhật xong rồi mới gỡ key cũ khỏi cấu hình.

### Exercise 4.4: Cost Guard bằng Redis & Lý do cần cả Rate Limit lẫn Cost Guard

- **Cách triển khai Cost Guard với Redis:**
  - Dùng khóa Redis theo chu kỳ thời gian UTC (`cost:daily:{YYYY-MM-DD}` với TTL 2 ngày và `cost:monthly:{YYYY-MM}` với TTL 32 ngày).
  - Trước khi gọi LLM (`check_budget()`), đọc tổng chi phí hiện tại trong Redis; nếu chạm hoặc vượt `DAILY_BUDGET_USD` / `MONTHLY_BUDGET_USD`, chặn ngay bằng `HTTP 402 Payment Required`.
  - Sau khi gọi LLM xong (`record_cost()`), tính chi phí thực tế từ `input_tokens * PRICE_INPUT_PER_1K / 1000 + output_tokens * PRICE_OUTPUT_PER_1K / 1000` và cộng dồn nguyên tử bằng `INCRBYFLOAT` + `EXPIRE` qua Redis pipeline.
- **Vì sao cần cả Rate Limit lẫn Cost Guard?** Rate limit bảo vệ **tốc độ** và khả năng chịu tải (tránh spam 1.000 req/giây làm nghẽn CPU/worker), nhưng kẻ tấn công vẫn có thể gửi chậm (ví dụ 9 req/phút với câu hỏi cực dài hoặc model đắt tiền) để đốt hết tiền API. Ngược lại, Cost Guard bảo vệ **ngân sách tài chính** theo tổng token/USD tiêu thụ. Hai lớp bổ sung cho nhau để bảo vệ cả hiệu năng lẫn ví tiền.

---

## Part 5: Scaling & Reliability

### Exercise 5.1–5.5: Health checks, Graceful shutdown, Stateless & Load balancing

**1. Phân biệt Liveness (`/health`) và Readiness (`/ready`):**
- **Liveness (`GET /health`):** Trả lời câu hỏi *"Tiến trình agent còn sống hay đang bị treo?"*. Luôn trả `200 OK` miễn process phản hồi được (không phụ thuộc Redis). Nếu `/health` fail, platform sẽ **restart container**.
- **Readiness (`GET /ready`):** Trả lời câu hỏi *"Instance đã sẵn sàng nhận traffic chưa?"*. Kiểm tra kết nối tới các dependency bắt buộc như Redis (`r.ping()`); nếu Redis mất kết nối thì trả `503 Service Unavailable`. Load balancer ngừng gửi traffic mới vào instance đó trong lúc chờ phục hồi mà **không restart oan container**.

**2. Kết quả test Graceful Shutdown (`05-scaling-reliability/develop/app.py`):**
Khi gửi request `POST /ask?question=Long+task` đồng thời phát tín hiệu `kill -TERM $PID`, uvicorn hoàn thành request đang xử lý (`200 OK`) rồi mới chạy nhánh shutdown trong `lifespan`:

```text
INFO:     Shutting down
INFO:     127.0.0.1:34150 - "POST /ask?question=Long+task HTTP/1.1" 200 OK
INFO:     Waiting for application shutdown.
2026-11-25 15:13:15,227 INFO 🔄 Graceful shutdown initiated...
2026-11-25 15:13:15,227 INFO ✅ Shutdown complete
INFO:     Application shutdown complete.
INFO:     Finished server process [4924]
2026-11-25 15:13:15,227 INFO Received signal 15 — uvicorn will handle graceful shutdown
```

Response nhận được: `HTTP/1.1 200 OK` — `{"answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}`.

**3. Thiết kế Stateless & Kết quả chạy `test_stateless.py` với 3 instances:**
- **Vì sao state trong RAM bị hỏng khi scale nhiều instance?** Mỗi container/worker có vùng nhớ RAM riêng biệt. Nếu lưu lịch sử hội thoại hoặc bộ đếm rate limit trong `dict` của Python, request 1 rơi vào Instance A sẽ tạo state ở RAM của A; request 2 được Nginx chuyển sang Instance B sẽ không thấy state đó và làm đứt ngữ cảnh hoặc sai lệch giới hạn.
- **Kết quả chạy `docker compose -p k5-day14-scaling up -d --build --scale agent=3` và `python test_stateless.py`:**

```text
Session ID: 91beb633-e781-4aed-8ae8-b34a81a3a94c

Request 1: [instance-b0ba55] -> What is Docker?
Request 2: [instance-882ec8] -> Why do we need containers?
Request 3: [instance-de886c] -> What is Kubernetes?
Request 4: [instance-b0ba55] -> How does load balancing work?
Request 5: [instance-882ec8] -> What is Redis used for?

Total requests: 5
Instances used: {'instance-de886c', 'instance-b0ba55', 'instance-882ec8'}
✅ All requests served despite different instances!

--- Conversation History ---
Total messages: 10
✅ Session history preserved across all instances via Redis!
```

Nginx điều phối round-robin qua cả 3 instance (`instance-b0ba55`, `instance-882ec8`, `instance-de886c`), nhưng toàn bộ 10 tin nhắn (5 lượt hỏi/đáp) vẫn được truy xuất nguyên vẹn từ Redis qua `GET /chat/{session_id}/history`.

---

## Part 6: Final Project (`06-lab-complete/`)

Kết quả chạy `python check_production_ready.py` trên môi trường Linux có Docker Engine & Redis (image `63 MB`, `docker stop` thoát `exit code 0` trong `0.6s`):

```text
================================================================
  📋 Checklist Deliverable
     ✅ Dockerfile (multi-stage, < 500 MB)
     ✅ docker-compose.yml (agent + redis)
     ✅ .dockerignore
     ✅ Health check endpoint (GET /health)
     ✅ Readiness endpoint (GET /ready)
     ✅ API Key authentication
     ✅ Rate limiting
     ✅ Cost guard
     ✅ Config từ environment variables
     ✅ Structured logging
     ✅ Graceful shutdown
     ✅ Public URL ready (Railway / Render config)
----------------------------------------------------------------
  Result: 12/12 tiêu chí đạt · 43/43 checks passed
  🎉 PASS 12/12 — PRODUCTION READY! Deploy nào!
================================================================
```

---

## AI Log

1. **Part 6 (`06-lab-complete/`):** Trao đổi với trợ lý AI về cách thiết kế rate limiter sliding window nguyên tử bằng Lua script trên Redis để tránh race condition giữa 2 uvicorn worker, và cách cấu hình multi-stage Dockerfile (`/opt/venv`, user non-root `appuser`, `exec uvicorn` giữ PID 1 cho SIGTERM). Đã tự kiểm tra toàn bộ bằng `python check_production_ready.py` đạt `PASS 12/12` (43/43 checks passed, image 63 MB, `docker stop` 0.6s).
2. **Part 1–5 & Part 7 (`BENCHMARK_REPORT.md`):** Dùng AI hỗ trợ viết script tự động hoá chạy thu thập số liệu thực tế từ `load_test.py`, `eval/run_eval.py`, Docker Compose stack và trích xuất dữ liệu Prometheus/Jaeger/Locust CSV. Mọi số liệu trong `MISSION_ANSWERS.md` và `BENCHMARK_REPORT.md` đều được đối chiếu trực tiếp với file JSON/CSV và log thực thi thật.
