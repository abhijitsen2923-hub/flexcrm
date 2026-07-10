"""HTML → PDF rendering with a resilient fallback.

Prefer WeasyPrint (best fidelity) when its native libs (Pango/HarfBuzz/Fontconfig)
are present on the runtime image; if that import or render fails for ANY reason,
fall back to the pure-Python xhtml2pdf so PDF generation never hard-fails (500)
on a serverless image missing those system libraries. The document HTML is
engine-neutral (tables + <hr>, "Rs." not ₹) so both renderers produce a clean,
on-brand PDF. See app/real_estate/documents.py.
"""
from __future__ import annotations


def _weasyprint_pdf(html: str) -> bytes:
    from weasyprint import HTML  # loads native libs at import — may raise OSError

    return HTML(string=html).write_pdf()


def _xhtml2pdf_pdf(html: str) -> bytes:
    from io import BytesIO

    from xhtml2pdf import pisa

    buf = BytesIO()
    pisa.CreatePDF(src=html, dest=buf, encoding="utf-8")
    return buf.getvalue()


def html_to_pdf(html: str) -> bytes:
    try:
        return _weasyprint_pdf(html)
    except Exception:
        pdf = _xhtml2pdf_pdf(html)
        if not pdf:
            raise  # both engines produced nothing — surface the original failure
        return pdf
