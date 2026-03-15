"""HTTP probe — grab title, detect OVMS via Mongoose server header and /api/status."""

import http.client
import json
import re
import socket


def _get(ip: str, port: int, path: str, timeout: float = 3.0):
    """
    Perform a simple GET request.
    Returns (status, headers_dict, body_bytes) or raises on error.
    """
    conn = http.client.HTTPConnection(ip, port, timeout=timeout)
    conn.request("GET", path, headers={"Host": ip, "Connection": "close"})
    resp = conn.getresponse()
    body = resp.read(8192)  # cap at 8 KB
    headers = {k.lower(): v for k, v in resp.getheaders()}
    conn.close()
    return resp.status, headers, body


def probe_http(ip: str, port: int = 80) -> dict:
    """
    Probe an HTTP host and return a dict with:
      title, server, ovms_score, ovms_confirmed, error
    """
    result = {
        "title": "",
        "server": "",
        "ovms_score": 0,
        "ovms_confirmed": False,
        "error": None,
    }

    try:
        status, headers, body = _get(ip, port, "/", timeout=3.0)
    except Exception as e:
        result["error"] = str(e)
        return result

    # Server header
    server = headers.get("server", "")
    result["server"] = server

    # Extract <title>
    body_text = body.decode("utf-8", errors="ignore")
    title_match = re.search(r"<title[^>]*>(.*?)</title>", body_text, re.IGNORECASE | re.DOTALL)
    if title_match:
        result["title"] = title_match.group(1).strip()[:80]

    # --- OVMS detection (hard signals only — no fuzzy text matching) ---
    score = 0

    # Signal 1: Mongoose web server header — OVMS ships Mongoose, almost
    # nothing else on a home LAN uses it.
    if "mongoose" in server.lower():
        score += 3
        result["ovms_confirmed"] = True

    # Signal 2: /api/status endpoint returning OVMS-specific JSON keys.
    # This is the gold standard — no other device will respond like this.
    try:
        st, _, api_body = _get(ip, port, "/api/status", timeout=2.0)
        if st == 200:
            api_text = api_body.decode("utf-8", errors="ignore")
            try:
                data = json.loads(api_text)
                if isinstance(data, dict) and any(
                    k in data for k in ("vehicle", "v", "m_version", "firmware")
                ):
                    score += 5
                    result["ovms_confirmed"] = True
            except json.JSONDecodeError:
                pass
    except Exception:
        pass

    # Signal 3: try a few other known OVMS endpoints as tie-breakers
    if not result["ovms_confirmed"]:
        for path in ("/api/metrics", "/api/vehicle"):
            try:
                st, hdrs, _ = _get(ip, port, path, timeout=1.5)
                if st == 200 and "mongoose" in hdrs.get("server", "").lower():
                    score += 3
                    result["ovms_confirmed"] = True
                    break
            except Exception:
                pass

    result["ovms_score"] = score
    return result
