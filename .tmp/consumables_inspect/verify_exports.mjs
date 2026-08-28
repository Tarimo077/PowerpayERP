import fs from "node:fs/promises";
import { FileBlob,SpreadsheetFile } from "@oai/artifact-tool";
const source="C:/Users/Admin/Documents/ChatGPT/PowerpayERP/.tmp/consumables_inspect/generated/IR-2026-0001.xlsx";
const workbook=await SpreadsheetFile.importXlsx(await FileBlob.load(source));
const region=await workbook.inspect({kind:"region",sheetId:"Consumable supplies",range:"A1:E16",maxChars:8000,tableMaxRows:20,tableMaxCols:8});
const formulas=await workbook.inspect({kind:"formula",sheetId:"Consumable supplies",range:"A1:E16",maxChars:2000,options:{maxResults:20}});
const errors=await workbook.inspect({kind:"match",searchTerm:"#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",options:{useRegex:true,maxResults:100},summary:"formula errors"});
const preview=await workbook.render({sheetName:"Consumable supplies",autoCrop:"all",scale:1.5,format:"png"}); await fs.writeFile("C:/Users/Admin/Documents/ChatGPT/PowerpayERP/.tmp/consumables_inspect/generated/xlsx.png",new Uint8Array(await preview.arrayBuffer()));
console.log(region.ndjson); console.log(formulas.ndjson); console.log(errors.ndjson);
