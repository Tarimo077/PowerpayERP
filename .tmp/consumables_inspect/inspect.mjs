import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const source="C:/Users/Admin/Downloads/Consumables supplies.xlsx";
const outputDir="C:/Users/Admin/Documents/ChatGPT/PowerpayERP/.tmp/consumables_inspect/renders";
await fs.mkdir(outputDir,{recursive:true});
const workbook=await SpreadsheetFile.importXlsx(await FileBlob.load(source));
const raw=(await workbook.inspect({kind:"sheet",include:"id,name",maxChars:10000})).ndjson||"";
const sheets=raw.split(/\r?\n/).filter(Boolean).map(line=>JSON.parse(line));
const report=[];
for(const record of sheets){
  const sheet=workbook.worksheets.getItem(record.name),used=sheet.getUsedRange(),address=used?.address||"A1";
  const region=await workbook.inspect({kind:"region",sheetId:record.name,range:address,maxChars:18000,tableMaxRows:80,tableMaxCols:30,tableMaxCellChars:160});
  const formulas=await workbook.inspect({kind:"formula",sheetId:record.name,range:address,maxChars:5000,options:{maxResults:100}});
  const preview=await workbook.render({sheetName:record.name,autoCrop:"all",scale:1.5,format:"png"});
  const safe=record.name.replace(/[<>:"/\\|?*]/g,"_"); await fs.writeFile(path.join(outputDir,`${safe}.png`),new Uint8Array(await preview.arrayBuffer()));
  report.push({name:record.name,address,region:region.ndjson,formulas:formulas.ndjson});
}
await fs.writeFile("C:/Users/Admin/Documents/ChatGPT/PowerpayERP/.tmp/consumables_inspect/report.json",JSON.stringify(report,null,2));
console.log(JSON.stringify(report.map(({name,address,region,formulas})=>({name,address,region,formulas})),null,2));
