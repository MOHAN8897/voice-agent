"""Statutory invoice numbering, serialisation and PDF rendering.

Numbers follow GST Rule 46(b): a consecutive serial, unique for a financial
year, at most 16 characters. Allocation takes a row lock so two concurrent
payments cannot be issued the same serial, and it happens inside the same
transaction as the invoice row so a rolled-back payment never burns a number.

PDFs are rendered on demand from the immutable invoice snapshot. Nothing about
the supplier, buyer or tax is read live, so re-downloading an old invoice
always reproduces the document that was issued.
"""
from __future__ import annotations

import io
from datetime import datetime
from typing import Any
from html import escape

from server.services.saas.tax_service import (
    financial_year,
    financial_year_compact,
    state_name_for,
)

try:  # ReportLab is an optional runtime dependency for deployments that email PDFs
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        KeepTogether,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    _PDF_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only when dependency is absent
    _PDF_AVAILABLE = False


async def allocate_number(session, kind: str, prefix: str, *, moment: datetime | None = None) -> tuple[str, str, int]:
    """Allocate the next serial for `kind` in the current financial year.

    Returns `(number, fy, sequence)`. Caller must already be in a transaction;
    the row lock is held until that transaction commits.
    """
    from sqlalchemy.exc import IntegrityError

    from server.db.models.saas_models import InvoiceSequence

    fy = financial_year(moment)
    compact = financial_year_compact(fy)
    clean_prefix = (prefix or ("INV" if kind == "INV" else "CN"))[:4]

    row = await session.get(InvoiceSequence, (kind, fy), with_for_update=True)
    if row is None:
        try:
            # Savepoint: losing the insert race must not poison the payment
            # transaction, which is about to issue the invoice itself.
            async with session.begin_nested():
                session.add(InvoiceSequence(kind=kind, fy=fy, last_number=0))
                await session.flush()
        except IntegrityError:
            pass
        row = await session.get(InvoiceSequence, (kind, fy), with_for_update=True)
    if row is None:  # pragma: no cover - only if the row vanished mid-transaction
        raise RuntimeError("invoice_sequence_unavailable")
    row.last_number = int(row.last_number or 0) + 1
    sequence = row.last_number
    number = f"{clean_prefix}-{compact}-{sequence:06d}"
    if len(number) > 16:  # pragma: no cover - prefix is capped at 4 chars
        number = number[:16]
    return number, fy, sequence


def invoice_payload(invoice: Any, *, credit_notes: list[Any] | None = None) -> dict[str, Any]:
    """JSON-safe invoice with every figure the console needs to show a breakdown."""
    currency = getattr(invoice, "currency", None) or "INR"
    gross_minor = getattr(invoice, "amount_minor", None)
    amount = (gross_minor / 100.0) if gross_minor is not None else int(invoice.amount_inr_paise or 0) / 100.0
    return {
        "invoiceId": str(invoice.invoice_id),
        "invoiceNumber": invoice.invoice_number,
        "status": invoice.status,
        "currency": currency,
        "amount": round(amount, 2),
        "gross": round(amount, 2),
        "subtotal": round(int(invoice.taxable_minor or 0) / 100.0, 2),
        "tax": round(int(invoice.tax_minor or 0) / 100.0, 2),
        "taxRatePercent": round(int(invoice.tax_rate_bps or 0) / 100.0, 2),
        "taxKind": invoice.tax_kind or "none",
        "amountInr": round(int(invoice.amount_inr_paise or 0) / 100.0, 2),
        "grossInr": round(
            (int(invoice.amount_inr_paise or 0) + int(invoice.tax_inr_paise or 0)) / 100.0, 2
        ),
        "taxableInr": round(int(invoice.taxable_inr_paise or 0) / 100.0, 2),
        "taxInr": round(int(invoice.tax_inr_paise or 0) / 100.0, 2),
        "cgstInr": round(int(invoice.cgst_inr_paise or 0) / 100.0, 2),
        "sgstInr": round(int(invoice.sgst_inr_paise or 0) / 100.0, 2),
        "igstInr": round(int(invoice.igst_inr_paise or 0) / 100.0, 2),
        "sacCode": invoice.sac_code,
        "placeOfSupply": invoice.place_of_supply,
        "placeOfSupplyCode": invoice.place_of_supply_code,
        "customerGstin": invoice.customer_gstin,
        "supplier": invoice.supplier_snapshot or {},
        "buyer": invoice.buyer_snapshot or {},
        "fy": invoice.fy,
        "sequence": invoice.sequence,
        "paymentId": invoice.razorpay_payment_id,
        "orderId": invoice.razorpay_order_id,
        "paymentMethod": invoice.payment_method,
        "paidAt": invoice.paid_at.isoformat() if getattr(invoice, "paid_at", None) else None,
        "createdAt": invoice.created_at.isoformat() if invoice.created_at else None,
        "lineItems": invoice.line_items or [],
        "creditNotes": [
            {
                "creditNoteId": str(note.credit_note_id),
                "creditNoteNumber": note.credit_note_number,
                "amountInr": round(int(note.taxable_inr_paise or 0) / 100.0, 2),
                "taxInr": round(int(note.tax_inr_paise or 0) / 100.0, 2),
                "reason": note.reason,
                "createdAt": note.created_at.isoformat() if note.created_at else None,
            }
            for note in (credit_notes or [])
        ],
        "downloadUrl": f"/api/billing/invoices/{invoice.invoice_id}/pdf",
    }


def credit_note_payload(note: Any) -> dict[str, Any]:
    return {
        "creditNoteId": str(note.credit_note_id),
        "creditNoteNumber": note.credit_note_number,
        "invoiceId": str(note.invoice_id),
        "invoiceNumber": note.invoice_number,
        "status": note.status,
        "currency": note.currency,
        "grossInr": round(int(note.gross_inr_paise or 0) / 100.0, 2),
        "taxableInr": round(int(note.taxable_inr_paise or 0) / 100.0, 2),
        "taxInr": round(int(note.tax_inr_paise or 0) / 100.0, 2),
        "cgstInr": round(int(note.cgst_inr_paise or 0) / 100.0, 2),
        "sgstInr": round(int(note.sgst_inr_paise or 0) / 100.0, 2),
        "igstInr": round(int(note.igst_inr_paise or 0) / 100.0, 2),
        "taxRatePercent": round(int(note.tax_rate_bps or 0) / 100.0, 2),
        "taxKind": note.tax_kind,
        "reason": note.reason,
        "refundId": note.razorpay_refund_id,
        "createdAt": note.created_at.isoformat() if note.created_at else None,
    }


# ---------------------------------------------------------------------------
# PDF rendering
# ---------------------------------------------------------------------------

_ONES = (
    "", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
    "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
    "Seventeen", "Eighteen", "Nineteen",
)
_TENS = ("", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety")


def _two_digits(n: int) -> str:
    if n < 20:
        return _ONES[n]
    return (_TENS[n // 10] + (" " + _ONES[n % 10] if n % 10 else "")).strip()


def _three_digits(n: int) -> str:
    if n >= 100:
        remainder = n % 100
        return _ONES[n // 100] + " Hundred" + (" " + _two_digits(remainder) if remainder else "")
    return _two_digits(n)


def amount_in_words(amount: float, currency: str = "INR") -> str:
    """Indian numbering (lakh/crore), the convention on Indian tax invoices."""
    total_paise = int(round(abs(float(amount or 0)) * 100))
    rupees, paise = divmod(total_paise, 100)
    if rupees == 0 and paise == 0:
        return "Zero"
    parts: list[str] = []
    crore, rupees = divmod(rupees, 10_000_000)
    lakh, rupees = divmod(rupees, 100_000)
    thousand, hundreds = divmod(rupees, 1000)
    if crore:
        parts.append(f"{_three_digits(crore)} Crore")
    if lakh:
        parts.append(f"{_two_digits(lakh)} Lakh")
    if thousand:
        parts.append(f"{_two_digits(thousand)} Thousand")
    if hundreds:
        parts.append(_three_digits(hundreds))
    words = " ".join(part for part in parts if part).strip() or "Zero"
    unit = "Rupees" if currency == "INR" else currency
    if paise:
        words += f" and {_two_digits(paise)} Paise"
    return f"{unit} {words} Only"


def _money(amount: float, currency: str = "INR") -> str:
    symbol = "Rs." if currency == "INR" else currency
    return f"{symbol} {amount:,.2f}"


def _esc(value: Any) -> str:
    return escape(str(value if value is not None else ""), quote=False)


def _address_lines(entity: dict[str, Any]) -> str:
    parts = [
        entity.get("addressLine1"),
        entity.get("addressLine2"),
        ", ".join(
            part
            for part in (
                entity.get("city"),
                entity.get("stateName"),
                entity.get("postalCode"),
            )
            if part
        ),
        entity.get("countryCode"),
    ]
    return "<br/>".join(_esc(part) for part in parts if part)


def render_invoice_pdf(invoice: Any, credit_notes: list[Any] | None = None) -> bytes:
    """Render a GST tax invoice. Raises RuntimeError if ReportLab is unavailable."""
    if not _PDF_AVAILABLE:
        raise RuntimeError("pdf_renderer_unavailable")
    supplier = invoice.supplier_snapshot or {}
    buyer = invoice.buyer_snapshot or {}
    currency = invoice.currency or "INR"
    credit_notes = credit_notes or []

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=16 * mm,
        title=f"Tax Invoice {invoice.invoice_number}",
        author=supplier.get("legalName") or "Dialtact",
    )
    styles = getSampleStyleSheet()
    small = ParagraphStyle("small", parent=styles["Normal"], fontSize=8, leading=10.5)
    tiny = ParagraphStyle("tiny", parent=styles["Normal"], fontSize=7, leading=9)
    right = ParagraphStyle("right", parent=small, alignment=TA_RIGHT)
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontSize=16, leading=19, spaceAfter=2)

    story: list[Any] = []
    title = "TAX INVOICE" if (invoice.tax_kind or "none") != "none" else "INVOICE"
    story.append(Paragraph(title, h1))
    story.append(
        Paragraph(
            f"Original for Recipient &nbsp;|&nbsp; Invoice No. <b>{_esc(invoice.invoice_number)}</b>"
            f" &nbsp;|&nbsp; Date: {_esc(invoice.created_at.strftime('%d %b %Y') if invoice.created_at else '')}",
            small,
        )
    )
    story.append(Spacer(1, 8))

    supplier_block = (
        f"<b>{_esc(supplier.get('legalName') or 'Supplier')}</b><br/>"
        f"{_esc(supplier.get('tradeName') or '')}<br/>"
        f"{_address_lines(supplier)}<br/>"
        f"GSTIN: <b>{_esc(supplier.get('gstin') or 'Not configured')}</b>"
        + (f"<br/>PAN: {_esc(supplier.get('pan'))}" if supplier.get("pan") else "")
        + (f"<br/>SAC: {_esc(invoice.sac_code or supplier.get('sacCode'))}" if (invoice.sac_code or supplier.get("sacCode")) else "")
        + (f"<br/>LUT: {_esc(supplier.get('lutNumber'))}" if supplier.get("lutNumber") else "")
    )
    buyer_block = (
        f"<b>Billed to</b><br/>{_esc(buyer.get('legalName') or 'Customer')}<br/>"
        f"{_address_lines(buyer) or 'Address not provided'}<br/>"
        + (f"GSTIN: <b>{_esc(buyer.get('gstin'))}</b><br/>" if buyer.get("gstin") else "")
        + (f"Email: {_esc(buyer.get('email'))}" if buyer.get("email") else "")
    )
    header_table = Table(
        [
            [Paragraph(supplier_block, small), Paragraph(buyer_block, small)],
        ],
        colWidths=[95 * mm, 80 * mm],
    )
    header_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#9CA3AF")),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D1D5DB")),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(header_table)
    story.append(Spacer(1, 8))

    meta = [
        ["Place of supply", invoice.place_of_supply or state_name_for(invoice.place_of_supply_code) or "—"],
        ["Reverse charge", "No"],
        ["Payment reference", invoice.razorpay_payment_id or "Manual adjustment"],
        ["Payment date", invoice.paid_at.strftime("%d %b %Y %H:%M") if getattr(invoice, "paid_at", None) else "—"],
    ]
    meta_table = Table(
        [[Paragraph(f"<b>{_esc(k)}</b>", tiny), Paragraph(_esc(v), tiny)] for k, v in meta],
        colWidths=[45 * mm, 130 * mm],
    )
    meta_table.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#D1D5DB")),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#E5E7EB")),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F9FAFB")),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    story.append(meta_table)
    story.append(Spacer(1, 8))

    description = "Prepaid voice services — wallet top-up"
    if getattr(invoice, "tax_kind", "none") == "export":
        description += " — export of services (zero-rated under LUT)"
    rows = [["#", "Description", "SAC", "Qty", "Rate", "Amount"]]
    rows.append(
        [
            "1",
            Paragraph(_esc(description), small),
            _esc(invoice.sac_code or supplier.get("sacCode") or ""),
            "1",
            _money(int(invoice.taxable_minor or 0) / 100.0, currency),
            _money(int(invoice.taxable_minor or 0) / 100.0, currency),
        ]
    )
    items = Table(rows, colWidths=[8 * mm, 82 * mm, 20 * mm, 12 * mm, 27 * mm, 26 * mm], repeatRows=1)
    items.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#111827")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 8),
                ("ALIGN", (-2, 1), (-1, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D1D5DB")),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(items)
    story.append(Spacer(1, 6))

    taxable = int(invoice.taxable_minor or 0) / 100.0
    tax_total = int(invoice.tax_minor or 0) / 100.0
    gross = (int(invoice.amount_minor or 0) / 100.0) if invoice.amount_minor else taxable + tax_total
    totals = [["Taxable value", _money(taxable, currency)]]
    if invoice.tax_kind == "cgst_sgst":
        totals.append([f"CGST @ {invoice.tax_rate_bps / 200:.2f}%", _money(int(invoice.cgst_inr_paise or 0) / 100.0, "INR")])
        totals.append([f"SGST @ {invoice.tax_rate_bps / 200:.2f}%", _money(int(invoice.sgst_inr_paise or 0) / 100.0, "INR")])
    elif invoice.tax_kind == "igst":
        totals.append([f"IGST @ {invoice.tax_rate_bps / 100:.2f}%", _money(int(invoice.igst_inr_paise or 0) / 100.0, "INR")])
    elif invoice.tax_kind == "export":
        totals.append(["IGST (export under LUT)", _money(0, "INR")])
    totals.append(["Total", _money(gross, currency)])
    totals_table = Table(
        [[Paragraph(_esc(k), small), Paragraph(_esc(v), right)] for k, v in totals],
        colWidths=[110 * mm, 65 * mm],
        hAlign="RIGHT",
    )
    totals_table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D1D5DB")),
                ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#F3F4F6")),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    story.append(totals_table)
    story.append(Spacer(1, 6))
    story.append(Paragraph(f"Amount in words: <b>{_esc(amount_in_words(gross, currency))}</b>", small))
    story.append(Spacer(1, 4))
    story.append(
        Paragraph(
            f"Wallet credit: <b>{_money(int(invoice.amount_inr_paise or 0) / 100.0, 'INR')}</b> "
            f"(taxable value in INR at the checkout rate).",
            small,
        )
    )

    if credit_notes:
        story.append(Spacer(1, 8))
        story.append(Paragraph("<b>Credit notes against this invoice</b>", small))
        cn_rows = [["Credit note", "Date", "Taxable (INR)", "Tax (INR)"]]
        for note in credit_notes:
            cn_rows.append(
                [
                    note.credit_note_number,
                    note.created_at.strftime("%d %b %Y") if note.created_at else "",
                    _money(int(note.taxable_inr_paise or 0) / 100.0, "INR"),
                    _money(int(note.tax_inr_paise or 0) / 100.0, "INR"),
                ]
            )
        cn_table = Table(cn_rows, colWidths=[50 * mm, 40 * mm, 42 * mm, 42 * mm])
        cn_table.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#D1D5DB")),
                    ("FONTSIZE", (0, 0), (-1, -1), 7),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F3F4F6")),
                ]
            )
        )
        story.append(cn_table)

    terms = supplier.get("invoiceTerms")
    if terms:
        story.append(Spacer(1, 8))
        story.append(Paragraph(f"<b>Terms</b><br/>{_esc(terms)}", tiny))
    story.append(Spacer(1, 14))
    story.append(
        KeepTogether(
            [
                Paragraph(
                    f"For <b>{_esc(supplier.get('legalName') or 'Supplier')}</b><br/><br/><br/>"
                    "Authorised signatory",
                    right,
                ),
                Spacer(1, 6),
                Paragraph(
                    "This is a computer-generated invoice. For questions contact "
                    f"{_esc(supplier.get('supportEmail') or 'support')}.",
                    tiny,
                ),
            ]
        )
    )

    doc.build(story)
    return buffer.getvalue()


def render_credit_note_pdf(note: Any, invoice: Any) -> bytes:
    if not _PDF_AVAILABLE:
        raise RuntimeError("pdf_renderer_unavailable")
    supplier = note.supplier_snapshot or {}
    buyer = note.buyer_snapshot or {}
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=16 * mm,
        title=f"Credit Note {note.credit_note_number}",
        author=supplier.get("legalName") or "Dialtact",
    )
    styles = getSampleStyleSheet()
    small = ParagraphStyle("small", parent=styles["Normal"], fontSize=8, leading=10.5)
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontSize=16, leading=19, spaceAfter=2)
    story: list[Any] = [
        Paragraph("CREDIT NOTE", h1),
        Paragraph(
            f"Credit Note No. <b>{_esc(note.credit_note_number)}</b> against invoice "
            f"<b>{_esc(note.invoice_number)}</b> dated "
            f"{_esc(invoice.created_at.strftime('%d %b %Y') if invoice and invoice.created_at else '—')}",
            small,
        ),
        Spacer(1, 8),
        Paragraph(f"<b>{_esc(supplier.get('legalName') or 'Supplier')}</b><br/>{_address_lines(supplier)}<br/>GSTIN: {_esc(supplier.get('gstin') or '')}", small),
        Spacer(1, 6),
        Paragraph(f"<b>Credit to</b><br/>{_esc(buyer.get('legalName') or 'Customer')}<br/>{_address_lines(buyer)}", small),
        Spacer(1, 8),
        Paragraph(f"<b>Reason:</b> {_esc(note.reason)}", small),
        Spacer(1, 8),
    ]
    rows = [["Taxable value", "CGST", "SGST", "IGST", "Total tax", "Credit total"]]
    rows.append(
        [
            _money(int(note.taxable_inr_paise or 0) / 100.0, "INR"),
            _money(int(note.cgst_inr_paise or 0) / 100.0, "INR"),
            _money(int(note.sgst_inr_paise or 0) / 100.0, "INR"),
            _money(int(note.igst_inr_paise or 0) / 100.0, "INR"),
            _money(int(note.tax_inr_paise or 0) / 100.0, "INR"),
            _money(int(note.gross_inr_paise or 0) / 100.0, "INR"),
        ]
    )
    table = Table(rows, colWidths=[32 * mm, 27 * mm, 27 * mm, 27 * mm, 28 * mm, 34 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#111827")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D1D5DB")),
                ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(table)
    story.append(Spacer(1, 6))
    story.append(
        Paragraph(
            f"Amount in words: <b>{_esc(amount_in_words(int(note.gross_inr_paise or 0) / 100.0, 'INR'))}</b>",
            small,
        )
    )
    story.append(Spacer(1, 12))
    story.append(Paragraph("This credit note reverses the tax shown on the original invoice.", small))
    doc.build(story)
    return buffer.getvalue()
