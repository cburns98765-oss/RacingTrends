/**
 * Racing Bet Tracker: receives paper bets from the Betfair paper-trading bot.
 * Paste into Extensions > Apps Script in the Racing Bet Tracker sheet, set TOKEN to the same
 * value as "sheet_token" in the bot's config.json, then Deploy > New deployment > Web app
 * (Execute as: Me, Who has access: Anyone). Put the web app URL in config.json "sheet_webhook".
 */
const TOKEN = 'CHANGE-ME';
const TAB = 'Paper bets';
const COLS = ['id', 'date', 'course', 'time', 'horse', 'rule', 'side', 'price', 'stake', 'struck_at',
              'status', 'horse_result', 'profit_loss', 'reason'];

function doPost(e) {
  const row = JSON.parse(e.postData.contents);
  if (row.token !== TOKEN) return ContentService.createTextOutput('bad token');
  const lock = LockService.getScriptLock();
  lock.waitLock(20000);
  const sh = SpreadsheetApp.getActive().getSheetByName(TAB);
  const ids = sh.getRange('A2:A').getValues().map(r => r[0]);
  const values = [COLS.map(c => row[c] === undefined ? '' : row[c])];
  let i = ids.indexOf(row.id);
  if (i < 0) i = ids.indexOf('');            // first empty row in column A
  sh.getRange(i + 2, 1, 1, COLS.length).setValues(values);
  lock.releaseLock();
  return ContentService.createTextOutput('ok');
}
