"""
csv_store.py — active CSV patch storage + column mapping for BO/CSV Label Station.

The CSV exporter may change column order and may include extra columns. This
module stores an uploaded active CSV, auto-detects useful columns by header name,
lets the website remap them, and converts selected rows into the same fixture
payload shape used by the DYMO label pipeline.
"""

from __future__ import annotations

import csv
import json
import os
import re
import shutil
from dataclasses import dataclass, asdict
from typing import Any

REQUIRED_CANONICAL_FIELDS = ("fid", "address_label", "fixturetype")
CANONICAL_FIELDS = (
    "fid",              # fixture number / label headline
    "address_label",    # preferred: universe/address string like 2/001
    "universe",         # optional fallback if separate universe col exists
    "address",          # optional fallback if separate address col exists
    "fixturetype",      # fixture type/name line
    "profile",          # label profile line, e.g. Mode 138
    "description",      # label description line
    "link",             # optional direct link column; link map used if empty
)

# Header aliases are normalized before matching.
ALIASES = {
    "fid": [
        "fixture_number", "fixturenumber", "fixture no", "fixture_no", "fixture",
        "fixture id", "fixture_id", "fid", "id", "number", "no", "channel",
    ],
    "address_label": [
        "address_for_labels", "addressforlabels", "address label", "address_label",
        "label address", "label_address", "dmx address for labels", "dmx_address_for_labels",
        "patch", "patched address", "patched_address",
    ],
    "universe": ["universe", "dmx universe", "dmx_universe", "u"],
    "address": ["address", "dmx address", "dmx_address", "addr", "start address", "start_address"],
    "fixturetype": [
        "fixture_type", "fixturetype", "fixture type", "type", "fixture name",
        "fixture_name", "name", "model", "instrument type", "instrument_type",
    ],
    "profile": ["mode", "profile", "dmx mode", "dmx_mode", "mode/profile", "profile mode"],
    "description": ["description", "desc", "mode description", "mode_description", "notes"],
    "link": ["link", "link field", "link_field", "linking key", "linking_key", "label_link"],
}

NULL_STRINGS = {"", "null", "none", "nan", "<invalid>"}


def _norm_header(s: Any) -> str:
    s = str(s or "").strip().lower()
    s = s.replace("#", "number")
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")


def _norm_value(s: Any) -> str:
    s = str(s or "").strip()
    return "" if s.lower() in NULL_STRINGS else s


def _digits_only(s: Any) -> str:
    return "".join(ch for ch in str(s or "") if ch.isdigit())


def _parse_int(s: Any) -> int | None:
    digits = _digits_only(s)
    if not digits:
        return None
    try:
        return int(digits)
    except ValueError:
        return None


def parse_address_parts(label_value: Any, universe_value: Any = None, address_value: Any = None) -> tuple[int | None, int | None]:
    """Return (universe, address) from flexible CSV address values.

    Preferred inputs include values like:
      2/001, 21.361, 2 / 1-33, 1-24, 404-422

    If a separate universe and address column are mapped, those are used as a
    fallback or override when the label address does not include a universe.
    """
    label = str(label_value or "").strip()

    # Strong forms: 21/361 or 21.361
    m = re.search(r"(\d+)\s*[/.]\s*(\d+)", label)
    if m:
        return int(m.group(1)), int(m.group(2))

    # BO sometimes exports ADDRESS as "2 / 1-33".
    m = re.search(r"(\d+)\s*/\s*(\d+)\s*(?:-|$)", label)
    if m:
        return int(m.group(1)), int(m.group(2))

    u = _parse_int(universe_value)
    a = None

    # A separate address column may be "404-422" or "404".
    addr_text = str(address_value if address_value is not None else label or "").strip()
    m = re.search(r"(\d+)\s*(?:-|$)", addr_text)
    if m:
        a = int(m.group(1))

    # If no universe supplied and address has no universe, assume 1. This matches
    # the sample CSV rows where ADDRESS_FOR_LABELS is the preferred source.
    if u is None and a is not None:
        u = 1

    return u, a


@dataclass
class CsvStatus:
    exists: bool
    filename: str | None
    rows: int
    columns: list[str]
    mapping: dict[str, str]
    missing_required: list[str]
    errors: list[str]


class CsvPatchStore:
    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self.active_path = os.path.join(data_dir, "active.csv")
        self.meta_path = os.path.join(data_dir, "metadata.json")
        self.map_path = os.path.join(data_dir, "column_map.json")
        os.makedirs(data_dir, exist_ok=True)

    def exists(self) -> bool:
        return os.path.exists(self.active_path)

    def filename(self) -> str | None:
        try:
            with open(self.meta_path, "r", encoding="utf-8") as f:
                return json.load(f).get("filename")
        except Exception:
            return os.path.basename(self.active_path) if self.exists() else None

    def save_upload(self, file_bytes: bytes, filename: str) -> None:
        os.makedirs(self.data_dir, exist_ok=True)
        with open(self.active_path, "wb") as f:
            f.write(file_bytes)
        with open(self.meta_path, "w", encoding="utf-8") as f:
            json.dump({"filename": filename}, f, indent=2)
        # Merge current mapping with auto-detected columns from the new file.
        columns = self.columns()
        current = self.mapping()
        auto = self.auto_detect_mapping(columns)
        merged: dict[str, str] = {}
        for key in CANONICAL_FIELDS:
            old = current.get(key, "")
            if old in columns:
                merged[key] = old
            else:
                merged[key] = auto.get(key, "")
        self.save_mapping(merged)

    def load_rows(self) -> list[dict[str, str]]:
        if not self.exists():
            return []
        with open(self.active_path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            return [dict(row) for row in reader]

    def columns(self) -> list[str]:
        if not self.exists():
            return []
        with open(self.active_path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f)
            try:
                return [str(c or "").strip() for c in next(reader)]
            except StopIteration:
                return []

    def auto_detect_mapping(self, columns: list[str] | None = None) -> dict[str, str]:
        columns = columns or self.columns()
        norm_to_original = {_norm_header(c): c for c in columns}
        out = {k: "" for k in CANONICAL_FIELDS}
        for field, aliases in ALIASES.items():
            for alias in aliases:
                norm_alias = _norm_header(alias)
                if norm_alias in norm_to_original:
                    out[field] = norm_to_original[norm_alias]
                    break
        # Avoid mapping ADDRESS to both address_label and address if a stronger
        # ADDRESS_FOR_LABELS column exists. Separate address is only a fallback.
        if out.get("address_label") and out.get("address") == out.get("address_label"):
            out["address"] = ""
        return out

    def mapping(self) -> dict[str, str]:
        columns = self.columns()
        auto = self.auto_detect_mapping(columns)
        try:
            with open(self.map_path, "r", encoding="utf-8") as f:
                saved = json.load(f)
        except Exception:
            saved = {}
        out = {}
        for key in CANONICAL_FIELDS:
            val = str(saved.get(key, "") or "")
            out[key] = val if val in columns else auto.get(key, "")
        return out

    def save_mapping(self, mapping: dict[str, Any]) -> None:
        columns = set(self.columns())
        clean: dict[str, str] = {}
        for key in CANONICAL_FIELDS:
            val = str(mapping.get(key, "") or "")
            clean[key] = val if val in columns else ""
        os.makedirs(self.data_dir, exist_ok=True)
        tmp = self.map_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(clean, f, indent=2, sort_keys=True)
        os.replace(tmp, self.map_path)

    def status(self) -> CsvStatus:
        errors: list[str] = []
        rows = []
        try:
            rows = self.load_rows()
        except Exception as e:
            errors.append(str(e))
        columns = self.columns()
        mapping = self.mapping()
        missing = [k for k in REQUIRED_CANONICAL_FIELDS if not mapping.get(k)]
        # Need either address_label, or universe+address.
        if "address_label" in missing and mapping.get("universe") and mapping.get("address"):
            missing.remove("address_label")
        return CsvStatus(
            exists=self.exists(),
            filename=self.filename(),
            rows=len(rows),
            columns=columns,
            mapping=mapping,
            missing_required=missing,
            errors=errors,
        )

    def rows_as_fixtures(self) -> tuple[list[dict[str, Any]], list[str]]:
        mapping = self.mapping()
        rows = self.load_rows()
        errors: list[str] = []
        fixtures: list[dict[str, Any]] = []

        for idx, row in enumerate(rows, start=2):  # spreadsheet-ish line number
            def col(field: str) -> str:
                name = mapping.get(field, "")
                return _norm_value(row.get(name, "")) if name else ""

            fid = col("fid")
            if not fid:
                continue
            universe, address = parse_address_parts(col("address_label"), col("universe"), col("address"))
            if universe is None or address is None:
                errors.append(f"Row {idx} fixture {fid}: could not parse universe/address")
                continue
            if not 1 <= int(address) <= 512:
                errors.append(f"Row {idx} fixture {fid}: address {address} out of 1-512 range")
                continue

            fixturetype = col("fixturetype") or "Fixture"
            profile = col("profile")
            description = col("description")
            link = col("link")

            fx = {
                "fid": fid,
                "universe": int(universe),
                "address": int(address),
                "profile": profile,
                "description": description,
                "fixturetype": fixturetype,
                "raw_profile": profile,
                "raw_description": description,
                "csv_link": link,
                "csv_row": idx,
            }
            fixtures.append(fx)
        return fixtures, errors

    def select_fixtures(self, range_text: str) -> tuple[list[dict[str, Any]], list[str]]:
        from range_parse import parse_range, RangeParseError
        all_fixtures, errors = self.rows_as_fixtures()
        try:
            wanted = set(parse_range(range_text))
        except RangeParseError as e:
            return [], [str(e)]
        selected = [fx for fx in all_fixtures if _parse_int(fx.get("fid")) in wanted]
        if not selected:
            errors.append(f"No fixtures matched range: {range_text}")
        return selected, errors
