"""Entry point for Eletrozone NetScan."""

import json
import os
import sys

from src.ui_main import run_app


def _run_self_test(report_path: str) -> int:
    from PySide6.QtWidgets import QApplication
    from src.network_scanner import get_local_interfaces, parse_cidr_pool, parse_range_pool
    from src.ui_main import MainWindow, resource_path

    app = QApplication(sys.argv)
    win = MainWindow()
    ifaces = get_local_interfaces()
    win._on_interfaces_loaded(ifaces)
    win.show()
    app.processEvents()

    logo_path = resource_path(os.path.join("assets", "eletrozone_logo.png"))
    ico_path = resource_path(os.path.join("assets", "eletrozone.ico"))
    c_ips, c_lbl = parse_cidr_pool("192.168.1.0/24")
    r_ips, r_lbl = parse_range_pool("10.0.0.1", "10.0.0.10")

    report = {
        "frozen": bool(getattr(sys, "frozen", False)),
        "window_title": win.windowTitle(),
        "window_visible": win.isVisible(),
        "logo_exists": os.path.exists(logo_path),
        "logo_loaded": not win.header._logo_pixmap.isNull(),
        "icon_exists": os.path.exists(ico_path),
        "interfaces_count": len(ifaces),
        "first_interface": ifaces[0].label if ifaces else None,
        "cidr_count": len(c_ips),
        "range_count": len(r_ips),
    }
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    win.close()
    return 0


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--self-test":
        sys.exit(_run_self_test(sys.argv[2]))
    sys.exit(run_app())

