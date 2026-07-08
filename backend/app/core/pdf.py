"""HTML → PDF rendering via WeasyPrint.

Isolated in its own module so the native-lib-backed import (Pango/Cairo) is easy
to diagnose, and so the strategy is swappable in one place: if WeasyPrint ever
proves too heavy on Cloud Run, replace ``html_to_pdf``'s body with
``return html.encode("utf-8")`` and have callers store ``.html`` instead — no
call sites change.
"""
from __future__ import annotations


def html_to_pdf(html: str) -> bytes:
    # Imported lazily: the module (and its native deps) only load when a PDF is
    # actually requested, keeping app startup light.
    from weasyprint import HTML

    return HTML(string=html).write_pdf()
