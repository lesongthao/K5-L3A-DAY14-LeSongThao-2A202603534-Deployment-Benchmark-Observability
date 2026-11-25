# Benchmark & Observability Report — Day 14

**Họ tên:** Lê Sông Thao (2A202603534)  
**Ngày chạy:** 2026-11-25  
**Môi trường:** Local Windows 11 + Python 3.12.10 (Part 7 Bước 1 `develop/`); Ubuntu Linux `ubuntu-latest` + Docker 29.4.2 + Docker Compose (Part 7 Bước 2 `production/`).

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | `< 500 ms` | Latency cơ bản mock LLM ~120ms + jitter 60ms + retrieval ~20ms (tổng ~200ms); ngưỡng 500ms đảm bảo 95% người dùng nhận phản hồi dưới nửa giây và chịu được dao động nhẹ mà không báo động giả. |
| Error rate `/ask` | `< 2.0 %` | Tỉ lệ lỗi upstream mặc định của mock LLM là 1% (`MOCK_ERROR_RATE=0.01`); đặt SLO 2.0% cho phép sai số mẫu ngẫu nhiên khi tải nhỏ, đồng thời bắt được sự cố ngay khi tỉ lệ lỗi vượt ngưỡng bình thường. |
| Accuracy trên golden dataset | `≥ 85 %` | Đảm bảo agent v2 giữ chất lượng trả lời đúng trọng tâm trên toàn bộ 23 câu hỏi cốt lõi trước khi cho phép merge/deploy; đạt 100% (23/23) sau khi bổ sung knowledge base. |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2)

Mỗi mức chạy 300 request tới `http://127.0.0.1:8002` với cấu hình mặc định (`MOCK_SLOW_RATE=0.03`, `MOCK_ERROR_RATE=0.01`), lưu trong `reports/load_v2_c{1,10,50,100}.json`:

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|
| 1 | 4.1 | 199.9 | 246.6 | 1693.9 | 1.67% | PASS |
| 10 | 37.48 | 197.0 | 233.6 | 1704.1 | 2.33% | FAIL (Error rate) |
| 50 | 107.97 | 201.0 | 258.6 | 1705.2 | 1.00% | PASS |
| 100 | 55.83 | 347.0 | 3343.7 | 3705.3 | 1.00% | FAIL (p95) |

**Nhận xét:** RPS **không tăng tuyến tính** theo concurrency. Từ `c=1` lên `c=10` và `c=50`, RPS tăng gần tuyến tính (`4.1 → 37.48 → 107.97 req/s`) nhờ mock LLM chạy bất đồng bộ (`asyncio.sleep`) nên một tiến trình uvicorn xử lý song song nhiều I/O wait rất tốt, giữ `p95` ổn định quanh `233–259 ms`. Tuy nhiên khi tăng lên `c=100`, **saturation (bão hòa)** xảy ra trên 1 tiến trình FastAPI/uvicorn đơn lẻ (tranh chấp event loop, lập lịch socket và kết nối đồng thời trên Windows): RPS tụt xuống còn `55.83 req/s`, `p50` tăng lên `347.0 ms` và `p95` vọt lên `3343.7 ms` (vượt xa SLO 500ms). Tại `c=10`, error rate ngẫu nhiên đạt `2.33%` (7/300 lỗi 503) nên cũng vi phạm SLO `≤ 2.0%`.

### 2.2 Tail latency

Chạy 300 request với `--concurrency 20` trên agent v2, thay đổi `MOCK_SLOW_RATE`, lưu trong `reports/load_v2_slow_{0,0.03,0.1}.json`:

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| 0 | 191.7 | 227.0 | 245.4 |
| 0.03 (mặc định) | 226.7 | 234.5 | 1693.4 |
| 0.1 | 357.4 | 1693.8 | 1725.6 |

**Nhận xét:** **`p99` và `p95` nhạy nhất** với request chậm (tail latency). Ở mức `MOCK_SLOW_RATE=0.03` (3% request bị chậm), `avg` chỉ nhích nhẹ từ `191.7 ms` lên `226.7 ms` (+35ms) và `p95` hầu như không đổi (`234.5 ms`), nhưng **`p99` nhảy vọt gần 7 lần lên `1693.4 ms`**. Khi `MOCK_SLOW_RATE=0.1` (>5% request chậm), `avg` vẫn ở mức `357.4 ms` (trông vẫn dưới ngưỡng 500ms), nhưng **`p95` đã bùng nổ lên `1693.8 ms`** (gấp >7 lần mức chuẩn). Vì giá trị trung bình bị 90–97% request nhanh kéo xuống nên che giấu hoàn toàn trải nghiệm tệ hại của nhóm người dùng gặp đuôi chậm; do đó **SLO phải đặt theo percentile (`p95`/`p99`)**, không đặt theo `average`.

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

Chạy trên `golden_dataset.jsonl` (23 câu hỏi) với `MOCK_ERROR_RATE=0`, lưu tại `reports/eval_v1.json`, `reports/eval_v2.json` và `reports/eval_v2_fixed.json`:

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4.3% (1/23) | 91.3% (21/23) | 100.0% (23/23) |
| Avg tokens / câu | 57.6 | 109.0 | 113.8 |
| Tổng cost (USD) | $0.000411 | $0.000760 | $0.000792 |
| Cost / câu đúng (USD) | $0.00041055 | $0.00003619 | $0.00003443 |
| Quality gate | FAIL | PASS | PASS |

**Những câu v2 trả lời sai ban đầu và cách sửa:**

| ID | Keyword bị thiếu | Đã sửa gì |
|---|---|---|
| `security-02` | `token`, `hết hạn`, `chữ ký` | Bổ sung entry `(["jwt"], ...)` vào `KNOWLEDGE_BASE` trong `utils/mock_llm.py` giải thích JWT là token có chữ ký số, chứa thông tin user và thời điểm hết hạn. |
| `scaling-03` | `cpu`, `memory`, `custom metrics` | Bổ sung entry `(["hpa", "kubernetes", "autoscal"], ...)` vào `KNOWLEDGE_BASE` trong `utils/mock_llm.py` mô tả Kubernetes HPA scale dựa trên CPU, memory hoặc custom metrics. |

*(Đã đồng bộ cả `develop/utils/mock_llm.py` và `production/utils/mock_llm.py`, giữ nguyên `golden_dataset.jsonl`. Lần chạy `eval_v2_fixed.json` với `--min-accuracy 1.0 --baseline reports/eval_v2.json` đạt **23/23 (100.0%)**, cải thiện 2 câu, **0 câu bị regression**, `Quality gate ✅ PASS`.)*

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:**
- Agent v2 thêm bước retrieval (RAG) đưa tài liệu vào prompt nên **tốn ~2× số token** (`109.0–113.8` so với `57.6` tokens/câu) và tăng latency khoảng ~20–35ms (`p50`: `214.6ms`/`198.8ms` so với `165.7ms` của v1).
- Tuy tổng chi phí mỗi lượt chạy tăng gần gấp đôi (`$0.000792` so với `$0.000411`), **chi phí trên mỗi câu trả lời đúng (`cost / câu đúng`) của v2 sau sửa KB chỉ là `$0.00003443` — rẻ hơn ~11.9 lần** so với v1 (`$0.00041055`). Điều này chứng minh đầu tư RAG/context tăng độ chính xác mang lại hiệu quả kinh tế thực chất hơn hẳn việc trả lời rẻ nhưng sai.
- **CI Quality Gate (`.github/workflows/eval.yml`):** Khi chạy thử regression gate `eval/run_eval.py --url http://127.0.0.1:8001 --baseline reports/eval_v2.json`, script phát hiện accuracy tụt từ 91.3% xuống 4.3% với 20 câu regression và **trả về `exit code = 1`**. Trong workflow `.github/workflows/eval.yml`, bước kiểm tra chạy `python eval/run_eval.py --url http://localhost:8000 --min-accuracy 0.85` trên sự kiện `pull_request`; nếu độ chính xác < 85% hoặc có regression so với baseline, exit code khác 0 làm job CI fail và chặn merge PR.

---

## 4. Observability stack (production)

### 4.1 Screenshot & Quan sát Grafana (Exercise 7.4)

- [x] Dashboard Grafana khi đang có tải: [grafana-dashboard.png](screenshots/grafana-dashboard.png)
- [x] Một trace chậm trong Jaeger: [jaeger-slow-trace.png](screenshots/jaeger-slow-trace.png)
- [x] Một trace lỗi trong Jaeger: [jaeger-error-trace.png](screenshots/jaeger-error-trace.png)
- [x] Trang Alerts của Prometheus khi có ≥ 2 alert đang **firing**: [prometheus-alert-firing.png](screenshots/prometheus-alert-firing.png)

**Trả lời câu hỏi Exercise 7.4 (từ ảnh Grafana và query Prometheus tại thời điểm 30 Locust users trên 2 instances):**
1. **p95 và avg đang là bao nhiêu? Khoảng cách nói lên điều gì?** Tại thời điểm chụp dashboard, **`p95 = 291.09 ms`** (snapshot PromQL: `0.2914 s`), **`avg = 224.75 ms`**, `Traffic = 19.0 req/s`, `Error rate = 0.67%`, `Saturation = 7` in-flight, `Instances = 2`. Khoảng cách giữa `avg` (~225ms) và `p95` (~291ms) nhỏ (chỉ ~66ms) cho thấy phần lớn request ổn định, trong khi đường **`p99` trên biểu đồ vọt lên ~1.8s** phản ánh nhóm ~3% request dính tail latency (`MOCK_SLOW_RATE=0.03`) mà `avg` và `p95` không làm lộ hết.
2. **Panel "Requests/s theo instance": Nginx có chia đều traffic cho 2 instance không?** **Có.** Biểu đồ Grafana và PromQL `sum by (instance) (rate(http_requests_total{route="/ask"}[1m]))` cho thấy tải chia gần như 50/50 giữa `172.18.0.5:8000` (`9.44 req/s`) và `172.18.0.8:8000` (`9.65 req/s`), các đường đồ thị bám sát nhau và header `X-Served-By` luân phiên giữa hai IP nội bộ.
3. **Vì sao input tokens/s lớn hơn output tokens/s?** PromQL ghi nhận **`input = 1473.3 tokens/s`** so với **`output = 773.8 tokens/s`** (gần gấp đôi). Nguyên nhân là mỗi prompt đầu vào của agent v2 chứa `SYSTEM_PROMPT` + đoạn tài liệu truy xuất từ `KNOWLEDGE_BASE` + câu hỏi người dùng (~81–95 input tokens), dài hơn câu trả lời ngắn gọn ở đầu ra (~46–55 output tokens).
4. **`curl http://localhost:8080/metrics` trả về gì? Vì sao?** Trả về **`HTTP/1.1 404 Not Found`** từ Nginx (`nginx/1.28.3`). Trong `nginx.conf` (dòng 22–24), block `location = /metrics { return 404; }` chủ động chặn truy cập `/metrics` từ bên ngoài để tránh lộ thông tin nội bộ hệ thống (route, lưu lượng, chi phí, số instance), chỉ cho phép Prometheus scrape trực tiếp trong mạng Docker nội bộ `obs_net`.

### 4.2 Thí nghiệm "phá hệ thống"

Trước khi chạy thí nghiệm, đã chạy unit test rule bằng `promtool test rules /p/alert_rules_test.yml` và đạt **`SUCCESS`**.  
*(Ghi chú: trong quá trình chạy tải 100 users trước đó rồi tiếp nối ngay 30 users, tổng chi phí tích lũy theo cửa sổ `[5m]` đã vượt ngưỡng $2/giờ nên `LLMCostBurnRateHigh` cũng ở trạng thái `FIRING` song song cùng `AgentHighErrorRate` và `AgentHighLatencyP95` trên ảnh [prometheus-alert-firing.png](screenshots/prometheus-alert-firing.png).)*

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` (chạy cùng B) | `AgentHighErrorRate` | **86.1 giây** (scrape + `rate[1m]` > 5% + `for: 1m`) | Golden Signals **Error rate** (đỏ), **Requests/s theo status code** (`503`), **LLM calls theo kết quả** (`error`) |
| B | `MOCK_SLOW_RATE=0.3` (chạy cùng A) | `AgentHighLatencyP95` | **146.1 giây** (`p95 > 1s` + `for: 2m`) | Golden Signals **Latency p95** (đỏ), **Latency /ask — p50/p95/p99** (p95 nhảy lên >1.5s) |
| C | `LLM_MODEL=mock-llm-large` | `LLMCostBurnRateHigh` | **2.4 giây** (burn rate đo được **$2.82/giờ** > $2/giờ, duy trì firing liên tục) | **Cost burn rate (USD/giờ)**, **LLM latency p95 theo model**, bảng **Phiên bản đang chạy** |
| D | `docker pause` 1 instance agent (`64b1130fb3b6`) | `AgentInstanceDown` | **40.0 giây** (`up == 0` + `for: 30s`) | Golden Signals **Instances** (giảm 2 → 1), **Requests/s theo instance** |
| E | `AGENT_VERSION=v1` | **Không có alert nào firing** (sau 75s: 0 alert) | Không firing | **Retrieval hit ratio (agent v2)** mất tín hiệu, **Tokens/s** giảm mạnh, bảng **Phiên bản đang chạy** đổi sang `v1` |

**Thí nghiệm E không làm alert nào firing. Phát hiện loại sự cố này trong production bằng cách nào?**
Alert hạ tầng chỉ đo HTTP 5xx, latency và mức tiêu thụ tài nguyên — agent v1 vẫn trả `200 OK` nhanh hơn và tốn ít tiền hơn dù độ chính xác tụt từ 100% xuống 4.3%. Để phát hiện lỗi suy giảm chất lượng trên production cần kết hợp:
1. **CI Quality Gate tự động trước deploy:** Chạy `eval/run_eval.py` trên golden dataset và chặn merge/release nếu accuracy giảm hoặc có regression.
2. **Online / Shadow Eval & Drift Monitoring:** Đánh giá định kỳ mẫu traffic thật bằng LLM-as-a-judge, theo dõi **Retrieval Hit Ratio** (`agent_retrieval_total`) và phản hồi người dùng (thumbs down / tỷ lệ hỏi lại), tạo alert khi retrieval hit ratio tụt đột ngột hoặc điểm eval online giảm.

**Vì sao trong thí nghiệm D (`docker pause`), lỗi 504 ở Nginx không hiện trên metric của agent?**
Container bị pause ngừng xử lý mọi socket nên request treo tại Nginx cho tới khi vượt `proxy_read_timeout 10s`; Nginx tự ngắt kết nối và trả `504 Gateway Timeout` cho client. Hàm xử lý và middleware bên trong agent chưa bao giờ hoàn tất request đó để chạy vào khối `finally` tăng `http_requests_total{status="504"}`. Metric của dịch vụ chỉ thấy những gì bản thân dịch vụ xử lý được, nên production bắt buộc phải giám sát thêm metric ở tầng **load balancer / Nginx** và **synthetic probe (blackbox monitoring)** từ bên ngoài.

### 4.3 Debug bằng trace

Trace chậm nhất tìm được qua log JSON và Jaeger v2 API (`/api/v3/traces/b4dcd2f8c8d9ddfadeab8b4c8acca57f`):

- `trace_id`: `b4dcd2f8c8d9ddfadeab8b4c8acca57f`
- Tổng thời gian (`POST /ask`): **1721.77 ms** (`agent.run`: `1720.29 ms`, `agent.retrieve_context`: `23.26 ms`)
- Span chiếm nhiều thời gian nhất: **`chat mock-llm-small`** (**1696.89 ms**, chiếm **98.6%** tổng thời gian trace; `gen_ai.usage.input_tokens=95`, `gen_ai.usage.output_tokens=55`, `llm.cost_usd=4.725e-05`)
- Dòng log JSON tương ứng (lọc theo `trace_id` từ `docker compose logs agent`):

```json
{"ts": "2026-11-25T15:41:46.280314+00:00", "level": "INFO", "service": "observable-agent", "instance": "591575d73c44", "event": "llm_call", "trace_id": "b4dcd2f8c8d9ddfadeab8b4c8acca57f", "span_id": "8cea5f463d5faa6d", "request_id": "a9132660c401", "model": "mock-llm-small", "agent_version": "v2", "input_tokens": 95, "output_tokens": 55, "cost_usd": 4.7e-05, "llm_ms": 1696.6}
```

*(Trace lỗi tham khảo trên [jaeger-error-trace.png](screenshots/jaeger-error-trace.png): `trace_id=2ae0321b7804bb079b09e757c98a4c85`, HTTP 503, tổng `102.29 ms`, span `chat mock-llm-small` `77.58 ms` ghi nhận event `exception` với `LLMError: Upstream LLM error: 503 Service Unavailable (mock)` khớp dòng log `llm_error` có cùng `trace_id`.)*

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

Số liệu trích xuất trực tiếp từ `benchmark-results/scale_1_stats.csv` và `benchmark-results/scale_3_stats.csv` (dòng `POST /ask`):

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | 59.62 (`Aggregated`: 65.79) | 190 | 230 | 1700 | 71 / 7101 (1.00%) |
| 3 | 60.42 (`Aggregated`: 66.57) | 190 | 230 | 1700 | 73 / 7195 (1.01%) |

**Giải thích kết quả:**
Khi tăng từ 1 lên 3 instance với kịch bản 100 Locust user (`wait_time = between(0.5, 2)` giây giữa các lần gửi), RPS chỉ tăng nhẹ từ `59.62` lên `60.42 req/s` và **`p50` (190ms), `p95` (230ms), `p99` (1700ms) hầu như giữ nguyên**. Nguyên nhân gồm hai yếu tố:
1. **Nút thắt nằm ở tầng LLM upstream (I/O latency), không nằm ở CPU của agent:** Thời gian xử lý của agent chủ yếu nằm ở `chat mock-llm-small` (~150–200ms bình thường và +1500ms với 3% request slow), nên dù có thêm container agent, mỗi request vẫn phải chờ LLM API từng ấy thời gian.
2. **Tải sinh ra từ 100 user có `wait_time` (0.5–2s) chưa làm bão hòa 1 instance async:** Mỗi user gửi trung bình ~0.67 req/s (`1 / (1.25s + 0.24s)`), nên 100 user chỉ tạo ra tổng ~60–67 req/s — mức mà 1 container FastAPI bất đồng bộ đã xử lý dư sức (chỉ khác nếu tăng tải lên hàng nghìn RPS hoặc tác vụ CPU-bound nặng thì scale 3 instance mới phát huy rõ tác dụng giảm queue latency). Tỉ lệ failure ~1.0% ở cả hai lần chạy đến từ `MOCK_ERROR_RATE=0.01` của upstream LLM nên scale instance không làm giảm lỗi upstream.

---

## 6. Kết luận

- **3 điều cốt lõi về benchmark & observability:**
  1. **Luôn đo tail latency (`p95`/`p99`) thay vì trung bình:** Chỉ 3–10% request chậm đủ để khiến người dùng trải nghiệm độ trễ gần 2 giây trong khi `average` vẫn hiển thị bình thường.
  2. **Kết hợp đủ cả Benchmark Hiệu năng, Benchmark Chất lượng (Eval) và 3 trụ cột Observability:** Metrics cho biết *hệ thống có đang gặp sự cố không*, Traces chỉ ra *span nào gây chậm/lỗi*, Logs JSON gắn `trace_id` cung cấp chi tiết ngữ cảnh, còn Eval + CI Quality Gate bắt được lỗi suy giảm chất lượng mà metric hạ tầng không thấy được.
  3. **Mọi chỉ số và alert cần gắn với hành vi thực của hệ thống:** Scale container không giải quyết được độ trễ từ LLM API ngoài, và monitoring ở service đơn lẻ không thấy lỗi timeout tại Load Balancer (`504`).

- **Nếu đưa agent này lên production thật, các metric / alert cần bổ sung:**
  1. **Metric & Alert tại tầng Load Balancer / Ingress:** Theo dõi `nginx_http_requests_total{status=~"502|504"}` để phát hiện lỗi kết nối/timeout mà agent không tự ghi nhận được.
  2. **Quality & Drift Metrics:** Theo dõi `agent_retrieval_total{result="miss"}` (cảnh báo khi miss ratio vượt ngưỡng) và điểm chấm LLM-as-judge trên mẫu traffic thật để bắt sớm sự cố giảm chất lượng như thí nghiệm E.
  3. **Saturation & Dependency Health:** Theo dõi Redis command latency / connection pool saturation và alert khi tỉ lệ `HTTP 429` (rate limit) hoặc `HTTP 402` (budget exhausted) tăng bất thường.
