"""docs/sunum.html → docs/sunum.pdf (her slayt 1920x1080 bir sayfa).

Kullanım: python scripts/sunum_pdf.py   (Playwright + Chromium gerekir, yazı tipleri için internet)
"""
from pathlib import Path

from playwright.sync_api import sync_playwright

DOCS = Path(__file__).resolve().parent.parent / "docs"

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1920, "height": 1080})
    page.goto((DOCS / "sunum.html").as_uri())
    page.evaluate("document.fonts.ready")
    page.wait_for_function("[...document.images].every(i => i.complete && i.naturalWidth)")
    page.pdf(path=str(DOCS / "sunum.pdf"), width="1920px", height="1080px", print_background=True)
    browser.close()
print("docs/sunum.pdf yazıldı")
