"""Tape chart: rooms down the side, nights across, bookings as bars.

Drag a bar to move it to another room or date. Drag across empty nights to
start a new booking. Double-click a bar to open it.
"""
from __future__ import annotations

import datetime as dt

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (QComboBox, QFrame, QGraphicsItem, QGraphicsRectItem, QGraphicsScene,
                               QGraphicsSimpleTextItem, QGraphicsView, QGridLayout, QHBoxLayout, QListWidget,
                               QListWidgetItem, QVBoxLayout)

from ...services import catalog
from ...services import reservations as R
from ..common import FAILED, Page, button, call, date_edit, from_qdate, label, state, to_qdate
from ..dialogs.reservation import open_reservation
from ..theme import GREEN, ROOM_STATUS_COLORS, ROOM_STATUS_LABELS, STATUS_COLORS, STATUS_LABELS

CELL_W, ROW_H, LABEL_W, HEAD_H = 58, 30, 190, 46
MOVABLE = ("tentative", "confirmed", "checked_in")


class BookingBar(QGraphicsRectItem):
    def __init__(self, page: "TapeChartPage", res, x0: float, x1: float, y: float):
        super().__init__(0, 0, max(8.0, x1 - x0), ROW_H - 8)
        self.page, self.res = page, res
        self.setPos(x0, y + 4)
        self.origin = QPointF(x0, y + 4)
        self.setZValue(10)
        movable = res.status in MOVABLE and state.can("reservations")
        self.setFlag(QGraphicsItem.ItemIsMovable, movable)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, movable)
        self.setCursor(Qt.OpenHandCursor if movable else Qt.PointingHandCursor)
        self.setAcceptHoverEvents(True)
        g = res.guest
        self.setToolTip(f"<b>{g.full_name}</b>{' ★ VIP' if g.vip else ''}<br/>{res.code} · "
                        f"{STATUS_LABELS[res.status]}<br/>{res.check_in:%a %d %b} → {res.check_out:%a %d %b} "
                        f"({res.nights} nights)<br/>{res.room_type.name} · {res.rate_plan.name}<br/>"
                        f"{res.adults} adult(s){', ' + str(res.children) + ' child(ren)' if res.children else ''}"
                        + (f"<br/><i>{res.notes}</i>" if res.notes else ""))

    def paint(self, p: QPainter, option, widget=None):
        r = self.rect()
        p.setRenderHint(QPainter.Antialiasing)
        color = QColor(STATUS_COLORS.get(self.res.status, "#999"))
        p.setPen(QPen(color.darker(125), 1))
        p.setBrush(color)
        p.drawRoundedRect(r, 5, 5)
        p.setPen(QColor("white") if self.res.status != "tentative" else QColor("#3b2a00"))
        f = QFont()
        f.setPointSizeF(9)
        f.setBold(self.res.guest.vip)
        p.setFont(f)
        text = self.res.guest.last_name + (", " + self.res.guest.first_name[:1] if self.res.guest.first_name else "")
        p.drawText(r.adjusted(6, 0, -4, 0), Qt.AlignVCenter | Qt.AlignLeft,
                   p.fontMetrics().elidedText(text, Qt.ElideRight, int(r.width() - 10)))

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange and self.scene():
            x, y = value.x(), value.y()
            if self.res.status == "checked_in":
                x = self.origin.x()  # a checked-in stay can only change room
            y = max(0.0, min(y, self.scene().height() - ROW_H))
            return QPointF(x, y)
        return super().itemChange(change, value)

    def mousePressEvent(self, e):
        self.setCursor(Qt.ClosedHandCursor)
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        super().mouseReleaseEvent(e)
        self.setCursor(Qt.OpenHandCursor)
        if not (self.flags() & QGraphicsItem.ItemIsMovable):
            return
        days = round((self.pos().x() - self.origin.x()) / CELL_W)
        row = int((self.pos().y() + ROW_H / 2 - 4) // ROW_H)
        room_id = self.page.row_room.get(row)
        if room_id is None or (days == 0 and room_id == self.res.room_id):
            self.setPos(self.origin)
            return
        self.page.move_booking(self, room_id, self.res.check_in + dt.timedelta(days=days))

    def mouseDoubleClickEvent(self, e):
        self.page.open(self.res.id)


class GridView(QGraphicsView):
    def __init__(self, page):
        super().__init__()
        self.page = page
        self.sel_item = None
        self.sel_start = None
        self.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.setFrameShape(QFrame.NoFrame)

    def _cell(self, pos):
        sp = self.mapToScene(pos)
        return int(sp.x() // CELL_W), int(sp.y() // ROW_H)

    def mousePressEvent(self, e):
        item = self.itemAt(e.position().toPoint())
        if e.button() == Qt.LeftButton and not isinstance(item, BookingBar) and state.can("reservations"):
            col, row = self._cell(e.position().toPoint())
            if row in self.page.row_room and 0 <= col < self.page.days:
                self.sel_start = (col, row)
                self.sel_item = self.scene().addRect(QRectF(col * CELL_W, row * ROW_H + 3, CELL_W, ROW_H - 6),
                                                     QPen(QColor(GREEN), 1, Qt.DashLine), QColor(63, 174, 73, 50))
                self.sel_item.setZValue(5)
                return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self.sel_item is not None:
            col, _ = self._cell(e.position().toPoint())
            c0, row = self.sel_start
            col = max(c0, min(col, self.page.days - 1))
            self.sel_item.setRect(QRectF(c0 * CELL_W, row * ROW_H + 3, (col - c0 + 1) * CELL_W, ROW_H - 6))
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if self.sel_item is not None:
            rect = self.sel_item.rect()
            self.scene().removeItem(self.sel_item)
            self.sel_item = None
            c0, row = self.sel_start
            nights = max(1, round(rect.width() / CELL_W))
            self.page.new_booking(self.page.row_room[row], self.page.start + dt.timedelta(days=c0), nights)
            return
        super().mouseReleaseEvent(e)


class TapeChartPage(Page):
    title = "Tape chart"
    permission = "tape_chart"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.start = state.business_date - dt.timedelta(days=1)
        self.days = 21
        self.row_room: dict[int, int] = {}
        self.start_edit = date_edit(self.start)
        self.span = QComboBox()
        for n in (14, 21, 31, 62):
            self.span.addItem(f"{n} days", n)
        self.span.setCurrentIndex(1)
        self.header.addWidget(button("◀", lambda: self._shift(-7), tip="Back one week"))
        self.header.addWidget(self.start_edit)
        self.header.addWidget(button("▶", lambda: self._shift(7), tip="Forward one week"))
        self.header.addWidget(button("Today", self._today))
        self.header.addWidget(self.span)
        self.header.addWidget(button("Refresh", self.refresh))
        if state.can("reservations"):
            self.header.addWidget(button("New reservation", lambda: self.new_booking(None, None, 1), "primary"))

        legend = QHBoxLayout()
        for st in ("tentative", "confirmed", "checked_in", "checked_out"):
            legend.addWidget(label(f"<span style='color:{STATUS_COLORS[st]}; font-size:16px'>■</span> {STATUS_LABELS[st]}"))
        legend.addSpacing(20)
        for st in ("clean", "inspected", "dirty", "out_of_order"):
            legend.addWidget(label(f"<span style='color:{ROOM_STATUS_COLORS[st]}'>●</span> {ROOM_STATUS_LABELS[st]}"))
        legend.addStretch(1)
        legend.addWidget(label("Drag a bar to move it · drag across empty nights to book · double-click to open", "muted"))
        self.outer.addLayout(legend)

        body = QHBoxLayout()
        grid = QGridLayout()
        grid.setSpacing(0)
        self.head_scene, self.label_scene, self.grid_scene = QGraphicsScene(), QGraphicsScene(), QGraphicsScene()
        self.head_view = QGraphicsView(self.head_scene)
        self.label_view = QGraphicsView(self.label_scene)
        self.grid_view = GridView(self)
        self.grid_view.setScene(self.grid_scene)
        for v in (self.head_view, self.label_view):
            v.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            v.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            v.setFrameShape(QFrame.NoFrame)
            v.setAlignment(Qt.AlignLeft | Qt.AlignTop)
            v.setInteractive(False)
        self.head_view.setFixedHeight(HEAD_H)
        self.label_view.setFixedWidth(LABEL_W)
        corner = QFrame()
        corner.setFixedSize(LABEL_W, HEAD_H)
        corner.setStyleSheet("background:#eef1f4; border-bottom:1px solid #dde2e7;")
        grid.addWidget(corner, 0, 0)
        grid.addWidget(self.head_view, 0, 1)
        grid.addWidget(self.label_view, 1, 0)
        grid.addWidget(self.grid_view, 1, 1)
        frame = QFrame()
        frame.setObjectName("card")
        frame.setLayout(grid)
        body.addWidget(frame, 1)
        self.grid_view.horizontalScrollBar().valueChanged.connect(self.head_view.horizontalScrollBar().setValue)
        self.grid_view.verticalScrollBar().valueChanged.connect(self.label_view.verticalScrollBar().setValue)

        side = QVBoxLayout()
        side.addWidget(label("Unassigned bookings", "h2"))
        self.unassigned = QListWidget()
        self.unassigned.setFixedWidth(230)
        self.unassigned.setSpacing(4)
        self.unassigned.itemDoubleClicked.connect(lambda it: self.open(it.data(Qt.UserRole)))
        side.addWidget(self.unassigned)
        side.addWidget(label("Double-click to assign a room.", "muted"))
        body.addLayout(side)
        self.outer.addLayout(body, 1)
        self.start_edit.dateChanged.connect(lambda _: self._range_changed())
        self.span.currentIndexChanged.connect(lambda _: self._range_changed())

    # ------------------------------------------------------------ navigation
    def _shift(self, days):
        self.start_edit.setDate(to_qdate(from_qdate(self.start_edit.date()) + dt.timedelta(days=days)))

    def _today(self):
        self.start_edit.setDate(to_qdate(state.business_date - dt.timedelta(days=1)))

    def _range_changed(self):
        self.start = from_qdate(self.start_edit.date())
        self.days = self.span.currentData()
        self.refresh()

    # ------------------------------------------------------------ actions
    def _later_refresh(self):
        # Never rebuild the scene inside a graphics item's own mouse handler.
        QTimer.singleShot(0, self.refresh)

    def open(self, res_id):
        if open_reservation(self, res_id):
            self._later_refresh()

    def new_booking(self, room_id, check_in, nights):
        kw = {"nights": nights}
        if room_id:
            kw["room_id"] = room_id
        if check_in:
            kw["check_in"] = max(check_in, state.business_date)
        if open_reservation(self, None, **kw):
            self._later_refresh()

    def move_booking(self, bar: BookingBar, room_id: int, check_in: dt.date):
        res = call(self, R.move, state.actor, bar.res.id, room_id, check_in)
        if res is FAILED:
            bar.setPos(bar.origin)
        else:
            state.changed()
        self._later_refresh()

    # ------------------------------------------------------------ drawing
    def refresh(self):
        end = self.start + dt.timedelta(days=self.days)
        data = call(self, lambda s: (catalog.room_types(s, active_only=True), catalog.rooms(s, active_only=True),
                                     R.for_chart(s, self.start, end)))
        if data is FAILED:
            return
        types, rooms, bookings = data
        hpos, vpos = self.grid_view.horizontalScrollBar().value(), self.grid_view.verticalScrollBar().value()
        for sc in (self.head_scene, self.label_scene, self.grid_scene):
            sc.clear()
        width = self.days * CELL_W
        self._draw_header(width)

        rows: list[tuple[str, object]] = []
        for t in types:
            trooms = [r for r in rooms if r.room_type_id == t.id]
            if trooms:
                rows.append(("type", t))
                rows.extend(("room", r) for r in trooms)
        self.row_room = {}
        room_y = {}
        bdate = state.business_date
        grid_pen = QPen(QColor("#edf0f2"))
        for i, (kind, obj) in enumerate(rows):
            y = i * ROW_H
            if kind == "type":
                self.grid_scene.addRect(0, y, width, ROW_H, QPen(Qt.NoPen), QColor("#eef1f4"))
                t = self.label_scene.addSimpleText(f"{obj.name}")
                f = QFont()
                f.setBold(True)
                t.setFont(f)
                t.setBrush(QColor("#46525e"))
                t.setPos(10, y + 7)
                self.label_scene.addRect(0, y, LABEL_W, ROW_H, QPen(Qt.NoPen), QColor("#eef1f4")).setZValue(-1)
                continue
            self.row_room[i] = obj.id
            room_y[obj.id] = y
            ooo = obj.status == "out_of_order"
            for d in range(self.days):
                day = self.start + dt.timedelta(days=d)
                fill = QColor("white")
                if day.weekday() >= 5:
                    fill = QColor("#f8fafb")
                if day == bdate:
                    fill = QColor("#eaf6eb")
                brush = QBrush(QColor("#d5d9de"), Qt.BDiagPattern) if ooo else QBrush(fill)
                self.grid_scene.addRect(d * CELL_W, y, CELL_W, ROW_H, grid_pen, brush)
            dot = QColor(ROOM_STATUS_COLORS.get(obj.status, "#999"))
            self.label_scene.addEllipse(12, y + 10, 10, 10, QPen(Qt.NoPen), dot).setToolTip(
                ROOM_STATUS_LABELS.get(obj.status, obj.status))
            t = self.label_scene.addSimpleText(f"{obj.number}")
            f = QFont()
            f.setBold(True)
            t.setFont(f)
            t.setPos(30, y + 7)
            t2 = self.label_scene.addSimpleText(obj.room_type.code + (" · OOO" if ooo else ""))
            t2.setBrush(QColor("#6b7785"))
            t2.setPos(90, y + 7)
            self.label_scene.addLine(0, y + ROW_H, LABEL_W, y + ROW_H, grid_pen)
        height = max(len(rows) * ROW_H, ROW_H)
        if bdate >= self.start and bdate < self.start + dt.timedelta(days=self.days):
            x = (bdate - self.start).days * CELL_W
            line = self.grid_scene.addLine(x, 0, x, height, QPen(QColor(GREEN), 2))
            line.setZValue(4)

        self.unassigned.clear()
        for r in sorted(bookings, key=lambda r: r.check_in):
            if r.room_id is None:
                it = QListWidgetItem(f"{r.check_in:%d %b} · {r.guest.full_name}\n{r.room_type.code} · {r.nights} n · "
                                     f"{STATUS_LABELS[r.status]}")
                it.setData(Qt.UserRole, r.id)
                self.unassigned.addItem(it)
                continue
            if r.room_id not in room_y:
                continue
            x0 = (r.check_in - self.start).days * CELL_W + CELL_W / 2
            x1 = (r.check_out - self.start).days * CELL_W + CELL_W / 2
            x0c, x1c = max(x0, 0), min(x1, width)
            if x1c <= x0c:
                continue
            bar = BookingBar(self, r, x0c, x1c, room_y[r.room_id])
            self.grid_scene.addItem(bar)
        self.grid_scene.setSceneRect(0, 0, width, height)
        self.label_scene.setSceneRect(0, 0, LABEL_W, height)
        self.head_scene.setSceneRect(0, 0, width, HEAD_H)
        self.grid_view.horizontalScrollBar().setValue(hpos)
        self.grid_view.verticalScrollBar().setValue(vpos)

    def _draw_header(self, width):
        pen = QPen(QColor("#dde2e7"))
        bdate = state.business_date
        self.head_scene.addRect(0, 0, width, HEAD_H, QPen(Qt.NoPen), QColor("#eef1f4"))
        for d in range(self.days):
            day = self.start + dt.timedelta(days=d)
            x = d * CELL_W
            if day == bdate:
                self.head_scene.addRect(x, 0, CELL_W, HEAD_H, QPen(Qt.NoPen), QColor("#d7eed9"))
            self.head_scene.addLine(x, 0, x, HEAD_H, pen)
            t1 = QGraphicsSimpleTextItem(day.strftime("%a"))
            t1.setBrush(QColor("#c0392b" if day.weekday() >= 5 else "#6b7785"))
            t2 = QGraphicsSimpleTextItem(day.strftime("%d %b"))
            f = QFont()
            f.setBold(day == bdate)
            t2.setFont(f)
            for t, y in ((t1, 5), (t2, 23)):
                self.head_scene.addItem(t)
                t.setPos(x + (CELL_W - t.boundingRect().width()) / 2, y)
        self.head_scene.addLine(0, HEAD_H - 1, width, HEAD_H - 1, pen)
