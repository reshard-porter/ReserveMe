"""A reservation's bill: charges, payments, corrections, invoices."""
from __future__ import annotations

from decimal import Decimal

from PySide6.QtWidgets import QDialog, QInputDialog, QVBoxLayout

from ...models import PAYMENT_METHODS
from ...services import folio, reservations
from .. import printing
from ..common import (F, FAILED, FormDialog, button, call, fill_table, fmt_money, hbox, label, make_table,
                      selected_id, state, warn)
from ..theme import STATUS_LABELS


class FolioDialog(QDialog):
    def __init__(self, parent, res_id: int):
        super().__init__(parent)
        self.res_id = res_id
        self.setWindowTitle("Guest bill")
        self.resize(900, 600)
        lay = QVBoxLayout(self)
        self.head = label("", "h2")
        self.sub = label("", "muted")
        lay.addWidget(self.head)
        lay.addWidget(self.sub)
        self.table = make_table(["Date", "Type", "Description", "Charge", "Credit", "By"], stretch=2)
        lay.addWidget(self.table)
        self.totals = label("", "h2")
        lay.addWidget(self.totals)
        self.btn_charge = button("Add charge…", self.add_charge)
        self.btn_pay = button("Take payment…", self.take_payment, "primary")
        self.btn_refund = button("Refund…", lambda: self.take_payment(refund=True))
        self.btn_reverse = button("Correct selected line…", self.reverse, "danger")
        lay.addLayout(hbox(self.btn_charge, self.btn_pay, self.btn_refund, self.btn_reverse, "stretch",
                           button("Print bill", self.print_bill), button("Issue invoice", self.invoice),
                           button("Close", self.accept)))
        self.btn_pay.setEnabled(state.can("take_payment"))
        self.btn_refund.setEnabled(state.can("take_payment"))
        self.btn_reverse.setEnabled(state.can("reverse_line"))
        self.btn_charge.setEnabled(state.can("billing"))
        self.load()

    def load(self):
        data = call(self, lambda s: (reservations.get(s, self.res_id), folio.summary(s, self.res_id)))
        if data is FAILED:
            return
        self.res, self.summary = data
        r = self.res
        self.head.setText(f"{r.guest.full_name} · {r.code} · Room {r.room.number if r.room else '—'}")
        self.sub.setText(f"{r.check_in:%d %b %Y} → {r.check_out:%d %b %Y} · {r.nights} night(s) · "
                         f"{STATUS_LABELS.get(r.status, r.status)} · Estimated stay total "
                         f"{fmt_money(r.estimated_total, state.base_currency)}")
        rows, colors = [], []
        for l in self.summary.lines:
            desc = l.description
            if l.original_currency:
                desc += f"  ({l.original_currency} {fmt_money(l.original_amount)} @ {l.exchange_rate})"
            if l.reference:
                desc += f"  · Ref {l.reference}"
            rows.append([l.stay_date or l.business_date, l.kind.title(), desc,
                         l.amount if l.amount > 0 else None, -l.amount if l.amount < 0 else None,
                         l.user.username if l.user else ""])
            colors.append("#fbeaea" if l.reverses_id else None)
        fill_table(self.table, rows, [l.id for l in self.summary.lines], colors)
        cur = state.base_currency
        bal = self.summary.balance
        alt = ""
        if state.alt_currency and state.alt_rate and Decimal(state.alt_rate) != 1:
            alt = f"   ({state.alt_currency} {fmt_money(bal * Decimal(state.alt_rate))})"
        color = "#c0392b" if bal > 0 else "#2f8f38"
        self.totals.setText(f"Charges {fmt_money(self.summary.charges)}   ·   Payments {fmt_money(self.summary.payments)}"
                            f"   ·   <span style='color:{color}'>Balance {cur} {fmt_money(bal)}</span>{alt}")

    def add_charge(self):
        dlg = FormDialog(self, "Add charge", [
            F("description", "Description", required=True, help="e.g. Restaurant, Spa, Airport transfer, Minibar"),
            F("unit", "Unit price", "money", minimum=-1_000_000, required=True),
            F("qty", "Quantity", "decimal", default=1, minimum=0.01, maximum=10_000)],
            on_save=lambda v: call(self, folio.add_charge, state.actor, self.res_id, v["description"],
                                   v["unit"], v["qty"]))
        if dlg.exec():
            self.load()
            state.changed()

    def take_payment(self, refund: bool = False):
        cur_choices = [(state.base_currency, state.base_currency)]
        if state.alt_currency and state.alt_currency != state.base_currency:
            cur_choices.append((f"{state.alt_currency} (rate {state.alt_rate})", state.alt_currency))
        default = max(self.summary.balance, Decimal("0")) if not refund else max(-self.summary.balance, Decimal("0"))
        dlg = FormDialog(self, "Refund" if refund else "Take payment", [
            F("amount", "Amount", "money", default=default, minimum=0.01, required=True),
            F("currency", "Currency", "choice", choices=cur_choices, default=state.base_currency),
            F("method", "Method", "choice", choices=[(m, m) for m in PAYMENT_METHODS]),
            F("reference", "Reference", help="Card terminal approval code, receipt or transfer number. "
                                            "Never type a full card number here.")],
            on_save=lambda v: call(self, folio.add_payment, state.actor, self.res_id, v["amount"], v["method"],
                                   v["reference"], v["currency"], refund))
        if dlg.exec():
            self.load()
            state.changed()

    def reverse(self):
        line_id = selected_id(self.table)
        if not line_id:
            warn(self, "Select the line to correct first.")
            return
        reason, okd = QInputDialog.getText(self, "Correct line", "Reason for the correction:")
        if okd and reason.strip():
            if call(self, folio.reverse, state.actor, line_id, reason) is not FAILED:
                self.load()
                state.changed()

    def print_bill(self):
        doc = call(self, lambda s: printing.folio_html(s, self.res, folio.summary(s, self.res_id)))
        if doc is not FAILED:
            printing.show(self, "Guest bill", doc, f"Bill {self.res.code}.pdf")

    def invoice(self):
        def work(s):
            inv = folio.issue_invoice(s, state.actor, self.res_id)
            return inv, printing.folio_html(s, self.res, folio.summary(s, self.res_id), inv)
        out = call(self, work)
        if out is not FAILED:
            inv, doc = out
            printing.show(self, f"Invoice {inv.number}", doc, f"{inv.number}.pdf")


def open_folio(parent, res_id: int) -> None:
    FolioDialog(parent, res_id).exec()
