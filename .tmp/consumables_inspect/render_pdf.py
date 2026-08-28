from pathlib import Path
import pypdfium2 as pdfium
source=Path(".tmp/consumables_inspect/generated/IR-2026-0001.pdf")
output=source.parent/"pdf_render"; output.mkdir(parents=True,exist_ok=True)
document=pdfium.PdfDocument(str(source))
for index,page in enumerate(document): page.render(scale=2).to_pil().save(output/f"page-{index+1}.png")
