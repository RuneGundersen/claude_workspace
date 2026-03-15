"""ICMP ping sweep via subprocess — no raw sockets, no admin required."""

import subprocess
import concurrent.futures
from ipaddress import IPv4Network


def ping_host(ip: str, timeout_ms: int = 300) -> bool:
    """Ping a single host. Returns True if it responds."""
    try:
        result = subprocess.run(
            ["ping", "-n", "1", "-w", str(timeout_ms), ip],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
        return b"TTL=" in result.stdout.upper()
    except Exception:
        return False


def sweep(network: str = "192.168.55.0/24", max_workers: int = 80) -> list:
    """Ping-sweep a network, return sorted list of responding IPs."""
    hosts = [str(ip) for ip in IPv4Network(network, strict=False).hosts()]
    live = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(ping_host, ip): ip for ip in hosts}
        for future in concurrent.futures.as_completed(futures):
            if future.result():
                live.append(futures[future])
    return sorted(live, key=lambda x: int(x.split(".")[-1]))
