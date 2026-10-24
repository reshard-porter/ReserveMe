"""Printable documents: confirmations, registration cards, bills/invoices, reports."""
from __future__ import annotations

import html
from decimal import Decimal

from PySide6.QtCore import QMarginsF, QSizeF
from PySide6.QtGui import QPageLayout, QPageSize, QPdfWriter, QTextDocument
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import QDialog, QFileDialog, QTextBrowser, QVBoxLayout

from ..services.common import settings
from .common import button, fmt_date, fmt_dt, fmt_money, hbox, info, state

CSS = """
body { font-family: 'Helvetica Neue', Arial, sans-serif; font-size: 10pt; color: #1f2a33; }
h1 { font-size: 18pt; margin: 0; color: #2f8f38; }
h2 { font-size: 13pt; margin: 14px 0 6px 0; }
.muted { color: #6b7785; }
table { border-collapse: collapse; width: 100%; }
th { background: #eef1f4; text-align: left; padding: 5px; border-bottom: 1px solid #c5ccd3; }
td { padding: 4px 5px; border-bottom: 1px solid #edf0f2; }
td.num, th.num { text-align: right; }
.total td { font-weight: bold; border-top: 1px solid #1f2a33; }
.box { border: 1px solid #c5ccd3; padding: 8px; }
"""


def e(v) -> str:
    return html.escape("" if v is None else str(v))


def _header(st, title: str, right: str = "") -> str:
    contact = " · ".join(x for x in (st.address, st.phone, st.email, st.website) if x)
    tax = f"<br/>Tax reg.: {e(st.tax_registration)}" if st.tax_registration else ""
    return (f"<table><tr><td style='border:none'><h1>{e(st.name)}</h1><span class='muted'>{e(contact)}{tax}</span></td>"
            f"<td style='border:none; text-align:right; vertical-align:top'><h2>{e(title)}</h2>{right}</td></tr></table>")


def wrap(body: str) -> str:
    # QTextDocument honours table width only as an attribute.
    body = body.replace("<table", "<table width='100%' cellspacing='0' cellpadding='4'")
    return f"<html><head><style>{CSS}</style></head><body>{body}</body></html>"


def stay_block(res) -> str:
    g = res.guest
    return (f"<table class='box'><tr><td style='border:none'><b>Guest</b><br/>{e(g.full_name)}<br/>{e(g.email)}"
            f"<br/>{e(g.phone)}<br/>{e(g.address)}</td>"
            f"<td style='border:none'><b>Reservation</b> {e(res.code)}<br/>Arrival: {fmt_date(res.check_in)}"
            f"<br/>Departure: {fmt_date(res.check_out)}<br/>Nights: {res.nights}</td>"
            f"<td style='border:none'><b>Room</b><br/>{e(res.room.number if res.room else 'To be assigned')}"
            f"<br/>{e(res.room_type.name)}<br/>{e(res.rate_plan.name)}<br/>Guests: {res.adults} adult(s)"
            f"{', ' + str(res.children) + ' child(ren)' if res.children else ''}</td></tr></table>")


def confirmation_html(s, res, quote) -> str:
    st = settings(s)
    cur = st.base_currency
    rows = "".join(f"<tr><td>{fmt_date(n.date)}</td><td>{e(n.season or '')}</td>"
                   f"<td class='num'>{fmt_money(n.amount)}</td></tr>" for n in quote.nights)
    taxes = "".join(f"<tr><td colspan='2'>{e(t.name)}</td><td class='num'>{fmt_money(t.amount)}</td></tr>"
                    for t in quote.taxes)
    body = (_header(st, "Booking confirmation", f"{e(res.code)}<br/>{fmt_date(state.business_date)}")
            + f"<p>Dear {e(res.guest.first_name)},<br/>thank you for your reservation. Here are the details.</p>"
            + stay_block(res)
            + f"<h2>Price ({e(cur)})</h2><table><tr><th>Night</th><th>Season</th><th class='num'>Rate</th></tr>"
            + rows + taxes
            + f"<tr class='total'><td colspan='2'>Estimated total</td><td class='num'>{fmt_money(quote.total)}</td></tr></table>"
            + f"<p>Check-in from {e(st.check_in_time)} · Check-out by {e(st.check_out_time)}</p>"
            + (f"<p><b>Notes:</b> {e(res.notes)}</p>" if res.notes else "")
            + f"<p class='muted'>{e(st.invoice_footer or '')}</p>")
    return wrap(body)


def registration_card_html(s, res) -> str:
    st = settings(s)
    g = res.guest
    body = (_header(st, "Registration card", e(res.code)) + stay_block(res)
            + "<h2>Guest details</h2><table>"
            + "".join(f"<tr><td style='width:35%'>{k}</td><td>{e(v) if v else '&nbsp;'}</td></tr>" for k, v in (
                ("Full name", g.full_name), ("Nationality", g.nationality), ("ID / passport type", g.id_type),
                ("ID / passport number", g.id_number), ("Date of birth", fmt_date(g.date_of_birth)),
                ("Address", g.address), ("Email", g.email), ("Phone", g.phone), ("Company", g.company)))
            + "</table><p>I agree to pay all charges incurred during my stay. Check-out time is "
            + f"{e(st.check_out_time)}.</p><br/><br/>"
            + "<table><tr><td style='border:none'>Guest signature: ______________________________</td>"
            + "<td style='border:none'>Date: ______________</td></tr></table>")
    return wrap(body)


def folio_html(s, res, summary, invoice=None) -> str:
    st = settings(s)
    title = "Invoice" if invoice else "Guest bill"
    right = (f"{e(invoice.number)}<br/>{fmt_dt(invoice.issued_at)}" if invoice
             else f"Printed {fmt_date(state.business_date)}")
    rows = []
    for l in summary.lines:
        rows.append(f"<tr><td>{fmt_date(l.stay_date or l.business_date)}</td><td>{e(l.description)}"
                    + (f" <span class='muted'>({e(l.original_currency)} {fmt_money(l.original_amount)} @ "
                       f"{l.exchange_rate})</span>" if l.original_currency else "")
                    + (f" <span class='muted'>Ref {e(l.reference)}</span>" if l.reference else "")
                    + f"</td><td class='num'>{fmt_money(l.amount) if l.amount > 0 else ''}</td>"
                    f"<td class='num'>{fmt_money(-l.amount) if l.amount < 0 else ''}</td></tr>")
    cur = st.base_currency
    alt = ""
    if st.alt_currency and st.alt_rate and Decimal(st.alt_rate) != 1:
        alt = (f"<p class='muted'>Balance in {e(st.alt_currency)} at {st.alt_rate}: "
               f"{fmt_money(summary.balance * Decimal(st.alt_rate))}</p>")
    body = (_header(st, title, right) + stay_block(res)
            + f"<h2>Charges and payments ({e(cur)})</h2><table><tr><th>Date</th><th>Description</th>"
              "<th class='num'>Charges</th><th class='num'>Credits</th></tr>" + "".join(rows)
            + f"<tr class='total'><td colspan='2'>Totals</td><td class='num'>{fmt_money(summary.charges)}</td>"
              f"<td class='num'>{fmt_money(summary.payments)}</td></tr>"
            + f"<tr class='total'><td colspan='3'>{'Balance due' if summary.balance >= 0 else 'Credit balance'}</td>"
              f"<td class='num'>{e(cur)} {fmt_money(abs(summary.balance))}</td></tr>"
              "</table>" + alt + f"<p class='muted'>{e(st.invoice_footer or '')}</p>")
    return wrap(body)


def table_html(title: str, subtitle: str, headers: list[str], rows: list[list[str]], numeric: set[int]) -> str:
    th = "".join(f"<th class='{'num' if i in numeric else ''}'>{e(h)}</th>" for i, h in enumerate(headers))
    trs = "".join("<tr>" + "".join(f"<td class='{'num' if i in numeric else ''}'>{e(v)}</td>" for i, v in enumerate(r))
                  + "</tr>" for r in rows)
    return wrap(f"<h1>{e(state.property_name)}</h1><h2>{e(title)}</h2><p class='muted'>{e(subtitle)}</p>"
                f"<table><tr>{th}</tr>{trs}</table>")


def table_widget_html(t, title: str, subtitle: str = "") -> str:
    from .common import NumItem
    headers = [t.horizontalHeaderItem(c).text() for c in range(t.columnCount())]
    numeric, rows = set(), []
    for r in range(t.rowCount()):
        row = []
        for c in range(t.columnCount()):
            it = t.item(r, c)
            if isinstance(it, NumItem):
                numeric.add(c)
            row.append(it.text() if it else "")
        rows.append(row)
    return table_html(title, subtitle, headers, rows, numeric)


def _document(html_text: str) -> QTextDocument:
    doc = QTextDocument()
    doc.setHtml(html_text)
    return doc


class DocumentDialog(QDialog):
    """Preview a document with Print and Save-as-PDF buttons."""

    def __init__(self, parent, title: str, html_text: str, filename: str):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(820, 900)
        self.html_text, self.filename = html_text, filename
        lay = QVBoxLayout(self)
        view = QTextBrowser()
        view.setHtml(html_text)
        view.setStyleSheet("background: white;")
        lay.addWidget(view)
        lay.addLayout(hbox("stretch", button("Save as PDF…", self.save_pdf), button("Print…", self.print_),
                           button("Close", self.accept, "primary")))

    def save_pdf(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save PDF", self.filename, "PDF (*.pdf)")
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        writer = QPdfWriter(path)
        writer.setPageSize(QPageSize(QPageSize.A4))
        writer.setPageMargins(QMarginsF(15, 15, 15, 15), QPageLayout.Millimeter)
        writer.setResolution(300)
        doc = _document(self.html_text)
        doc.setPageSize(QSizeF(writer.width(), writer.height()))
        doc.print_(writer)
        info(self, f"Saved to {path}")

    def print_(self):
        printer = QPrinter(QPrinter.HighResolution)
        printer.setPageSize(QPageSize(QPageSize.A4))
        dlg = QPrintDialog(printer, self)
        if dlg.exec() == QDialog.Accepted:
            _document(self.html_text).print_(printer)


def show(parent, title: str, html_text: str, filename: str) -> None:
    DocumentDialog(parent, title, html_text, filename).exec()
