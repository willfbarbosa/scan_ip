"""High-speed Windows network discovery engine for Eletrozone NetScan.

Uses native Windows iphlpapi.dll (SendARP + IcmpSendEcho) via ctypes for fast,
zero-subprocess host discovery, paired with NetBIOS + Reverse DNS hostname
resolution and multi-signal Wi-Fi vs Cabeado classification.
"""

from __future__ import annotations

import ctypes
import ipaddress
import json
import re
import socket
import struct
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

from src.oui_db import is_randomized_mac, lookup_oui

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class NetworkInterface:
    alias: str
    description: str
    ip: str
    prefix_length: int
    mac: str
    media: str  # "Wi-Fi" | "Cabeado" | "Outro"
    gateway: str = ""

    @property
    def cidr(self) -> str:
        try:
            net = ipaddress.IPv4Network(f"{self.ip}/{self.prefix_length}", strict=False)
            return str(net)
        except ValueError:
            return f"{self.ip}/24"

    @property
    def label(self) -> str:
        return f"{self.alias} ({self.media}) — {self.cidr} [{self.ip}]"


@dataclass
class DiscoveredHost:
    ip: str
    hostname: str
    mac: str
    vendor: str
    connection_type: str   # "Wi-Fi", "Cabeado", "Wi-Fi (Est.)", "Cabeado (Est.)", "Indeterminado"
    connection_reason: str
    latency_ms: Optional[float]
    is_local: bool = False
    is_gateway: bool = False

    @property
    def ip_sort_key(self) -> int:
        try:
            return int(ipaddress.IPv4Address(self.ip))
        except ValueError:
            return 0


# ---------------------------------------------------------------------------
# Native Windows iphlpapi.dll bindings (SendARP & IcmpSendEcho)
# ---------------------------------------------------------------------------

_iphlpapi = ctypes.windll.iphlpapi
_ws2_32 = ctypes.windll.ws2_32

_SendARP = _iphlpapi.SendARP
_SendARP.argtypes = [ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
_SendARP.restype = ctypes.c_uint32

_IcmpCreateFile = _iphlpapi.IcmpCreateFile
_IcmpCreateFile.argtypes = []
_IcmpCreateFile.restype = ctypes.c_void_p

_IcmpCloseHandle = _iphlpapi.IcmpCloseHandle
_IcmpCloseHandle.argtypes = [ctypes.c_void_p]
_IcmpCloseHandle.restype = ctypes.c_bool

_IcmpSendEcho = _iphlpapi.IcmpSendEcho
_IcmpSendEcho.argtypes = [
    ctypes.c_void_p,   # IcmpHandle
    ctypes.c_uint32,   # DestinationAddress
    ctypes.c_void_p,   # RequestData
    ctypes.c_uint16,   # RequestSize
    ctypes.c_void_p,   # RequestOptions
    ctypes.c_void_p,   # ReplyBuffer
    ctypes.c_uint32,   # ReplySize
    ctypes.c_uint32,   # Timeout
]
_IcmpSendEcho.restype = ctypes.c_uint32


class _IP_OPTION_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("Ttl", ctypes.c_ubyte),
        ("Tos", ctypes.c_ubyte),
        ("Flags", ctypes.c_ubyte),
        ("OptionsSize", ctypes.c_ubyte),
        ("OptionsData", ctypes.c_void_p),
    ]


class _ICMP_ECHO_REPLY(ctypes.Structure):
    _fields_ = [
        ("Address", ctypes.c_uint32),
        ("Status", ctypes.c_uint32),
        ("RoundTripTime", ctypes.c_uint32),
        ("DataSize", ctypes.c_uint16),
        ("Reserved", ctypes.c_uint16),
        ("Data", ctypes.c_void_p),
        ("Options", _IP_OPTION_INFORMATION),
    ]


def _ip_to_uint32(ip: str) -> int:
    packed = socket.inet_aton(ip)
    return struct.unpack("<I", packed)[0]


def send_arp(ip: str) -> Optional[str]:
    """Send native Windows ARP request. Returns formatted MAC 'AA:BB:CC:DD:EE:FF' or None."""
    try:
        dest = _ip_to_uint32(ip)
        mac_buf = (ctypes.c_ubyte * 6)()
        mac_len = ctypes.c_ulong(6)
        res = _SendARP(dest, 0, ctypes.byref(mac_buf), ctypes.byref(mac_len))
        if res == 0 and mac_len.value == 6:
            mac = ":".join(f"{b:02X}" for b in mac_buf)
            if mac != "00:00:00:00:00:00":
                return mac
    except Exception:
        pass
    return None


def icmp_ping(ip: str, timeout_ms: int = 450) -> Tuple[bool, Optional[float], Optional[int]]:
    """Send native Windows ICMP echo request. Returns (alive, rtt_ms, ttl)."""
    handle = _IcmpCreateFile()
    if not handle or handle == ctypes.c_void_p(-1).value:
        return (False, None, None)
    try:
        dest = _ip_to_uint32(ip)
        payload = b"EletrozoneNetScanPing!"
        reply_size = ctypes.sizeof(_ICMP_ECHO_REPLY) + len(payload) + 32
        reply_buf = ctypes.create_string_buffer(reply_size)
        t0 = time.perf_counter()
        count = _IcmpSendEcho(
            handle,
            dest,
            payload,
            len(payload),
            None,
            reply_buf,
            reply_size,
            timeout_ms,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        if count > 0:
            reply = ctypes.cast(reply_buf, ctypes.POINTER(_ICMP_ECHO_REPLY)).contents
            if reply.Status == 0:
                rtt = float(reply.RoundTripTime)
                # Windows RoundTripTime is integer ms; preserve sub-ms precision when 0
                if rtt == 0.0 and elapsed_ms < 5.0:
                    rtt = round(elapsed_ms, 2)
                return (True, rtt, int(reply.Options.Ttl))
    except Exception:
        pass
    finally:
        _IcmpCloseHandle(handle)
    return (False, None, None)


# ---------------------------------------------------------------------------
# Local interfaces & ARP cache helpers
# ---------------------------------------------------------------------------

def _creation_flags() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def get_local_interfaces() -> List[NetworkInterface]:
    """Discover active Windows IPv4 network interfaces with media type and gateway."""
    ps_script = r"""
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
$OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'SilentlyContinue'
$adapters = Get-NetAdapter | Where-Object { $_.Status -eq 'Up' }
$configs = Get-NetIPConfiguration
$out = @()
foreach ($cfg in $configs) {
    if (-not $cfg.IPv4Address) { continue }
    $ad = $adapters | Where-Object { $_.InterfaceIndex -eq $cfg.InterfaceIndex } | Select-Object -First 1
    $alias = [string]$cfg.InterfaceAlias
    $desc = [string]$cfg.InterfaceDescription
    $mac = if ($ad -and $ad.MacAddress) { ($ad.MacAddress -replace '-', ':').ToUpper() } else { '' }
    $mediaRaw = ''
    if ($ad) {
        $mediaRaw = "$($ad.PhysicalMediaType) $($ad.MediaType) $($ad.InterfaceDescription) $alias"
    } else {
        $mediaRaw = "$desc $alias"
    }
    $gw = ''
    if ($cfg.IPv4DefaultGateway) {
        $gw = [string]($cfg.IPv4DefaultGateway | Select-Object -First 1 -ExpandProperty NextHop)
    }
    foreach ($ipv4 in $cfg.IPv4Address) {
        if ($ipv4.IPAddress -like '169.254.*' -or $ipv4.IPAddress -eq '127.0.0.1') { continue }
        $out += [PSCustomObject]@{
            alias = $alias
            description = $desc
            ip = [string]$ipv4.IPAddress
            prefix = [int]$ipv4.PrefixLength
            mac = $mac
            mediaRaw = $mediaRaw
            gateway = $gw
        }
    }
}
$out | ConvertTo-Json -Compress
"""
    interfaces: List[NetworkInterface] = []
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            creationflags=_creation_flags(),
        )
        raw = proc.stdout.strip()
        if raw:
            data = json.loads(raw)
            if isinstance(data, dict):
                data = [data]
            for item in data:
                media_raw = (item.get("mediaRaw") or "").lower()
                if any(k in media_raw for k in ("802.11", "wi-fi", "wifi", "wireless", "wlan")):
                    media = "Wi-Fi"
                elif any(k in media_raw for k in ("802.3", "ethernet", "gigabit", "realtek", "intel(r) ethernet", "lan")):
                    media = "Cabeado"
                elif any(k in media_raw for k in ("vpn", "tap", "tun", "wireguard", "tailscale", "zerotier")):
                    media = "VPN / Virtual"
                else:
                    media = "Cabeado"
                interfaces.append(
                    NetworkInterface(
                        alias=item.get("alias", "Rede"),
                        description=item.get("description", ""),
                        ip=item.get("ip", ""),
                        prefix_length=int(item.get("prefix", 24) or 24),
                        mac=item.get("mac", ""),
                        media=media,
                        gateway=item.get("gateway", ""),
                    )
                )
    except Exception:
        pass

    # Fallback using standard socket if PowerShell returned nothing
    if not interfaces:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            interfaces.append(
                NetworkInterface(
                    alias="Interface Principal",
                    description="Detectada automaticamente",
                    ip=local_ip,
                    prefix_length=24,
                    mac="",
                    media="Cabeado",
                    gateway="",
                )
            )
        except Exception:
            interfaces.append(
                NetworkInterface(
                    alias="Rede Padrão",
                    description="Sub-rede local padrão",
                    ip="192.168.1.1",
                    prefix_length=24,
                    mac="",
                    media="Cabeado",
                    gateway="192.168.1.1",
                )
            )

    # Sort: interfaces with a default gateway first, then Wi-Fi/Cabeado before VPN
    interfaces.sort(
        key=lambda i: (
            0 if i.gateway else 1,
            0 if i.media in ("Cabeado", "Wi-Fi") else 1,
            i.alias.lower(),
        )
    )
    return interfaces


def read_system_arp_table() -> dict[str, str]:
    """Read Windows ARP cache as supplemental IP -> MAC mapping."""
    table: dict[str, str] = {}
    try:
        proc = subprocess.run(
            ["arp", "-a"],
            capture_output=True,
            text=True,
            encoding="latin-1",
            errors="replace",
            timeout=3,
            creationflags=_creation_flags(),
        )
        pattern = re.compile(r"(\d+\.\d+\.\d+\.\d+)\s+([0-9a-fA-F]{2}(?:-[0-9a-fA-F]{2}){5})")
        for match in pattern.finditer(proc.stdout):
            ip, mac = match.group(1), match.group(2).replace("-", ":").upper()
            if mac != "FF:FF:FF:FF:FF:FF" and not mac.startswith("01:00:5E"):
                table[ip] = mac
    except Exception:
        pass
    return table


# ---------------------------------------------------------------------------
# Hostname resolution (Reverse DNS + NetBIOS NBSTAT UDP/137)
# ---------------------------------------------------------------------------

def _query_netbios_name(ip: str, timeout: float = 0.35) -> Optional[str]:
    """Send a NetBIOS Node Status (NBSTAT) UDP packet to port 137 to fetch Windows/Samba hostname."""
    # Standard NBSTAT query for '*'
    packet = (
        b"\x82\x28"  # Transaction ID
        b"\x00\x00"  # Flags
        b"\x00\x01"  # Questions: 1
        b"\x00\x00"  # Answer RRs
        b"\x00\x00"  # Authority RRs
        b"\x00\x00"  # Additional RRs
        b"\x20" + b"CK" + b"A" * 30 + b"\x00"  # Encoded '*'
        b"\x00\x21"  # Type: NBSTAT
        b"\x00\x01"  # Class: IN
    )
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    try:
        sock.sendto(packet, (ip, 137))
        data, _ = sock.recvfrom(1024)
        if len(data) < 57:
            return None
        num_names = data[56]
        offset = 57
        for _ in range(num_names):
            if offset + 18 > len(data):
                break
            raw_name = data[offset : offset + 15]
            suffix = data[offset + 15]
            flags = struct.unpack("!H", data[offset + 16 : offset + 18])[0]
            offset += 18
            is_group = bool(flags & 0x8000)
            # Suffix 0x00 or 0x20 with unique (non-group) flag = Workstation / File Server name
            if not is_group and suffix in (0x00, 0x20):
                name = raw_name.decode("latin-1", errors="ignore").strip()
                if name:
                    return name
    except Exception:
        return None
    finally:
        sock.close()
    return None


def resolve_hostname(ip: str, is_local: bool = False) -> str:
    """Resolve hostname via local socket, Reverse DNS, and NetBIOS fallback."""
    if is_local:
        try:
            return socket.gethostname()
        except Exception:
            pass

    # Try Reverse DNS first
    try:
        host, _, _ = socket.gethostbyaddr(ip)
        if host and host != ip:
            return host.split(".")[0] if host.endswith(".local") or host.endswith(".lan") else host
    except Exception:
        pass

    # Fallback: NetBIOS NBSTAT query (UDP 137)
    nb_name = _query_netbios_name(ip, timeout=0.35)
    if nb_name:
        return nb_name

    return "—"


# ---------------------------------------------------------------------------
# Wi-Fi vs Cabeado multi-signal classifier
# ---------------------------------------------------------------------------

_WIFI_HOSTNAME_PATTERNS = (
    "iphone", "ipad", "ipod", "android", "galaxy", "samsung", "redmi", "xiaomi",
    "poco", "moto", "motorola", "pixel", "oneplus", "realme", "oppo", "vivo",
    "esp_", "esp-", "espressif", "tuya", "sonoff", "shelly", "chromecast",
    "alexa", "echo", "firetv", "fire-tv", "apple-tv", "appletv", "wifi", "wi-fi",
    "wlan", "wireless", "celular", "tablet", "macbook", "notebook", "laptop",
    "smartwatch", "mi-", "huawei-", "honor-",
)

_WIRED_HOSTNAME_PATTERNS = (
    "dvr", "nvr", "xvr", "cftv", "ipc", "cam-", "camera", "intelbras",
    "hikvision", "dahua", "axis", "switch", "router", "roteador", "gateway",
    "mikrotik", "unifi", "server", "srv", "nas", "printer", "impressora",
    "desktop", "workstation", "pdv", "caixa", "eth", "lan-", "pc-",
)

_CFTV_INFRA_PORTS = (554, 37777, 8000, 9100)  # RTSP, Dahua/Intelbras, Hikvision, Printer


def _has_wired_service_port(ip: str) -> Optional[int]:
    """Quick non-intrusive TCP probe on CFTV/printer ports (110ms timeout)."""
    for port in _CFTV_INFRA_PORTS:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.11)
        try:
            if sock.connect_ex((ip, port)) == 0:
                return port
        except Exception:
            pass
        finally:
            sock.close()
    return None


def classify_connection(
    ip: str,
    mac: str,
    hostname: str,
    vendor: str,
    vendor_hint: str,
    latency_ms: Optional[float],
    is_local: bool,
    local_media: Optional[str],
    is_gateway: bool,
) -> Tuple[str, str]:
    """Classify a host's connection type as Wi-Fi or Cabeado with explanation."""
    # 1. Local PC adapter — 100% exact
    if is_local and local_media in ("Wi-Fi", "Cabeado"):
        return (local_media, f"Confirmado pelo adaptador local do Windows ({local_media})")

    # 2. Default Gateway / Router
    if is_gateway:
        return ("Cabeado", "Gateway / roteador principal da sub-rede")

    host_l = (hostname or "").lower()

    # 3. Randomized / Locally Administered MAC (iOS/Android/Windows Wi-Fi privacy)
    if mac and mac != "—" and is_randomized_mac(mac):
        return ("Wi-Fi", "Endereço MAC aleatório (padrão de privacidade Wi-Fi)")

    # 4. Explicit hostname indicators
    for kw in _WIRED_HOSTNAME_PATTERNS:
        if kw in host_l:
            return ("Cabeado", f"Identificado pelo hostname ('{hostname}')")

    for kw in _WIFI_HOSTNAME_PATTERNS:
        if kw in host_l:
            return ("Wi-Fi", f"Identificado pelo hostname ('{hostname}')")

    # 5. Strong OUI vendor hints
    if vendor_hint == "wifi":
        return ("Wi-Fi", f"Fabricante típico de dispositivos Wi-Fi ({vendor})")
    if vendor_hint == "wired":
        return ("Cabeado", f"Fabricante de infraestrutura / CFTV / Ethernet ({vendor})")

    # 6. Check CFTV / Printer / Server service ports for ambiguous devices
    wired_port = _has_wired_service_port(ip)
    if wired_port is not None:
        port_names = {554: "RTSP/Câmera IP", 37777: "DVR/Intelbras/Dahua", 8000: "Serviço de rede / CFTV", 9100: "Impressora"}
        return ("Cabeado", f"Serviço cabeado detectado (porta {wired_port} — {port_names.get(wired_port, 'Infra')})")

    # 7. Latency profile heuristic (estimated)
    if latency_ms is not None:
        if latency_ms <= 2.0:
            return ("Cabeado (Est.)", f"Estimativa por baixa latência estável ({latency_ms:.1f} ms)")
        return ("Wi-Fi (Est.)", f"Estimativa por perfil de latência sem fio ({latency_ms:.1f} ms)")

    if not mac or mac == "—":
        return ("Indeterminado", "Host fora da sub-rede local (sem ARP/MAC direto)")

    return ("Cabeado (Est.)", "Estimativa padrão de rede local (ARP direto)")


# ---------------------------------------------------------------------------
# Pool parsing & parallel scanner
# ---------------------------------------------------------------------------

MAX_POOL_HOSTS = 4096


def parse_cidr_pool(cidr_text: str) -> Tuple[List[str], str]:
    """Parse CIDR or single IP string into a list of host IPv4 strings."""
    cleaned = cidr_text.strip()
    if not cleaned:
        raise ValueError("Informe uma sub-rede válida (ex: 192.168.1.0/24).")
    if "/" not in cleaned:
        ip = ipaddress.IPv4Address(cleaned)
        return ([str(ip)], f"{ip}/32")
    net = ipaddress.IPv4Network(cleaned, strict=False)
    if net.num_addresses == 1:
        hosts = [str(net.network_address)]
    elif net.num_addresses == 2:
        hosts = [str(ip) for ip in net]
    else:
        hosts = [str(ip) for ip in net.hosts()]
    if len(hosts) > MAX_POOL_HOSTS:
        raise ValueError(
            f"O pool {net} possui {len(hosts):,} endereços. "
            f"Use um intervalo menor (máximo de {MAX_POOL_HOSTS:,} IPs por consulta)."
        )
    return (hosts, str(net))


def parse_range_pool(start_ip_text: str, end_ip_text: str) -> Tuple[List[str], str]:
    """Parse start_ip .. end_ip inclusive range into a list of IPv4 strings."""
    start_s = start_ip_text.strip()
    end_s = end_ip_text.strip()
    if not start_s or not end_s:
        raise ValueError("Informe o IP inicial e o IP final do pool.")
    start = ipaddress.IPv4Address(start_s)
    end = ipaddress.IPv4Address(end_s)
    if int(end) < int(start):
        raise ValueError("O IP final deve ser maior ou igual ao IP inicial.")
    count = int(end) - int(start) + 1
    if count > MAX_POOL_HOSTS:
        raise ValueError(
            f"A faixa selecionada possui {count:,} endereços. "
            f"Limite máximo por consulta: {MAX_POOL_HOSTS:,} IPs."
        )
    hosts = [str(ipaddress.IPv4Address(i)) for i in range(int(start), int(end) + 1)]
    return (hosts, f"{start} — {end}")


class NetworkScanner:
    """Thread-safe parallel IP pool scanner with live progress and cancellation."""

    def __init__(self, max_workers: int = 160):
        self.max_workers = max_workers
        self._cancel_event = threading.Event()

    def cancel(self) -> None:
        self._cancel_event.set()

    @property
    def is_cancelled(self) -> bool:
        return self._cancel_event.is_set()

    def scan_pool(
        self,
        ip_list: List[str],
        local_interfaces: List[NetworkInterface],
        on_host_found: Optional[Callable[[DiscoveredHost], None]] = None,
        on_progress: Optional[Callable[[int, int], None]] = None,
    ) -> List[DiscoveredHost]:
        """Scan all IPs in ip_list concurrently and return discovered hosts."""
        self._cancel_event.clear()
        total = len(ip_list)
        if total == 0:
            return []

        local_by_ip = {iface.ip: iface for iface in local_interfaces}
        local_networks = []
        for iface in local_interfaces:
            try:
                local_networks.append(ipaddress.IPv4Network(iface.cidr, strict=False))
            except ValueError:
                pass
        gateways = {iface.gateway for iface in local_interfaces if iface.gateway}
        arp_cache = read_system_arp_table()

        def is_on_local_subnet(ip_str: str) -> bool:
            try:
                addr = ipaddress.IPv4Address(ip_str)
                return any(addr in net for net in local_networks)
            except ValueError:
                return False

        results: List[DiscoveredHost] = []
        completed = 0
        lock = threading.Lock()

        def probe_ip(ip: str) -> Optional[DiscoveredHost]:
            if self._cancel_event.is_set():
                return None

            local_iface = local_by_ip.get(ip)
            if local_iface is not None:
                mac = local_iface.mac or "—"
                vendor, hint = lookup_oui(mac) if mac != "—" else ("Adaptador Local", "mixed")
                hostname = resolve_hostname(ip, is_local=True)
                conn, reason = classify_connection(
                    ip=ip,
                    mac=mac,
                    hostname=hostname,
                    vendor=vendor,
                    vendor_hint=hint,
                    latency_ms=0.0,
                    is_local=True,
                    local_media=local_iface.media,
                    is_gateway=(ip in gateways),
                )
                return DiscoveredHost(
                    ip=ip,
                    hostname=hostname,
                    mac=mac,
                    vendor=vendor,
                    connection_type=conn,
                    connection_reason=reason,
                    latency_ms=0.0,
                    is_local=True,
                    is_gateway=(ip in gateways),
                )

            # 1. Fast Layer-2 ARP discovery (finds even ping-firewalled LAN hosts!)
            on_local_lan = is_on_local_subnet(ip)
            mac = send_arp(ip) if on_local_lan else None
            alive_icmp = False
            rtt_ms: Optional[float] = None

            if mac:
                # Host is alive on L2; quick ping to measure latency for display & heuristics
                alive_icmp, rtt_ms, _ = icmp_ping(ip, timeout_ms=220)
            else:
                if self._cancel_event.is_set():
                    return None
                # 2. Layer-3 ICMP ping: short timeout on local LAN (proxy-ARP/routed edge cases),
                #    standard timeout on remote subnets
                ping_timeout = 200 if on_local_lan else 420
                alive_icmp, rtt_ms, _ = icmp_ping(ip, timeout_ms=ping_timeout)
                if not alive_icmp:
                    return None
                mac = arp_cache.get(ip) or (send_arp(ip) if on_local_lan else None) or "—"

            if self._cancel_event.is_set():
                return None

            hostname = resolve_hostname(ip, is_local=False)
            vendor, vendor_hint = lookup_oui(mac) if mac != "—" else ("Não disponível", "unknown")
            conn, reason = classify_connection(
                ip=ip,
                mac=mac,
                hostname=hostname,
                vendor=vendor,
                vendor_hint=vendor_hint,
                latency_ms=rtt_ms,
                is_local=False,
                local_media=None,
                is_gateway=(ip in gateways),
            )
            return DiscoveredHost(
                ip=ip,
                hostname=hostname,
                mac=mac,
                vendor=vendor,
                connection_type=conn,
                connection_reason=reason,
                latency_ms=rtt_ms,
                is_local=False,
                is_gateway=(ip in gateways),
            )

        workers = min(self.max_workers, max(8, total))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(probe_ip, ip): ip for ip in ip_list}
            for future in as_completed(futures):
                host = None
                try:
                    host = future.result()
                except Exception:
                    host = None

                with lock:
                    completed += 1
                    curr = completed
                    if host is not None:
                        results.append(host)

                if host is not None and on_host_found:
                    on_host_found(host)
                if on_progress:
                    on_progress(curr, total)

        results.sort(key=lambda h: h.ip_sort_key)
        return results
