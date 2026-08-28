import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const source = "C:/Users/Admin/Documents/ChatGPT/PowerpayERP/.tmp/timesheet_inspect/app_generated.xlsx";
const outputDir = "C:/Users/Admin/Documents/ChatGPT/PowerpayERP/.tmp/timesheet_inspect/app_renders";
await fs.mkdir(outputDir, { recursive: true });
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(source));
const sheetOutput = (await workbook.inspect({ kind: "sheet", include: "id,name", maxChars: 12000 })).ndjson || "";
const sheets = sheetOutput.split(/\r?\n/).filter(Boolean).map(line => JSON.parse(line));
const report = { sheets: [] };
for (const record of sheets) {
  const name = record.name;
  const sheet = workbook.worksheets.getItem(name);
  const used = sheet.getUsedRange();
  const address = used?.address || "A1";
  const region = await workbook.inspect({ kind: "region", sheetId: name, range: address, maxChars: 15000, tableMaxRows: 45, tableMaxCols: 40, tableMaxCellChars: 120 });
  const formulas = await workbook.inspect({ kind: "formula", sheetId: name, range: address, maxChars: 6000, options: { maxResults: 150 } });
  const drawings = await workbook.inspect({ kind: "drawing", sheetId: name, maxChars: 5000, options: { maxResults: 50 } });
  const styles = await workbook.inspect({ kind: "computedStyle", sheetId: name, range: address, maxChars: 8000 });
  const preview = await workbook.render({ sheetName: name, autoCrop: "all", scale: 1.2, format: "png" });
  const safe = name.replace(/[<>:"/\\|?*]/g, "_");
  await fs.writeFile(path.join(outputDir, `${safe}.png`), new Uint8Array(await preview.arrayBuffer()));
  report.sheets.push({ name, address, region: region.ndjson, formulas: formulas.ndjson, drawings: drawings.ndjson, styles: styles.ndjson });
}
await fs.writeFile("C:/Users/Admin/Documents/ChatGPT/PowerpayERP/.tmp/timesheet_inspect/app_report.json", JSON.stringify(report, null, 2));
console.log(JSON.stringify(report.sheets.map(({name,address,formulas,drawings}) => ({name,address,formulaSummary:formulas.slice(0,500),drawingSummary:drawings.slice(0,500)})), null, 2));
