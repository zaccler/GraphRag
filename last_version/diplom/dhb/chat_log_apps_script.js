const SHEET_NAME = "chat_logs";

function doPost(e) {
  const payload = JSON.parse(e.postData.contents || "{}");
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(SHEET_NAME)
    || SpreadsheetApp.getActiveSpreadsheet().insertSheet(SHEET_NAME);

  if (sheet.getLastRow() === 0) {
    sheet.appendRow(["timestamp", "email", "question", "answer"]);
  }

  sheet.appendRow([
    payload.timestamp || new Date().toISOString(),
    payload.email || "",
    payload.question || "",
    payload.answer || "",
  ]);

  return ContentService
    .createTextOutput(JSON.stringify({ status: "ok" }))
    .setMimeType(ContentService.MimeType.JSON);
}
