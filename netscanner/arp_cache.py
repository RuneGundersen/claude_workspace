"""Parse Windows ARP cache to get IP→MAC mappings — no admin required."""

import subprocess
import re


def get_arp_table() -> dict:
    """
    Run `arp -a` and return {ip: mac} dict.
    Windows uses dashes (aa-bb-cc); we normalise to colons.
    """
    try:
        result = subprocess.run(
            ["arp", "-a"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
        output = result.stdout.decode("utf-8", errors="ignore")
    except Exception:
        return {}

    table = {}
    # Match lines like:  192.168.55.1          aa-bb-cc-dd-ee-ff     dynamic
    pattern = re.compile(
        r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\s+"
        r"([\da-fA-F]{2}[:\-][\da-fA-F]{2}[:\-][\da-fA-F]{2}"
        r"[:\-][\da-fA-F]{2}[:\-][\da-fA-F]{2}[:\-][\da-fA-F]{2})"
    )
    for m in pattern.finditer(output):
        ip, mac = m.group(1), m.group(2)
        # Skip broadcast / multicast
        if mac.lower() in ("ff-ff-ff-ff-ff-ff", "ff:ff:ff:ff:ff:ff"):
            continue
        if mac.lower().startswith("01-00-5e") or mac.lower().startswith("01:00:5e"):
            continue
        # Normalise dashes → colons, lowercase
        table[ip] = mac.lower().replace("-", ":")
    return table
