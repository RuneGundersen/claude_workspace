"""Non-privileged TCP connect port scanner."""

import socket
import concurrent.futures

DEFAULT_PORTS = [22, 23, 80, 443, 1883, 8080, 8443, 8883]


def scan_port(ip: str, port: int, timeout: float = 0.5) -> tuple:
    """Try TCP connect to ip:port. Returns (ip, port, open)."""
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return (ip, port, True)
    except Exception:
        return (ip, port, False)


def scan_hosts(hosts: list, ports: list = None, timeout: float = 0.5,
               max_workers: int = 200) -> dict:
    """
    Scan all (host, port) combos in parallel.
    Returns {ip: [open_port, ...]} for hosts with at least one open port.
    """
    if ports is None:
        ports = DEFAULT_PORTS

    tasks = [(ip, port) for ip in hosts for port in ports]
    results: dict = {ip: [] for ip in hosts}

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(scan_port, ip, port, timeout): (ip, port)
                   for ip, port in tasks}
        for future in concurrent.futures.as_completed(futures):
            ip, port, is_open = future.result()
            if is_open:
                results[ip].append(port)

    # Sort open ports per host; drop hosts with no open ports
    return {ip: sorted(ports) for ip, ports in results.items() if ports}
