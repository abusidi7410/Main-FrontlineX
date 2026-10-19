"""Server-rendered PDF for an issued receipt.

Everything drawn here comes from the receipt's immutable snapshots, so a
downloaded receipt can never disagree with the one that was printed on the day
it was issued — even if the student later changes class or the school renames
itself. The PDF is generated with ReportLab (pure-Python; no system libraries),
so it works on the same Railway image as the rest of the API.
"""
from __future__ import annotations

import io
import os

from django.conf import settings
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, A5
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas

BOLD = 'Helvetica-Bold'
REGULAR = 'Helvetica'
MUTED = colors.HexColor('#475569')
INK = colors.HexColor('#0f172a')
LINE = colors.HexColor('#cbd5e1')
VOID_RED = colors.HexColor('#dc2626')


def _money(value) -> str:
    try:
        return f'{float(value):,.2f}'
    except (TypeError, ValueError):
        return str(value or '')


def _fit(text: str, font: str, size: float, max_width: float) -> str:
    text = str(text or '')
    if pdfmetrics.stringWidth(text, font, size) <= max_width:
        return text
    ellipsis = '…'
    while text and pdfmetrics.stringWidth(text + ellipsis, font, size) > max_width:
        text = text[:-1]
    return text + ellipsis


def _logo_path(school_snapshot: dict) -> str | None:
    name = (school_snapshot or {}).get('logo') or ''
    media_root = getattr(settings, 'MEDIA_ROOT', '')
    if not name or not media_root:
        return None
    path = os.path.join(str(media_root), name)
    return path if os.path.exists(path) else None


def _draw_logo(pdf, school_snapshot, *, center_x, top_y) -> float:
    path = _logo_path(school_snapshot)
    if path is None:
        return top_y
    try:
        image = ImageReader(path)
        width, height = image.getSize()
    except Exception:
        return top_y
    max_h = 16 * mm
    ratio = max_h / float(height)
    draw_w = width * ratio
    draw_h = max_h
    pdf.drawImage(
        image, center_x - draw_w / 2, top_y - draw_h,
        width=draw_w, height=draw_h, mask='auto',
    )
    return top_y - draw_h - 4 * mm


def render_receipt_pdf(receipt) -> bytes:
    paper = 'A4' if (receipt.school_snapshot or {}).get('paperSize') == 'A4' else 'A5'
    page_size = A4 if paper == 'A4' else A5
    width, height = page_size
    margin = 12 * mm
    content_width = width - 2 * margin

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=page_size)
    pdf.setTitle(f'Receipt {receipt.receipt_number}')
    pdf.setAuthor((receipt.school_snapshot or {}).get('name', ''))

    y = height - margin
    y = _draw_logo(
        pdf, receipt.school_snapshot, center_x=width / 2, top_y=y,
    )

    school = receipt.school_snapshot or {}
    name = school.get('name') or 'School'
    pdf.setFillColor(INK)
    pdf.setFont(BOLD, 13)
    pdf.drawCentredString(width / 2, y, _fit(name, BOLD, 13, content_width))
    y -= 5 * mm

    pdf.setFont(REGULAR, 8)
    pdf.setFillColor(MUTED)
    for line in (school.get('address'), ' · '.join(
        part for part in (school.get('phone'), school.get('email')) if part
    )):
        if line:
            pdf.drawCentredString(width / 2, y, _fit(line, REGULAR, 8, content_width))
            y -= 3.6 * mm

    y -= 1 * mm
    pdf.setStrokeColor(INK)
    pdf.setLineWidth(1)
    pdf.line(margin, y, width - margin, y)
    y -= 6 * mm

    pdf.setFont(BOLD, 11)
    pdf.setFillColor(INK)
    pdf.drawCentredString(width / 2, y, 'OFFICIAL FEE RECEIPT')
    y -= 7 * mm

    pdf.setFont(REGULAR, 8.5)
    pdf.setFillColor(MUTED)
    pdf.drawString(margin, y, f'Receipt No: {receipt.receipt_number}')
    pdf.drawRightString(
        width - margin, y,
        f'Date: {(receipt.issued_at or "").strftime("%d %b %Y") if receipt.issued_at else ""}',
    )
    y -= 5 * mm

    status_text = 'ISSUED' if receipt.status == 'issued' else 'VOID'
    pdf.setFont(BOLD, 9)
    pdf.setFillColor(VOID_RED if receipt.status == 'voided' else colors.HexColor('#166534'))
    pdf.drawString(margin, y, f'Status: {status_text}')
    if receipt.status == 'voided':
        pdf.setFont(REGULAR, 7.5)
        pdf.setFillColor(MUTED)
        pdf.drawString(margin + 22 * mm, y, _fit(
            receipt.void_reason, REGULAR, 7.5, content_width - 22 * mm,
        ))
    y -= 6 * mm

    student = receipt.student_snapshot or {}
    pdf.setFillColor(colors.HexColor('#f1f5f9'))
    box_top = y + 2 * mm
    box_rows = [
        ('Received from', receipt.payer_name),
        ('Student', student.get('name', '')),
        ('Admission No', student.get('admissionNumber', '')),
        ('Class', student.get('className', '')),
    ]
    box_height = len(box_rows) * 4.6 * mm + 2 * mm
    pdf.rect(margin, box_top - box_height, content_width, box_height, stroke=0, fill=1)
    y = box_top - 4.4 * mm
    for label, value in box_rows:
        pdf.setFont(REGULAR, 8)
        pdf.setFillColor(MUTED)
        pdf.drawString(margin + 2 * mm, y, label)
        pdf.setFont(BOLD, 8.5)
        pdf.setFillColor(INK)
        pdf.drawString(margin + 32 * mm, y, _fit(value, BOLD, 8.5, content_width - 34 * mm))
        y -= 4.6 * mm
    y -= 4 * mm

    amount_lines = [('Amount paid', f'NGN {_money(receipt.amount)}')]
    rows = [
        ('Amount in words', receipt.amount_in_words),
        ('Purpose', receipt.purpose),
        ('Payment method', (receipt.payment_snapshot or {}).get('method', '')),
        ('Reference', (receipt.payment_snapshot or {}).get('reference', '')),
    ]
    invoice = receipt.invoice_snapshot or {}
    if invoice.get('term') or invoice.get('session'):
        rows.append(('Invoice', ' · '.join(
            part for part in (invoice.get('term'), invoice.get('session')) if part
        )))
    rows.append(('Balance after payment', f'NGN {_money(receipt.balance_after)}'))

    for label, value in amount_lines + rows:
        pdf.setStrokeColor(LINE)
        pdf.setLineWidth(0.4)
        pdf.line(margin, y + 1.2 * mm, width - margin, y + 1.2 * mm)
        pdf.setFont(REGULAR, 8.5)
        pdf.setFillColor(MUTED)
        pdf.drawString(margin, y, label)
        pdf.setFont(BOLD if label == 'Amount paid' else REGULAR, 9)
        pdf.setFillColor(INK)
        value = str(value or '')
        if label in ('Amount paid', 'Balance after payment'):
            pdf.drawRightString(width - margin, y, value)
        else:
            left = margin + 42 * mm
            pdf.drawString(left, y, _fit(value, REGULAR, 8.5, width - margin - left))
        y -= 6.2 * mm

    y -= 4 * mm
    settings_obj_note = (receipt.school_snapshot or {}).get('footerNote')
    if settings_obj_note:
        pdf.setFont(REGULAR, 7.5)
        pdf.setFillColor(MUTED)
        pdf.drawString(margin, y, _fit(settings_obj_note, REGULAR, 7.5, content_width))
        y -= 5 * mm

    pdf.setStrokeColor(LINE)
    pdf.line(width - margin - 50 * mm, y, width - margin, y)
    y -= 4 * mm
    pdf.setFont(REGULAR, 8)
    pdf.setFillColor(MUTED)
    issued_by = receipt.issued_by.get_full_name() if receipt.issued_by else ''
    pdf.drawString(margin, y, _fit(f'Issued by: {issued_by}', REGULAR, 8, content_width / 2))
    pdf.drawRightString(width - margin, y, 'Authorised signature')

    if receipt.status == 'voided':
        pdf.saveState()
        pdf.setFillColor(colors.Color(0.86, 0.15, 0.15, alpha=0.12))
        pdf.setFont(BOLD, 70)
        pdf.translate(width / 2, height / 2)
        pdf.rotate(35)
        pdf.drawCentredString(0, 0, 'VOID')
        pdf.restoreState()

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()
