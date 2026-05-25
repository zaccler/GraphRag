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
## Chat History Google Sheets Read/Write

Chat logs use one Google Apps Script endpoint in two directions:

- `POST` writes `{ timestamp, email, question, answer }` to the sheet.
- `GET ?email=user@example.com&limit=200` returns history for one user.

Use this Apps Script for the chat log sheet:

```javascript
const SHEET_NAME = 'chat_logs';
const HEADERS = ['timestamp', 'email', 'question', 'answer'];

function sheet() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sh = ss.getSheetByName(SHEET_NAME);
  if (!sh) sh = ss.insertSheet(SHEET_NAME);
  if (sh.getLastRow() === 0) sh.appendRow(HEADERS);
  return sh;
}

function doPost(e) {
  const sh = sheet();
  const data = JSON.parse(e.postData.contents || '{}');
  sh.appendRow([
    data.timestamp || new Date().toISOString(),
    data.email || '',
    data.question || '',
    data.answer || '',
  ]);
  return ContentService
    .createTextOutput(JSON.stringify({ status: 'ok' }))
    .setMimeType(ContentService.MimeType.JSON);
}

function doGet(e) {
  const email = String((e.parameter.email || '')).trim().toLowerCase();
  const limit = Math.min(Number(e.parameter.limit || 200), 500);
  const sh = sheet();
  const values = sh.getDataRange().getValues();
  const headers = values.shift().map(String);
  const rows = values.map(row => Object.fromEntries(headers.map((h, i) => [h, row[i]])));
  const items = rows
    .filter(row => String(row.email || '').trim().toLowerCase() === email)
    .slice(-limit);

  return ContentService
    .createTextOutput(JSON.stringify({ items }))
    .setMimeType(ContentService.MimeType.JSON);
}
```

Deploy it as Web app with access allowed for the app owner, then put the same `/exec` URL into:

```env
GOOGLE_SHEETS_LOG_WEBHOOK_URL=https://script.google.com/macros/s/.../exec
GOOGLE_SHEETS_LOG_READ_URL=https://script.google.com/macros/s/.../exec
```
