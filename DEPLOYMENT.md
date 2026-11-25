# Deployment Information

## Public URL
*(Đang cập nhật sau khi hoàn tất cấu hình dịch vụ Cloud trên Render/Railway)*

## Platform
Render / Railway

## Test Commands

### Health Check
```bash
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"
# Expected: 200

curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"
# Expected: 200
```

### API Test (with authentication)
```bash
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H 'Content-Type: application/json' \
  -d '{"question":"Hello"}'
# Expected: 401

curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: $AGENT_API_KEY" \
  -d '{"question":"Hello"}'
# Expected: 200
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
