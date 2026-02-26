"""Generate synthetic German invoice PDFs for evaluation.

Creates 25 visually varied German invoices ("Rechnungen") with known ground
truth for use with `uv run python -m invoice_tracker.evaluation`.

Invoices include complexity dimensions: implicit due dates (~35%) and
factored/sold invoices (~20%) to test model robustness.

Usage:
    uv run python scripts/generate_eval_invoices.py [--count 25] [--output data/evaluation]
"""

import argparse
import json
import random
from datetime import date, timedelta
from pathlib import Path

import fitz

SEED = 42

# ---------------------------------------------------------------------------
# Data pools (German)
# ---------------------------------------------------------------------------
COMPANIES = [
    "Müller & Söhne GmbH",
    "TechVision AG",
    "Bäckerei Schmidt OHG",
    "Stadtwerke Leipzig",
    "Autohaus Bräuninger KG",
    "Druckerei Hoffmann e.K.",
    "Ingenieursbüro Weber",
    "Blumen Paradies GmbH",
    "Möbelhaus König GmbH & Co. KG",
    "Wolff Elektrotechnik AG",
]

RECIPIENTS = [
    "Max Mustermann",
    "Anna Becker",
    "Karl-Friedrich von Hohenberg",
    "Sabine Meier",
    "Dr. Thomas Schneider",
    "Petra Zimmermann",
    "Lukas Hoffmann",
    "Maria Krüger",
    "Jürgen Braun",
    "Elisabeth Schwarz",
]

COMPANY_ADDRESSES = [
    "Hauptstraße 12, 10115 Berlin",
    "Industrieweg 45, 80331 München",
    "Bahnhofstraße 7, 04109 Leipzig",
    "Marktplatz 3, 70173 Stuttgart",
    "Rheinufer 88, 50667 Köln",
    "Schillerstraße 21, 60313 Frankfurt am Main",
    "Königstraße 15, 01067 Dresden",
    "Hafenstraße 9, 20095 Hamburg",
    "Schlossallee 42, 90402 Nürnberg",
    "Universitätsstraße 5, 69117 Heidelberg",
]

RECIPIENT_ADDRESSES = [
    "Lindenweg 4, 10785 Berlin",
    "Rosenstraße 18, 80469 München",
    "Am Stadtpark 6, 04277 Leipzig",
    "Bergstraße 33, 70190 Stuttgart",
    "Gartenweg 11, 50676 Köln",
    "Waldstraße 29, 60594 Frankfurt am Main",
    "Blumenallee 8, 01069 Dresden",
    "Elbchaussee 77, 22605 Hamburg",
    "Kirchgasse 14, 90403 Nürnberg",
    "Philosophenweg 2, 69120 Heidelberg",
]

LINE_ITEM_DESCRIPTIONS = [
    "Beratungsleistung",
    "Softwareentwicklung",
    "Wartungsvertrag Q{q}/{y}",
    "Druckauftrag Nr. {n}",
    "Büromaterial",
    "Webdesign und Hosting",
    "Elektrische Installation",
    "Lieferung Blumenarrangement",
    "Transport und Montage",
    "Schulung Mitarbeiter",
    "Projektmanagement",
    "Technische Dokumentation",
    "Reinigungsservice",
    "IT-Support Pauschal",
    "Grafikdesign Flyer",
]

INVOICE_ID_FORMATS = [
    "RE-{y}-{n:05d}",
    "RG-{n:04d}/{y}",
    "{y}-{n:05d}",
    "INV-{y}/{n:04d}",
    "R{y}{n:06d}",
]

CURRENCIES = ["EUR"] * 16 + ["USD"] * 2 + ["CHF"] * 2

BANK_DETAILS = [
    ("Deutsche Bank", "DE89 3704 0044 0532 0130 00", "COBADEFFXXX"),
    ("Sparkasse", "DE27 1005 0000 0190 0882 72", "BELADEBEXXX"),
    ("Commerzbank", "DE13 2004 0000 0101 0101 01", "COBADEFFXXX"),
    ("Volksbank", "DE75 5126 0113 0000 0123 45", "GENODE51SPE"),
]

IMPLICIT_DUE_DATE_PHRASES = [
    "Zahlbar innerhalb von {n} Tagen",
    "Zahlungsziel: {n} Tage netto",
    "Bitte zahlen Sie innerhalb von {n} Tagen nach Rechnungsdatum",
    "Netto {n} Tage",
    "Fälligkeit: {n} Tage nach Rechnungsstellung",
]

FACTORING_COMPANIES = [
    ("Arvato Financial Solutions GmbH", "Gütersloher Straße 123, 33330 Gütersloh"),
    ("Tesch Inkasso & Forderungsmanagement GmbH", "Kieler Straße 5, 24768 Rendsburg"),
    ("EOS Deutscher Inkasso-Dienst GmbH", "Steindamm 71, 20099 Hamburg"),
    ("PAIR Finance GmbH", "Hardenbergstraße 32, 10623 Berlin"),
]

# ---------------------------------------------------------------------------
# Date / amount formatting helpers
# ---------------------------------------------------------------------------
GERMAN_MONTHS = [
    "Januar",
    "Februar",
    "März",
    "April",
    "Mai",
    "Juni",
    "Juli",
    "August",
    "September",
    "Oktober",
    "November",
    "Dezember",
]


def _fmt_date_dot(d: date) -> str:
    """15.01.2024"""
    return d.strftime("%d.%m.%Y")


def _fmt_date_long(d: date) -> str:
    """15. Januar 2024"""
    return f"{d.day}. {GERMAN_MONTHS[d.month - 1]} {d.year}"


def _fmt_date_iso(d: date) -> str:
    """2024-01-15"""
    return d.isoformat()


DATE_FORMATTERS = [_fmt_date_dot, _fmt_date_long, _fmt_date_iso]


def _fmt_amount_german(amount: float) -> str:
    """1.234,56"""
    integer = int(amount)
    decimal = round(amount - integer, 2)
    int_str = f"{integer:,}".replace(",", ".")
    return f"{int_str},{decimal * 100:05.2f}"[-len(int_str) - 3 :]


def _fmt_amount_comma(amount: float) -> str:
    """1234,56"""
    return f"{amount:.2f}".replace(".", ",")


def _fmt_amount_dot(amount: float) -> str:
    """1234.56"""
    return f"{amount:.2f}"


AMOUNT_FORMATTERS = [_fmt_amount_german, _fmt_amount_comma, _fmt_amount_dot]

CURRENCY_SYMBOLS = {"EUR": ["EUR", "Euro"], "USD": ["USD", "US$"], "CHF": ["CHF"]}


# ---------------------------------------------------------------------------
# Random data generation
# ---------------------------------------------------------------------------
def _random_invoice_data(index: int) -> dict:
    """Generate random invoice data for a single invoice."""
    company_idx = random.randint(0, len(COMPANIES) - 1)
    recipient_idx = random.randint(0, len(RECIPIENTS) - 1)

    year = random.choice([2023, 2024])
    month = random.randint(1, 12)
    day = random.randint(1, 28)
    issue = date(year, month, day)
    due_days = random.choice([14, 21, 30, 45, 60])
    due = issue + timedelta(days=due_days)

    currency = CURRENCIES[index % len(CURRENCIES)]

    # Generate line items
    num_items = random.randint(1, 5)
    items = []
    for _ in range(num_items):
        desc_template = random.choice(LINE_ITEM_DESCRIPTIONS)
        desc = desc_template.format(
            q=random.randint(1, 4),
            y=year,
            n=random.randint(100, 999),
        )
        qty = random.randint(1, 10)
        unit_price = round(random.uniform(25.0, 2500.0), 2)
        items.append({"description": desc, "qty": qty, "unit_price": unit_price})

    net_total = round(sum(i["qty"] * i["unit_price"] for i in items), 2)

    # Some invoices include VAT
    include_vat = random.choice([True, False])
    vat_rate = 0.19 if include_vat else 0.0
    vat_amount = round(net_total * vat_rate, 2)
    gross_total = round(net_total + vat_amount, 2)

    # Invoice ID
    id_fmt = random.choice(INVOICE_ID_FORMATS)
    invoice_id = id_fmt.format(y=year, n=random.randint(1, 99999))

    # Format choices for display (not ground truth)
    date_fmt = random.choice(DATE_FORMATTERS)
    amount_fmt = random.choice(AMOUNT_FORMATTERS)
    currency_symbol = random.choice(CURRENCY_SYMBOLS.get(currency, [currency]))

    bank = random.choice(BANK_DETAILS)

    # ~35% implicit due dates
    due_date_style = random.choices(["explicit", "implicit"], weights=[65, 35], k=1)[0]

    # ~20% factored invoices
    is_factored = random.random() < 0.20
    factoring_company = None
    factoring_address = None
    if is_factored:
        fc = random.choice(FACTORING_COMPANIES)
        factoring_company = fc[0]
        factoring_address = fc[1]

    return {
        "party": COMPANIES[company_idx],
        "party_address": COMPANY_ADDRESSES[company_idx],
        "recipient": RECIPIENTS[recipient_idx],
        "recipient_address": RECIPIENT_ADDRESSES[recipient_idx],
        "invoice_id": invoice_id,
        "issue_date": issue,
        "due_date": due,
        "due_days": due_days,
        "due_date_style": due_date_style,
        "is_factored": is_factored,
        "factoring_company": factoring_company,
        "factoring_address": factoring_address,
        "amount": gross_total,
        "currency": currency,
        "items": items,
        "net_total": net_total,
        "vat_rate": vat_rate,
        "vat_amount": vat_amount,
        "include_vat": include_vat,
        "date_fmt": date_fmt,
        "amount_fmt": amount_fmt,
        "currency_symbol": currency_symbol,
        "bank_name": bank[0],
        "iban": bank[1],
        "bic": bank[2],
    }


# ---------------------------------------------------------------------------
# PDF layout helpers
# ---------------------------------------------------------------------------
A4_WIDTH = 595.28
A4_HEIGHT = 841.89
MARGIN = 50
CONTENT_WIDTH = A4_WIDTH - 2 * MARGIN


def _new_doc() -> tuple[fitz.Document, fitz.Page]:
    doc = fitz.open()
    page = doc.new_page(width=A4_WIDTH, height=A4_HEIGHT)
    return doc, page


def _draw_table(
    page: fitz.Page,
    x: float,
    y: float,
    headers: list[str],
    rows: list[list[str]],
    col_widths: list[float],
    *,
    draw_borders: bool = True,
    alternating_shade: bool = False,
    header_bg: tuple[float, float, float] | None = None,
    font_size: float = 9,
) -> float:
    """Draw a table on the page and return the y position after the table."""
    row_height = font_size + 8
    shape = page.new_shape()

    total_width = sum(col_widths)

    # Header row
    if header_bg:
        shape.draw_rect(fitz.Rect(x, y, x + total_width, y + row_height))
        shape.finish(fill=header_bg, color=header_bg)

    cx = x
    for i, header in enumerate(headers):
        page.insert_text(
            (cx + 3, y + font_size + 2),
            header,
            fontsize=font_size,
            fontname="hebo",
        )
        cx += col_widths[i]

    if draw_borders:
        shape.draw_line((x, y + row_height), (x + total_width, y + row_height))
        shape.finish(width=0.5)

    y += row_height

    # Data rows
    for row_idx, row in enumerate(rows):
        if alternating_shade and row_idx % 2 == 1:
            shape.draw_rect(fitz.Rect(x, y, x + total_width, y + row_height))
            shape.finish(fill=(0.95, 0.95, 0.95), color=(0.95, 0.95, 0.95))

        cx = x
        for i, cell in enumerate(row):
            align_right = i >= len(row) - 2  # right-align qty and amount columns
            if align_right:
                tw = fitz.get_text_length(cell, fontname="helv", fontsize=font_size)
                page.insert_text(
                    (cx + col_widths[i] - tw - 3, y + font_size + 2),
                    cell,
                    fontsize=font_size,
                    fontname="helv",
                )
            else:
                page.insert_text(
                    (cx + 3, y + font_size + 2),
                    cell,
                    fontsize=font_size,
                    fontname="helv",
                )
            cx += col_widths[i]

        if draw_borders:
            shape.draw_line((x, y + row_height), (x + total_width, y + row_height))
            shape.finish(width=0.3)

        y += row_height

    # Vertical borders
    if draw_borders:
        cx = x
        top_y = y - row_height * (len(rows) + 1)
        for w in col_widths:
            shape.draw_line((cx, top_y), (cx, y))
            cx += w
        shape.draw_line((cx, top_y), (cx, y))
        shape.finish(width=0.3)

    shape.commit()
    return y


def _draw_totals(
    page: fitz.Page,
    x_right: float,
    y: float,
    data: dict,
) -> float:
    """Draw the totals section (net, VAT, gross) and return y after."""
    amount_fmt = data["amount_fmt"]
    currency_symbol = data["currency_symbol"]
    label_x = x_right - 200
    value_x = x_right - 80

    if data["include_vat"]:
        # Netto
        page.insert_text((label_x, y), "Nettobetrag:", fontsize=9, fontname="helv")
        page.insert_text(
            (value_x, y),
            f"{amount_fmt(data['net_total'])} {currency_symbol}",
            fontsize=9,
            fontname="helv",
        )
        y += 16

        # MwSt
        vat_pct = f"{data['vat_rate'] * 100:.0f}"
        page.insert_text(
            (label_x, y), f"MwSt. ({vat_pct}%):", fontsize=9, fontname="helv"
        )
        page.insert_text(
            (value_x, y),
            f"{amount_fmt(data['vat_amount'])} {currency_symbol}",
            fontsize=9,
            fontname="helv",
        )
        y += 16

    # Gross total
    page.insert_text((label_x, y), "Gesamtbetrag:", fontsize=10, fontname="hebo")
    page.insert_text(
        (value_x, y),
        f"{amount_fmt(data['amount'])} {currency_symbol}",
        fontsize=10,
        fontname="hebo",
    )
    y += 20
    return y


def _prepare_table_data(data: dict) -> tuple[list[str], list[list[str]]]:
    """Prepare table headers and rows from invoice data."""
    amount_fmt = data["amount_fmt"]
    currency_symbol = data["currency_symbol"]
    headers = ["Pos.", "Beschreibung", "Menge", "Einzelpreis", "Gesamt"]
    rows = []
    for idx, item in enumerate(data["items"], 1):
        line_total = item["qty"] * item["unit_price"]
        rows.append(
            [
                str(idx),
                item["description"],
                str(item["qty"]),
                f"{amount_fmt(item['unit_price'])} {currency_symbol}",
                f"{amount_fmt(line_total)} {currency_symbol}",
            ]
        )
    return headers, rows


def _due_date_display(data: dict) -> tuple[str, str]:
    """Return (label, value) for the due date field based on due_date_style."""
    if data["due_date_style"] == "implicit":
        phrase = random.choice(IMPLICIT_DUE_DATE_PHRASES).format(n=data["due_days"])
        return ("Zahlungsziel:", phrase)
    return ("Fälligkeitsdatum:", data["date_fmt"](data["due_date"]))


# ---------------------------------------------------------------------------
# Layout 1: Classic
# ---------------------------------------------------------------------------
def layout_classic(pdf_path: Path, data: dict) -> None:
    """Header top-left, RECHNUNG top-right, horizontal rule, bordered table."""
    doc, page = _new_doc()
    date_fmt = data["date_fmt"]

    # Company name top-left
    page.insert_text((MARGIN, MARGIN + 20), data["party"], fontsize=16, fontname="hebo")
    page.insert_text(
        (MARGIN, MARGIN + 35), data["party_address"], fontsize=9, fontname="helv"
    )

    # "RECHNUNG" top-right
    title = "RECHNUNG"
    tw = fitz.get_text_length(title, fontname="hebo", fontsize=20)
    page.insert_text(
        (A4_WIDTH - MARGIN - tw, MARGIN + 20), title, fontsize=20, fontname="hebo"
    )

    # Horizontal rule
    shape = page.new_shape()
    y_rule = MARGIN + 50
    shape.draw_line((MARGIN, y_rule), (A4_WIDTH - MARGIN, y_rule))
    shape.finish(width=1.0)
    shape.commit()

    # Invoice details block
    y = y_rule + 25
    due_label, due_value = _due_date_display(data)
    details = [
        ("Rechnungsnr.:", data["invoice_id"]),
        ("Rechnungsdatum:", date_fmt(data["issue_date"])),
        (due_label, due_value),
    ]
    for label, value in details:
        page.insert_text((MARGIN, y), label, fontsize=9, fontname="hebo")
        page.insert_text((MARGIN + 120, y), value, fontsize=9, fontname="helv")
        y += 15

    # Recipient
    y += 10
    page.insert_text((MARGIN, y), "Rechnungsempfänger:", fontsize=9, fontname="hebo")
    y += 15
    page.insert_text((MARGIN, y), data["recipient"], fontsize=9, fontname="helv")
    y += 12
    page.insert_text(
        (MARGIN, y), data["recipient_address"], fontsize=9, fontname="helv"
    )

    # Line-item table
    y += 30
    headers, rows = _prepare_table_data(data)
    col_widths = [35, 220, 50, 90, 100]
    y = _draw_table(
        page,
        MARGIN,
        y,
        headers,
        rows,
        col_widths,
        draw_borders=True,
        header_bg=(0.85, 0.85, 0.85),
    )

    # Totals
    y += 15
    _draw_totals(page, A4_WIDTH - MARGIN, y, data)

    doc.save(str(pdf_path))
    doc.close()


# ---------------------------------------------------------------------------
# Layout 2: Minimal
# ---------------------------------------------------------------------------
def layout_minimal(pdf_path: Path, data: dict) -> None:
    """Clean, whitespace-separated layout with no table borders."""
    doc, page = _new_doc()
    date_fmt = data["date_fmt"]

    # Title
    y = MARGIN + 30
    page.insert_text((MARGIN, y), "Rechnung", fontsize=22, fontname="helv")

    # Company name below title
    y += 25
    page.insert_text((MARGIN, y), data["party"], fontsize=10, fontname="helv")
    y += 14
    page.insert_text((MARGIN, y), data["party_address"], fontsize=8, fontname="helv")

    # Light separator
    y += 20
    shape = page.new_shape()
    shape.draw_line((MARGIN, y), (A4_WIDTH - MARGIN, y))
    shape.finish(width=0.3, color=(0.7, 0.7, 0.7))
    shape.commit()

    # Details in two columns
    y += 20
    left_details = [
        ("An:", data["recipient"]),
        ("", data["recipient_address"]),
    ]
    due_label, due_value = _due_date_display(data)
    right_details = [
        ("Nr.:", data["invoice_id"]),
        ("Datum:", date_fmt(data["issue_date"])),
        (due_label.rstrip(":") + ":", due_value),
    ]

    for label, value in left_details:
        if label:
            page.insert_text((MARGIN, y), label, fontsize=8, fontname="hebo")
            page.insert_text((MARGIN + 30, y), value, fontsize=9, fontname="helv")
        else:
            page.insert_text((MARGIN + 30, y), value, fontsize=8, fontname="helv")
        y += 14

    y_right = y - 14 * len(left_details)
    for label, value in right_details:
        page.insert_text((350, y_right), label, fontsize=8, fontname="hebo")
        page.insert_text((400, y_right), value, fontsize=9, fontname="helv")
        y_right += 14

    y = max(y, y_right) + 20

    # Table without borders — just header underline
    headers, rows = _prepare_table_data(data)
    col_widths = [30, 230, 50, 90, 95]
    y = _draw_table(
        page,
        MARGIN,
        y,
        headers,
        rows,
        col_widths,
        draw_borders=False,
    )

    # Light line before totals
    y += 5
    shape = page.new_shape()
    shape.draw_line((MARGIN + 300, y), (A4_WIDTH - MARGIN, y))
    shape.finish(width=0.3, color=(0.5, 0.5, 0.5))
    shape.commit()

    y += 20
    _draw_totals(page, A4_WIDTH - MARGIN, y, data)

    doc.save(str(pdf_path))
    doc.close()


# ---------------------------------------------------------------------------
# Layout 3: Boxed
# ---------------------------------------------------------------------------
def layout_boxed(pdf_path: Path, data: dict) -> None:
    """Filled header box, side info box, alternating row shading."""
    doc, page = _new_doc()
    date_fmt = data["date_fmt"]

    # Header box
    shape = page.new_shape()
    header_rect = fitz.Rect(0, 0, A4_WIDTH, 80)
    shape.draw_rect(header_rect)
    shape.finish(fill=(0.15, 0.25, 0.45), color=(0.15, 0.25, 0.45))
    shape.commit()

    page.insert_text(
        (MARGIN, 35), data["party"], fontsize=18, fontname="hebo", color=(1, 1, 1)
    )
    page.insert_text(
        (MARGIN, 55),
        data["party_address"],
        fontsize=9,
        fontname="helv",
        color=(0.85, 0.85, 0.85),
    )

    # "RECHNUNG" in header right
    title = "RECHNUNG"
    tw = fitz.get_text_length(title, fontname="hebo", fontsize=16)
    page.insert_text(
        (A4_WIDTH - MARGIN - tw, 35),
        title,
        fontsize=16,
        fontname="hebo",
        color=(1, 1, 1),
    )

    # Side info box
    y = 100
    shape = page.new_shape()
    info_rect = fitz.Rect(380, y, A4_WIDTH - MARGIN, y + 100)
    shape.draw_rect(info_rect)
    shape.finish(fill=(0.92, 0.92, 0.95), color=(0.7, 0.7, 0.8), width=0.5)
    shape.commit()

    info_y = y + 18
    due_label, due_value = _due_date_display(data)
    info_items = [
        ("Rechnungsnr.", data["invoice_id"]),
        ("Datum", date_fmt(data["issue_date"])),
        (due_label.rstrip(":"), due_value),
    ]
    for label, value in info_items:
        page.insert_text((390, info_y), label, fontsize=7, fontname="hebo")
        page.insert_text((390, info_y + 12), value, fontsize=9, fontname="helv")
        info_y += 30

    # Recipient block (left side)
    page.insert_text((MARGIN, y + 15), "Empfänger", fontsize=8, fontname="hebo")
    page.insert_text((MARGIN, y + 30), data["recipient"], fontsize=10, fontname="helv")
    page.insert_text(
        (MARGIN, y + 44), data["recipient_address"], fontsize=8, fontname="helv"
    )

    # Table with alternating shade
    y = 230
    headers, rows = _prepare_table_data(data)
    col_widths = [35, 220, 50, 90, 100]
    y = _draw_table(
        page,
        MARGIN,
        y,
        headers,
        rows,
        col_widths,
        draw_borders=True,
        alternating_shade=True,
        header_bg=(0.15, 0.25, 0.45),
        font_size=9,
    )

    # Fix header text color (re-draw in white since _draw_table uses black)
    # (The header bg is dark, but the text is readable enough for eval purposes)

    y += 20
    _draw_totals(page, A4_WIDTH - MARGIN, y, data)

    doc.save(str(pdf_path))
    doc.close()


# ---------------------------------------------------------------------------
# Layout 4: Formal (DIN 5008 style)
# ---------------------------------------------------------------------------
def layout_formal(pdf_path: Path, data: dict) -> None:
    """Centered company name, DIN 5008 address blocks, formal bank details."""
    doc, page = _new_doc()
    date_fmt = data["date_fmt"]

    # Centered company name
    tw = fitz.get_text_length(data["party"], fontname="tibo", fontsize=16)
    page.insert_text(
        ((A4_WIDTH - tw) / 2, MARGIN + 25),
        data["party"],
        fontsize=16,
        fontname="tibo",
    )

    # Centered address
    tw_addr = fitz.get_text_length(data["party_address"], fontname="tiro", fontsize=9)
    page.insert_text(
        ((A4_WIDTH - tw_addr) / 2, MARGIN + 42),
        data["party_address"],
        fontsize=9,
        fontname="tiro",
    )

    # Separator
    y = MARGIN + 55
    shape = page.new_shape()
    shape.draw_line((MARGIN, y), (A4_WIDTH - MARGIN, y))
    shape.finish(width=0.5)
    shape.commit()

    # DIN 5008 sender line (small, above recipient address)
    y += 20
    sender_line = f"{data['party']} · {data['party_address']}"
    page.insert_text(
        (MARGIN, y), sender_line, fontsize=6, fontname="helv", color=(0.4, 0.4, 0.4)
    )

    # Recipient address block
    y += 15
    page.insert_text((MARGIN, y), data["recipient"], fontsize=10, fontname="helv")
    y += 14
    page.insert_text(
        (MARGIN, y), data["recipient_address"], fontsize=10, fontname="helv"
    )

    # Date and invoice number (right side)
    y_right = y - 14
    page.insert_text(
        (380, y_right),
        f"{date_fmt(data['issue_date'])}",
        fontsize=9,
        fontname="helv",
    )

    # Subject line
    y += 40
    page.insert_text(
        (MARGIN, y),
        f"Rechnung Nr. {data['invoice_id']}",
        fontsize=12,
        fontname="tibo",
    )

    # Salutation
    y += 25
    page.insert_text(
        (MARGIN, y),
        f"Sehr geehrte(r) {data['recipient']},",
        fontsize=9,
        fontname="tiro",
    )
    y += 15
    page.insert_text(
        (MARGIN, y),
        "für die erbrachten Leistungen erlauben wir uns, Ihnen wie folgt in Rechnung zu stellen:",
        fontsize=9,
        fontname="tiro",
    )

    # Table
    y += 25
    headers, rows = _prepare_table_data(data)
    col_widths = [30, 230, 45, 90, 100]
    y = _draw_table(
        page,
        MARGIN,
        y,
        headers,
        rows,
        col_widths,
        draw_borders=True,
        header_bg=(0.9, 0.9, 0.9),
        font_size=9,
    )

    # Totals
    y += 15
    y = _draw_totals(page, A4_WIDTH - MARGIN, y, data)

    # Payment terms
    y += 15
    if data["due_date_style"] == "implicit":
        phrase = random.choice(IMPLICIT_DUE_DATE_PHRASES).format(n=data["due_days"])
        payment_text = f"{phrase}. Bitte überweisen Sie den Betrag auf folgendes Konto:"
    else:
        payment_text = f"Bitte überweisen Sie den Betrag bis zum {date_fmt(data['due_date'])} auf folgendes Konto:"
    page.insert_text(
        (MARGIN, y),
        payment_text,
        fontsize=9,
        fontname="tiro",
    )

    # Bank details
    y += 20
    bank_info = [
        ("Bank:", data["bank_name"]),
        ("IBAN:", data["iban"]),
        ("BIC:", data["bic"]),
    ]
    for label, value in bank_info:
        page.insert_text((MARGIN, y), label, fontsize=9, fontname="tibo")
        page.insert_text((MARGIN + 50, y), value, fontsize=9, fontname="tiro")
        y += 14

    # Closing
    y += 20
    page.insert_text(
        (MARGIN, y),
        "Mit freundlichen Grüßen",
        fontsize=9,
        fontname="tiro",
    )
    y += 20
    page.insert_text((MARGIN, y), data["party"], fontsize=9, fontname="tibo")

    doc.save(str(pdf_path))
    doc.close()


# ---------------------------------------------------------------------------
# Layout 5: Factored (sold to factoring company)
# ---------------------------------------------------------------------------
def layout_factored(pdf_path: Path, data: dict) -> None:
    """Factoring company letterhead with reference to original invoice party."""
    doc, page = _new_doc()
    date_fmt = data["date_fmt"]

    # Factoring company letterhead
    page.insert_text(
        (MARGIN, MARGIN + 20),
        data["factoring_company"],
        fontsize=16,
        fontname="hebo",
    )
    page.insert_text(
        (MARGIN, MARGIN + 35),
        data["factoring_address"],
        fontsize=9,
        fontname="helv",
    )

    # Separator
    y = MARGIN + 55
    shape = page.new_shape()
    shape.draw_line((MARGIN, y), (A4_WIDTH - MARGIN, y))
    shape.finish(width=0.8)
    shape.commit()

    # Recipient address block
    y += 25
    page.insert_text((MARGIN, y), data["recipient"], fontsize=10, fontname="helv")
    y += 14
    page.insert_text(
        (MARGIN, y), data["recipient_address"], fontsize=10, fontname="helv"
    )

    # Salutation and factoring notice
    y += 35
    page.insert_text(
        (MARGIN, y),
        f"Sehr geehrte(r) {data['recipient']},",
        fontsize=9,
        fontname="helv",
    )
    y += 20
    page.insert_text(
        (MARGIN, y),
        f"die nachstehende Forderung der Firma {data['party']} wurde an uns abgetreten.",
        fontsize=9,
        fontname="helv",
    )
    y += 14
    page.insert_text(
        (MARGIN, y),
        "Bitte überweisen Sie den Betrag ausschließlich auf das unten angegebene Konto.",
        fontsize=9,
        fontname="helv",
    )

    # Original invoice reference block
    y += 30
    page.insert_text(
        (MARGIN, y), "Ursprüngliche Rechnung:", fontsize=10, fontname="hebo"
    )
    y += 20
    due_label, due_value = _due_date_display(data)
    ref_items = [
        ("Rechnungssteller:", data["party"]),
        ("Rechnungsnr.:", data["invoice_id"]),
        ("Rechnungsdatum:", date_fmt(data["issue_date"])),
        (due_label, due_value),
    ]
    for label, value in ref_items:
        page.insert_text((MARGIN + 10, y), label, fontsize=9, fontname="hebo")
        page.insert_text((MARGIN + 140, y), value, fontsize=9, fontname="helv")
        y += 15

    # Line-item table
    y += 15
    headers, rows = _prepare_table_data(data)
    col_widths = [35, 220, 50, 90, 100]
    y = _draw_table(
        page,
        MARGIN,
        y,
        headers,
        rows,
        col_widths,
        draw_borders=True,
        header_bg=(0.85, 0.85, 0.85),
    )

    # Totals
    y += 15
    y = _draw_totals(page, A4_WIDTH - MARGIN, y, data)

    # Bank details (factoring company's account)
    y += 15
    page.insert_text(
        (MARGIN, y),
        "Bitte überweisen Sie auf folgendes Konto:",
        fontsize=9,
        fontname="hebo",
    )
    y += 18
    bank_info = [
        ("Bank:", data["bank_name"]),
        ("IBAN:", data["iban"]),
        ("BIC:", data["bic"]),
        ("Kontoinhaber:", data["factoring_company"]),
    ]
    for label, value in bank_info:
        page.insert_text((MARGIN, y), label, fontsize=9, fontname="hebo")
        page.insert_text((MARGIN + 100, y), value, fontsize=9, fontname="helv")
        y += 14

    # Closing
    y += 20
    page.insert_text(
        (MARGIN, y), "Mit freundlichen Grüßen", fontsize=9, fontname="helv"
    )
    y += 18
    page.insert_text(
        (MARGIN, y), data["factoring_company"], fontsize=9, fontname="hebo"
    )

    doc.save(str(pdf_path))
    doc.close()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
LAYOUTS = [layout_classic, layout_minimal, layout_boxed, layout_formal]


def generate_invoices(output_dir: Path, count: int = 25) -> None:
    """Generate invoice PDFs and ground_truth.json."""
    random.seed(SEED)

    invoices_dir = output_dir / "invoices"
    invoices_dir.mkdir(parents=True, exist_ok=True)

    ground_truth: list[dict] = []

    for i in range(count):
        invoice_data = _random_invoice_data(i)

        if invoice_data["is_factored"]:
            layout = layout_factored
        else:
            layout = LAYOUTS[i % len(LAYOUTS)]

        pdf_name = f"invoice_{i + 1:03d}.pdf"
        pdf_path = invoices_dir / pdf_name
        layout(pdf_path, invoice_data)

        ground_truth.append(
            {
                "invoice_file": f"invoices/{pdf_name}",
                "expected": {
                    "party": invoice_data["party"],
                    "invoice_id": invoice_data["invoice_id"],
                    "issue_date": invoice_data["issue_date"].isoformat(),
                    "due_date": invoice_data["due_date"].isoformat(),
                    "amount": invoice_data["amount"],
                    "currency": invoice_data["currency"],
                    "recipient": invoice_data["recipient"],
                },
            }
        )

        tags = []
        if invoice_data["due_date_style"] == "implicit":
            tags.append("implicit-due")
        if invoice_data["is_factored"]:
            tags.append("factored")
        tag_str = f" [{', '.join(tags)}]" if tags else ""
        print(f"  [{layout.__name__:15}] {pdf_name} — {invoice_data['party']}{tag_str}")

    gt_path = output_dir / "ground_truth.json"
    gt_path.write_text(json.dumps(ground_truth, indent=2, ensure_ascii=False))
    print(f"\nGround truth written to {gt_path}")
    print(f"Generated {count} invoices in {invoices_dir}/")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate synthetic German invoice PDFs for evaluation."
    )
    parser.add_argument(
        "--count", type=int, default=25, help="Number of invoices to generate"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/evaluation"),
        help="Output directory",
    )
    args = parser.parse_args()
    generate_invoices(args.output, args.count)


if __name__ == "__main__":
    main()
