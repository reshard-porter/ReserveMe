"""Application look: one stylesheet for every window (light theme)."""
from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

GREEN = "#3fae49"
GREEN_DARK = "#2f8f38"
SIDEBAR = "#2f343b"
SIDEBAR_HOVER = "#3a4049"
SIDEBAR_ACTIVE = "#23272d"
BG = "#f4f6f8"
CARD = "#ffffff"
BORDER = "#dde2e7"
TEXT = "#1f2a33"
MUTED = "#6b7785"
DANGER = "#c0392b"
WARNING = "#d98e04"
INFO = "#2f6fb5"

STATUS_COLORS = {
    "tentative": "#f0b44c",
    "confirmed": "#4a90d9",
    "checked_in": GREEN,
    "checked_out": "#a5aeb8",
    "cancelled": "#d0d5da",
    "no_show": "#e3a19a",
}
STATUS_LABELS = {
    "tentative": "Tentative", "confirmed": "Confirmed", "checked_in": "In house",
    "checked_out": "Checked out", "cancelled": "Cancelled", "no_show": "No-show",
}
ROOM_STATUS_COLORS = {"clean": "#4a90d9", "inspected": GREEN, "dirty": "#e67e22", "out_of_order": "#7f8c8d"}
ROOM_STATUS_LABELS = {"clean": "Clean", "inspected": "Inspected", "dirty": "Dirty", "out_of_order": "Out of order"}

from pathlib import Path

RES = (Path(__file__).resolve().parent.parent / "resources").as_posix()

QSS = f"""
QWidget {{ color: {TEXT}; font-size: 13px; }}
QMainWindow, QDialog, #page {{ background: {BG}; }}
QLabel#h1 {{ font-size: 22px; font-weight: 600; }}
QLabel#h2 {{ font-size: 15px; font-weight: 600; }}
QLabel#muted {{ color: {MUTED}; }}
QLabel#error {{ color: {DANGER}; }}
#topbar {{ background: {GREEN}; }}
#topbar QLabel {{ color: white; }}
#topbar QLabel#brand {{ font-size: 17px; font-weight: 700; }}
#topbar QPushButton {{ background: transparent; color: white; border: 1px solid rgba(255,255,255,0.55);
    border-radius: 4px; padding: 4px 10px; }}
#topbar QPushButton:hover {{ background: rgba(255,255,255,0.15); }}
QListWidget#sidebar {{ background: {SIDEBAR}; color: #dfe4ea; border: none; outline: 0; font-size: 14px; }}
QListWidget#sidebar::item {{ padding: 11px 16px; border-left: 3px solid transparent; }}
QListWidget#sidebar::item:hover {{ background: {SIDEBAR_HOVER}; }}
QListWidget#sidebar::item:selected {{ background: {SIDEBAR_ACTIVE}; color: white; border-left: 3px solid {GREEN}; }}
QFrame#card {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 8px; }}
QFrame#card QLabel#kpi {{ font-size: 26px; font-weight: 600; }}
QFrame#card QLabel#kpiLabel {{ color: {MUTED}; }}
QPushButton {{ background: white; border: 1px solid #c5ccd3; border-radius: 4px; padding: 6px 14px; }}
QPushButton:hover {{ border-color: {GREEN}; }}
QPushButton:pressed {{ background: #eef1f4; }}
QPushButton:disabled {{ color: #a0a8b0; background: #f1f3f5; }}
QPushButton#primary {{ background: {GREEN}; color: white; border: 1px solid {GREEN_DARK}; font-weight: 600; }}
QPushButton#primary:hover {{ background: {GREEN_DARK}; }}
QPushButton#danger {{ color: {DANGER}; border-color: #e3b3ad; }}
QLineEdit, QComboBox, QDateEdit, QSpinBox, QDoubleSpinBox, QTextEdit, QPlainTextEdit, QTimeEdit {{
    background: white; border: 1px solid #c5ccd3; border-radius: 4px; padding: 4px 6px; min-height: 20px; }}
QComboBox::drop-down, QDateEdit::drop-down {{ subcontrol-origin: padding; subcontrol-position: top right;
    width: 22px; border: none; border-left: 1px solid #e1e5e9; }}
QComboBox::down-arrow, QDateEdit::down-arrow {{ image: url({RES}/arrow-down.svg); width: 10px; height: 10px; }}
QSpinBox::up-button, QDoubleSpinBox::up-button, QTimeEdit::up-button {{ subcontrol-origin: border;
    subcontrol-position: top right; width: 18px; border: none; border-left: 1px solid #e1e5e9; }}
QSpinBox::down-button, QDoubleSpinBox::down-button, QTimeEdit::down-button {{ subcontrol-origin: border;
    subcontrol-position: bottom right; width: 18px; border: none; border-left: 1px solid #e1e5e9; }}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow, QTimeEdit::up-arrow {{ image: url({RES}/arrow-up.svg); width: 8px; height: 8px; }}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow, QTimeEdit::down-arrow {{ image: url({RES}/arrow-down.svg); width: 8px; height: 8px; }}
QComboBox QAbstractItemView {{ background: white; border: 1px solid #c5ccd3; selection-background-color: #d7eed9; }}
QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QTextEdit:focus, QPlainTextEdit:focus {{ border-color: {GREEN}; }}
QTableView, QTableWidget, QTreeWidget {{ background: white; border: 1px solid {BORDER}; gridline-color: #edf0f2;
    selection-background-color: #d7eed9; selection-color: {TEXT}; alternate-background-color: #f8fafb; }}
QHeaderView::section {{ background: #eef1f4; border: none; border-right: 1px solid {BORDER};
    border-bottom: 1px solid {BORDER}; padding: 6px; font-weight: 600; color: #46525e; }}
QTabWidget::pane {{ border: 1px solid {BORDER}; background: white; border-radius: 4px; top: -1px; }}
QTabBar::tab {{ padding: 7px 16px; border: 1px solid transparent; color: {MUTED}; }}
QTabBar::tab:selected {{ color: {TEXT}; border-bottom: 2px solid {GREEN}; font-weight: 600; }}
QGroupBox {{ border: 1px solid {BORDER}; border-radius: 6px; margin-top: 14px; padding-top: 8px; background: white; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; color: #46525e; font-weight: 600; }}
QStatusBar {{ background: white; border-top: 1px solid {BORDER}; color: {MUTED}; }}
QToolTip {{ background: #2f343b; color: white; border: none; padding: 4px; }}
"""


def apply(app: QApplication) -> None:
    app.setStyle("Fusion")  # same look on Windows and macOS
    pal = app.palette()
    pal.setColor(QPalette.Window, QColor(BG))
    pal.setColor(QPalette.Base, QColor("white"))
    pal.setColor(QPalette.Text, QColor(TEXT))
    pal.setColor(QPalette.WindowText, QColor(TEXT))
    pal.setColor(QPalette.Button, QColor("white"))
    pal.setColor(QPalette.ButtonText, QColor(TEXT))
    pal.setColor(QPalette.Highlight, QColor("#d7eed9"))
    pal.setColor(QPalette.HighlightedText, QColor(TEXT))
    app.setPalette(pal)
    f = QFont()
    f.setPointSizeF(10.5 if f.pointSizeF() < 11 else f.pointSizeF())
    app.setFont(f)
    app.setStyleSheet(QSS)
