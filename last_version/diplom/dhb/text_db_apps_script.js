const SHEET_NAME = "knowledge_text_db";
const HEADERS = [
  "timestamp",
  "source_key",
  "source_kind",
  "title",
  "url",
  "source_type",
  "package_manager",
  "package_id",
  "version",
  "download_url",
  "file_path",
  "text",
];

function doPost(e) {
  const payload = JSON.parse(e.postData.contents || "{}");
  const records = Array.isArray(payload.records) ? payload.records : [];
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(SHEET_NAME)
    || SpreadsheetApp.getActiveSpreadsheet().insertSheet(SHEET_NAME);

  ensureHeaders(sheet);

  records.forEach((record) => {
    const row = HEADERS.map((name) => record[name] || "");
    upsertBySourceKey(sheet, record.source_key || record.file_path || record.url || record.title, row);
  });

  return ContentService
    .createTextOutput(JSON.stringify({ status: "ok", records: records.length }))
    .setMimeType(ContentService.MimeType.JSON);
}

function ensureHeaders(sheet) {
  if (sheet.getLastRow() === 0) {
    sheet.appendRow(HEADERS);
    return;
  }

  const current = sheet.getRange(1, 1, 1, HEADERS.length).getValues()[0];
  if (current.join("|") !== HEADERS.join("|")) {
    sheet.getRange(1, 1, 1, HEADERS.length).setValues([HEADERS]);
  }
}

function upsertBySourceKey(sheet, sourceKey, row) {
  if (!sourceKey) {
    sheet.appendRow(row);
    return;
  }

  const lastRow = sheet.getLastRow();
  if (lastRow > 1) {
    const keys = sheet.getRange(2, 2, lastRow - 1, 1).getValues();
    for (let i = 0; i < keys.length; i += 1) {
      if (String(keys[i][0]) === String(sourceKey)) {
        sheet.getRange(i + 2, 1, 1, HEADERS.length).setValues([row]);
        return;
      }
    }
  }

  sheet.appendRow(row);
}
