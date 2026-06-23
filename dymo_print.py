"""
dymo_print.py — the ONLY hardware-dependent module.

Talks to the DYMO Connect web service running on localhost (port 41951, HTTPS
with a self-signed cert). Everything else in the app is testable without a
printer; this is the single place that needs real hardware.

While the printer is away, set SIMULATE = True (the default). In simulate mode
the print functions log what they *would* do and always "succeed", so the whole
pipeline — receive, map, fill, preview, "print" — runs end to end. Flip
SIMULATE to False (or set env DYMO_SIMULATE=0) when the printer is connected.
"""

import os
import re
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DYMO_BASE = "https://127.0.0.1:41951/DYMO/DLS/Printing"

# Default to simulation so nothing breaks without a printer.
SIMULATE = os.environ.get("DYMO_SIMULATE", "1") != "0"


class PrinterError(RuntimeError):
    pass


def service_alive() -> bool:
    if SIMULATE:
        return True
    try:
        r = requests.get(f"{DYMO_BASE}/StatusConnected", verify=False, timeout=5)
        return r.status_code == 200
    except requests.exceptions.RequestException:
        return False


def get_printer_name() -> str | None:
    if SIMULATE:
        return "SIMULATED-LabelWriter"
    try:
        r = requests.get(f"{DYMO_BASE}/GetPrinters", verify=False, timeout=5)
    except requests.exceptions.RequestException as e:
        raise PrinterError(f"Could not reach DYMO service: {e}")
    if r.status_code != 200:
        raise PrinterError(f"GetPrinters returned HTTP {r.status_code}")
    names = re.findall(r"<Name>(.*?)</Name>", r.text)
    return names[0] if names else None


def print_label_xml(label_xml: str, printer_name: str | None = None,
                    copies: int = 1) -> None:
    """
    Print one filled label. Raises PrinterError on failure.
    In SIMULATE mode this just returns successfully.
    """
    if SIMULATE:
        # Log a short identifier so simulated runs are traceable.
        fid = _peek_fid(label_xml)
        print(f"[SIMULATE] would print label (fid={fid}, copies={copies})")
        return

    if printer_name is None:
        printer_name = get_printer_name()
    if not printer_name:
        raise PrinterError("No DYMO printer found.")

    print_params_xml = (
        "<LabelWriterPrintParams>"
        f"<Copies>{copies}</Copies>"
        "<PrintQuality>Auto</PrintQuality>"
        "</LabelWriterPrintParams>"
    )
    payload = {
        "printerName": printer_name,
        "printParamsXml": print_params_xml,
        "labelXml": label_xml,
        "labelSetXml": "",
    }
    try:
        r = requests.post(f"{DYMO_BASE}/PrintLabel", data=payload,
                          verify=False, timeout=15)
    except requests.exceptions.RequestException as e:
        raise PrinterError(f"Print request failed: {e}")
    if r.status_code != 200:
        raise PrinterError(f"PrintLabel HTTP {r.status_code}: {r.text[:200]}")


def _peek_fid(label_xml: str) -> str:
    # best-effort: the FID is the big text object; just grab first short <Text>
    for t in re.findall(r"<Text>(.*?)</Text>", label_xml, re.S):
        t = t.strip()
        if t.isdigit():
            return t
    return "?"


if __name__ == "__main__":
    print(f"  SIMULATE = {SIMULATE}")
    print(f"  service_alive() = {service_alive()}")
    print(f"  get_printer_name() = {get_printer_name()}")
    print_label_xml("<Text>703</Text>")
