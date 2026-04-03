from io import BytesIO

# Lazy-import reportlab so app can start without the optional dependency installed.
try:
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter
except ImportError:  # pragma: no cover - defensive path for missing optional dependency
    canvas = None
    letter = None


def _ensure_reportlab():
    if canvas is None or letter is None:
        raise RuntimeError(
            "reportlab is required for PDF generation. Install with `pip install reportlab`."
        )


def generate_ps_pdf(case_id: str, case_no: str, doc_no: str, requester_id: str, category_id: str, account_code: str, amount: float, created_at: str) -> bytes:
    _ensure_reportlab()
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    p.drawString(100, 750, f"Document Type: PS")
    p.drawString(100, 730, f"Document No: {doc_no}")
    p.drawString(100, 710, f"Case ID: {case_id}")
    p.drawString(100, 690, f"Case No: {case_no}")
    p.drawString(100, 670, f"Requester ID: {requester_id}")
    p.drawString(100, 650, f"Category ID: {category_id}")
    p.drawString(100, 630, f"Account Code: {account_code}")
    p.drawString(100, 610, f"Amount: {amount}")
    p.drawString(100, 590, f"Created At: {created_at}")
    p.showPage()
    p.save()
    buffer.seek(0)
    return buffer.getvalue()

def generate_cr_pdf(case_id: str, case_no: str, doc_no: str, requester_id: str, category_id: str, account_code: str, amount: float, created_at: str) -> bytes:
    _ensure_reportlab()
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    p.drawString(100, 750, f"Document Type: CR")
    p.drawString(100, 730, f"Document No: {doc_no}")
    p.drawString(100, 710, f"Case ID: {case_id}")
    p.drawString(100, 690, f"Case No: {case_no}")
    p.drawString(100, 670, f"Requester ID: {requester_id}")
    p.drawString(100, 650, f"Category ID: {category_id}")
    p.drawString(100, 630, f"Account Code: {account_code}")
    p.drawString(100, 610, f"Amount: {amount}")
    p.drawString(100, 590, f"Created At: {created_at}")
    p.showPage()
    p.save()
    buffer.seek(0)
    return buffer.getvalue()

def generate_db_pdf(case_id: str, case_no: str, doc_no: str, requester_id: str, category_id: str, account_code: str, amount: float, created_at: str, cr_amount: float = None, variance: float = None) -> bytes:
    _ensure_reportlab()
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    p.drawString(100, 750, f"Document Type: DB")
    p.drawString(100, 730, f"Document No: {doc_no}")
    p.drawString(100, 710, f"Case ID: {case_id}")
    p.drawString(100, 690, f"Case No: {case_no}")
    p.drawString(100, 670, f"Requester ID: {requester_id}")
    p.drawString(100, 650, f"Category ID: {category_id}")
    p.drawString(100, 630, f"Account Code: {account_code}")
    p.drawString(100, 610, f"Amount: {amount}")
    if cr_amount is not None:
        p.drawString(100, 590, f"CR Amount: {cr_amount}")
    if variance is not None:
        p.drawString(100, 570, f"Variance: {variance}")
    p.drawString(100, 550, f"Created At: {created_at}")
    p.showPage()
    p.save()
    buffer.seek(0)
    return buffer.getvalue()
