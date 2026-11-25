# Deployment Information

## Public URL
https://k5-l3a-day14-lesongthao-2a202603534-deployment-b-production.up.railway.app

## Platform
Railway (`protective-energy` / `production` — service `day14-agent` kết nối `Redis`)

## Test Commands & Observed Results

```bash
export BASE="https://k5-l3a-day14-lesongthao-2a202603534-deployment-b-production.up.railway.app"
```

### Health Check
```bash
curl -sS -w '\nHTTP_CODE:%{http_code}\n' "$BASE/health"
# {"status":"ok","environment":"production","uptime_seconds":196.0}
# HTTP_CODE:200

curl -sS -w '\nHTTP_CODE:%{http_code}\n' "$BASE/ready"
# {"ready":true,"redis":"ok"}
# HTTP_CODE:200
```

### API Test (with authentication)
```bash
curl -sS -w '\nHTTP_CODE:%{http_code}\n' -X POST "$BASE/ask" \
  -H 'Content-Type: application/json' \
  -d '{"question":"What is Docker?"}'
# {"detail":"Invalid or missing X-API-Key"}
# HTTP_CODE:401

curl -sS -w '\nHTTP_CODE:%{http_code}\n' -X POST "$BASE/ask" \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: $AGENT_API_KEY" \
  -d '{"question":"What is Docker?"}'
# {"question":"What is Docker?","answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!","user_id":null,"usage":{"input_tokens":3,"output_tokens":18,"cost_usd":1.125e-05}}
# HTTP_CODE:200
```

## Environment Variables Set
- `PORT` (do nền tảng cấp tự động)
- `ENVIRONMENT=production`
- `REDIS_URL` (trỏ tới dịch vụ Redis trên nền tảng)
- `AGENT_API_KEY` (khai báo bí mật trên dashboard nền tảng, không lưu trong Git)
- `LOG_LEVEL=INFO`
- `RATE_LIMIT_PER_MINUTE=10`
- `DAILY_BUDGET_USD=1.0`
- `MONTHLY_BUDGET_USD=10.0`

## Screenshots
- [Deployment dashboard](screenshots/dashboard.png)
- [Service running](screenshots/running.png)
- [Test results](screenshots/test.png)
