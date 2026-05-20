# DHB Dashboard

`dhb` соответствует блоку Dashboard на схеме.

Google Sheet здесь не считается основной базой знаний. Он используется как dashboard:

1. Админ ведет таблицу источников в Google Sheet.
2. `/dhb/sync-google-sheet` читает таблицу.
3. На основе строк генерируются registry-файлы:
   - `dhb/data/packages.from_sheet.txt`
   - `dhb/data/docs_registry.from_sheet.json`
4. Парсеры `xdt` уже работают с этими registry-файлами.
5. Итоговая база знаний остается в Dgraph/GraphRAG.

## Формат таблицы

Минимальные колонки:

```text
typ,url,enabled
```

Примеры строк:

```text
nuget,Newtonsoft.Json,true
pypi,requests,true
npm,axios,true
maven,org.springframework.boot:spring-boot-starter-web,true
github,https://github.com/fastapi/fastapi,true
doc_page,https://docs.python.org/3.12/library/functions.html#eval,true
python_docs,https://docs.python.org/3.12/,false
```

Также поддерживаются названия колонок из схемы:

```text
cod,url,typ,mtd,rul,shd
```

Пока реально используются `cod`, `url`, `typ`, `enabled`.

## Google Sheet как текстовая витрина базы

Для схемы добавлен режим, где backend зеркалит raw-тексты базы знаний в Google Sheet. Dgraph остается основной базой для GraphRAG, а Google Sheet нужна человеку, чтобы быстро посмотреть, что загружено.

```text
POST /dhb/export-text-db
```

Backend читает `.txt/.md/.json` из `raw/lit`, собирает строки вида `title`, `url`, `package_id`, `version`, `download_url`, `file_path`, `text` и отправляет их в отдельную Google Sheet через Apps Script webhook `dhb/text_db_apps_script.js`.

Для этого нужен `.env`:

```env
GOOGLE_SHEETS_TEXT_DB_WEBHOOK_URL=https://script.google.com/macros/s/.../exec
```

Новые данные после `parse packages/docs/url/python-docs` также автоматически пытаются попасть в эту таблицу. Если webhook не указан, данные все равно сохраняются локально в `dhb/data/text_db_rows.jsonl`.
