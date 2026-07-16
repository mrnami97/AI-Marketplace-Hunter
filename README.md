# AI Marketplace Hunter v0.5.0 — PIKKAPI DeepSeek

Uses PIKKAPI's documented OpenAI-compatible Responses API.

```env
AI_ENABLED=true
PIKKAPI_API_KEY=your_token_from_token_management
PIKKAPI_BASE_URL=https://pikkapi.cooltechgp.online/v1
PIKKAPI_MODEL=deepseek-v4-flash
PIKKAPI_TIMEOUT_SECONDS=45
AI_MAX_LISTINGS_PER_SEARCH=5
AI_CONCURRENCY=2
```

Install and run:

```powershell
py -m pip install -U -r requirements.txt
py app.py
```

Telegram tests:

```text
/aistatus
/analyze RTX 3070 under RM1200
/search iPhone 15 Pro under RM3000 cheapest
```

The bot locally filters first, sends only the best shortlist to PIKKAPI, validates structured JSON with Pydantic, and caches unchanged results in SQLite.
