import asyncio
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from urllib.request import urlopen

from app.database.models import Order
from app.enums.order import InvoiceTypeEnum
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.utils import ImageReader
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from app.rpc_client.auth import AuthRpcClient
from app.services.invoice_generator.invoice_types import InvoiceTypes, BaseInvoice


class InvoiceGenerator:
    CURRENCY = "PLN"

    def __init__(self, order: Order, user=None):
        self.order = order
        self.user = user

    @staticmethod
    def _format_amount(amount: float) -> str:
        return f"{amount:.2f} {InvoiceGenerator.CURRENCY}"

    @staticmethod
    def _scaled_logo(logo_source: str | BytesIO, max_height: float = 36) -> Image:
        reader = ImageReader(logo_source)
        intrinsic_width, intrinsic_height = reader.getSize()
        height = max_height
        width = height * (intrinsic_width / intrinsic_height)
        return Image(logo_source, width=width, height=height, mask="auto")

    @staticmethod
    def _resolve_logo_source(logo_path: str | None) -> str | BytesIO | None:
        if not logo_path:
            return None
        if logo_path.startswith(("http://", "https://")):
            try:
                with urlopen(logo_path, timeout=10) as response:
                    return BytesIO(response.read())
            except Exception:
                return None
        local_logo_path = Path(logo_path)
        if local_logo_path.exists():
            return str(local_logo_path)
        return None

    def _load_user_via_rpc(self):

        async def _fetch():
            async with AuthRpcClient() as client:
                return await client.get_user(user_uuid=self.order.user_uuid)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # Avoid nesting event loops; skip RPC in this edge case.
            return None

        try:
            return asyncio.run(_fetch())
        except Exception:
            return None

    def _build_invoice_to_lines(self) -> list[str]:
        lines: list[str] = []
        user = self.user or self._load_user_via_rpc()
        if user:
            full_name = f"{user.first_name} {user.last_name}".strip()
            if full_name:
                lines.append(full_name)
            if user.email:
                lines.append(user.email)
            if user.phone_number:
                lines.append('+' + user.phone_number)

        elif getattr(self.order, "user_uuid", None):
            lines.append(f"UUID użytkownika: {self.order.user_uuid}")

        return [line for line in lines if line]

    def generate_invoice_based_on_invoice_type(
        self,
        invoice_type: InvoiceTypeEnum | None = None,
        save_path: str | Path | None = None,
    ) -> bytes:
        info_mapping = {
            InvoiceTypeEnum.DEFAULT: InvoiceTypes.get_default_info,
        }
        if not invoice_type:
            invoice_type = self.order.invoice_type

        info_getter = info_mapping.get(invoice_type)
        if not info_getter:
            raise ValueError(f"Unsupported invoice type: {invoice_type}")

        info = info_getter()
        pdf_bytes = self.generate_pdf(info)

        if save_path:
            output_path = Path(save_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(pdf_bytes)

        return pdf_bytes

    def generate_pdf(self, info: BaseInvoice) -> bytes:
        """
        Build invoice PDF bytes using BaseInvoice metadata and the current order data.
        """
        buffer = BytesIO()

        # Fonts: attempt to load DejaVu, fallback to Helvetica
        font_name = "Helvetica"
        font_bold = "Helvetica-Bold"
        try:
            font_dir = Path(__file__).resolve().parent
            regular_font = font_dir / "fonts" / "dejavu-sans.ttf"
            bold_font = font_dir / "fonts" / "dejavu-sans-bold.ttf"
            if regular_font.exists() and bold_font.exists():
                pdfmetrics.registerFont(TTFont("DejaVuSans", str(regular_font)))
                pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", str(bold_font)))
                font_name = "DejaVuSans"
                font_bold = "DejaVuSans-Bold"
        except Exception:
            # fall back silently to Helvetica
            font_name = "Helvetica"
            font_bold = "Helvetica-Bold"

        pdf = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=40,
            leftMargin=40,
            topMargin=28,
            bottomMargin=28,
        )

        content_width = letter[0] - pdf.leftMargin - pdf.rightMargin
        invoice_items = self.order.invoice_items or []
        item_count = len(invoice_items)
        compact = item_count > 6
        dense = item_count > 10

        body_size = 7 if dense else 8
        header_size = 18 if dense else 20
        row_pad = 2 if dense else 3 if compact else 4
        section_gap = 4 if dense else 6 if compact else 8

        styles = getSampleStyleSheet()
        header_title_style = ParagraphStyle(
            "HeaderTitleStyle",
            parent=styles["Heading1"],
            fontSize=header_size,
            textColor=colors.HexColor("#1a202c"),
            fontName=font_bold,
            leading=header_size + 2,
            spaceAfter=0,
            spaceBefore=0,
            alignment=TA_LEFT,
        )
        header_subtitle_style = ParagraphStyle(
            "HeaderSubtitleStyle",
            parent=styles["Normal"],
            fontSize=body_size,
            textColor=colors.HexColor("#4a5568"),
            fontName=font_name,
            leading=body_size + 2,
            spaceAfter=0,
            spaceBefore=0,
            alignment=TA_LEFT,
        )
        invoice_title_style = ParagraphStyle(
            "InvoiceTitleStyle",
            parent=styles["Heading1"],
            fontSize=13,
            alignment=TA_RIGHT,
            spaceBefore=0,
            spaceAfter=2,
            fontName=font_bold,
            textColor=colors.HexColor("#1a202c"),
            leading=15,
        )
        value_style = ParagraphStyle(
            "ValueStyle",
            parent=styles["Normal"],
            fontSize=body_size,
            fontName=font_name,
            textColor=colors.HexColor("#1a202c"),
            alignment=TA_LEFT,
            leading=body_size + 2,
        )
        bold_style = ParagraphStyle(
            "BoldStyle",
            parent=styles["Heading4"],
            fontSize=body_size,
            fontName=font_bold,
            textColor=colors.black,
            leading=body_size + 2,
        )
        body_style = ParagraphStyle(
            "BodyStyle",
            parent=styles["Normal"],
            fontSize=body_size,
            fontName=font_name,
            textColor=colors.black,
            leading=body_size + 2,
        )
        normal_style = ParagraphStyle(
            "NormalStyle",
            parent=styles["Normal"],
            fontSize=body_size,
            fontName=font_name,
            textColor=colors.black,
            leading=body_size + 2,
        )
        delivery_terms_style = ParagraphStyle(
            "DeliveryTerms",
            fontName=font_name,
            fontSize=body_size,
            textColor=colors.black,
            leading=body_size + 2,
            leftIndent=0,
        )
        item_text_style = ParagraphStyle(
            "ItemTextStyle",
            parent=styles["Normal"],
            fontSize=body_size,
            fontName=font_name,
            textColor=colors.black,
            leading=body_size + 1,
        )
        thank_you_style = ParagraphStyle(
            "ThankYouStyle",
            parent=styles["Normal"],
            fontSize=body_size,
            fontName=font_name,
            alignment=TA_RIGHT,
            textColor=colors.HexColor("#4a5568"),
            leading=body_size + 2,
        )

        elements = []

        subtitle = info.header_subtitle or ""
        logo_source = self._resolve_logo_source(info.logo_path)
        logo_width = 0
        logo_cell: Image | str = ""

        logo_max_height = 28 if dense else 32
        if logo_source:
            try:
                logo = self._scaled_logo(logo_source, max_height=logo_max_height)
                logo_width = logo.drawWidth
                logo_cell = logo
            except Exception:
                logo_cell = ""

        company_block = [Paragraph(info.company_name, header_title_style)]
        if subtitle:
            company_block.append(Paragraph(str(subtitle), header_subtitle_style))

        invoice_number = f"{self.order.vin}"
        invoice_date = (
            self.order.created_at if isinstance(self.order.created_at, datetime) else datetime.now(timezone.utc)
        )
        meta_block = [
            Paragraph("FAKTURA", invoice_title_style),
            Paragraph(f"<b>Numer:</b> {invoice_number}", value_style),
            Paragraph(f"<b>Data:</b> {invoice_date.strftime('%d.%m.%Y')}", value_style),
        ]

        if logo_cell:
            top_table = Table(
                [[logo_cell, company_block, meta_block]],
                colWidths=[logo_width + 10, content_width * 0.45, content_width * 0.55 - logo_width - 10],
            )
        else:
            top_table = Table(
                [[company_block, meta_block]],
                colWidths=[content_width * 0.5, content_width * 0.5],
            )
        top_table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("ALIGN", (-1, 0), (-1, 0), "RIGHT"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )
        elements.append(top_table)

        divider = Table([[""]], colWidths=[content_width], rowHeights=[1])
        divider.setStyle(
            TableStyle(
                [
                    ("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e0")),
                    ("TOPPADDING", (0, 0), (-1, -1), section_gap),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), section_gap),
                ]
            )
        )
        elements.append(divider)

        company_lines = info.company_info_lines or [info.company_name]
        seller_lines = "<br/>".join(str(line) for line in company_lines)
        invoice_to_lines = self._build_invoice_to_lines()
        buyer_lines = "<br/>".join(invoice_to_lines) if invoice_to_lines else "—"

        parties_table = Table(
            [
                [
                    Paragraph("<b>Sprzedawca</b><br/>" + seller_lines, body_style),
                    Paragraph("<b>Nabywca</b><br/>" + buyer_lines, body_style),
                ]
            ],
            colWidths=[content_width / 2, content_width / 2],
        )
        parties_table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (0, 0), 10),
                    ("RIGHTPADDING", (1, 0), (1, 0), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )
        elements.append(parties_table)
        elements.append(Spacer(1, section_gap))

        auction_summary = (
            f"<b>Aukcja:</b> {self.order.auction} &nbsp;|&nbsp; "
            f"<b>Lot:</b> {self.order.lot_id} &nbsp;|&nbsp; "
            f"<b>VIN:</b> {self.order.vin}<br/>"
            f"<b>Pojazd:</b> {self.order.vehicle_name} &nbsp;|&nbsp; "
            f"<b>Lokalizacja:</b> {self.order.location_name}"
        )
        elements.append(Paragraph(auction_summary, body_style))
        elements.append(Spacer(1, section_gap))

        # Items
        items_table_data = [
            [
                Paragraph("<b>Opis</b>", bold_style),
                Paragraph("<b>Ilość</b>", bold_style),
                Paragraph("<b>Cena jedn.</b>", bold_style),
                Paragraph("<b>Razem</b>", bold_style),
            ]
        ]

        total_amount = 0.0
        for item in invoice_items:
            quantity = 1
            amount = float(item.amount)
            total_amount += amount
            items_table_data.append(
                [
                    Paragraph(item.name, item_text_style),
                    Paragraph(str(quantity), item_text_style),
                    Paragraph(self._format_amount(amount), item_text_style),
                    Paragraph(self._format_amount(amount), item_text_style),
                ]
            )

        items_table_data.append(
            [
                "",
                "",
                Paragraph("<b>Razem:</b>", bold_style),
                Paragraph(self._format_amount(total_amount), bold_style),
            ]
        )

        qty_col = 36
        price_col = 78
        total_col = 78
        items_table = Table(
            items_table_data,
            colWidths=[content_width - qty_col - price_col - total_col, qty_col, price_col, total_col],
            repeatRows=1,
        )
        items_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#edf2f7")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#1a202c")),
                    ("FONTNAME", (0, 0), (-1, 0), font_bold),
                    ("FONTSIZE", (0, 0), (-1, 0), body_size),
                    ("FONTNAME", (0, 1), (-1, -1), font_name),
                    ("FONTSIZE", (0, 1), (-1, -1), body_size),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e0")),
                    ("ALIGN", (1, 0), (-1, -1), "CENTER"),
                    ("ALIGN", (0, 0), (0, -1), "LEFT"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), row_pad),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), row_pad),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#f7fafc")),
                ]
            )
        )
        elements.append(items_table)
        elements.append(Spacer(1, section_gap))

        if info.delivery_terms:
            elements.append(Paragraph(f"<b>Warunki dostawy:</b> {info.delivery_terms}", delivery_terms_style))
            elements.append(Spacer(1, section_gap))

        payment_details_pln = getattr(info, "payment_details_pln", None) or info.payment_details_eur
        footer_rows = []
        if payment_details_pln:
            bank_text = "<br/>".join(str(line) for line in payment_details_pln)
            footer_rows.append(
                [
                    Paragraph(f"<b>Dane bankowe ({self.CURRENCY})</b><br/>{bank_text}", normal_style),
                    Paragraph("<i>Dziękujemy za współpracę.</i>", thank_you_style),
                ]
            )
        else:
            footer_rows.append(["", Paragraph("<i>Dziękujemy za współpracę.</i>", thank_you_style)])

        footer_table = Table(footer_rows, colWidths=[content_width * 0.65, content_width * 0.35])
        footer_table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )
        elements.append(footer_table)

        pdf.build(elements)
        buffer.seek(0)
        return buffer.read()


if __name__ == "__main__":
    class _DummyItem:
        def __init__(self, name: str, amount: int):
            self.name = name
            self.amount = amount
            self.is_extra_fee = False

    class _DummyOrder:
        def __init__(self):
            self.invoice_type = InvoiceTypeEnum.DEFAULT
            self.vin = "TESTVIN1234567890"
            self.created_at = datetime.now(timezone.utc)
            self.auction = "COPART"
            self.lot_id = 123456
            self.vehicle_name = "Test Vehicle"
            self.location_name = "Test Location"
            self.user_uuid = "c2ead8a4-36b5-49ba-b884-4ee818ec8ce9"
            self.invoice_items = [
                _DummyItem("Cena pojazdu", 10000),
                _DummyItem("Prowizja brokerska", 500),
                _DummyItem("Transport", 800),
                _DummyItem("Transport morski", 1200),
                _DummyItem("Opłata aukcyjna", 350),
            ]

    dummy_order = _DummyOrder()
    generator = InvoiceGenerator(dummy_order)  # type: ignore[arg-type]
    output_file = Path(__file__).resolve().parent / "test_invoice.pdf"
    generator.generate_invoice_based_on_invoice_type(save_path=output_file)
    print(f"Invoice generated at {output_file}")
