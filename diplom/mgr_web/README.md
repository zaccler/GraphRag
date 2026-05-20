# GraphRAG Manager Web

Локальный web-кабинет вместо Telegram/VK бота.

Что умеет:
- регистрация и вход;
- первый пользователь автоматически становится админом;
- чат с основным GraphRAG API;
- админские команды: статус, парсинг пакетов, парсинг docs registry, sync Google Sheet dashboard, rebuild.

Запуск:

```powershell
uvicorn mgr_web.app:app --host 127.0.0.1 --port 8100
```

Основной сервер GraphRAG должен быть запущен отдельно на `http://127.0.0.1:8099`.
Если адрес другой:

```powershell
$env:RAG_API_URL="http://127.0.0.1:8099"
uvicorn mgr_web.app:app --host 127.0.0.1 --port 8100
```

Открыть:

```text
http://127.0.0.1:8100
```

Данные пользователей лежат в `mgr_web/data/users.json`.
