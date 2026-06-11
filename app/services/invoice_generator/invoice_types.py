from pathlib import Path

from pydantic import BaseModel, Field

_INVOICE_DIR = Path(__file__).resolve().parent


class BaseInvoice(BaseModel):
    company_name: str
    logo_path: str | None = None
    header_subtitle: str | None = None
    payment_details_usd: list[str] = Field(default_factory=list)
    payment_details_eur: list[str] = Field(default_factory=list)
    delivery_terms: str | None = None
    company_info_lines: list[str] = Field(default_factory=list)


class InvoiceTypes:
    @classmethod
    def get_default_info(cls) -> BaseInvoice:
        logo_path = str(_INVOICE_DIR / "images" / "bidmax_logo.png")
        delivery_terms = (
            ""
        )

        return BaseInvoice(
            company_name='BIDMAX.EU',
            logo_path=logo_path,
            header_subtitle=None,
            company_info_lines=[
                'UAB "HVJ LOGISTIC"',
                "Kod firmy: 306661666",
                "Numer VAT: LT100016791816",
                "ul. V. Nagevičiaus 3, Wilno, Litwa",
                "SEB — LT887044090108483458",
            ],
            payment_details_usd=[],
            payment_details_eur=[
                "Bank: SEB",
                "Numer IBAN: LT887044090108483458",
            ],
            delivery_terms=delivery_terms,
        )
