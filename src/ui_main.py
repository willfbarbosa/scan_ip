"""Main PySide6 GUI for Eletrozone NetScan — themed after Eletrozone Segurança Eletrônica."""

from __future__ import annotations

import csv
import math
import os
import sys
import time
import webbrowser
from typing import List, Optional

from PySide6.QtCore import QPointF, QRectF, Qt, QThread, Signal
from PySide6.QtGui import (
    QAction,
    QBrush,
    QColor,
    QFont,
    QGuiApplication,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.network_scanner import (
    DiscoveredHost,
    NetworkInterface,
    NetworkScanner,
    get_local_interfaces,
    parse_cidr_pool,
    parse_range_pool,
)
from src.theme import COLORS, build_stylesheet


def resource_path(relative_path: str) -> str:
    """Resolve asset paths for both source execution and PyInstaller frozen exe."""
    base = getattr(sys, "_MEIPASS", os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    return os.path.join(base, relative_path)


# ---------------------------------------------------------------------------
# Background scan worker (QThread)
# ---------------------------------------------------------------------------

class ScanWorker(QThread):
    host_found = Signal(object)       # DiscoveredHost
    progress_changed = Signal(int, int)  # completed, total
    scan_finished = Signal(list, float, bool)  # hosts, elapsed_s, cancelled

    def __init__(self, ip_list: List[str], interfaces: List[NetworkInterface]):
        super().__init__()
        self.ip_list = ip_list
        self.interfaces = interfaces
        self.scanner = NetworkScanner(max_workers=160)

    def stop(self) -> None:
        self.scanner.cancel()

    def run(self) -> None:
        t0 = time.perf_counter()
        hosts = self.scanner.scan_pool(
            self.ip_list,
            self.interfaces,
            on_host_found=lambda h: self.host_found.emit(h),
            on_progress=lambda done, total: self.progress_changed.emit(done, total),
        )
        elapsed = time.perf_counter() - t0
        self.scan_finished.emit(hosts, elapsed, self.scanner.is_cancelled)


class InterfaceLoader(QThread):
    loaded = Signal(list)

    def run(self) -> None:
        self.loaded.emit(get_local_interfaces())


# ---------------------------------------------------------------------------
# Numeric-sortable table item
# ---------------------------------------------------------------------------

class SortableTableItem(QTableWidgetItem):
    """Table item that sorts by a custom sort key (e.g., IPv4 int or latency float)."""

    def __init__(self, text: str, sort_key):
        super().__init__(text)
        self._sort_key = sort_key

    def __lt__(self, other: QTableWidgetItem) -> bool:
        if isinstance(other, SortableTableItem):
            return self._sort_key < other._sort_key
        return super().__lt__(other)


# ---------------------------------------------------------------------------
# Custom Painted Eletrozone Hero Header
# ---------------------------------------------------------------------------

class EletrozoneHeader(QWidget):
    """Branded header matching the Eletrozone dark carbon + crimson circuit aesthetic."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setMinimumHeight(112)
        self.setMaximumHeight(118)
        self._logo_pixmap = QPixmap(resource_path(os.path.join("assets", "eletrozone_logo.png")))
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 12, 20, 14)
        layout.setSpacing(16)

        # Left: Logo + App Subtitle
        brand_box = QHBoxLayout()
        brand_box.setSpacing(14)

        logo_label = QLabel()
        if not self._logo_pixmap.isNull():
            scaled = self._logo_pixmap.scaledToHeight(
                78, Qt.TransformationMode.SmoothTransformation
            )
            logo_label.setPixmap(scaled)
        else:
            logo_label.setText("ELETROZONE")
            logo_label.setStyleSheet("color: white; font-size: 26px; font-weight: 900;")
        brand_box.addWidget(logo_label)

        # Divider bar
        v_div = QFrame()
        v_div.setFixedWidth(2)
        v_div.setFixedHeight(52)
        v_div.setStyleSheet(f"background-color: {COLORS['red_primary']}; border-radius: 1px;")
        brand_box.addWidget(v_div)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title_col.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        app_name = QLabel("NETSCAN PRO")
        app_name.setStyleSheet(
            "color: #F4F4F8; font-size: 16px; font-weight: 900; letter-spacing: 2px;"
        )
        app_desc = QLabel("MONITOR DE DISPOSITIVOS & POOL IP")
        app_desc.setStyleSheet(
            f"color: {COLORS['red_bright']}; font-size: 10px; font-weight: 700; letter-spacing: 1.5px;"
        )
        title_col.addWidget(app_name)
        title_col.addWidget(app_desc)
        brand_box.addLayout(title_col)

        layout.addLayout(brand_box)
        layout.addStretch(1)

        # Right: KPI Telemetry Cards
        self.kpi_total = self._make_kpi_card("DISPOSITIVOS", "0")
        self.kpi_wired = self._make_kpi_card("CABEADO", "0", value_color=COLORS["wired_text"])
        self.kpi_wifi = self._make_kpi_card("WI-FI", "0", value_color=COLORS["wifi_text"])
        self.kpi_pool = self._make_kpi_card("POOL ATIVO", "—", is_pool=True)

        for card in (self.kpi_total, self.kpi_wired, self.kpi_wifi, self.kpi_pool):
            layout.addWidget(card)

    def _make_kpi_card(
        self, title: str, value: str, value_color: Optional[str] = None, is_pool: bool = False
    ) -> QFrame:
        card = QFrame()
        card.setObjectName("KpiCard")
        card.setMinimumWidth(148 if is_pool else 104)
        card.setFixedHeight(68)

        vb = QVBoxLayout(card)
        vb.setContentsMargins(12, 8, 12, 8)
        vb.setSpacing(2)

        lbl_title = QLabel(title)
        lbl_title.setObjectName("KpiTitle")

        lbl_val = QLabel(value)
        lbl_val.setObjectName("KpiValuePool" if is_pool else "KpiValue")
        if value_color:
            lbl_val.setStyleSheet(f"color: {value_color}; font-size: 20px; font-weight: 800;")
        lbl_val.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        vb.addWidget(lbl_title)
        vb.addWidget(lbl_val)
        card.value_label = lbl_val  # type: ignore[attr-defined]
        return card

    def update_kpis(self, total: int, wired: int, wifi: int, pool_label: str) -> None:
        self.kpi_total.value_label.setText(str(total))  # type: ignore[attr-defined]
        self.kpi_wired.value_label.setText(str(wired))  # type: ignore[attr-defined]
        self.kpi_wifi.value_label.setText(str(wifi))  # type: ignore[attr-defined]
        short_pool = pool_label if len(pool_label) <= 22 else pool_label[:21] + "…"
        self.kpi_pool.value_label.setText(short_pool)  # type: ignore[attr-defined]
        self.kpi_pool.setToolTip(pool_label)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        # 1. Deep obsidian gradient base
        bg = QLinearGradient(0, 0, w, h)
        bg.setColorAt(0.0, QColor("#0B0608"))
        bg.setColorAt(0.35, QColor("#09090D"))
        bg.setColorAt(0.75, QColor("#0C0B10"))
        bg.setColorAt(1.0, QColor("#140709"))
        painter.fillRect(0, 0, w, h, bg)

        # 2. Subtle crimson radial glows positioned so the logo blends seamlessly
        left_glow = QRadialGradient(0, h, 220)
        left_glow.setColorAt(0.0, QColor(229, 9, 20, 65))
        left_glow.setColorAt(1.0, QColor(229, 9, 20, 0))
        painter.fillRect(0, 0, 260, h, left_glow)

        right_glow = QRadialGradient(w, 0, 300)
        right_glow.setColorAt(0.0, QColor(229, 9, 20, 70))
        right_glow.setColorAt(1.0, QColor(229, 9, 20, 0))
        painter.fillRect(max(0, w - 360), 0, 360, h, right_glow)

        # 3. Faint hexagonal tech mesh texture
        hex_pen = QPen(QColor(255, 255, 255, 11), 1.0)
        painter.setPen(hex_pen)
        r = 16
        dx = r * 1.5
        dy = r * math.sqrt(3)
        for col in range(0, int(w / dx) + 2):
            cx = col * dx
            # Concentrate mesh near edges to keep center ultra-clean
            if 280 < cx < w - 380:
                continue
            for row in range(0, int(h / dy) + 2):
                cy = row * dy + (dy / 2 if col % 2 else 0)
                path = QPainterPath()
                for i in range(6):
                    ang = math.radians(60 * i)
                    px = cx + r * math.cos(ang)
                    py = cy + r * math.sin(ang)
                    if i == 0:
                        path.moveTo(px, py)
                    else:
                        path.lineTo(px, py)
                path.closeSubpath()
                painter.drawPath(path)

        # 4. Subtle target crosshair watermark on right side
        tcx, tcy = w - 130, h * 0.48
        painter.setPen(QPen(QColor(229, 9, 20, 28), 3.0))
        painter.drawEllipse(QPointF(tcx, tcy), 72, 72)
        painter.setPen(QPen(QColor(229, 9, 20, 20), 14.0))
        painter.drawEllipse(QPointF(tcx, tcy), 40, 40)

        # 5. Sleek glowing crimson circuit trace lines
        trace_pen = QPen(QColor(229, 9, 20, 120), 1.5)
        painter.setPen(trace_pen)
        # Top-left angled circuit trace
        p1 = QPainterPath()
        p1.moveTo(0, 22)
        p1.lineTo(42, 22)
        p1.lineTo(66, 4)
        p1.lineTo(240, 4)
        painter.drawPath(p1)
        painter.setBrush(QColor("#09090D"))
        painter.drawEllipse(QPointF(240, 4), 3.2, 3.2)

        # Bottom-right circuit trace
        p2 = QPainterPath()
        p2.moveTo(w, h - 22)
        p2.lineTo(w - 50, h - 22)
        p2.lineTo(w - 76, h - 4)
        p2.lineTo(w - 280, h - 4)
        painter.drawPath(p2)
        painter.drawEllipse(QPointF(w - 280, h - 4), 3.2, 3.2)

        # 6. Signature laser-red horizontal glow bottom border
        line_grad = QLinearGradient(0, 0, w, 0)
        line_grad.setColorAt(0.0, QColor(229, 9, 20, 40))
        line_grad.setColorAt(0.25, QColor(255, 36, 48, 220))
        line_grad.setColorAt(0.5, QColor(255, 110, 118, 255))
        line_grad.setColorAt(0.75, QColor(255, 36, 48, 220))
        line_grad.setColorAt(1.0, QColor(229, 9, 20, 40))
        painter.fillRect(0, h - 2, w, 2, line_grad)


# ---------------------------------------------------------------------------
# Styled Connection Pill Badge Widget
# ---------------------------------------------------------------------------

def make_connection_badge(conn_type: str, tooltip: str) -> QWidget:
    """Create a sleek pill widget indicating Wi-Fi or Cabeado."""
    container = QWidget()
    container.setToolTip(tooltip)
    lay = QHBoxLayout(container)
    lay.setContentsMargins(6, 2, 6, 2)
    lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

    low = conn_type.lower()
    if "wi-fi" in low or "wifi" in low:
        bg, bd, fg, icon_char = (
            COLORS["wifi_bg"],
            COLORS["wifi_border"],
            COLORS["wifi_text"],
            "◉",
        )
    elif "cabeado" in low:
        bg, bd, fg, icon_char = (
            COLORS["wired_bg"],
            COLORS["wired_border"],
            COLORS["wired_text"],
            "■",
        )
    else:
        bg, bd, fg, icon_char = (
            COLORS["unknown_bg"],
            COLORS["unknown_border"],
            COLORS["unknown_text"],
            "•",
        )

    pill = QLabel(f"{icon_char}  {conn_type}")
    pill.setToolTip(tooltip)
    pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
    pill.setStyleSheet(
        f"""
        background-color: {bg};
        color: {fg};
        border: 1px solid {bd};
        border-radius: 10px;
        padding: 3px 10px;
        font-size: 11px;
        font-weight: 700;
        """
    )
    lay.addWidget(pill)
    return container


# ---------------------------------------------------------------------------
# Main Window
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Eletrozone NetScan — Scanner de Rede")
        self.resize(1220, 760)
        self.setMinimumSize(1020, 620)

        ico_path = resource_path(os.path.join("assets", "eletrozone.ico"))
        if os.path.exists(ico_path):
            self.setWindowIcon(QIcon(ico_path))

        self.interfaces: List[NetworkInterface] = []
        self.all_hosts: List[DiscoveredHost] = []
        self.worker: Optional[ScanWorker] = None
        self.iface_loader: Optional[InterfaceLoader] = None
        self.current_pool_label = "—"
        self.conn_filter = "all"  # "all" | "wired" | "wifi"

        self._build_ui()
        self.setStyleSheet(build_stylesheet())
        self._load_interfaces_async()

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("CentralRoot")
        self.setCentralWidget(root)

        main_lay = QVBoxLayout(root)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)

        # 1. Branded Hero Header
        self.header = EletrozoneHeader()
        main_lay.addWidget(self.header)

        # Inner content wrapper
        content = QWidget()
        content_lay = QVBoxLayout(content)
        content_lay.setContentsMargins(16, 14, 16, 14)
        content_lay.setSpacing(12)
        main_lay.addWidget(content, 1)

        # 2. Pool Selector & Action Controls Panel
        ctrl_panel = QFrame()
        ctrl_panel.setObjectName("ControlPanel")
        ctrl_lay = QVBoxLayout(ctrl_panel)
        ctrl_lay.setContentsMargins(16, 13, 16, 13)
        ctrl_lay.setSpacing(11)

        # Row 1: Interface selector + Pool mode segmented switch
        row1 = QHBoxLayout()
        row1.setSpacing(12)

        lbl_iface = QLabel("INTERFACE / REDE:")
        lbl_iface.setObjectName("SectionLabel")
        row1.addWidget(lbl_iface)

        self.iface_combo = QComboBox()
        self.iface_combo.setMinimumWidth(240)
        self.iface_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.iface_combo.addItem("Detectando interfaces de rede...")
        self.iface_combo.currentIndexChanged.connect(self._on_interface_changed)
        row1.addWidget(self.iface_combo, 1)

        self.btn_refresh_ifaces = QPushButton("↻ Atualizar")
        self.btn_refresh_ifaces.setObjectName("SecondaryBtn")
        self.btn_refresh_ifaces.setToolTip("Recarregar adaptadores de rede ativos do Windows")
        self.btn_refresh_ifaces.clicked.connect(self._load_interfaces_async)
        row1.addWidget(self.btn_refresh_ifaces)

        row1.addSpacing(8)

        lbl_mode = QLabel("MODO DO POOL:")
        lbl_mode.setObjectName("SectionLabel")
        row1.addWidget(lbl_mode)

        self.btn_mode_cidr = QPushButton("Sub-rede (CIDR)")
        self.btn_mode_cidr.setObjectName("TogglePill")
        self.btn_mode_cidr.setCheckable(True)
        self.btn_mode_cidr.setChecked(True)

        self.btn_mode_range = QPushButton("Faixa de IP (Início — Fim)")
        self.btn_mode_range.setObjectName("TogglePill")
        self.btn_mode_range.setCheckable(True)

        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.btn_mode_cidr, 0)
        self.mode_group.addButton(self.btn_mode_range, 1)
        self.mode_group.idClicked.connect(self._on_pool_mode_changed)

        row1.addWidget(self.btn_mode_cidr)
        row1.addWidget(self.btn_mode_range)
        ctrl_lay.addLayout(row1)

        # Row 2: Pool input fields + Presets + Scan/Stop/Export buttons
        row2 = QHBoxLayout()
        row2.setSpacing(10)

        self.pool_stack = QStackedWidget()
        self.pool_stack.setMinimumHeight(38)

        # Page 0: CIDR input + quick presets
        cidr_page = QWidget()
        cidr_lay = QHBoxLayout(cidr_page)
        cidr_lay.setContentsMargins(0, 0, 0, 0)
        cidr_lay.setSpacing(7)

        lbl_cidr = QLabel("POOL (CIDR):")
        lbl_cidr.setObjectName("SectionLabel")
        cidr_lay.addWidget(lbl_cidr)

        self.cidr_input = QLineEdit("192.168.1.0/24")
        self.cidr_input.setObjectName("IpInput")
        self.cidr_input.setPlaceholderText("Ex: 192.168.1.0/24 ou 10.0.0.0/24")
        self.cidr_input.setFixedWidth(168)
        self.cidr_input.textChanged.connect(self._update_pool_count_badge)
        self.cidr_input.returnPressed.connect(self._start_scan)
        cidr_lay.addWidget(self.cidr_input)

        for preset in ("192.168.0.0/24", "192.168.1.0/24", "10.0.0.0/24"):
            chip = QPushButton(preset)
            chip.setObjectName("PresetChip")
            chip.clicked.connect(lambda _=False, p=preset: self.cidr_input.setText(p))
            cidr_lay.addWidget(chip)
        cidr_lay.addStretch(1)
        self.pool_stack.addWidget(cidr_page)

        # Page 1: Start IP -> End IP
        range_page = QWidget()
        range_lay = QHBoxLayout(range_page)
        range_lay.setContentsMargins(0, 0, 0, 0)
        range_lay.setSpacing(8)

        lbl_start = QLabel("IP INICIAL:")
        lbl_start.setObjectName("SectionLabel")
        range_lay.addWidget(lbl_start)

        self.start_ip_input = QLineEdit("192.168.1.1")
        self.start_ip_input.setObjectName("IpInput")
        self.start_ip_input.setFixedWidth(150)
        self.start_ip_input.textChanged.connect(self._update_pool_count_badge)
        self.start_ip_input.returnPressed.connect(self._start_scan)
        range_lay.addWidget(self.start_ip_input)

        lbl_to = QLabel("ATÉ")
        lbl_to.setObjectName("SectionLabel")
        range_lay.addWidget(lbl_to)

        self.end_ip_input = QLineEdit("192.168.1.254")
        self.end_ip_input.setObjectName("IpInput")
        self.end_ip_input.setFixedWidth(150)
        self.end_ip_input.textChanged.connect(self._update_pool_count_badge)
        self.end_ip_input.returnPressed.connect(self._start_scan)
        range_lay.addWidget(self.end_ip_input)
        range_lay.addStretch(1)
        self.pool_stack.addWidget(range_page)

        row2.addWidget(self.pool_stack, 1)

        self.lbl_pool_count = QLabel("254 IPs")
        self.lbl_pool_count.setObjectName("PoolCountBadge")
        row2.addWidget(self.lbl_pool_count)

        self.btn_scan = QPushButton("▶  ESCANEAR REDE")
        self.btn_scan.setObjectName("PrimaryBtn")
        self.btn_scan.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_scan.clicked.connect(self._start_scan)
        row2.addWidget(self.btn_scan)

        self.btn_stop = QPushButton("■ PARAR")
        self.btn_stop.setObjectName("StopBtn")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._stop_scan)
        row2.addWidget(self.btn_stop)

        self.btn_export = QPushButton("↓ Exportar CSV")
        self.btn_export.setObjectName("SecondaryBtn")
        self.btn_export.setEnabled(False)
        self.btn_export.clicked.connect(self._export_csv)
        row2.addWidget(self.btn_export)

        ctrl_lay.addLayout(row2)
        content_lay.addWidget(ctrl_panel)

        # 3. Results Panel (Search/Filter bar + Table)
        table_panel = QFrame()
        table_panel.setObjectName("TablePanel")
        tp_lay = QVBoxLayout(table_panel)
        tp_lay.setContentsMargins(14, 12, 14, 12)
        tp_lay.setSpacing(10)

        # Filter bar
        filter_bar = QHBoxLayout()
        filter_bar.setSpacing(8)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Filtrar por IP, hostname, MAC ou fabricante...")
        self.search_input.textChanged.connect(self._refresh_table_view)
        filter_bar.addWidget(self.search_input, 1)

        self.btn_flt_all = QPushButton("Todos")
        self.btn_flt_all.setObjectName("TogglePill")
        self.btn_flt_all.setCheckable(True)
        self.btn_flt_all.setChecked(True)

        self.btn_flt_wired = QPushButton("■ Cabeado")
        self.btn_flt_wired.setObjectName("TogglePill")
        self.btn_flt_wired.setCheckable(True)

        self.btn_flt_wifi = QPushButton("◉ Wi-Fi")
        self.btn_flt_wifi.setObjectName("TogglePill")
        self.btn_flt_wifi.setCheckable(True)

        self.filter_group = QButtonGroup(self)
        self.filter_group.addButton(self.btn_flt_all, 0)
        self.filter_group.addButton(self.btn_flt_wired, 1)
        self.filter_group.addButton(self.btn_flt_wifi, 2)
        self.filter_group.idClicked.connect(self._on_filter_changed)

        filter_bar.addWidget(self.btn_flt_all)
        filter_bar.addWidget(self.btn_flt_wired)
        filter_bar.addWidget(self.btn_flt_wifi)
        tp_lay.addLayout(filter_bar)

        # Results Table
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Endereço IP", "Hostname", "Endereço MAC", "Fabricante", "Conexão", "Latência"]
        )
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSortingEnabled(True)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(38)
        self.table.setShowGrid(False)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.cellDoubleClicked.connect(self._on_cell_double_clicked)

        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 185)
        self.table.setColumnWidth(2, 160)
        self.table.setColumnWidth(4, 152)
        self.table.setColumnWidth(5, 92)

        tp_lay.addWidget(self.table, 1)
        content_lay.addWidget(table_panel, 1)

        # 4. Bottom Progress & Status Bar
        footer = QVBoxLayout()
        footer.setSpacing(6)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        footer.addWidget(self.progress)

        status_row = QHBoxLayout()
        self.lbl_status = QLabel("Pronto. Selecione o pool desejado e clique em ESCANEAR REDE.")
        self.lbl_status.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 12px;")
        status_row.addWidget(self.lbl_status, 1)

        lbl_tip = QLabel("Botão direito no dispositivo: copiar dados ou abrir no navegador")
        lbl_tip.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px;")
        status_row.addWidget(lbl_tip)
        footer.addLayout(status_row)

        content_lay.addLayout(footer)

    # ------------------------------------------------------------------
    # Interface loading & pool selection handlers
    # ------------------------------------------------------------------

    def _load_interfaces_async(self) -> None:
        self.btn_refresh_ifaces.setEnabled(False)
        self.iface_combo.clear()
        self.iface_combo.addItem("Detectando interfaces de rede...")
        self.iface_loader = InterfaceLoader()
        self.iface_loader.loaded.connect(self._on_interfaces_loaded)
        self.iface_loader.start()

    def _on_interfaces_loaded(self, ifaces: List[NetworkInterface]) -> None:
        self.interfaces = ifaces
        self.iface_combo.blockSignals(True)
        self.iface_combo.clear()
        for iface in ifaces:
            self.iface_combo.addItem(iface.label, iface)
        self.iface_combo.blockSignals(False)
        self.btn_refresh_ifaces.setEnabled(True)

        if ifaces:
            self._apply_interface_to_pool(ifaces[0])
            self.lbl_status.setText(
                f"Interface detectada: {ifaces[0].alias} ({ifaces[0].media}) — Pool sugerido: {ifaces[0].cidr}"
            )

    def _on_interface_changed(self, index: int) -> None:
        if 0 <= index < len(self.interfaces):
            self._apply_interface_to_pool(self.interfaces[index])

    def _apply_interface_to_pool(self, iface: NetworkInterface) -> None:
        self.cidr_input.setText(iface.cidr)
        try:
            hosts, _ = parse_cidr_pool(iface.cidr)
            if hosts:
                self.start_ip_input.setText(hosts[0])
                self.end_ip_input.setText(hosts[-1])
        except ValueError:
            pass
        self._update_pool_count_badge()

    def _on_pool_mode_changed(self, mode_id: int) -> None:
        self.pool_stack.setCurrentIndex(mode_id)
        self._update_pool_count_badge()

    def _get_selected_pool(self) -> tuple[List[str], str]:
        if self.mode_group.checkedId() == 0:
            return parse_cidr_pool(self.cidr_input.text())
        return parse_range_pool(self.start_ip_input.text(), self.end_ip_input.text())

    def _update_pool_count_badge(self) -> None:
        try:
            hosts, _ = self._get_selected_pool()
            self.lbl_pool_count.setText(f"{len(hosts):,} IPs".replace(",", "."))
            self.lbl_pool_count.setStyleSheet(
                f"background-color: {COLORS['bg_input']}; color: {COLORS['text_primary']}; "
                f"border: 1px solid {COLORS['border']}; border-radius: 6px; padding: 5px 10px; font-weight: 600;"
            )
        except ValueError:
            self.lbl_pool_count.setText("Pool inválido")
            self.lbl_pool_count.setStyleSheet(
                f"background-color: #2B1216; color: {COLORS['red_bright']}; "
                f"border: 1px solid {COLORS['red_primary']}; border-radius: 6px; padding: 5px 10px; font-weight: 700;"
            )

    # ------------------------------------------------------------------
    # Scanning lifecycle
    # ------------------------------------------------------------------

    def _start_scan(self) -> None:
        if self.worker and self.worker.isRunning():
            return

        try:
            ip_list, pool_label = self._get_selected_pool()
        except ValueError as exc:
            QMessageBox.warning(self, "Pool de IP Inválido", str(exc))
            return

        self.current_pool_label = pool_label
        self.all_hosts.clear()
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        self.table.setSortingEnabled(True)

        self.header.update_kpis(0, 0, 0, pool_label)
        self.progress.setRange(0, len(ip_list))
        self.progress.setValue(0)
        self.btn_scan.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.btn_export.setEnabled(False)
        self.lbl_status.setText(f"Iniciando varredura em {pool_label} ({len(ip_list)} endereços)...")

        self.worker = ScanWorker(ip_list, self.interfaces)
        self.worker.host_found.connect(self._on_host_found)
        self.worker.progress_changed.connect(self._on_scan_progress)
        self.worker.scan_finished.connect(self._on_scan_finished)
        self.worker.start()

    def _stop_scan(self) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.btn_stop.setEnabled(False)
            self.lbl_status.setText("Interrompendo varredura...")

    def _on_host_found(self, host: DiscoveredHost) -> None:
        self.all_hosts.append(host)
        if self._host_matches_filters(host):
            self._append_host_row(host)
        self._update_kpi_counts()

    def _on_scan_progress(self, completed: int, total: int) -> None:
        self.progress.setValue(completed)
        pct = int((completed / total) * 100) if total else 0
        self.lbl_status.setText(
            f"Varrendo {self.current_pool_label} — {completed}/{total} IPs ({pct}%) | "
            f"{len(self.all_hosts)} dispositivo(s) encontrado(s)"
        )

    def _on_scan_finished(self, hosts: List[DiscoveredHost], elapsed: float, cancelled: bool) -> None:
        self.all_hosts = sorted(hosts, key=lambda h: h.ip_sort_key)
        self._refresh_table_view()
        self._update_kpi_counts()
        self.btn_scan.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.btn_export.setEnabled(len(self.all_hosts) > 0)

        if cancelled:
            self.lbl_status.setText(
                f"Varredura interrompida em {elapsed:.1f}s — {len(self.all_hosts)} dispositivo(s) encontrado(s)."
            )
        else:
            self.progress.setValue(self.progress.maximum())
            self.lbl_status.setText(
                f"Consulta concluída em {elapsed:.2f}s — {len(self.all_hosts)} dispositivo(s) ativo(s) em {self.current_pool_label}."
            )

    def _update_kpi_counts(self) -> None:
        total = len(self.all_hosts)
        wifi = sum(1 for h in self.all_hosts if "wi-fi" in h.connection_type.lower())
        wired = sum(1 for h in self.all_hosts if "cabeado" in h.connection_type.lower())
        self.header.update_kpis(total, wired, wifi, self.current_pool_label)

    # ------------------------------------------------------------------
    # Table rendering, filtering & interactions
    # ------------------------------------------------------------------

    def _on_filter_changed(self, flt_id: int) -> None:
        self.conn_filter = {0: "all", 1: "wired", 2: "wifi"}.get(flt_id, "all")
        self._refresh_table_view()

    def _host_matches_filters(self, host: DiscoveredHost) -> bool:
        low_conn = host.connection_type.lower()
        if self.conn_filter == "wired" and "cabeado" not in low_conn:
            return False
        if self.conn_filter == "wifi" and "wi-fi" not in low_conn:
            return False

        query = self.search_input.text().strip().lower()
        if query:
            haystack = f"{host.ip} {host.hostname} {host.mac} {host.vendor} {host.connection_type}".lower()
            if query not in haystack:
                return False
        return True

    def _refresh_table_view(self) -> None:
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        for host in self.all_hosts:
            if self._host_matches_filters(host):
                self._append_host_row(host)
        self.table.setSortingEnabled(True)
        self.table.sortItems(0, Qt.SortOrder.AscendingOrder)

    def _append_host_row(self, host: DiscoveredHost) -> None:
        was_sorting = self.table.isSortingEnabled()
        self.table.setSortingEnabled(False)
        row = self.table.rowCount()
        self.table.insertRow(row)

        mono_font = QFont("Consolas", 10)
        mono_bold = QFont("Consolas", 10, QFont.Weight.Bold)

        # Column 0: IP + tag
        ip_display = host.ip
        if host.is_local:
            ip_display += "  [ESTE PC]"
        elif host.is_gateway:
            ip_display += "  [GW]"
        item_ip = SortableTableItem(ip_display, host.ip_sort_key)
        item_ip.setFont(mono_bold)
        item_ip.setForeground(QBrush(QColor("#FFFFFF")))
        item_ip.setData(Qt.ItemDataRole.UserRole, host)
        item_ip.setToolTip(host.connection_reason)

        # Column 1: Hostname
        item_host = QTableWidgetItem(host.hostname)
        if host.hostname == "—":
            item_host.setForeground(QBrush(QColor(COLORS["text_muted"])))
        item_host.setToolTip(host.connection_reason)

        # Column 2: MAC
        item_mac = QTableWidgetItem(host.mac)
        item_mac.setFont(mono_font)
        item_mac.setForeground(
            QBrush(QColor(COLORS["text_primary"] if host.mac != "—" else COLORS["text_muted"]))
        )
        item_mac.setToolTip(host.connection_reason)

        # Column 3: Vendor
        item_vendor = QTableWidgetItem(host.vendor)
        if "Desconhecido" in host.vendor or "Não disponível" in host.vendor:
            item_vendor.setForeground(QBrush(QColor(COLORS["text_muted"])))
        item_vendor.setToolTip(host.connection_reason)

        # Column 4: Connection (sortable text hidden behind badge widget)
        item_conn = SortableTableItem("", host.connection_type.lower())
        item_conn.setToolTip(host.connection_reason)

        # Column 5: Latency
        if host.latency_ms is not None:
            lat_text = "< 1 ms" if host.latency_ms < 1.0 else f"{host.latency_ms:.0f} ms"
            lat_key = host.latency_ms
        else:
            lat_text = "—"
            lat_key = 999999.0
        item_lat = SortableTableItem(lat_text, lat_key)
        item_lat.setFont(mono_font)
        item_lat.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        item_lat.setForeground(QBrush(QColor(COLORS["text_secondary"])))

        self.table.setItem(row, 0, item_ip)
        self.table.setItem(row, 1, item_host)
        self.table.setItem(row, 2, item_mac)
        self.table.setItem(row, 3, item_vendor)
        self.table.setItem(row, 4, item_conn)
        self.table.setItem(row, 5, item_lat)
        self.table.setCellWidget(
            row, 4, make_connection_badge(host.connection_type, f"Critério: {host.connection_reason}")
        )

        self.table.setSortingEnabled(was_sorting)

    def _get_host_at_row(self, row: int) -> Optional[DiscoveredHost]:
        item = self.table.item(row, 0)
        if not item:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def _on_cell_double_clicked(self, row: int, _col: int) -> None:
        host = self._get_host_at_row(row)
        if host:
            QGuiApplication.clipboard().setText(host.ip)
            self.lbl_status.setText(f"IP copiado para a área de transferência: {host.ip}")

    def _show_context_menu(self, pos) -> None:
        row = self.table.rowAt(pos.y())
        if row < 0:
            return
        host = self._get_host_at_row(row)
        if not host:
            return

        menu = QMenu(self)
        act_ip = QAction(f"Copiar IP ({host.ip})", self)
        act_mac = QAction(f"Copiar MAC ({host.mac})", self)
        act_host = QAction(f"Copiar Hostname ({host.hostname})", self)
        act_row = QAction("Copiar Linha Completa", self)
        act_http = QAction(f"Abrir no Navegador (http://{host.ip})", self)
        act_https = QAction(f"Abrir no Navegador (https://{host.ip})", self)

        act_ip.triggered.connect(lambda: self._copy_text(host.ip, "IP"))
        act_mac.triggered.connect(lambda: self._copy_text(host.mac, "MAC"))
        act_host.triggered.connect(lambda: self._copy_text(host.hostname, "Hostname"))
        act_row.triggered.connect(
            lambda: self._copy_text(
                f"{host.ip}\t{host.hostname}\t{host.mac}\t{host.vendor}\t{host.connection_type}",
                "Linha",
            )
        )
        act_http.triggered.connect(lambda: webbrowser.open(f"http://{host.ip}"))
        act_https.triggered.connect(lambda: webbrowser.open(f"https://{host.ip}"))

        menu.addAction(act_ip)
        menu.addAction(act_mac)
        menu.addAction(act_host)
        menu.addAction(act_row)
        menu.addSeparator()
        menu.addAction(act_http)
        menu.addAction(act_https)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _copy_text(self, text: str, label: str) -> None:
        QGuiApplication.clipboard().setText(text)
        self.lbl_status.setText(f"{label} copiado: {text}")

    # ------------------------------------------------------------------
    # CSV Export
    # ------------------------------------------------------------------

    def _export_csv(self) -> None:
        if not self.all_hosts:
            return
        default_name = f"eletrozone_scan_{time.strftime('%Y%m%d_%H%M%S')}.csv"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Exportar Resultado da Varredura",
            default_name,
            "Arquivos CSV (*.csv);;Todos os Arquivos (*.*)",
        )
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f, delimiter=";")
                writer.writerow(
                    ["IP", "Hostname", "MAC", "Fabricante", "Conexão", "Critério", "Latência (ms)"]
                )
                for h in self.all_hosts:
                    lat = "" if h.latency_ms is None else f"{h.latency_ms:.1f}"
                    writer.writerow(
                        [h.ip, h.hostname, h.mac, h.vendor, h.connection_type, h.connection_reason, lat]
                    )
            self.lbl_status.setText(f"Relatório CSV salvo em: {path}")
        except OSError as exc:
            QMessageBox.critical(self, "Erro ao Exportar", f"Não foi possível salvar o arquivo:\n{exc}")

    def closeEvent(self, event) -> None:  # noqa: N802
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(1500)
        super().closeEvent(event)


def run_app() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Eletrozone NetScan")
    app.setOrganizationName("Eletrozone Segurança Eletrônica")
    window = MainWindow()
    window.show()
    return app.exec()
