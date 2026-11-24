"""Eletrozone Segurança Eletrônica — Dark Carbon & Neon Crimson Qt theme."""

from __future__ import annotations

COLORS = {
    "bg_root": "#08080B",
    "bg_panel": "#111117",
    "bg_card": "#16161F",
    "bg_input": "#1B1B25",
    "bg_row_alt": "#13131A",
    "bg_row_hover": "#221419",
    "bg_selected": "#2E1217",
    "border": "#262633",
    "border_strong": "#3A3A4A",
    "red_primary": "#E50914",
    "red_bright": "#FF2430",
    "red_dark": "#9E060E",
    "red_glow": "#FF3B47",
    "text_primary": "#F4F4F8",
    "text_secondary": "#9A9AAA",
    "text_muted": "#6D6D7E",
    "wired_bg": "#0D2434",
    "wired_border": "#1E5B7D",
    "wired_text": "#4CC9F0",
    "wifi_bg": "#2F1116",
    "wifi_border": "#8F1D26",
    "wifi_text": "#FF5A65",
    "unknown_bg": "#20202A",
    "unknown_border": "#3B3B4D",
    "unknown_text": "#A0A0B2",
    "success": "#22C55E",
}


def build_stylesheet() -> str:
    c = COLORS
    return f"""
    QMainWindow, QWidget#CentralRoot {{
        background-color: {c['bg_root']};
        color: {c['text_primary']};
        font-family: "Segoe UI", "Inter", sans-serif;
        font-size: 13px;
    }}

    /* Cards & Panels */
    QFrame#ControlPanel, QFrame#TablePanel {{
        background-color: {c['bg_panel']};
        border: 1px solid {c['border']};
        border-radius: 10px;
    }}

    QFrame#KpiCard {{
        background-color: rgba(20, 20, 28, 220);
        border: 1px solid {c['border']};
        border-top: 2px solid {c['red_primary']};
        border-radius: 8px;
    }}

    QLabel#KpiTitle {{
        color: {c['text_secondary']};
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 1px;
    }}

    QLabel#KpiValue {{
        color: {c['text_primary']};
        font-size: 20px;
        font-weight: 800;
    }}

    QLabel#KpiValuePool {{
        color: {c['red_bright']};
        font-size: 13px;
        font-weight: 700;
        font-family: "Consolas", "Cascadia Mono", monospace;
    }}

    QLabel#SectionLabel {{
        color: {c['text_secondary']};
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 0.8px;
    }}

    QLabel#PoolCountBadge {{
        background-color: {c['bg_input']};
        color: {c['text_secondary']};
        border: 1px solid {c['border']};
        border-radius: 6px;
        padding: 5px 10px;
        font-size: 12px;
        font-weight: 600;
    }}

    /* Inputs & Comboboxes */
    QLineEdit, QComboBox {{
        background-color: {c['bg_input']};
        color: {c['text_primary']};
        border: 1px solid {c['border']};
        border-radius: 7px;
        padding: 7px 11px;
        font-size: 13px;
        selection-background-color: {c['red_primary']};
    }}

    QLineEdit:focus, QComboBox:focus {{
        border: 1px solid {c['red_primary']};
        background-color: #201A1F;
    }}

    QLineEdit#IpInput {{
        font-family: "Consolas", "Cascadia Mono", monospace;
        font-size: 13px;
        font-weight: 600;
    }}

    QComboBox::drop-down {{
        subcontrol-origin: padding;
        subcontrol-position: top right;
        width: 26px;
        border-left: 1px solid {c['border']};
        border-top-right-radius: 7px;
        border-bottom-right-radius: 7px;
        background-color: #181822;
    }}

    QComboBox::down-arrow {{
        image: none;
        width: 0px;
        height: 0px;
        border-left: 5px solid transparent;
        border-right: 5px solid transparent;
        border-top: 6px solid {c['red_bright']};
        margin-right: 2px;
    }}

    QComboBox QAbstractItemView {{
        background-color: {c['bg_card']};
        color: {c['text_primary']};
        border: 1px solid {c['red_primary']};
        selection-background-color: {c['red_primary']};
        selection-color: #FFFFFF;
        outline: 0;
        padding: 4px;
    }}

    /* Primary Crimson Action Button */
    QPushButton#PrimaryBtn {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 {c['red_bright']}, stop:0.5 {c['red_primary']}, stop:1 {c['red_dark']});
        color: #FFFFFF;
        border: 1px solid {c['red_glow']};
        border-radius: 7px;
        padding: 8px 20px;
        font-size: 13px;
        font-weight: 800;
        letter-spacing: 0.8px;
    }}

    QPushButton#PrimaryBtn:hover {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 #FF3D47, stop:1 {c['red_primary']});
        border: 1px solid #FF6B74;
    }}

    QPushButton#PrimaryBtn:pressed {{
        background-color: {c['red_dark']};
    }}

    QPushButton#PrimaryBtn:disabled {{
        background-color: #2A1A1D;
        border: 1px solid #45242A;
        color: #886B70;
    }}

    /* Stop / Danger Secondary Button */
    QPushButton#StopBtn {{
        background-color: #261418;
        color: {c['red_bright']};
        border: 1px solid {c['red_primary']};
        border-radius: 7px;
        padding: 8px 16px;
        font-size: 12px;
        font-weight: 700;
        letter-spacing: 0.6px;
    }}

    QPushButton#StopBtn:hover {{
        background-color: {c['red_primary']};
        color: #FFFFFF;
    }}

    QPushButton#StopBtn:disabled {{
        background-color: {c['bg_input']};
        border: 1px solid {c['border']};
        color: {c['text_muted']};
    }}

    /* Utility Buttons */
    QPushButton#SecondaryBtn {{
        background-color: {c['bg_input']};
        color: {c['text_primary']};
        border: 1px solid {c['border_strong']};
        border-radius: 7px;
        padding: 7px 14px;
        font-size: 12px;
        font-weight: 600;
    }}

    QPushButton#SecondaryBtn:hover {{
        border: 1px solid {c['red_primary']};
        background-color: #21161A;
        color: #FFFFFF;
    }}

    QPushButton#SecondaryBtn:disabled {{
        color: {c['text_muted']};
        border-color: {c['border']};
    }}

    /* Mode Toggle & Filter Pills */
    QPushButton#TogglePill {{
        background-color: {c['bg_input']};
        color: {c['text_secondary']};
        border: 1px solid {c['border']};
        border-radius: 6px;
        padding: 6px 13px;
        font-size: 12px;
        font-weight: 700;
    }}

    QPushButton#TogglePill:hover {{
        border-color: {c['border_strong']};
        color: {c['text_primary']};
    }}

    QPushButton#TogglePill:checked {{
        background-color: {c['red_primary']};
        color: #FFFFFF;
        border: 1px solid {c['red_glow']};
    }}

    QPushButton#PresetChip {{
        background-color: #171720;
        color: {c['text_secondary']};
        border: 1px solid {c['border']};
        border-radius: 5px;
        padding: 4px 9px;
        font-size: 11px;
        font-family: "Consolas", monospace;
    }}

    QPushButton#PresetChip:hover {{
        border-color: {c['red_primary']};
        color: #FFFFFF;
        background-color: #241418;
    }}

    /* Results Table */
    QTableWidget {{
        background-color: {c['bg_panel']};
        alternate-background-color: {c['bg_row_alt']};
        color: {c['text_primary']};
        border: none;
        gridline-color: #1D1D27;
        selection-background-color: {c['bg_selected']};
        selection-color: #FFFFFF;
        outline: 0;
        font-size: 13px;
    }}

    QTableWidget::item {{
        padding: 6px 10px;
        border-bottom: 1px solid #1B1B24;
    }}

    QTableWidget::item:hover {{
        background-color: {c['bg_row_hover']};
    }}

    QTableWidget::item:selected {{
        background-color: {c['bg_selected']};
        color: #FFFFFF;
    }}

    QHeaderView::section {{
        background-color: #0D0D12;
        color: {c['text_secondary']};
        padding: 9px 10px;
        border: none;
        border-bottom: 2px solid {c['red_primary']};
        border-right: 1px solid #1C1C26;
        font-size: 11px;
        font-weight: 800;
        letter-spacing: 0.7px;
        text-transform: uppercase;
    }}

    QHeaderView::section:hover {{
        color: #FFFFFF;
        background-color: #161014;
    }}

    /* Scrollbars */
    QScrollBar:vertical {{
        background: {c['bg_root']};
        width: 10px;
        margin: 0;
        border-radius: 5px;
    }}

    QScrollBar::handle:vertical {{
        background: #2C2C3A;
        min-height: 28px;
        border-radius: 5px;
    }}

    QScrollBar::handle:vertical:hover {{
        background: {c['red_primary']};
    }}

    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}

    QScrollBar:horizontal {{
        background: {c['bg_root']};
        height: 10px;
        margin: 0;
        border-radius: 5px;
    }}

    QScrollBar::handle:horizontal {{
        background: #2C2C3A;
        min-width: 28px;
        border-radius: 5px;
    }}

    QScrollBar::handle:horizontal:hover {{
        background: {c['red_primary']};
    }}

    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0px;
    }}

    /* Progress Bar */
    QProgressBar {{
        background-color: #16161F;
        border: 1px solid {c['border']};
        border-radius: 5px;
        height: 10px;
        text-align: center;
        color: transparent;
    }}

    QProgressBar::chunk {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {c['red_dark']}, stop:0.6 {c['red_primary']}, stop:1 {c['red_glow']});
        border-radius: 4px;
    }}

    /* Context Menu & Tooltips */
    QMenu {{
        background-color: {c['bg_card']};
        color: {c['text_primary']};
        border: 1px solid {c['red_primary']};
        border-radius: 6px;
        padding: 4px;
    }}

    QMenu::item {{
        padding: 7px 18px;
        border-radius: 4px;
    }}

    QMenu::item:selected {{
        background-color: {c['red_primary']};
        color: #FFFFFF;
    }}

    QToolTip {{
        background-color: #171720;
        color: #F4F4F8;
        border: 1px solid {c['red_primary']};
        padding: 6px 9px;
        border-radius: 5px;
        font-size: 12px;
    }}
    """
