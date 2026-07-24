"""
Memorial flyer PDF generator — creates printable bifold memorial programs.
Uses ReportLab for precise print-ready PDF generation.
"""
import os
from pathlib import Path
from datetime import datetime

from django.conf import settings

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader


# Design constants
NAVY = HexColor('#1a2a3a')
GOLD = HexColor('#c4a97d')
SAGE = HexColor('#8a9a7a')
CREAM = HexColor('#f5f0eb')
CHARCOAL = HexColor('#2d2d2d')


def generate_bifold_flyer(
    output_path,
    name,
    dates,
    photo_path=None,
    message=None,
    obituary_text=None,
):
    """
    Generate a bifold (half-fold) memorial program PDF.

    Layout:
    - Front cover: photo + name + dates
    - Inside left: obituary or tribute message
    - Inside right: order of service or photo collage
    - Back cover: thank you message with decorative elements

    Args:
        output_path: Where to save the PDF
        name: Full name of the deceased
        dates: Date string (e.g. "1950 — 2026")
        photo_path: Optional path to a photo for the cover
        message: Optional short tribute message
        obituary_text: Optional full obituary text
    """
    width, height = letter  # 8.5 x 11 inches
    half = width / 2

    c = canvas.Canvas(output_path, pagesize=letter)

    # ---- PAGE 1: Front Cover (right panel) + Inside Left (left panel) ----
    # Front cover — right half
    c.setFillColor(NAVY)
    c.rect(half, 0, half, height, fill=1, stroke=0)

    # Decorative border
    c.setStrokeColor(GOLD)
    c.setLineWidth(2)
    margin = 0.3 * inch
    c.rect(half + margin, margin, half - 2 * margin, height - 2 * margin)

    # Gold accent line
    c.setStrokeColor(GOLD)
    c.setLineWidth(1)
    line_y = height * 0.62
    c.line(half + 1 * inch, line_y, width - 1 * inch, line_y)

    # Photo on cover (if provided)
    if photo_path and os.path.exists(photo_path):
        try:
            img = ImageReader(photo_path)
            img_w, img_h = img.getSize()
            # Scale to fit within 3.5" x 3.5" area
            max_w = 3.2 * inch
            max_h = 3.2 * inch
            scale = min(max_w / img_w, max_h / img_h)
            disp_w = img_w * scale
            disp_h = img_h * scale
            img_x = half + (half - disp_w) / 2
            img_y = height - 4.5 * inch
            # Clip to circle using a white circle background
            c.setFillColor(HexColor('#ffffff'))
            circle_x = half + half / 2
            circle_y = img_y + disp_h / 2
            c.circle(circle_x, circle_y, disp_w / 2 + 5, fill=1, stroke=0)
            c.drawImage(img, img_x, img_y, width=disp_w, height=disp_h, mask='auto')
        except Exception:
            pass  # Skip photo on error

    # Name on cover
    c.setFillColor(GOLD)
    c.setFont('Times-Bold', 28)
    c.drawCentredString(half + half / 2, height * 0.48, name)

    # Dates
    c.setFillColor(HexColor('#ffffff'))
    c.setFont('Times-Italic', 16)
    c.drawCentredString(half + half / 2, height * 0.43, dates)

    # Decorative element
    c.setFillColor(GOLD)
    c.setFont('Times-Roman', 14)
    c.drawCentredString(half + half / 2, height * 0.37, '✦ Forever in Our Hearts ✦')

    # Inside left panel — Tribute message
    c.setFillColor(CREAM)
    c.rect(0, 0, half, height, fill=1, stroke=0)

    # Title
    c.setFillColor(NAVY)
    c.setFont('Times-Bold', 18)
    c.drawCentredString(half / 2, height - 1.2 * inch, 'In Loving Memory')

    # Gold divider
    c.setStrokeColor(GOLD)
    c.setLineWidth(1)
    c.line(0.8 * inch, height - 1.5 * inch, half - 0.8 * inch, height - 1.5 * inch)

    # Message text
    c.setFillColor(CHARCOAL)
    c.setFont('Times-Roman', 11)

    text_content = obituary_text or message or 'A life beautifully lived.'
    text = c.beginText(0.6 * inch, height - 2 * inch)
    text.textLines(text_content)
    c.drawText(text)

    # ---- PAGE 2: Inside Right (left panel) + Back Cover (right panel) ----
    c.showPage()

    # Inside right — Photos or order of service
    c.setFillColor(HexColor('#ffffff'))
    c.rect(0, 0, half, height, fill=1, stroke=0)

    c.setFillColor(NAVY)
    c.setFont('Times-Bold', 18)
    c.drawCentredString(half / 2, height - 1.2 * inch, 'Order of Service')

    c.setStrokeColor(GOLD)
    c.setLineWidth(1)
    c.line(0.8 * inch, height - 1.5 * inch, half - 0.8 * inch, height - 1.5 * inch)

    # Back cover — right panel
    c.setFillColor(NAVY)
    c.rect(half, 0, half, height, fill=1, stroke=0)

    c.setStrokeColor(GOLD)
    c.setLineWidth(2)
    c.rect(half + margin, margin, half - 2 * margin, height - 2 * margin)

    # Thank you message
    c.setFillColor(GOLD)
    c.setFont('Times-Italic', 14)
    c.drawCentredString(half + half / 2, height * 0.6, 'Thank You')

    c.setFillColor(HexColor('#ffffff'))
    c.setFont('Times-Roman', 11)
    thank_you = c.beginText(half + 0.6 * inch, height * 0.52)
    thank_you.textLines('For your love, support,\nand presence today.\n\nYour kindness will always\nbe remembered.')
    c.drawText(thank_you)

    # Gold divider on back
    c.setStrokeColor(GOLD)
    c.setLineWidth(0.5)
    c.line(half + 1 * inch, height * 0.42, width - 1 * inch, height * 0.42)

    # Bottom text
    c.setFont('Times-Italic', 10)
    c.drawCentredString(half + half / 2, height * 0.12, 'Crafted with care by Everlasting Frames')

    c.save()
    return output_path


def generate_flyer_for_order(order, photo_path=None):
    """
    Generate a memorial flyer PDF for a given order.
    Returns the file path.
    """
    user = order.user
    output_dir = Path(settings.MEDIA_ROOT) / 'flyers'
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = str(output_dir / f'flyer_order_{order.id}.pdf')

    generate_bifold_flyer(
        output_path=output_path,
        name=f'{user.get_full_name() or user.username}\'s Order',
        dates='Your loved one\nDate — Date',
        photo_path=photo_path,
        message='A celebration of a life beautifully lived.\nCherished memories that will last forever.',
    )
    return output_path
