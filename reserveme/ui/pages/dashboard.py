from __future__ import annotations

from PySide6.QtWidgets import QGridLayout, QHBoxLayout

from ...services import reports
from ..common import FAILED, Page, button, call, card, fill_table, fmt_money, label, make_table, selected_id, state
from ..dialogs.reservation import open_reservation
from ..theme import STATUS_LABELS


class DashboardPage(Page):
    title = "Overview"
    permission = "dashboard"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.subtitle = label("", "muted")
        self.header.insertWidget(1, self.subtitle)
        if state.can("reservations"):
            self.header.addWidget(button("New reservation", lambda: self._new(), "primary"))
        self.header.addWidget(button("Refresh", self.refresh))

        self.kpis = {}
        grid = QGridLayout()
        grid.setSpacing(12)
        specs = [("arrivals", "Arrivals today"), ("departures", "Departures today"), ("inhouse", "In house"),
                 ("occ", "Occupancy tonight"), ("dirty", "Rooms to clean"), ("revenue", "Charges posted today")]
        for i, (key, text) in enumerate(specs):
            f, lay = card()
            v = label("–", "kpi")
            lay.addWidget(v)
            sub = label(text, "kpiLabel")
            sub.setWordWrap(True)
            lay.addWidget(sub)
            self.kpis[key] = (v, sub)
            grid.addWidget(f, 0, i)
        self.outer.addLayout(grid)

        row = QHBoxLayout()
        row.setSpacing(12)
        f1, l1 = card("Arrivals")
        self.arr = make_table(["Guest", "Room", "Nights", "Status", "ETA"], stretch=0)
        l1.addWidget(self.arr)
        f2, l2 = card("Departures")
        self.dep = make_table(["Guest", "Room", "Status"], stretch=0)
        l2.addWidget(self.dep)
        f3, l3 = card("Next 14 nights")
        self.fc = make_table(["Night", "Sold", "Occ. %", "Revenue"], stretch=0)
        self.fc.setSortingEnabled(False)
        l3.addWidget(self.fc)
        row.addWidget(f1, 3)
        row.addWidget(f2, 2)
        row.addWidget(f3, 2)
        self.outer.addLayout(row, 1)
        for t in (self.arr, self.dep):
            t.doubleClicked.connect(lambda _=None, t=t: self._open(t))

    def _new(self):
        if open_reservation(self):
            self.refresh()

    def _open(self, t):
        rid = selected_id(t)
        if rid and open_reservation(self, rid):
            self.refresh()

    def refresh(self):
        d = call(self, reports.dashboard)
        if d is FAILED:
            return
        self.subtitle.setText(f"  {d.property_name} · business date {d.business_date:%A %d %B %Y}")
        arrived = sum(1 for r in d.arrivals if r.status == "checked_in")
        left = sum(1 for r in d.departures if r.status == "checked_out")
        vals = {
            "arrivals": (f"{arrived} / {len(d.arrivals)}", "Arrived / expected today"),
            "departures": (f"{left} / {len(d.departures)}", "Departed / due today"),
            "inhouse": (str(len(d.in_house)), "Rooms occupied now"),
            "occ": (f"{d.today.occupancy:.0f}%", f"Occupancy tonight ({d.today.sold} of {d.today.available})"),
            "dirty": (str(d.rooms_dirty), f"To clean · {d.rooms_ooo} out of order"),
            "revenue": (fmt_money(d.charges_today), f"Charged today ({d.currency})"),
        }
        for k, (v, sub) in vals.items():
            self.kpis[k][0].setText(v)
            self.kpis[k][1].setText(sub)
        fill_table(self.arr, [[r.guest.full_name + (" ★" if r.guest.vip else ""), r.room.number if r.room else "—",
                               r.nights, STATUS_LABELS[r.status], r.arrival_time or ""]
                              for r in d.arrivals], [r.id for r in d.arrivals])
        fill_table(self.dep, [[r.guest.full_name, r.room.number if r.room else "—", STATUS_LABELS[r.status]]
                              for r in d.departures], [r.id for r in d.departures])
        fill_table(self.fc, [[x.date.strftime("%a %d"), x.sold, f"{x.occupancy:.0f}%", x.room_revenue]
                             for x in d.next_days])
