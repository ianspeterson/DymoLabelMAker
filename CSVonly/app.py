"""
app.py — the laptop appliance.

Runs as a background web server on your cart laptop. MA POSTs fixture data to
/print; the server applies link mappings, fills templates, and prints. When any
universe is unmapped, it opens the review screen instead of printing blind.

Useful routes while developing:
  POST /ma-test          prove MA -> laptop HTTP without needing template/printer
  GET  /api/status       JSON status for the always-open cart browser tab
  POST /print            real/simulated fixture-label print request

Design notes:
  - MA only ever sends. The server never calls back to MA.
  - Pending jobs are in memory and expire automatically.
  - Simulate mode still fills the DYMO template; /ma-test does not.
"""

from __future__ import annotations

import os
import sys
import time
import uuid
import webbrowser
import threading
import socket
import subprocess
import re
from typing import Any
from dataclasses import asdict
from flask import (Flask, request, jsonify, render_template,
                   redirect, url_for, Response, abort, send_file)

from link_store import LinkStore
from profile_store import ProfileOverrideStore, make_profile_key
from label_fill import fill_template, REQUIRED_FIELDS
from label_render import render_to_png_bytes
from template_store import TemplateStore, REQUIRED_TOKENS
from csv_store import CsvPatchStore, CANONICAL_FIELDS
import dymo_print

# PyInstaller support:
# - APP_DIR is the writable folder next to BOLabelStation.exe.
# - RESOURCE_DIR is where bundled read-only files live during a PyInstaller run.
# This keeps uploaded CSVs, templates, link maps, and overrides next to the EXE
# instead of inside PyInstaller's temporary/read-only bundle area.
def _app_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _resource_dir() -> str:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS
    return _app_dir()


APP_DIR = _app_dir()
RESOURCE_DIR = _resource_dir()
DEFAULT_TEMPLATE_FILE = os.path.join(APP_DIR, "LabelTemplate_2026_Python.dymo")
BUNDLED_DEFAULT_TEMPLATE_FILE = os.path.join(RESOURCE_DIR, "LabelTemplate_2026_Python.dymo")
if not os.path.exists(DEFAULT_TEMPLATE_FILE) and os.path.exists(BUNDLED_DEFAULT_TEMPLATE_FILE):
    DEFAULT_TEMPLATE_FILE = BUNDLED_DEFAULT_TEMPLATE_FILE
DATA_DIR = os.path.join(APP_DIR, "data")
LINK_MAP_PATH = os.path.join(DATA_DIR, "link_map.json")
PROFILE_OVERRIDE_PATH = os.path.join(DATA_DIR, "profile_overrides.json")
TEMPLATE_DIR = os.path.join(DATA_DIR, "templates")
CSV_DIR = os.path.join(DATA_DIR, "csv")

# Behavior toggles. Environment variables override these defaults.
AUTO_PRINT_WHEN_ALL_MAPPED = os.environ.get("LABEL_AUTO_PRINT", "1") != "0"
OPEN_BROWSER_ON_REVIEW = os.environ.get("LABEL_OPEN_BROWSER", "1") != "0"
PENDING_JOB_TTL_SECONDS = int(os.environ.get("LABEL_PENDING_TTL", "7200"))

# Optional light security for show networks. Defaults are intentionally open for easy testing.
# If LABEL_STATION_TOKEN is set, /print and /ma-test require X-Label-Station-Token.
AUTH_TOKEN = os.environ.get("LABEL_STATION_TOKEN", "").strip()
# If LABEL_ALLOWED_IPS is set, comma-separated remote IPs are allowed to POST.
ALLOWED_SOURCE_IPS = {
    ip.strip() for ip in os.environ.get("LABEL_ALLOWED_IPS", "").split(",") if ip.strip()
}

app = Flask(__name__, template_folder=os.path.join(RESOURCE_DIR, "templates"), static_folder=os.path.join(RESOURCE_DIR, "static"))
links = LinkStore(LINK_MAP_PATH)
profile_overrides = ProfileOverrideStore(PROFILE_OVERRIDE_PATH)
templates = TemplateStore(DEFAULT_TEMPLATE_FILE, TEMPLATE_DIR)
csv_patch = CsvPatchStore(CSV_DIR)

# In-memory pending jobs: job_id -> {"fixtures": [...], "unmapped": [...], "created": float}
_pending: dict[str, dict[str, Any]] = {}
_pending_lock = threading.Lock()
_print_lock = threading.Lock()

_last_request: dict[str, Any] | None = None
_last_request_lock = threading.Lock()


def _load_template() -> str:
    return templates.load()


def _template_ok() -> bool:
    return templates.status().ok


def _client_ip() -> str:
    # request.remote_addr is enough for a direct console/laptop network.
    return request.remote_addr or "unknown"


def _local_ipv4_addresses() -> list[str]:
    """Best-effort list of local IPv4 addresses for the status page.

    Flask binds to 0.0.0.0, which listens on all interfaces, but Werkzeug
    usually only prints localhost plus one chosen LAN address. On carts with
    Wi-Fi + Ethernet + USB/Ethernet adapters, this helper shows more of the
    actual addresses users can try from MA.
    """
    found: set[str] = {"127.0.0.1"}

    def add(ip: str | None):
        if not ip:
            return
        ip = ip.strip()
        if re.fullmatch(r"(?:\d{1,3}\.){3}\d{1,3}", ip):
            parts = [int(x) for x in ip.split(".")]
            if all(0 <= x <= 255 for x in parts) and ip != "0.0.0.0":
                found.add(ip)

    # Hostname lookup often catches one or more active adapters.
    try:
        hostname = socket.gethostname()
        for ip in socket.gethostbyname_ex(hostname)[2]:
            add(ip)
    except Exception:
        pass

    # UDP trick catches the default-route interface without sending packets.
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        add(s.getsockname()[0])
        s.close()
    except Exception:
        pass

    # Windows: parse ipconfig so Wi-Fi/Ethernet/USB adapters all show.
    if os.name == "nt":
        try:
            out = subprocess.check_output(["ipconfig"], text=True, encoding="utf-8", errors="ignore")
            for m in re.finditer(r"IPv4 Address[^:]*:\s*([0-9.]+)", out):
                add(m.group(1))
        except Exception:
            pass
    else:
        # Linux/macOS fallback.
        for cmd in (["hostname", "-I"], ["ifconfig"]):
            try:
                out = subprocess.check_output(cmd, text=True, encoding="utf-8", errors="ignore")
                for ip in re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", out):
                    add(ip)
            except Exception:
                pass

    def sort_key(ip: str):
        if ip == "127.0.0.1":
            return (0, ip)
        return (1, tuple(int(x) for x in ip.split(".")))

    return sorted(found, key=sort_key)


def _access_urls() -> list[str]:
    return [f"http://{ip}:5000" for ip in _local_ipv4_addresses()]


def _check_post_access() -> tuple[bool, str | None]:
    if ALLOWED_SOURCE_IPS and _client_ip() not in ALLOWED_SOURCE_IPS:
        return False, f"Source IP {_client_ip()} is not allowed."
    if AUTH_TOKEN:
        got = request.headers.get("X-Label-Station-Token", "") or request.args.get("token", "")
        if got != AUTH_TOKEN:
            return False, "Missing or incorrect Label Station token."
    return True, None


def _read_json_request() -> tuple[dict[str, Any] | None, str]:
    """Parse JSON even if MA/Lua sends text/plain instead of application/json."""
    raw = request.get_data(as_text=True) or ""
    data = request.get_json(silent=True)
    if data is None and raw.strip():
        try:
            import json
            data = json.loads(raw)
        except Exception:
            data = None
    return data, raw


def _remember_request(kind: str, data: Any, raw: str = "") -> None:
    global _last_request
    with _last_request_lock:
        _last_request = {
            "kind": kind,
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "remote_addr": _client_ip(),
            "content_type": request.content_type,
            "data": data,
            "raw": raw[:2000],
        }


def _cleanup_pending() -> None:
    cutoff = time.time() - PENDING_JOB_TTL_SECONDS
    with _pending_lock:
        stale = [jid for jid, job in _pending.items() if job.get("created", 0) < cutoff]
        for jid in stale:
            _pending.pop(jid, None)


@app.before_request
def before_any_request():
    _cleanup_pending()


def _coerce_int(value: Any, field: str, errors: list[str]) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        errors.append(f"{field} must be a whole number; got {value!r}")
        return None


def _validate_fixtures(fixtures: Any) -> tuple[list[dict[str, Any]], list[str]]:
    """Validate and normalize the JSON fixtures list from MA.

    profile/description may be blank because MA fixture profiles are not always
    well-authored. Blank or ugly values are handled on the review page as
    profile/mode overrides, not rejected at the API boundary.
    """
    errors: list[str] = []
    out: list[dict[str, Any]] = []

    if not isinstance(fixtures, list) or not fixtures:
        return [], ["fixtures must be a non-empty list"]

    required = ("fid", "universe", "address", "fixturetype")

    for idx, fx in enumerate(fixtures):
        label = f"fixtures[{idx}]"
        if not isinstance(fx, dict):
            errors.append(f"{label} must be an object")
            continue

        missing = [k for k in required if k not in fx]
        if missing:
            errors.append(f"{label} missing field(s): {', '.join(missing)}")
            continue

        universe = _coerce_int(fx.get("universe"), f"{label}.universe", errors)
        address = _coerce_int(fx.get("address"), f"{label}.address", errors)
        if universe is None or address is None:
            continue
        if universe < 1:
            errors.append(f"{label}.universe must be >= 1")
            continue
        if not 1 <= address <= 512:
            errors.append(f"{label}.address must be 1-512; got {address}")
            continue

        raw_profile = str(fx.get("profile", "")).strip()
        raw_description = str(fx.get("description", "")).strip()
        fixturetype = str(fx.get("fixturetype", "")).strip()

        clean = {
            "fid": str(fx.get("fid", "")).strip(),
            "universe": universe,
            "address": address,
            "profile": raw_profile,
            "description": raw_description,
            "fixturetype": fixturetype,
            # Preserve exactly what MA sent, so overrides can be keyed against
            # the original fixture/profile/mode group instead of mutated values.
            "raw_profile": raw_profile,
            "raw_description": raw_description,
            "profile_key": make_profile_key(fixturetype, raw_profile, raw_description),
            "csv_link": str(fx.get("csv_link", "") or "").strip(),
        }
        for text_field in ("fid", "fixturetype"):
            if clean[text_field] == "":
                errors.append(f"{label}.{text_field} must not be empty")
        out.append(clean)

    return out, errors


def _field_needs_review(value: Any) -> bool:
    s = str(value or "").strip().lower()
    return s in ("", "unknown", "unknown profile", "unknown mode", "none", "<invalid>")


def _apply_profile_overrides(fixtures: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    """Apply saved profile/mode overrides and return groups needing review."""
    groups_need_review: list[str] = []
    out: list[dict[str, Any]] = []

    for fx in fixtures:
        fx = dict(fx)
        key = fx.get("profile_key") or make_profile_key(
            fx.get("fixturetype"), fx.get("raw_profile"), fx.get("raw_description")
        )
        fx["profile_key"] = key

        override = profile_overrides.get_by_key(key)
        if override:
            if override.get("profile"):
                fx["profile"] = override["profile"]
            if override.get("description"):
                fx["description"] = override["description"]
            fx["profile_override_applied"] = True
        else:
            fx["profile_override_applied"] = False

        if (_field_needs_review(fx.get("profile")) or _field_needs_review(fx.get("description"))) and key not in groups_need_review:
            groups_need_review.append(key)

        out.append(fx)

    return out, groups_need_review

def _resolve_links(fixtures: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[int]]:
    """
    Attach a 'link' to each fixture from the store.
    Returns (fixtures_with_links, list_of_unmapped_universes).
    Fixtures whose universe is unmapped get link = "" for now.
    """
    unmapped: list[int] = []
    out = []
    for fx in fixtures:
        u = fx.get("universe")
        csv_link = str(fx.get("csv_link", "") or "").strip()
        if csv_link.lower() in ("null", "none", "<invalid>"):
            csv_link = ""

        link = csv_link if csv_link else links.get(u)
        if link is None and u not in unmapped:
            unmapped.append(u)
        fx = dict(fx)
        fx["link"] = link if link is not None else ""
        out.append(fx)
    return out, unmapped


def _refresh_pending_job_from_stores(job: dict[str, Any]) -> None:
    """Refresh an existing review job from the latest saved maps.

    This makes the workflow feel live: if a print job opens review because
    U21 is unmapped, you can go to Link Map, add U21, return to Status/Review,
    and the pending job will pick up the saved link without needing MA to resend.
    """
    fixtures = job.get("fixtures", [])
    refreshed, profile_review_groups = _apply_profile_overrides(fixtures)
    refreshed, unmapped = _resolve_links(refreshed)
    job["fixtures"] = refreshed
    job["unmapped"] = unmapped
    job["profile_review_groups"] = profile_review_groups


def _print_fixtures(fixtures: list[dict[str, Any]]) -> dict[str, Any]:
    """Fill and print every fixture. Returns a summary dict. Never raises."""
    with _print_lock:
        printed, errors = 0, []
        try:
            tpl = _load_template()
        except Exception as e:
            return {"printed": 0, "errors": [{"fid": "ALL", "error": str(e)}], "total": len(fixtures)}

        try:
            printer = dymo_print.get_printer_name()
        except Exception as e:
            return {"printed": 0, "errors": [{"fid": "ALL", "error": str(e)}], "total": len(fixtures)}

        total_copies = 0
        for fx in fixtures:
            try:
                filled = fill_template(tpl, fx)
                copies = int(fx.get("copies", 1) or 1)
                if copies < 1:
                    copies = 1
                dymo_print.print_label_xml(filled, printer_name=printer, copies=copies)
                printed += 1
                total_copies += copies
            except Exception as e:
                errors.append({"fid": fx.get("fid"), "error": str(e)})
        return {"printed": printed, "errors": errors, "total": len(fixtures), "total_copies": total_copies}


def _latest_review_url() -> str | None:
    with _pending_lock:
        if not _pending:
            return None
        latest = max(_pending.items(), key=lambda item: item[1].get("created", 0))[0]
    return url_for("review", job_id=latest, _external=False)


# ---------------------------------------------------------------------------
# Control panel + setup
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html",
                           simulate=dymo_print.SIMULATE,
                           mapping_count=len(links.all()),
                           override_count=len(profile_overrides.all()),
                           template_ok=_template_ok(),
                           template_name=templates.current_name(),
                           template_source=templates.source(),
                           csv_status=csv_patch.status(),
                           access_urls=_access_urls())


def _digits_only(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _normalize_link_type(value: Any) -> str:
    s = str(value or "CRMX").strip().lower().replace(" ", "")
    if s in ("crmx2", "crmx^2", "crmx²"):
        return "CRMX²"
    if s in ("dmxhardline", "hardline", "dmx"):
        return "DMX Hardline"
    if s == "other":
        return "Other"
    return "CRMX"


def _compose_link_value(link_key: Any, link_letter: Any, link_type: Any, other_text: Any) -> tuple[str, str | None]:
    """Build the stored/printed Link string from the setup form fields."""
    kind = _normalize_link_type(link_type)
    key = _digits_only(link_key)
    letter = str(link_letter or "").strip().upper()[:1]
    other = str(other_text or "").strip()

    if kind in ("CRMX", "CRMX²"):
        if len(key) != 8:
            return "", f"{kind} links need an 8-digit Link key."
        return f"{key}{letter} {kind}".strip(), None

    if kind == "DMX Hardline":
        # Hardline usually does not need a key, but if you type one we keep it
        # so the label can still carry a line/circuit identifier.
        if key:
            if len(key) != 8:
                return "", "A typed Link key must be exactly 8 digits."
            return f"{key}{letter} DMX Hardline".strip(), None
        return "DMX Hardline", None

    # Other: custom text intentionally replaces the entire Link field.
    # Ignore key/letter completely for this mode.
    if other:
        return other, None
    return "", "Other needs custom link text."


@app.route("/setup")
def setup():
    return render_template("setup.html", mapping=links.all())


@app.route("/setup/save", methods=["POST"])
def setup_save():
    universe = request.form.get("universe", "").strip()
    link, error = _compose_link_value(
        request.form.get("link_key", ""),
        request.form.get("link_letter", ""),
        request.form.get("link_type", "CRMX"),
        request.form.get("link_other", ""),
    )
    if error:
        return jsonify({"ok": False, "error": error}), 400
    if universe:
        links.set(universe, link)
    return redirect(url_for("setup"))


@app.route("/setup/bulk-save", methods=["POST"])
def setup_bulk_save():
    universes = request.form.getlist("universe")
    keys = request.form.getlist("link_key")
    letters = request.form.getlist("link_letter")
    types = request.form.getlist("link_type")
    others = request.form.getlist("link_other")

    saved = 0
    errors = []
    for i, universe in enumerate(universes):
        universe = str(universe or "").strip()
        if not universe:
            continue
        link, error = _compose_link_value(
            keys[i] if i < len(keys) else "",
            letters[i] if i < len(letters) else "",
            types[i] if i < len(types) else "CRMX",
            others[i] if i < len(others) else "",
        )
        if error:
            errors.append(f"U{universe}: {error}")
            continue
        links.set(universe, link)
        saved += 1

    if errors and saved == 0:
        return jsonify({"ok": False, "error": "No rows saved.", "details": errors}), 400
    return redirect(url_for("setup"))


@app.route("/setup/delete", methods=["POST"])
def setup_delete():
    universe = request.form.get("universe", "").strip()
    if universe:
        links.delete(universe)
    # Refresh pending review jobs so the deleted universe immediately appears as unmapped.
    with _pending_lock:
        for job in _pending.values():
            _refresh_pending_job_from_stores(job)
    return redirect(url_for("setup"))


@app.route("/setup/reset", methods=["POST"])
def setup_reset():
    """Clear the entire universe->link map.

    This is intentionally destructive: it resets the Link Map back to zero
    mappings and removes all added universes from data/link_map.json.
    """
    confirm = request.form.get("confirm_reset", "")
    if confirm != "RESET":
        return jsonify({"ok": False, "error": "Reset confirmation missing."}), 400
    links.clear()
    # Refresh pending review jobs so all universe links are cleared immediately.
    with _pending_lock:
        for job in _pending.values():
            _refresh_pending_job_from_stores(job)
    return redirect(url_for("setup"))



# ---------------------------------------------------------------------------
# CSV patch manager + website-driven print flow
# ---------------------------------------------------------------------------
@app.route("/patch")
def patch_manager():
    status = csv_patch.status()
    sample_rows = []
    try:
        sample_rows = csv_patch.load_rows()[:8]
    except Exception:
        sample_rows = []
    return render_template("patch.html",
                           status=status,
                           canonical_fields=CANONICAL_FIELDS,
                           sample_rows=sample_rows)


@app.route("/patch/upload", methods=["POST"])
def patch_upload():
    f = request.files.get("csv_file")
    if not f or not f.filename:
        return jsonify({"ok": False, "error": "Choose a CSV file first."}), 400
    try:
        csv_patch.save_upload(f.read(), f.filename)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    return redirect(url_for("patch_manager"))


@app.route("/patch/mapping", methods=["POST"])
def patch_mapping_save():
    mapping = {field: request.form.get(field, "") for field in CANONICAL_FIELDS}
    csv_patch.save_mapping(mapping)
    return redirect(url_for("patch_manager"))


@app.route("/csv/print", methods=["POST"])
def csv_print():
    """Website form: select labels from the active CSV and use the normal review/print flow."""
    range_text = request.form.get("range", "").strip()
    if not range_text:
        return jsonify({"ok": False, "error": "Enter a fixture range."}), 400
    force_review = request.form.get("force_review") == "1"
    fixtures, csv_errors = csv_patch.select_fixtures(range_text)
    if csv_errors and not fixtures:
        return jsonify({"ok": False, "error": "Could not create print job.", "details": csv_errors}), 400

    # Feed CSV rows into the same pipeline as MA /print.
    fixtures, validation_errors = _validate_fixtures(fixtures)
    if validation_errors:
        return jsonify({"ok": False, "error": "Invalid fixture payload.", "details": validation_errors + csv_errors}), 400

    fixtures, profile_review_groups = _apply_profile_overrides(fixtures)
    fixtures, unmapped = _resolve_links(fixtures)

    with _pending_lock:
        _pending.clear()

    if not force_review and not unmapped and not profile_review_groups and AUTO_PRINT_WHEN_ALL_MAPPED:
        summary = _print_fixtures(fixtures)
        return render_template("done.html", summary=summary)

    job_id = uuid.uuid4().hex[:8]
    with _pending_lock:
        _pending[job_id] = {
            "fixtures": fixtures,
            "unmapped": unmapped,
            "profile_review_groups": profile_review_groups,
            "created": time.time(),
            "source": "csv",
            "range": range_text,
            "csv_errors": csv_errors,
        }

    return redirect(url_for("review", job_id=job_id))

# ---------------------------------------------------------------------------
# Template manager
# ---------------------------------------------------------------------------
@app.route("/templates")
def template_manager():
    status = templates.status()
    return render_template("templates.html",
                           status=status,
                           required_tokens=REQUIRED_TOKENS)


@app.route("/templates/upload", methods=["POST"])
def template_upload():
    f = request.files.get("template")
    if not f or not f.filename:
        return jsonify({"ok": False, "error": "Choose a .dymo template file first."}), 400
    allow_missing = request.form.get("allow_missing") == "1"
    try:
        templates.save_upload(f.read(), f.filename, allow_missing=allow_missing)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    return redirect(url_for("template_manager"))


@app.route("/templates/restore", methods=["POST"])
def template_restore():
    templates.restore_default()
    return redirect(url_for("template_manager"))


@app.route("/templates/download")
def template_download():
    path = templates.current_path()
    if not path:
        abort(404)
    return send_file(path, as_attachment=True, download_name=templates.current_name())


@app.route("/templates/sample-preview.png")
def template_sample_preview():
    sample = {
        "fid": "703",
        "universe": 1,
        "address": 1,
        "profile": "Mode 140",
        "description": "D16 CCT GM C RGB S",
        "fixturetype": "Titan Tube",
        "link": "11111111A CRMX²",
    }
    try:
        tpl = _load_template()
        png = render_to_png_bytes(fill_template(tpl, sample))
        return Response(png, mimetype="image/png")
    except Exception as e:
        return Response(f"Preview unavailable: {e}", status=409, mimetype="text/plain")


# ---------------------------------------------------------------------------
# MA communication test — does NOT require printer or template
# ---------------------------------------------------------------------------
@app.route("/ma-test", methods=["GET", "POST"])
def ma_test():
    if request.method == "GET":
        return jsonify({
            "ok": True,
            "message": "Label Station MA test endpoint is reachable.",
            "remote_addr": _client_ip(),
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        })

    allowed, error = _check_post_access()
    if not allowed:
        return jsonify({"ok": False, "error": error}), 403

    data, raw = _read_json_request()
    _remember_request("ma-test", data if data is not None else None, raw)
    return jsonify({
        "ok": True,
        "message": "MA POST received by Label Station.",
        "remote_addr": _client_ip(),
        "parsed_json": data is not None,
        "echo": data if data is not None else raw[:500],
    })


# ---------------------------------------------------------------------------
# Print flow — MA posts here
# ---------------------------------------------------------------------------
@app.route("/print", methods=["POST"])
def do_print():
    """
    Expected JSON:
      {"fixtures": [
         {"fid": "703", "universe": 1, "address": 463,
          "profile": "37 ch", "description": "...", "fixturetype": "..."} ]}
    """
    allowed, error = _check_post_access()
    if not allowed:
        return jsonify({"ok": False, "error": error}), 403

    data, raw = _read_json_request()
    _remember_request("print", data, raw)
    if not data or "fixtures" not in data:
        return jsonify({"ok": False, "error": "No fixtures in request."}), 400

    fixtures, validation_errors = _validate_fixtures(data["fixtures"])
    if validation_errors:
        return jsonify({"ok": False, "error": "Invalid fixture payload.", "details": validation_errors}), 400

    fixtures, profile_review_groups = _apply_profile_overrides(fixtures)
    fixtures, unmapped = _resolve_links(fixtures)
    force_review = bool(data.get("force_review"))

    # Every valid /print request replaces the previous active review job.
    # This keeps the cart browser from staying on an old batch when you resend
    # a corrected range from MA. If this new request auto-prints, pending jobs
    # are still cleared and old review pages will redirect back to Status.
    with _pending_lock:
        _pending.clear()

    # Dream path: everything mapped, profile/mode OK, and review not forced -> print now.
    if not force_review and not unmapped and not profile_review_groups and AUTO_PRINT_WHEN_ALL_MAPPED:
        summary = _print_fixtures(fixtures)
        return jsonify({"ok": len(summary["errors"]) == 0, "mode": "auto", **summary})

    # Otherwise stash a pending job and surface the review screen.
    # Label Station is intentionally single-active-job for show workflow:
    # if you resend from MA because you made a mistake, the new batch replaces
    # the old review batch instead of leaving the browser stuck on stale labels.
    job_id = uuid.uuid4().hex[:8]
    with _pending_lock:
        _pending[job_id] = {
            "fixtures": fixtures,
            "unmapped": unmapped,
            "profile_review_groups": profile_review_groups,
            "created": time.time(),
        }

    review_url = url_for("review", job_id=job_id, _external=True)
    if OPEN_BROWSER_ON_REVIEW:
        try:
            webbrowser.open(review_url)
        except Exception:
            pass  # headless / no browser; the URL is still returned and status page can redirect

    return jsonify({
        "ok": True,
        "mode": "review",
        "job_id": job_id,
        "unmapped_universes": unmapped,
        "profile_review_groups": profile_review_groups,
        "force_review": force_review,
        "review_url": review_url,
    })


@app.route("/review/<job_id>", methods=["GET"])
def review(job_id):
    job = _pending.get(job_id)
    if not job:
        abort(404)
    # Pick up any Link Map/Profile Override edits made after this job was created.
    _refresh_pending_job_from_stores(job)
    return render_template("review.html", job_id=job_id,
                           fixtures=job["fixtures"],
                           unmapped=job["unmapped"],
                           profile_review_groups=job.get("profile_review_groups", []),
                           template_ok=_template_ok(),
                           template_name=templates.current_name(),
                           template_source=templates.source(),
                           csv_status=csv_patch.status(),
                           access_urls=_access_urls())


@app.route("/review/<job_id>", methods=["POST"])
def review_confirm(job_id):
    job = _pending.get(job_id)
    if not job:
        abort(404)

    fixtures = job["fixtures"]
    save_universes = request.form.getlist("save_universe")
    save_profile_groups = set(request.form.getlist("save_profile_group"))
    ballast_types = {str(v) for v in request.form.getlist("ballast_fixturetype")}

    for i, fx in enumerate(fixtures):
        link_override = request.form.get(f"link_{i}")
        if link_override is not None:
            fx["link"] = link_override.strip()
        if str(fx.get("universe")) in save_universes and fx["link"]:
            links.set(fx["universe"], fx["link"])

        profile_override = request.form.get(f"profile_{i}")
        description_override = request.form.get(f"description_{i}")
        if profile_override is not None:
            fx["profile"] = profile_override.strip()
        if description_override is not None:
            fx["description"] = description_override.strip()

        # Ballast labels are per-print only. If any fixture type is checked,
        # every fixture with that same type prints as two copies, regardless of
        # its mode/profile group.
        fx["copies"] = 2 if str(fx.get("fixturetype", "")) in ballast_types else 1

    # Persist one override per matching profile group. The form may submit the
    # same group multiple times; the last value is fine because synced fields
    # should already match in the browser.
    for fx in fixtures:
        key = str(fx.get("profile_key", ""))
        if key and key in save_profile_groups:
            profile_overrides.set_by_key(key, fx.get("profile", ""), fx.get("description", ""))

    summary = _print_fixtures(fixtures)
    with _pending_lock:
        _pending.pop(job_id, None)
    return render_template("done.html", summary=summary)


@app.route("/review/<job_id>/discard", methods=["POST"])
def review_discard(job_id):
    """Discard one pending review job without printing.

    Useful when the range was wrong or you want to resend a corrected batch from MA.
    """
    with _pending_lock:
        _pending.pop(job_id, None)
    return redirect(url_for("index"))


@app.route("/api/current-review")
def api_current_review():
    """Return the current active review URL, so stale review tabs can redirect.

    If a review page passes ?job_id=<id>, we also report whether that job still
    exists. This lets old review pages redirect away when a new batch auto-prints
    and clears the previous pending job.
    """
    job_id = request.args.get("job_id", "")
    with _pending_lock:
        job_exists = bool(job_id and job_id in _pending)
    return jsonify({
        "latest_review_url": _latest_review_url(),
        "job_id": job_id or None,
        "job_exists": job_exists if job_id else None,
    })


@app.route("/preview/<job_id>/<int:idx>.png", methods=["GET", "POST"])
def preview(job_id, idx):
    job = _pending.get(job_id)
    if not job or idx < 0 or idx >= len(job["fixtures"]):
        abort(404)

    # GET renders the stored pending fixture. POST renders a temporary preview
    # using the user's current review-screen overrides without mutating the job.
    fx = dict(job["fixtures"][idx])
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        for field in ("link", "profile", "description"):
            if field in data:
                fx[field] = str(data.get(field, "")).strip()

    try:
        tpl = _load_template()
        png = render_to_png_bytes(fill_template(tpl, fx))
        return Response(png, mimetype="image/png")
    except Exception as e:
        # Return text with a 409 so the page can still load and the error is visible in dev tools.
        return Response(f"Preview unavailable: {e}", status=409, mimetype="text/plain")


@app.route("/api/status")
def api_status():
    with _last_request_lock:
        last = dict(_last_request) if _last_request else None
    return jsonify({
        "simulate": dymo_print.SIMULATE,
        "printer_ok": dymo_print.service_alive(),
        "template_ok": _template_ok(),
        "template_name": templates.current_name(),
        "template_source": templates.source(),
        "mappings": len(links.all()),
        "profile_overrides": len(profile_overrides.all()),
        "csv": asdict(csv_patch.status()),
        "pending_jobs": len(_pending),
        "latest_review_url": _latest_review_url(),
        "access_urls": _access_urls(),
        "last_request": last,
    })


@app.route("/api/last-request")
def api_last_request():
    with _last_request_lock:
        return jsonify({"last_request": _last_request})


if __name__ == "__main__":
    # host=0.0.0.0 so MA on the network can reach it; port 5000 by default.
    print("BO Label Station starting...")
    print(f"  REAL PRINT MODE = {not dymo_print.SIMULATE}")
    print(f"  SIMULATE = {dymo_print.SIMULATE}")
    print(f"  APP_DIR = {APP_DIR}")
    print(f"  template = {'OK' if _template_ok() else 'MISSING'} ({templates.current_name()})")
    print(f"  link mappings loaded: {len(links.all())}")
    print(f"  profile/mode overrides loaded: {len(profile_overrides.all())}")
    try:
        st = csv_patch.status()
        print(f"  active CSV: {st.filename or 'none'} ({st.rows} rows)")
    except Exception:
        print("  active CSV: unavailable")
    print("  listening on all IPv4 interfaces (0.0.0.0:5000). Try:")
    for url in _access_urls():
        print(f"    {url}")
    if AUTH_TOKEN:
        print("  auth token required for /print and /ma-test")
    if ALLOWED_SOURCE_IPS:
        print(f"  allowed POST source IPs: {', '.join(sorted(ALLOWED_SOURCE_IPS))}")
    app.run(host="0.0.0.0", port=5000, debug=False)
