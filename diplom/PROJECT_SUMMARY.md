# Project Summary

Краткая память по проекту `diplom`.

## Что делает проект

Проект реализует систему интеллектуального поиска по базе знаний:

1. Пользователь открывает Chrome/Edge extension.
2. Пользователь входит по email-коду.
3. Пользователь задает вопрос в чате.
4. Backend FastAPI ищет контекст через RAGU/GraphRAG.
5. Данные GraphRAG берутся из Dgraph.
6. LLM формирует ответ строго по найденному контексту.
7. Расширение показывает ответ и делает ссылки кликабельными.
8. История вопросов хранится в браузере отдельно по email.
9. Вопрос/ответ логируются локально и могут отправляться в Google Sheets.

Админ входит по постоянному коду и через вкладку MGR может запускать парсинг, rebuild, status и debug ask.

## Основные файлы

- `server.py` - основной FastAPI backend.
- `api/config.py` - чтение `.env` и основные настройки backend.
- `api/models.py` - Pydantic-модели запросов и ответов API.
- `browser_extension/` - основное расширение браузера.
- `browser_extension/popup.html` - UI расширения.
- `browser_extension/popup.js` - логика чата, email-входа, MGR, истории.
- `browser_extension/styles.css` - оформление popup.
- `browser_extension/access_codes.json` - постоянный admin-code.
- `knb/dgraph_adapter.py` - graph storage RAGU для Dgraph.
- `knb/dgraph_unified_storage.py` - KV/vector runtime storage RAGU в Dgraph.
- `knb/ragu_runtime.py` - сборка RAGU runtime, миграция local runtime storage в Dgraph, transactional rebuild.
- `knb/package_downloads.py` - точный поиск прямых ссылок на скачивание пакетов в Dgraph chunks.
- `lms/answer_service.py` - формирование grounded-ответа через LLM по найденному контексту.
- `mgr/auth_service.py` - email-коды входа пользователя.
- `xdt/scp/parser.py` - парсинг docs, URL, packages.
- `xdt/scp/web_docs.py` - парсинг HTML/docs-страниц и обход документации.
- `xdt/rpo/packages.txt` - список package-источников.
- `xdt/rpo/docs_registry.json` - registry документации.
- `xdt/pul/resource_pool.py` - retries/timeouts/headers/tokens/proxy для HTTP источников.
- `dhb/dashboard.py` - Google Sheet как dashboard/registry source.
- `dhb/chat_logs.py` - локальные и Google Sheet-логи чата.
- `dhb/text_db_mirror.py` - выгрузка raw-текстов базы знаний в Google Sheet-витрину.
- `dhb/chat_log_apps_script.js` - Apps Script webhook для записи chat logs в Google Sheets.
- `dhb/text_db_apps_script.js` - Apps Script webhook для Google Sheet-витрины базы знаний.
- `dhb/data/chat_logs.jsonl` - локальный лог email/question/answer.
- `docker-compose.yml` - Dgraph zero/alpha/ratel.
- `scripts/reset_dgraph.py` - сброс Dgraph.
- `scripts/build_diploma_note.py` - генерация расширенной дипломной записки.
- `tododb/` - исходный прототип/референс по схеме, не основной runtime.
- `RAGU/` - библиотека/папка, НЕ редактировать.

## Backend endpoints

- `GET /health` - проверка живости сервера.
- `GET /status` - текущий статус обработки.
- `GET /debug/error` - последняя ошибка.
- `POST /ask` - обычный вопрос.
- `POST /ask_debug` - вопрос + retrieved context.
- `POST /rebuild` - rebuild базы знаний из `raw/lit`.
- `POST /parse/url` - спарсить одну страницу по URL.
- `POST /parse/packages` - спарсить package list.
- `POST /parse/docs-registry` - спарсить docs registry.
- `POST /parse/python-docs` - обход Python docs.
- `POST /dhb/sync-google-sheet` - прочитать Google Sheet как registry.
- `POST /dhb/export-text-db` - выгрузить raw/lit как человекочитаемую Google Sheet-витрину базы знаний.
- `POST /dhb/log-chat` - записать email/question/answer локально и в Google Sheets webhook.
- `POST /auth/request-code` - отправить одноразовый email-код.
- `POST /auth/verify-code` - проверить email-код.

## Хранилище

Основное итоговое хранилище - Dgraph.

В Dgraph хранятся:

- RAGU entities;
- RAGU relations;
- chunks;
- community summaries;
- KV runtime data;
- vector rows.

Локальные `storage/llm_cache` и `storage/embed_cache` - это кеши запросов к LLM/embeddings, не основная база знаний.

## Парсинг данных

Поддерживается:

- одиночная HTML-страница по URL;
- docs registry;
- Google Sheet как registry source;
- NuGet;
- PyPI;
- npm;
- Maven;
- crates.io;
- Docker Hub;
- Go modules;
- GitHub releases.

Для package-запросов добавлен deterministic fallback: если пользователь просит ссылку на конкретный пакет/версию, backend ищет точный package/version/download URL в Dgraph chunks и возвращает прямую ссылку, если она есть.

## Extension

Основной UI сейчас - `browser_extension`.

Режимы:

- user: вход по email-коду, чат, история по email;
- admin: постоянный код из `access_codes.json`, чат + MGR.

MGR умеет:

- status;
- rebuild KB;
- ask debug;
- parse packages/docs registry из файла с limit/force;
- parse single URL;
- export text DB mirror to Google Sheet;
- вывод результата в text/json.

Сессия хранится в `chrome.storage.session`, история - в `chrome.storage.local`.
После закрытия popup состояние ввода email-кода сохраняется, после закрытия браузера сессия сбрасывается.

## Google Sheets

Есть три сценария:

1. `dhb/sync-google-sheet` - читать Google Sheet как dashboard/registry и генерировать:
   - `dhb/data/packages.from_sheet.txt`;
   - `dhb/data/docs_registry.from_sheet.json`.
2. `dhb/export-text-db` - писать текстовую витрину базы знаний в Google Sheet. Это не основная БД, а удобная таблица для человека: title, url, package/version/download_url, file_path, text.
3. `dhb/log-chat` - писать chat logs в Google Sheets через Apps Script webhook.

Для chat logs нужен `.env`:

```env
GOOGLE_SHEETS_LOG_WEBHOOK_URL=https://script.google.com/macros/s/.../exec
```

Для текстовой витрины базы знаний нужен отдельный webhook:

```env
GOOGLE_SHEETS_TEXT_DB_WEBHOOK_URL=https://script.google.com/macros/s/.../exec
```

Таблица может быть read-only для пользователей. Запись делает Apps Script от имени владельца.

## Email auth

Для отправки email-кодов нужен SMTP в `.env`:

```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASSWORD=google_app_password
SMTP_FROM=your_email@gmail.com
SMTP_USE_TLS=true
AUTH_CODE_TTL_SEC=600
AUTH_CODE_LENGTH=6
```

Для Gmail нужен App Password, не обычный пароль.

Коды:

- генерируются случайно;
- живут в памяти backend;
- удаляются после успешной проверки;
- при выходе надо запрашивать новый код.

## Как запускать

1. Запустить Dgraph:

```powershell
docker compose up -d
```

2. Запустить backend:

```powershell
.\.venv312\Scripts\python.exe -m uvicorn server:app --host 127.0.0.1 --port 8099
```

Для долгих rebuild/parsing не использовать `--reload`, иначе процесс может перезапуститься и начать заново.

3. Перезагрузить extension:

```text
chrome://extensions -> Reload extension
```

## Отличия от исходной схемы/tododb

`tododb/` - старый прототип ближе к исходной схеме.

Главные отличия текущего проекта:

- ArcadeDB заменен на Dgraph.
- Telegram bot заменен на browser extension.
- C# XDT заменен на Python parser.
- Отдельные сервисы сведены в один FastAPI backend.
- MGR реализован внутри browser extension.
- Google Sheets используется как registry source, chat logs и человекочитаемая текстовая витрина KB; полноценный dashboard с двусторонней синхронизацией не реализован.
- Observability VictoriaLogs/VictoriaMetrics не реализована.
- xdt_acc не реализован.
- xdt_pul реализован частично: headers/retries/timeouts/token/proxy, без полноценного VPN/account pool.
- Scheduler/автоматическое расписание обновлений не реализовано, запуск ручной через MGR/API.

Оценка отличия от `tododb`: концептуально похожи, технически отличаются примерно на 65-75%.

## Важные ограничения

- Не редактировать `RAGU/`.
- Не использовать destructive git/filesystem команды без прямого разрешения.
- Dgraph должен быть запущен для полноценного поиска.
- Если Dgraph выключен, server может стартовать, но `/ask` нормально работать не будет.
- Rate limit внешних LLM/registry API возможен; в проекте есть retry/backoff, но долгие rebuild могут занимать много времени.
- `run_ragu.py` сейчас не используется основным runtime, это старый standalone-тест.
