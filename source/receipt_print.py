"""Letter-size receipt printing through the Windows default browser."""
import html
from pathlib import Path
import uuid
import webbrowser


def receipt_html(receipts, *, auto_print=True):
    if not receipts:
        raise ValueError('No receipts are available to print.')
    pages='\n'.join('<section class="receipt"><pre>'+html.escape(text)+'</pre></section>' for text in receipts)
    return '''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Receipt print preview</title>
<style>
@page { size: letter portrait; margin: 0.75in; }
* { box-sizing: border-box; }
body { margin: 0; background: #212121; color: #f5f7f8; font-family: "Segoe UI", Arial, sans-serif; }
.toolbar { padding: 16px; text-align: center; }
button { padding: 10px 24px; font-size: 16px; cursor: pointer; background: #327a9e; color: white; border: 0; border-radius: 8px; }
.receipt { background: white; color: #141d2d; margin: 20px auto; padding: 0.5in; width: min(8.5in, 95%); border-radius: 12px; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; font: 11pt/1.5 Consolas, monospace; margin: 0; }
@media print {
 body { background: white; }
 .toolbar { display: none; }
 .receipt { color: black; margin: 0; padding: 0; width: auto; break-after: page; }
 pre { font-size: 10pt; line-height: 1.3; }
 .receipt:last-child { break-after: auto; }
}
</style></head><body>
<div class="toolbar"><button onclick="window.print()">Print on letter-size paper</button>
<p>Select Letter (8.5 × 11 inches), portrait. Turn off browser headers and footers.</p></div>
'''+pages+(
        "<script>window.addEventListener('load', function () { window.print(); });</script>"
        if auto_print else ''
    )+'</body></html>'


def open_print_preview(receipts, folder):
    folder=Path(folder)
    folder.mkdir(parents=True,exist_ok=True)
    path=folder/('receipt-'+uuid.uuid4().hex+'.html')
    path.write_text(receipt_html(receipts),encoding='utf-8')
    if not webbrowser.open(path.resolve().as_uri()):
        raise OSError('The print preview could not open. Open this file in your browser: '+str(path))
    return path
