# Docker launch
-
## First run

1. Open the project folder:

```powershell
cd "C:\Users\Vlad\OneDrive\Desktop\практика производственная\code\GraphRag\diplom"
```

2. Create `.env` only if it does not exist yet:

```powershell
Copy-Item .env.example .env
```

3. Fill required values in `.env`:

```env
OPENAI_API_KEY=...
EMBEDDING_API_KEY=...
GOOGLE_SHEETS_LOG_WEBHOOK_URL=...
GOOGLE_SHEETS_LOG_READ_URL=... # usually the same Apps Script URL if doGet is implemented
GOOGLE_SHEETS_TEXT_DB_WEBHOOK_URL=...
```

For Gmail SMTP use an app password, not the normal account password:

```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your@gmail.com
SMTP_PASSWORD=16_symbol_app_password_without_spaces
SMTP_FROM=your@gmail.com
SMTP_USE_TLS=true
```

4. Start Dgraph and backend:

```powershell
docker compose up --build
```

5. Open API:

```text
http://127.0.0.1:8099/docs
```

6. Install the browser extension separately:

```text
chrome://extensions -> Developer mode -> Load unpacked -> browser_extension
```

The extension API endpoint should stay `http://127.0.0.1:8099`.

## Restart after `.env` changes

Docker reads `.env` when the container is created. After changing keys or SMTP settings, recreate the API container:

```powershell
docker compose up -d --force-recreate api
```

## Local data

The backend container uses Dgraph through `dgraph-alpha:9080`. Local data is mounted:

- `raw/` -> parsed text files
- `storage/` -> RAGU runtime cache/storage
- `dhb/data/` -> local dashboard/chat logs
- `xdt/rpo/` -> package/docs registries

Google Sheet text DB mirror is automatic after parsing. The endpoint `POST /dhb/export-text-db` is kept only for one-time manual resync of existing raw files.