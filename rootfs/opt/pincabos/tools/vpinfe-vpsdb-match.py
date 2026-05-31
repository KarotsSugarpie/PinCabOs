#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from difflib import SequenceMatcher
from pathlib import Path

CONFIG_DIR = Path("/home/pinball/.config/vpinfe")
VPSDB_PATH = CONFIG_DIR / "vpsdb.json"
VPSDB_LAST_PATH = CONFIG_DIR / "vpsdb-last.txt"

VPS_URL_LAST_UPDATE = "https://raw.githubusercontent.com/VirtualPinballSpreadsheet/vps-db/refs/heads/main/lastUpdated.json"
VPS_URL_DB = "https://github.com/VirtualPinballSpreadsheet/vps-db/raw/refs/heads/main/db/vpsdb.json"


def http_get_text(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "PinCabOs-VPSdb-Cache/1.0",
            "Accept": "application/json,text/plain,*/*",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def http_get_bytes(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "PinCabOs-VPSdb-Cache/1.0",
            "Accept": "application/json,*/*",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def fetch_last_update() -> str:
    try:
        data = http_get_text(VPS_URL_LAST_UPDATE).strip()
        # lastUpdated.json peut être un JSON string ou un objet.
        try:
            parsed = json.loads(data)
            if isinstance(parsed, str):
                return parsed.strip()
            if isinstance(parsed, dict):
                for k in ["last", "lastUpdated", "updated", "version", "date"]:
                    if parsed.get(k):
                        return str(parsed[k]).strip()
        except Exception:
            pass
        return data.strip()
    except Exception:
        return ""


def download_db() -> bool:
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        data = http_get_bytes(VPS_URL_DB)
        if not data.strip():
            return False

        # Valider JSON avant écriture finale.
        parsed = json.loads(data.decode("utf-8", errors="replace"))
        if not isinstance(parsed, (list, dict)):
            return False

        tmp = VPSDB_PATH.with_suffix(".json.tmp")
        tmp.write_bytes(data)
        tmp.replace(VPSDB_PATH)
        return True
    except Exception:
        return False


def ensure_current() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    remote_version = fetch_last_update()
    local_version = VPSDB_LAST_PATH.read_text(errors="replace").strip() if VPSDB_LAST_PATH.exists() else ""

    if not VPSDB_PATH.exists():
        if download_db() and remote_version:
            VPSDB_LAST_PATH.write_text(remote_version, encoding="utf-8")
        return

    if remote_version and remote_version != local_version:
        if download_db():
            VPSDB_LAST_PATH.write_text(remote_version, encoding="utf-8")


def load_local() -> list[dict]:
    if not VPSDB_PATH.exists():
        return []

    try:
        data = json.loads(VPSDB_PATH.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return []

    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]

    if isinstance(data, dict):
        for key in ["tables", "items", "data", "rows"]:
            val = data.get(key)
            if isinstance(val, list):
                return [x for x in val if isinstance(x, dict)]

    return []


def norm(value: object) -> str:
    s = str(value or "").lower()
    s = re.sub(r"[_\\/\-]+", " ", s)
    s = re.sub(r"\([^)]*\)", " ", s)
    s = re.sub(r"[^a-z0-9à-ÿ ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def field(table: dict, names: list[str]) -> str:
    for name in names:
        if name in table and table.get(name) not in [None, ""]:
            return str(table.get(name))
    return ""


def table_title(table: dict) -> str:
    return field(table, ["name", "title", "tableName", "table_name", "game", "Game"])


def table_manufacturer(table: dict) -> str:
    return field(table, ["manufacturer", "Manufacturer", "mfg", "company"])


def table_year(table: dict) -> str:
    return field(table, ["year", "Year"])


def table_id(table: dict) -> str:
    return field(table, ["id", "ID", "vpsId", "vpsid", "VPSId"])


def extract_roms(table: dict) -> list[str]:
    out: list[str] = []

    direct_keys = [
        "rom", "Rom", "ROM",
        "romName", "RomName", "rom_name",
        "romFile", "RomFile", "rom_file",
        "pinmame", "PinMAME",
    ]

    for k in direct_keys:
        v = table.get(k)
        if isinstance(v, str) and v.strip():
            out.append(v.strip())

    for k in ["roms", "Roms", "romFiles", "pinmameRoms"]:
        v = table.get(k)
        if isinstance(v, list):
            for item in v:
                if isinstance(item, str):
                    out.append(item)
                elif isinstance(item, dict):
                    for kk in direct_keys + ["name", "file"]:
                        if item.get(kk):
                            out.append(str(item.get(kk)))
        elif isinstance(v, dict):
            for item in v.values():
                if isinstance(item, str):
                    out.append(item)
                elif isinstance(item, dict):
                    for kk in direct_keys + ["name", "file"]:
                        if item.get(kk):
                            out.append(str(item.get(kk)))

    cleaned = []
    for r in out:
        r = Path(str(r).strip()).name
        if r.lower().endswith(".zip"):
            r = r[:-4]
        if r and r not in cleaned:
            cleaned.append(r)

    return cleaned


def score_match(query: str, rom: str, table: dict) -> float:
    q = norm(query)
    r = norm(rom)

    title = table_title(table)
    manu = table_manufacturer(table)
    year = table_year(table)
    tid = table_id(table)

    title_n = norm(title)
    manu_n = norm(manu)
    year_n = norm(year)
    id_n = norm(tid)

    haystack = " ".join([title_n, manu_n, year_n, id_n])

    score = 0.0

    if q:
        if q == title_n:
            score += 1.0
        elif q in title_n or title_n in q:
            score += 0.75
        else:
            score += SequenceMatcher(None, q, title_n).ratio() * 0.65

        # Bonus si la recherche contient manufacturier/année.
        for token in q.split():
            if len(token) >= 3 and token in haystack:
                score += 0.03

    roms = extract_roms(table)
    if r and roms:
        rom_scores = []
        for rr in roms:
            rrn = norm(rr)
            if not rrn:
                continue
            if r == rrn:
                rom_scores.append(1.0)
            elif r in rrn or rrn in r:
                rom_scores.append(0.75)
            else:
                rom_scores.append(SequenceMatcher(None, r, rrn).ratio() * 0.7)

        if rom_scores:
            score += max(rom_scores) * 0.55

    # Bonus si query ressemble au VPSId.
    if q and id_n and q == id_n:
        score += 1.0

    return round(score, 4)


def make_match(table: dict, score: float) -> dict:
    roms = extract_roms(table)

    return {
        "id": table_id(table),
        "title": table_title(table),
        "manufacturer": table_manufacturer(table),
        "year": table_year(table),
        "rom": roms[0] if roms else "",
        "roms": roms,
        "score": score,
    }


def search(query: str, rom: str, limit: int = 30) -> list[dict]:
    ensure_current()
    data = load_local()

    matches = []
    for table in data:
        score = score_match(query, rom, table)
        if score > 0.22:
            m = make_match(table, score)
            if m["title"]:
                matches.append(m)

    matches.sort(key=lambda x: float(x.get("score", 0)), reverse=True)
    return matches[:limit]


def main() -> int:
    query = sys.argv[1] if len(sys.argv) > 1 else ""
    rom = sys.argv[2] if len(sys.argv) > 2 else ""

    matches = search(query, rom)

    print(json.dumps({
        "ok": True,
        "cache": str(VPSDB_PATH),
        "last": VPSDB_LAST_PATH.read_text(errors="replace").strip() if VPSDB_LAST_PATH.exists() else "",
        "count": len(load_local()),
        "matches": matches,
    }, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
