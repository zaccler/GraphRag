# GraphRAG Manager Browser Extension

Расширение для Chrome/Edge. Работает с локальным GraphRAG API.

## Установка

1. Открой `chrome://extensions` или `edge://extensions`.
2. Включи Developer mode.
3. Нажми Load unpacked.
4. Выбери папку `browser_extension`.

## Перед запуском

Основной сервер должен быть запущен:

```powershell
.\.venv312\Scripts\python.exe -m uvicorn server:app --host 127.0.0.1 --port 8099
```

По умолчанию расширение ходит на:

```text
http://127.0.0.1:8099
```

Адрес можно поменять прямо в popup.

## Что умеет

- вход по коду из `access_codes.json`;
- роль `user`: чат через `/ask`;
- роль `admin`: чат и вкладка MGR;
- MGR: `/status`, `/parse/url`, `/parse/packages`, `/parse/docs-registry`, `/rebuild`, `/ask_debug`;
- для `Parse Packages` и `Parse Docs` можно выбрать весь список или только первые N источников;
- если `force` выключен, уже скачанные источники пропускаются;
- вывод результата в двух режимах: короткий Text или полный JSON.

## Коды доступа

Коды лежат в:

```text
browser_extension/access_codes.json
```

По умолчанию:

```json
{
  "user_code": "U7qK2mZ9pR4xA1b",
  "admin_code": "A9vT3nQ6sL8wE2c"
}
```

После изменения файла расширение нужно перезагрузить на странице `chrome://extensions`.

## Формат Google Sheet для dashboard

Минимальные колонки:

```text
typ,url,enabled
```

Примеры:

```text
nuget,Newtonsoft.Json,true
pypi,requests,true
npm,axios,true
github,https://github.com/fastapi/fastapi,true
doc_page,https://docs.python.org/3.12/library/functions.html#eval,true
```
