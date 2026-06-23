"""
template_store.py — manages user-uploaded DYMO templates.

Users can upload their own DYMO Connect .dymo/.label/XML template as long as it
contains the required Label Station placeholder tokens. The active user template
is stored under data/templates/active.dymo so it persists across restarts.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any

REQUIRED_TOKENS = [
    "#fid",
    "#u",
    "#add",
    "#profile",
    "#description",
    "#fixturetype",
    "#link",
]


@dataclass
class TemplateStatus:
    ok: bool
    path: str | None
    name: str
    source: str
    missing_tokens: list[str]
    found_tokens: list[str]
    xml_ok: bool
    xml_error: str | None = None


class TemplateStore:
    def __init__(self, default_path: str, template_dir: str):
        self.default_path = default_path
        self.template_dir = template_dir
        self.active_path = os.path.join(template_dir, "active.dymo")
        self.meta_path = os.path.join(template_dir, "active_template.json")

    def _ensure_dir(self) -> None:
        os.makedirs(self.template_dir, exist_ok=True)

    def _read_meta(self) -> dict[str, Any]:
        try:
            with open(self.meta_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _write_meta(self, meta: dict[str, Any]) -> None:
        self._ensure_dir()
        tmp = self.meta_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, sort_keys=True)
        os.replace(tmp, self.meta_path)

    def current_path(self) -> str | None:
        if os.path.exists(self.active_path):
            return self.active_path
        if os.path.exists(self.default_path):
            return self.default_path
        return None

    def current_name(self) -> str:
        if os.path.exists(self.active_path):
            return str(self._read_meta().get("original_filename") or "active.dymo")
        if os.path.exists(self.default_path):
            return os.path.basename(self.default_path)
        return "No template loaded"

    def source(self) -> str:
        if os.path.exists(self.active_path):
            return "uploaded"
        if os.path.exists(self.default_path):
            return "default"
        return "missing"

    def load(self) -> str:
        path = self.current_path()
        if not path:
            raise FileNotFoundError(
                "No active DYMO template found. Upload a template on the Template page "
                "or put LabelTemplate_2026_Python.dymo next to app.py."
            )
        with open(path, "r", encoding="utf-8-sig") as f:
            return f.read()

    def validate_xml(self, text: str) -> tuple[bool, str | None]:
        # Most DYMO Connect .dymo files are XML. We don't require a specific root
        # because legacy formats vary, but we do catch obvious broken uploads.
        stripped = text.lstrip("\ufeff\r\n\t ")
        if not stripped.startswith("<"):
            return False, "File does not look like XML/DYMO text."
        try:
            ET.fromstring(stripped.encode("utf-8"))
            return True, None
        except Exception as e:
            return False, str(e)

    def scan_tokens(self, text: str) -> tuple[list[str], list[str]]:
        found = [t for t in REQUIRED_TOKENS if t in text]
        missing = [t for t in REQUIRED_TOKENS if t not in text]
        return found, missing

    def validate_text(self, text: str) -> TemplateStatus:
        xml_ok, xml_error = self.validate_xml(text)
        found, missing = self.scan_tokens(text)
        return TemplateStatus(
            ok=xml_ok and not missing,
            path=None,
            name="uploaded file",
            source="upload-check",
            missing_tokens=missing,
            found_tokens=found,
            xml_ok=xml_ok,
            xml_error=xml_error,
        )

    def status(self) -> TemplateStatus:
        path = self.current_path()
        if not path:
            return TemplateStatus(False, None, self.current_name(), self.source(), REQUIRED_TOKENS[:], [], False, "No template file found.")
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                text = f.read()
            xml_ok, xml_error = self.validate_xml(text)
            found, missing = self.scan_tokens(text)
            return TemplateStatus(
                ok=xml_ok and not missing,
                path=path,
                name=self.current_name(),
                source=self.source(),
                missing_tokens=missing,
                found_tokens=found,
                xml_ok=xml_ok,
                xml_error=xml_error,
            )
        except Exception as e:
            return TemplateStatus(False, path, self.current_name(), self.source(), REQUIRED_TOKENS[:], [], False, str(e))

    def save_upload(self, file_bytes: bytes, original_filename: str, allow_missing: bool = False) -> TemplateStatus:
        name = os.path.basename(original_filename or "uploaded_template.dymo")
        if not re.search(r"\.(dymo|label|xml)$", name, re.I):
            raise ValueError("Template file must end in .dymo, .label, or .xml")
        try:
            text = file_bytes.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = file_bytes.decode("utf-8", errors="replace")
        status = self.validate_text(text)
        if not status.xml_ok:
            raise ValueError(f"Template is not valid readable DYMO XML: {status.xml_error}")
        if status.missing_tokens and not allow_missing:
            raise ValueError("Template is missing required token(s): " + ", ".join(status.missing_tokens))

        self._ensure_dir()
        tmp = self.active_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, self.active_path)
        self._write_meta({
            "original_filename": name,
            "uploaded_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "missing_tokens_allowed": bool(status.missing_tokens and allow_missing),
            "missing_tokens": status.missing_tokens,
        })
        return self.status()

    def restore_default(self) -> None:
        # Removing active makes current_path fall back to the bundled/default file.
        try:
            if os.path.exists(self.active_path):
                os.remove(self.active_path)
        finally:
            try:
                if os.path.exists(self.meta_path):
                    os.remove(self.meta_path)
            except Exception:
                pass

    def copy_default_to_active(self) -> None:
        if not os.path.exists(self.default_path):
            raise FileNotFoundError("Default template is missing.")
        self._ensure_dir()
        shutil.copyfile(self.default_path, self.active_path)
        self._write_meta({
            "original_filename": os.path.basename(self.default_path),
            "uploaded_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "copied_from_default": True,
        })
