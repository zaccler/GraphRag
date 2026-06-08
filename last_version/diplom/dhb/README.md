# DHB

`dhb` отвечает за внешние табличные данные и историю чата.

## Что осталось в проекте

- `chat_logs.py` сохраняет вопросы и ответы пользователя.
- `text_db_mirror.py` зеркалит распарсенные raw-тексты в Google Sheet как читаемую витрину базы.
- `chat_log_apps_script.js` и `text_db_apps_script.js` лежат как примеры Google Apps Script.

## Что удалено

Старый endpoint `/dhb/sync-google-sheet` удалён. Таблица больше не используется как источник registry-файлов. Основной источник пакетов и документации теперь лежит в `xdt/rpo`.

## Chat logs

Backend пишет историю через:

```env
GOOGLE_SHEETS_LOG_WEBHOOK_URL=https://script.google.com/macros/s/.../exec
GOOGLE_SHEETS_LOG_READ_URL=https://script.google.com/macros/s/.../exec
```

Если URL не указаны, история сохраняется локально в `dhb/data/chat_logs.jsonl`.

## Text DB mirror

После парсинга backend автоматически пытается отправить raw-текст в Google Sheet через:

```env
GOOGLE_SHEETS_TEXT_DB_WEBHOOK_URL=https://script.google.com/macros/s/.../exec
```

Если webhook не указан, строки сохраняются локально в `dhb/data/text_db_rows.jsonl`.
