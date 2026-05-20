# Docker launch

1. Create `.env` from example:

```powershell
Copy-Item .env.example .env
```

2. Fill required keys in `.env`:

```env
OPENAI_API_KEY=...
EMBEDDING_API_KEY=...
GOOGLE_SHEETS_TEXT_DB_WEBHOOK_URL=...
```

3. Start Dgraph and backend:

```powershell
docker compose up --build
```

4. Open API:

```text
http://127.0.0.1:8099/docs
```

5. Browser extension is installed separately:

```text
chrome://extensions -> Developer mode -> Load unpacked -> browser_extension
```

The backend container uses Dgraph through `dgraph-alpha:9080`. Local data is mounted:

- `raw/` -> parsed text files
- `storage/` -> RAGU runtime cache/storage
- `dhb/data/` -> local dashboard/chat logs
- `xdt/rpo/` -> package/docs registries

Google Sheet mirror is automatic after parsing. The MGR button was removed; the service endpoint
`POST /dhb/export-text-db` is kept only for one-time manual resync of existing raw files.
