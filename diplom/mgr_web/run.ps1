$env:RAG_API_URL = $env:RAG_API_URL -replace "^$", "http://127.0.0.1:8099"
uvicorn mgr_web.app:app --host 127.0.0.1 --port 8100
