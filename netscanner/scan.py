#!/usr/bin/env python3
"""
netscanner — LAN scanner optimised for OVMS device discovery.

Usage:
    python scan.py
    python scan.py --network 192.168.1.0/24
    python scan.py --network 192.168.55.0/24 --ports 80,443,22,8080
"""

import argparse
import concurrent.futures
import io
import socket
import sys
import time

# Force UTF-8 output on Windows so box-drawing characters render correctly.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from ping import sweep
from arp_cache import get_arp_table
from port_scan import scan_hosts
from http_probe import probe_http
from oui import lookup, is_esp32


# ── Helpers ───────────────────────────────────────────────────────────────────

def resolve_hostname(ip: str, timeout: float = 1.5) -> str:
    """Reverse-DNS lookup with timeout. Returns '' on failure."""
    import concurrent.futures as cf
    with cf.ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(socket.gethostbyaddr, ip)
        try:
            name, _, _ = fut.result(timeout=timeout)
            return name
        except Exception:
            return ""


def resolve_all(ips: list, total_timeout: float = 8.0, max_workers: int = 30) -> dict:
    """
    Resolve hostnames for all IPs in parallel with a hard wall-clock cutoff.
    socket.gethostbyaddr() ignores per-thread timeouts, so we use wait() with
    a total budget and abandon any lookups still running after that.
    """
    results = {ip: "" for ip in ips}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
        future_to_ip = {ex.submit(socket.gethostbyaddr, ip): ip for ip in ips}
        done, _ = concurrent.futures.wait(future_to_ip, timeout=total_timeout)
        for fut in done:
            ip = future_to_ip[fut]
            try:
                name, _, _ = fut.result()
                results[ip] = name
            except Exception:
                pass
    return results


# ── Display ───────────────────────────────────────────────────────────────────

def _col(s: str, width: int) -> str:
    s = str(s)
    if len(s) > width:
        s = s[:width - 1] + "…"
    return s.ljust(width)


def _ports_str(ports: list) -> str:
    if not ports:
        return "-"
    return ", ".join(str(p) for p in ports)


def print_results(results: list, ovms_hosts: list, elapsed: float, network: str) -> None:
    sep = "─" * 110

    print()
    print(f"  Scan of {network}  ·  {len(results)} hosts  ·  {elapsed:.1f}s")
    print()

    # ── OVMS highlight ────────────────────────────────────────────────────────
    if ovms_hosts:
        confirmed = [h for h in ovms_hosts if h["ovms_confirmed"]]
        candidates = [h for h in ovms_hosts if not h["ovms_confirmed"]]

        for h in confirmed:
            print("  ╔══════════════════════════════════════════════════════╗")
            print("  ║            ✓  OVMS DEVICE FOUND                     ║")
            print("  ╚══════════════════════════════════════════════════════╝")
            print(f"    IP       : {h['ip']}")
            if h["hostname"]:
                print(f"    Hostname : {h['hostname']}")
            print(f"    MAC      : {h['mac']}")
            print(f"    Vendor   : {h['vendor']}")
            print(f"    Ports    : {_ports_str(h['ports'])}")
            if h["http"].get("title"):
                print(f"    HTTP     : \"{h['http']['title']}\"  [{h['http'].get('server','')}]")
            print(f"    Score    : {h['ovms_score']}  (CONFIRMED)")
            print()

        for h in candidates:
            print(f"  ? Possible OVMS at {h['ip']}  (score {h['ovms_score']}, not confirmed)")
            print()
    else:
        print("  OVMS device not found on this scan.")
        print("  (Try connecting the OVMS to WiFi first, or check it's on this subnet.)")
        print()

    # ── Full table ────────────────────────────────────────────────────────────
    print(sep)
    print(
        _col("IP ADDRESS", 16) +
        _col("MAC ADDRESS", 20) +
        _col("VENDOR", 22) +
        _col("OPEN PORTS", 22) +
        _col("HOSTNAME", 22) +
        "HTTP TITLE"
    )
    print(sep)

    for h in results:
        ovms_flag = " ◄ OVMS" if h["ovms_confirmed"] else ""
        print(
            _col(h["ip"], 16) +
            _col(h["mac"], 20) +
            _col(h["vendor"], 22) +
            _col(_ports_str(h["ports"]), 22) +
            _col(h["hostname"] or "-", 22) +
            (h["http"].get("title") or "-") +
            ovms_flag
        )

    print(sep)
    print()

    if ovms_hosts and any(h["ovms_confirmed"] for h in ovms_hosts):
        ip = next(h["ip"] for h in ovms_hosts if h["ovms_confirmed"])
        print(f"  → OVMS web UI:  http://{ip}/")
        print(f"  → OVMS shell:   telnet {ip}")
        print()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="LAN scanner — finds OVMS and identifies all devices"
    )
    parser.add_argument("--network", default="192.168.55.0/24",
                        help="Network to scan (default: 192.168.55.0/24)")
    parser.add_argument("--ports", default=None,
                        help="Comma-separated port list (default: 22,23,80,443,1883,8080,8443,8883)")
    parser.add_argument("--timeout", type=float, default=0.5,
                        help="TCP connect timeout in seconds (default: 0.5)")
    args = parser.parse_args()

    ports = [int(p) for p in args.ports.split(",")] if args.ports else None

    t0 = time.time()

    # 1. Ping sweep
    print(f"[1/5] Pinging {args.network} ...", flush=True)
    live = sweep(args.network)
    print(f"      {len(live)} host(s) responding", flush=True)

    if not live:
        print("\n  No hosts found. Check the network range and try again.")
        return

    # 2. ARP cache
    print("[2/5] Reading ARP cache ...", flush=True)
    arp = get_arp_table()

    # 3. Port scan
    print(f"[3/5] Port scanning {len(live)} host(s) ...", flush=True)
    open_ports = scan_hosts(live, ports=ports, timeout=args.timeout)

    # 4. HTTP probe
    web_hosts = [ip for ip, p in open_ports.items() if 80 in p or 8080 in p]
    print(f"[4/5] HTTP probing {len(web_hosts)} web host(s) ...", flush=True)
    http_data: dict = {}
    for ip in web_hosts:
        port = 80 if 80 in open_ports[ip] else 8080
        http_data[ip] = probe_http(ip, port)

    # 5. Hostname resolution
    print(f"[5/5] Resolving hostnames ...", flush=True)
    hostnames = resolve_all(live)

    # Assemble results
    results = []
    ovms_hosts = []

    for ip in live:
        mac = arp.get(ip, "??:??:??:??:??:??")
        http = http_data.get(ip, {})
        ovms_score = http.get("ovms_score", 0) + (2 if is_esp32(mac) else 0)
        entry = {
            "ip": ip,
            "mac": mac,
            "vendor": lookup(mac),
            "ports": open_ports.get(ip, []),
            "hostname": hostnames.get(ip, ""),
            "http": http,
            "ovms_score": ovms_score,
            "ovms_confirmed": http.get("ovms_confirmed", False),
        }
        if ovms_score > 0:
            ovms_hosts.append(entry)
        results.append(entry)

    print_results(results, ovms_hosts, time.time() - t0, args.network)


if __name__ == "__main__":
    main()
