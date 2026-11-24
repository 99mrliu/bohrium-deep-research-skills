"""Shared helpers for source-veritas-deck.

Everything in this skill revolves around one idea: a SOURCE CORPUS LEDGER.
All text and figures extracted from the upstream paper are hashed (sha256) at
extraction time; every downstream artifact must trace back to ledger entries.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

# ---------------------------------------------------------------------------
# hashing / io
# ---------------------------------------------------------------------------

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: str, default=None):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def dump_json(obj, path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def norm_ws(text: str) -> str:
    """Whitespace-normalized form used for verbatim substring checks."""
    return re.sub(r"\s+", " ", text or "").strip()


# ---------------------------------------------------------------------------
# numeric tokens
# ---------------------------------------------------------------------------

# A numeric token = digit core with optional decimals/thousands separators,
# plus an optional adjacent unit.  The digit core is what must appear verbatim
# in the corpus; the unit is kept for reporting.
NUM_TOKEN_RE = re.compile(
    r"(?<![\w.])(-?\d+(?:,\d{3})*(?:\.\d+)?)"
    r"(\s*(?:%|％|ms|s|min|h|hours?|hrs?|GB|MB|KB|kB|KiB|MiB|Hz|kHz|MHz|GHz|eV|keV|MeV|GeV|"
    r"K|°C|μm|um|nm|mm|cm|m|km|g|kg|mg|mL|L|x|×|pp|pts?))?",
    re.IGNORECASE,
)


def extract_number_tokens(text: str) -> list[dict]:
    """Return [{'raw': '92.4%', 'core': '92.4', 'unit': '%'}, ...]."""
    out = []
    for m in NUM_TOKEN_RE.finditer(text or ""):
        core = m.group(1)
        unit = (m.group(2) or "").strip()
        out.append({"raw": m.group(0).strip(), "core": core, "unit": unit})
    return out


def core_in_text(core: str, text: str) -> bool:
    """True when the digit core appears verbatim (not glued to other digits)."""
    if not core:
        return True
    pat = r"(?<![\d.,])" + re.escape(core) + r"(?![\d.])"
    return re.search(pat, text) is not None


# ---------------------------------------------------------------------------
# dependency bootstrap (honest: missing deps are reported, never faked)
# ---------------------------------------------------------------------------

def ensure_deps(change_log: list) -> dict:
    """Import required packages; pip-install when missing. Returns status map."""
    deps = {
        "pptx": "python-pptx",
        "pymupdf": "PyMuPDF",
        "PIL": "pillow",
    }
    status = {}
    for mod, pipname in deps.items():
        try:
            __import__(mod)
            status[pipname] = "present"
        except ImportError:
            try:
                subprocess.check_call(
                    [sys.executable, "-m", "pip", "install", "--quiet", pipname]
                )
                __import__(mod)
                status[pipname] = "installed"
                change_log.append(
                    {"action": "bootstrap-dep", "package": pipname,
                     "detail": "was missing; installed via pip"}
                )
            except Exception as exc:  # noqa: BLE001
                status[pipname] = f"missing ({exc})"
                change_log.append(
                    {"action": "bootstrap-dep-failed", "package": pipname,
                     "detail": str(exc)}
                )
    return status


def find_tool(names: list[str]) -> str | None:
    """Locate an external binary; check known absolute paths first."""
    candidates = list(names)
    for n in names:
        candidates.append(os.path.join("/opt/homebrew/bin", n))
        candidates.append(os.path.join("/usr/local/bin", n))
    for c in candidates:
        if os.path.isabs(c) and os.path.exists(c) and os.access(c, os.X_OK):
            return c
        hit = shutil.which(c)
        if hit:
            return hit
    return None


# ---------------------------------------------------------------------------
# corpus ledger io
# ---------------------------------------------------------------------------

def read_corpus(corpus_path: str) -> list[dict]:
    entries = []
    if not os.path.exists(corpus_path):
        return entries
    with open(corpus_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def corpus_full_text(entries: list[dict]) -> str:
    return norm_ws(" ".join(e.get("text", "") for e in entries
                            if e.get("kind") == "text"))
