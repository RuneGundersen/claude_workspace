"""OUI vendor lookup — inline table, no external files or pip installs."""

# Known Espressif (ESP32/ESP8266) OUI prefixes — OVMS uses ESP32
ESP32_OUIS = {
    "24:6f:28", "30:ae:a4", "a4:cf:12", "40:91:51",
    "24:6a:0e", "40:b0:76", "7c:df:a1", "84:cc:a8",
    "cc:50:e3", "b4:e6:2d", "ac:67:b2", "ec:fa:bc",
    "80:7d:3a", "d8:a0:1d", "3c:71:bf", "08:3a:f2",
    "e8:68:e7", "10:52:1c",
}

OUI_TABLE = {
    # Espressif
    "24:6f:28": "Espressif (ESP32)",
    "30:ae:a4": "Espressif (ESP32)",
    "a4:cf:12": "Espressif (ESP32)",
    "40:91:51": "Espressif (ESP32)",
    "24:6a:0e": "Espressif (ESP32)",
    "40:b0:76": "Espressif (ESP32)",
    "7c:df:a1": "Espressif (ESP32)",
    "84:cc:a8": "Espressif (ESP32)",
    "cc:50:e3": "Espressif (ESP32)",
    "b4:e6:2d": "Espressif (ESP32)",
    "ac:67:b2": "Espressif",
    "ec:fa:bc": "Espressif",
    "80:7d:3a": "Espressif (ESP32)",
    "d8:a0:1d": "Espressif (ESP32)",
    "3c:71:bf": "Espressif (ESP32)",
    "08:3a:f2": "Espressif (ESP32)",
    "e8:68:e7": "Espressif (ESP32)",
    "10:52:1c": "Espressif (ESP32)",
    "18:fe:34": "Espressif (ESP8266)",
    "60:01:94": "Espressif (ESP8266)",
    # Raspberry Pi
    "b8:27:eb": "Raspberry Pi",
    "dc:a6:32": "Raspberry Pi 4",
    "e4:5f:01": "Raspberry Pi",
    "d8:3a:dd": "Raspberry Pi",
    "28:cd:c1": "Raspberry Pi",
    # Apple
    "04:18:d6": "Apple",
    "a8:66:7f": "Apple",
    "3c:22:fb": "Apple",
    "f8:ff:c2": "Apple",
    "ac:bc:32": "Apple",
    "8c:85:90": "Apple",
    "70:56:81": "Apple",
    "f4:d4:88": "Apple",
    "18:65:90": "Apple",
    "a4:83:e7": "Apple",
    # Google
    "00:1a:11": "Google",
    "54:60:09": "Google (Nest/Home)",
    "f4:f5:d8": "Google (Nest)",
    "d4:f5:47": "Google (Chromecast)",
    "48:d6:d5": "Google",
    "3c:28:6d": "Google (Chromecast)",
    "58:ef:68": "Google (Chromecast)",
    # Amazon
    "28:6d:cd": "Amazon",
    "fc:a1:83": "Amazon (Echo)",
    "44:65:0d": "Amazon",
    "f0:81:73": "Amazon (Echo)",
    "74:c2:46": "Amazon",
    # Samsung
    "2c:f0:5d": "Samsung",
    "8c:77:12": "Samsung",
    "50:32:75": "Samsung",
    "f4:7b:5e": "Samsung",
    "e4:7d:bd": "Samsung",
    # TP-Link
    "50:c7:bf": "TP-Link",
    "b0:be:76": "TP-Link",
    "98:da:c4": "TP-Link",
    "e8:de:27": "TP-Link",
    "a0:f3:c1": "TP-Link",
    "18:d6:c7": "TP-Link",
    "b0:4e:26": "TP-Link",
    "60:32:b1": "TP-Link",
    # Netgear
    "b4:79:a7": "Netgear",
    "28:c6:8e": "Netgear",
    "a0:40:a0": "Netgear",
    "20:e5:2a": "Netgear",
    "9c:d3:6d": "Netgear",
    # Asus
    "04:92:26": "Asus",
    "a8:5e:45": "Asus",
    "2c:56:dc": "Asus",
    "30:5a:3a": "Asus",
    "50:46:5d": "Asus",
    # Ubiquiti
    "00:1e:c0": "Ubiquiti",
    "24:a4:3c": "Ubiquiti",
    "78:45:58": "Ubiquiti",
    "44:d9:e7": "Ubiquiti",
    "f0:9f:c2": "Ubiquiti",
    "80:2a:a8": "Ubiquiti",
    # Synology
    "f0:08:d1": "Synology",
    "00:11:32": "Synology",
    "b8:ae:ed": "Synology",
    "00:50:43": "Synology",
    # Philips Hue / Signify
    "00:17:88": "Philips Hue",
    "ec:b5:fa": "Philips Hue",
    # Sonos
    "78:28:ca": "Sonos",
    "94:9f:3e": "Sonos",
    "34:7e:5c": "Sonos",
    # Intel (common in laptops)
    "8c:8d:28": "Intel",
    "94:65:9c": "Intel",
    "a4:c3:f0": "Intel",
    "00:1b:21": "Intel",
    # Realtek (common in desktops/laptops)
    "e0:d5:5e": "Realtek",
    "00:e0:4c": "Realtek",
    # VMware
    "00:50:56": "VMware",
    "00:0c:29": "VMware",
    "00:05:69": "VMware",
    # Printer vendors
    "00:00:48": "Seiko Epson",
    "08:00:37": "HP",
    "00:80:77": "HP",
    "3c:d9:2b": "HP",
    "58:20:b1": "HP",
    "1c:98:ec": "Canon",
    "00:1e:8f": "Canon",
    "00:00:74": "Ricoh",
    "00:26:73": "Brother",
    "00:80:92": "Xerox",
}


def _normalise(mac: str) -> str:
    """Normalise MAC to lowercase colon-separated."""
    return mac.lower().replace("-", ":").replace(".", ":")


def lookup(mac: str) -> str:
    """Return vendor string for a MAC address, or 'Unknown'."""
    if not mac or mac.startswith("?"):
        return "Unknown"
    norm = _normalise(mac)
    oui = ":".join(norm.split(":")[:3])
    return OUI_TABLE.get(oui, "Unknown")


def is_esp32(mac: str) -> bool:
    """Return True if MAC OUI matches a known ESP32 prefix."""
    if not mac or mac.startswith("?"):
        return False
    norm = _normalise(mac)
    oui = ":".join(norm.split(":")[:3])
    return oui in ESP32_OUIS
