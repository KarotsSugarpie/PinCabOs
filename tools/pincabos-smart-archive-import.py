#!/usr/bin/env python3
# PinCabOs-File created by Karots Sugarpie
import argparse
import json
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

try:
    import olefile
except Exception:
    olefile = None

def pincabos_force_standard_table_name(name):
    """
    Force le format:
    Table Name (Manufacturer Year)

    Exemples:
    The Leprechaun King_Original_2019_ -> The Leprechaun King (Original 2019)
    Ramones _Original 2021_           -> Ramones (Original 2021)
    Ramones_Original_2021_            -> Ramones (Original 2021)
    """
    name = str(name or "").strip()

    name = name.replace("\\", " ").replace("/", " ")
    name = re.sub(r'[:"*?<>|]+', " ", name)
    name = re.sub(r"\s+", " ", name).strip()

    # Cas: Table_Manufacturer_Year_
    m = re.match(r"^(?P<table>.+?)_(?P<mfg>[^_()]+)_(?P<year>\d{4})_$", name)
    if m:
        table = re.sub(r"[_\s]+", " ", m.group("table")).strip()
        mfg = re.sub(r"[_\s]+", " ", m.group("mfg")).strip()
        year = m.group("year").strip()
        return f"{table} ({mfg} {year})"

    # Cas: Table _Manufacturer Year_
    m = re.match(r"^(?P<table>.+?)\s+_(?P<mfg>[^_()]+?)\s+(?P<year>\d{4})_$", name)
    if m:
        table = re.sub(r"[_\s]+", " ", m.group("table")).strip()
        mfg = re.sub(r"[_\s]+", " ", m.group("mfg")).strip()
        year = m.group("year").strip()
        return f"{table} ({mfg} {year})"

    # Cas: Table Manufacturer 2021, seulement si pas déjà avec parenthèses
    if "(" not in name and ")" not in name:
        m = re.match(r"^(?P<table>.+?)\s+(?P<mfg>Original|Williams|Stern|Bally|Gottlieb|Data East|Sega|HauntFreaks|MOD)\s+(?P<year>\d{4})$", name, re.I)
        if m:
            table = re.sub(r"[_\s]+", " ", m.group("table")).strip()
            mfg = re.sub(r"[_\s]+", " ", m.group("mfg")).strip()
            year = m.group("year").strip()
            return f"{table} ({mfg} {year})"

    return name or "Imported Table"


BASE = Path("/opt/pincabos")
TABLES_ROOT = Path("/home/pinball/Tables")
IMPORT_LOGS_ROOT = BASE / "imports" / "logs"

ARCHIVE_EXTS = {".zip", ".rar", ".7z", ".pincabos"}

VIDEO_EXTS = {".mp4", ".avi", ".mov", ".mkv", ".webm"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".apng"}
AUDIO_EXTS = {".mp3", ".wav", ".ogg", ".flac"}
FONT_EXTS = {".ttf", ".otf", ".woff", ".woff2"}
DOC_EXTS = {".txt", ".pdf", ".doc", ".docx", ".rtf", ".nfo", ".md"}

MEDIA_EXTS = VIDEO_EXTS | IMAGE_EXTS | AUDIO_EXTS

ROOT_EXTS = {
    ".vpx",
    ".directb2s",
    ".vbs",
    ".scv",
    ".pov",
    ".res",
}

VNI_EXTS = {".pal", ".vni"}
SERUM_EXTS = {".crz", ".serum"}
ALTCOLOR_MISC_EXTS = {".pac"}

PINMAME_CFG_EXTS = {".cfg"}
PINMAME_NVRAM_EXTS = {".nv", ".nvram"}

TEMP_NAMES = {
    "extract",
    "tmp",
    "temp",
    "_raw_files",
    "raw_files",
    "upload",
    "uploads",
    "archive",
    "nested",
}

def log(msg):
    print(msg, flush=True)


def standard_table_folder_name(name):
    return pincabos_force_standard_table_name(name)



def safe_name(value):
    value = str(value or "").strip()
    value = value.replace("\\", " ").replace("/", " ")
    value = re.sub(r'[:"*?<>|]+', " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value or "Imported Table"

def is_temp_name(name):
    n = str(name or "").strip().lower()
    return (
        n in TEMP_NAMES
        or n.startswith("_archive_")
        or n.startswith("archive_")
        or n.startswith("_nested_")
        or n.startswith("nested_")
        or n.startswith("_forced_")
        or n.startswith("forced_")
        or n.startswith("_already_extracted_")
        or n.startswith("already_extracted_")
        or n.startswith("pincabos-")
    )

def run(cmd, timeout=1800):
    log("$ " + " ".join(str(x) for x in cmd))
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)

def list_files(root):
    return [p for p in Path(root).rglob("*") if p.is_file()]

def list_dirs(root):
    return [p for p in Path(root).rglob("*") if p.is_dir()]

def archive_probe(src):
    try:
        r = run(["7z", "l", "-slt", str(src)], timeout=180)
        return (r.stdout or "") + "\n" + (r.stderr or "")
    except Exception as e:
        return str(e)

def archive_is_passworded(src):
    data = archive_probe(src).lower()
    return any(x in data for x in [
        "encrypted = +",
        "headers encrypted = +",
        "wrong password",
        "can not open encrypted archive",
        "encrypted archive",
    ])

def archive_file_list(src):
    data = archive_probe(src)
    out = []
    for line in data.splitlines():
        line = line.strip()
        if line.startswith("Path = "):
            val = line.split("=", 1)[1].strip()
            if val and val != str(src):
                out.append(val)
    return out

def archive_kind(src):
    src = Path(src)
    if src.suffix.lower() not in ARCHIVE_EXTS:
        return ""

    files = [x.lower().replace("\\", "/") for x in archive_file_list(src)]
    names = [Path(x).name.lower() for x in files]

    if any(x.endswith(".vpx") for x in files):
        return "table_archive"

    if "pinupplayer.ini" in names or any(x.endswith(".pup") for x in files):
        return "pup_archive"

    if "altsound.ini" in names or "altsound.csv" in names or any("/altsound/" in x or x.startswith("altsound/") for x in files):
        return "altsound_archive"

    audio_files = [x for x in files if x.endswith((".mp3", ".wav", ".ogg", ".flac"))]
    if audio_files:
        if any("/music/" in x or x.startswith("music/") for x in files):
            return "music_archive"
        if len(audio_files) >= 1:
            return "music_archive"

    if any(x.endswith(".crz") for x in files):
        return "serum_archive"

    if any(x.endswith(".pal") or x.endswith(".vni") for x in files):
        return "vni_archive"

    if src.suffix.lower() == ".zip":
        # Une ROM PinMAME est souvent un ZIP avec des fichiers binaires sans VPX/media/config.
        if not any(x.endswith((
            ".vpx", ".directb2s", ".vbs", ".scv", ".pov", ".res",
            ".pup", ".mp4", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".apng",
            ".ini", ".cfg", ".nv", ".nvram", ".pal", ".vni", ".crz"
        )) for x in files):
            return "rom_zip"

    return "support_archive"

def extract_archive(src, dest):
    src = Path(src)
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)

    if archive_is_passworded(src):
        raise RuntimeError(f"ARCHIVE PASSWORD REFUSÉE: {src}")

    r = run(["7z", "x", "-y", f"-o{dest}", str(src)])
    data = ((r.stdout or "") + "\n" + (r.stderr or "")).lower()

    if "wrong password" in data or ("encrypted" in data and "error" in data):
        raise RuntimeError(f"ARCHIVE PASSWORD REFUSÉE: {src}")

    if r.returncode != 0:
        raise RuntimeError((r.stdout or "") + "\n" + (r.stderr or ""))

    if not any(dest.rglob("*")):
        raise RuntimeError(f"Extraction vide: {src}")

def is_password_protected_error(exc):
    return "ARCHIVE PASSWORD REFUSÉE:" in str(exc)

def copy_file(src, dest_dir, new_name=None):
    src = Path(src)
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    dest = dest_dir / safe_name(new_name or src.name)
    shutil.copy2(src, dest)
    log(f"INSTALLÉ: {src} -> {dest}")
    return dest

def copy_dir_contents(src_dir, dest_dir):
    src_dir = Path(src_dir)
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    copied = []
    for f in sorted(src_dir.rglob("*")):
        if not f.is_file():
            continue
        rel = f.relative_to(src_dir)
        target = dest_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, target)
        copied.append(str(target))
        log(f"INSTALLÉ: {f} -> {target}")

    return copied

def extract_all_inputs(batch_dir, extract_root):
    batch_dir = Path(batch_dir)
    extract_root = Path(extract_root)
    extract_root.mkdir(parents=True, exist_ok=True)

    raw_dir = extract_root / "_raw_files"
    raw_dir.mkdir(parents=True, exist_ok=True)

    for item in sorted(batch_dir.rglob("*")):
        if not item.is_file():
            continue

        suffix = item.suffix.lower()

        if suffix in ARCHIVE_EXTS:
            kind = archive_kind(item)

            if kind == "rom_zip":
                copy_file(item, raw_dir)
                continue

            dest = extract_root / ("archive_" + safe_name(item.stem))
            log("")
            log("==================================================")
            log(f"ARCHIVE: {item}")
            log(f"TYPE: {kind}")
            log("==================================================")
            try:
                extract_archive(item, dest)
            except RuntimeError as exc:
                # Une table chiffrée est bloquante. Les composants annexes
                # (AltSound, PuP, médias, VNI, etc.) sont ignorés proprement.
                if is_password_protected_error(exc) and kind != "table_archive":
                    log(f"WARNING: ARCHIVE OPTIONNEL IGNORÉ — protégé par mot de passe: {item} | type={kind}")
                    continue
                raise
        else:
            copy_file(item, raw_dir)

    changed = True
    loop = 0

    while changed and loop < 6:
        changed = False
        loop += 1

        for item in sorted(extract_root.rglob("*")):
            if not item.is_file():
                continue

            if item.suffix.lower() not in ARCHIVE_EXTS:
                continue

            if item.name.startswith("already_extracted_"):
                continue

            kind = archive_kind(item)

            if kind == "rom_zip":
                continue

            dest = item.parent / ("nested_" + safe_name(item.stem))
            if dest.exists():
                continue

            log("")
            log(f"ARCHIVE INTERNE: {item}")
            log(f"TYPE INTERNE: {kind}")
            try:
                extract_archive(item, dest)
            except RuntimeError as exc:
                if is_password_protected_error(exc) and kind != "table_archive":
                    log(f"WARNING: ARCHIVE INTERNE OPTIONNEL IGNORÉ — protégé par mot de passe: {item} | type={kind}")
                    item.rename(item.with_name("already_extracted_" + item.name))
                    changed = True
                    continue
                raise

            item.rename(item.with_name("already_extracted_" + item.name))
            changed = True

def choose_main_vpx(root):
    vpxs = [p for p in list_files(root) if p.suffix.lower() == ".vpx"]
    if not vpxs:
        return None
    vpxs.sort(key=lambda p: p.stat().st_size if p.exists() else 0, reverse=True)
    return vpxs[0]

def read_text_script(path):
    path = Path(path)
    for enc in ("utf-8-sig", "utf-16", "utf-16-le", "latin-1"):
        try:
            data = path.read_text(encoding=enc, errors="ignore")
            if data.strip():
                return data
        except Exception:
            pass
    return ""


def extract_vbs_from_vpx(vpx_path, dest_dir=None):
    """
    Extrait le script VBS avec la méthode officielle VPX Standalone:
    VPinballX-BGFX -extractvbs table.vpx

    Règles PinCabOS:
    - ne jamais écrire de VBS vide;
    - le .vbs final doit avoir le même nom de base que le .vpx;
    - le .vbs final va dans dest_dir si fourni, sinon à côté du .vpx;
    - compatible import .vpx seul, archive .zip/.rar/.7z, et package .pincabos.
    """
    import shutil
    import subprocess

    vpx_path = Path(vpx_path)
    if not vpx_path.exists() or vpx_path.suffix.lower() != ".vpx":
        return None

    vpxbin = Path("/opt/pincabos/bin/vpx.sh")
    if not vpxbin.exists():
        log(f"WARNING: VPinballX-BGFX absent, extraction VBS sautée: {vpxbin}")
        return None

    dest_dir = Path(dest_dir) if dest_dir else vpx_path.parent
    dest_dir.mkdir(parents=True, exist_ok=True)

    expected_src_vbs = vpx_path.with_suffix(".vbs")
    final_vbs = dest_dir / (vpx_path.stem + ".vbs")

    # Backup si un VBS final non vide existe déjà.
    if final_vbs.exists() and final_vbs.stat().st_size > 0:
        log(f"INFO: VBS déjà présent, extraction sautée: {final_vbs}")
        return final_vbs

    # Supprimer les VBS vides avant extraction pour éviter de garder un faux succès.
    for candidate in {expected_src_vbs, final_vbs}:
        try:
            if candidate.exists() and candidate.stat().st_size == 0:
                candidate.unlink()
                log(f"INFO: VBS vide supprimé avant extraction: {candidate}")
        except Exception:
            pass

    try:
        cmd = [str(vpxbin), "-extractvbs", str(vpx_path)]
        log("$ " + " ".join(cmd))

        proc = subprocess.run(
            cmd,
            cwd=str(vpx_path.parent),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=120,
        )

        if proc.stdout:
            for line in proc.stdout.splitlines()[-80:]:
                log("extractvbs: " + line)

        if proc.returncode != 0:
            log(f"WARNING: extractvbs retour non zéro: rc={proc.returncode}")
            return None

        if not expected_src_vbs.exists():
            log(f"WARNING: extractvbs terminé mais VBS absent: {expected_src_vbs}")
            return None

        size = expected_src_vbs.stat().st_size
        if size < 1000:
            log(f"WARNING: VBS extrait trop petit ({size} bytes), refus: {expected_src_vbs}")
            return None

        if expected_src_vbs.resolve() != final_vbs.resolve():
            shutil.copy2(expected_src_vbs, final_vbs)

        if not final_vbs.exists() or final_vbs.stat().st_size < 1000:
            log(f"WARNING: VBS final invalide: {final_vbs}")
            return None

        log(f"VBS EXTRAIT OFFICIEL: {vpx_path} -> {final_vbs} ({final_vbs.stat().st_size} bytes)")
        return final_vbs

    except subprocess.TimeoutExpired:
        log(f"WARNING: extractvbs timeout pour {vpx_path}")
        return None
    except Exception as e:
        log(f"WARNING: extraction VBS officielle impossible pour {vpx_path}: {e}")
        return None


def detect_rom_from_script_text(script):
    script = str(script or "")

    # Détection robuste sans regex complexe:
    # cherche GameName, RomName, cGameName ou OptRom puis extrait la valeur entre quotes.
    keys = ("cGameName", "GameName", "RomName", "OptRom")

    for raw_line in script.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("'"):
            continue

        low = line.lower()

        for key in keys:
            k = key.lower()
            if k not in low:
                continue
            if "=" not in line:
                continue

            right = line.split("=", 1)[1].strip()

            # Enlever commentaires VBScript après la valeur si possible.
            if "'" in right:
                right = right.split("'", 1)[0].strip()

            if len(right) >= 2 and right[0] in ("'", '"'):
                quote = right[0]
                rest = right[1:]
                if quote in rest:
                    rom = rest.split(quote, 1)[0].strip()
                else:
                    rom = rest.strip()
            else:
                rom = right.split()[0].strip() if right.split() else ""

            rom = rom.strip().strip('"').strip("'").strip()

            if rom:
                return rom[:-4] if rom.lower().endswith(".zip") else rom

    return ""

def detect_rom_name(root, provided_rom="", main_vpx=None):
    provided_rom = str(provided_rom or "").strip()
    if provided_rom:
        return provided_rom[:-4] if provided_rom.lower().endswith(".zip") else provided_rom

    for vbs in sorted([p for p in list_files(root) if p.suffix.lower() == ".vbs"], key=lambda p: p.stat().st_size if p.exists() else 0, reverse=True):
        rom = detect_rom_from_script_text(read_text_script(vbs))
        if rom:
            log(f"ROM détectée depuis VBS: {rom} ({vbs})")
            return rom

    if main_vpx:
        tmp_vbs = extract_vbs_from_vpx(main_vpx, Path(root) / "_raw_files")
        if tmp_vbs:
            rom = detect_rom_from_script_text(read_text_script(tmp_vbs))
            if rom:
                log(f"ROM détectée depuis VPX/VBS extrait: {rom}")
                return rom

    roms = []
    for p in list_files(root):
        if p.suffix.lower() == ".zip" and archive_kind(p) == "rom_zip":
            roms.append(p)
    if roms:
        roms.sort(key=lambda p: p.stat().st_size if p.exists() else 0, reverse=True)
        return roms[0].stem
    return ""

def ensure_table_tree(table_dir):
    table_dir.mkdir(parents=True, exist_ok=True)

    for sub in [
        "altsound",
        "cache",
        "medias",
        "music",
        "pinmame",
        "pinmame/roms",
        "pinmame/altcolor",
        "pinmame/altsound",
        "pinmame/nvram",
        "pinmame/cfg",
        "pinmame/ini",
        "pupvideos",
        "scripts",
        "serum",
        "user",
        "vni",
        "extras",
    ]:
        (table_dir / sub).mkdir(parents=True, exist_ok=True)

def normalize_media_name(src):
    p = Path(src)
    name = p.name.lower()
    suffix = p.suffix.lower()

    if "wheel" in name:
        return "wheel" + suffix

    if "backglass" in name or "background" in name or name.startswith("bg") or "(backglass)" in name:
        return "bg" + suffix

    if "realdmd" in name or "real-dmd" in name or "(realdmd)" in name:
        return "realdmd" + suffix

    if "fulldmd" in name or "dmd" in name or "(dmd)" in name:
        return "dmd" + suffix

    if "flyer" in name:
        return "flyer" + suffix

    if "cab" in name or "cabinet" in name:
        return "cab" + suffix

    if "playfield" in name or "(playfield)" in name:
        if suffix in VIDEO_EXTS:
            return "table" + suffix
        if suffix in IMAGE_EXTS:
            return "table" + suffix

    if suffix in AUDIO_EXTS and ("audio" in name or "music" in name or "theme" in name):
        return "audio" + suffix

    return p.name


def find_literal_pupvideos_dirs(root):
    """
    Règle PinCabOS:
    Si l'archive contient un dossier nommé pupvideos / PupVideos,
    on copie son contenu tel quel dans <table>/pupvideos/.
    On ne renomme pas, on ne classe pas, on ne touche pas à ce qu'il y a dedans.
    """
    root = Path(root)
    found = []

    for d in sorted(root.rglob("*")):
        if not d.is_dir():
            continue

        if d.name.lower() != "pupvideos":
            continue

        # Ne jamais prendre un dossier temporaire créé par l'importeur comme racine logique.
        if any(is_temp_name(part) for part in d.parts):
            # On permet quand même archive_xxx/.../pupvideos, car archive_xxx est notre extract container.
            # Le dossier important est le dossier pupvideos lui-même.
            pass

        found.append(d)

    # Garder seulement les pupvideos les plus hauts.
    final = []
    for d in found:
        if any(parent in found for parent in d.parents):
            continue
        final.append(d)

    return final


def looks_like_pup_dir(d):
    """
    Reconnaît uniquement la vraie racine d'un PupPack.

    Important : ne pas utiliser une recherche récursive ici, sinon le
    dossier parent d'une archive peut être pris pour le PupPack et toute
    la table risque d'être copiée dans pupvideos/.
    """
    d = Path(d)

    if is_temp_name(d.name) or not d.is_dir():
        return False

    direct_files = [p for p in d.iterdir() if p.is_file()]
    direct_dirs = {p.name.lower() for p in d.iterdir() if p.is_dir()}
    names = {p.name.lower() for p in direct_files}
    lname = d.name.lower()

    if "pinupplayer.ini" in names or "screens.pup" in names:
        return True

    if any(p.suffix.lower() == ".pup" for p in direct_files):
        return True

    pup_asset_dirs = {"fonts", "pupalphas", "pupoverlays"}
    if "pup" in lname and direct_dirs.intersection(pup_asset_dirs):
        return True

    return False


def looks_like_music_dir(d):
    d = Path(d)
    if is_temp_name(d.name):
        return False

    lname = d.name.lower()
    files = list_files(d)
    audio_count = sum(1 for x in files if x.suffix.lower() in AUDIO_EXTS)

    if lname == "music":
        return audio_count >= 1

    return False


def looks_like_altsound_dir(d):
    d = Path(d)
    if is_temp_name(d.name):
        return False

    files = list_files(d)
    names = {x.name.lower() for x in files}

    if "altsound.ini" in names or "altsound.csv" in names:
        return True

    audio_count = sum(1 for x in files if x.suffix.lower() in AUDIO_EXTS)
    return audio_count >= 10 and "alt" in d.name.lower()

def looks_like_ultradmd_dir(d):
    d = Path(d)
    if is_temp_name(d.name):
        return False

    lname = d.name.lower()
    files = list_files(d)
    names = {x.name.lower() for x in files}

    if lname.endswith(".ultradmd"):
        return True

    if "ultradmd" in lname or "flexdmd" in lname:
        return True

    if any("ultradmd" in n or "flexdmd" in n for n in names):
        return True

    return False

def find_roots(root, predicate):
    candidates = []

    for d in sorted(list_dirs(root)):
        if predicate(d):
            candidates.append(d)

    final = []
    for d in candidates:
        if any(parent in candidates for parent in d.parents):
            continue
        final.append(d)

    return final

def best_plugin_folder_name(d, fallback):
    d = Path(d)
    n = safe_name(d.name)
    if n and not is_temp_name(n) and n.lower() not in {"pupvideos", "pupvideo", "puppack", "pup-pack", "altsound"}:
        return n
    return safe_name(fallback)

def detect_ultradmd_folder_name(ultra_roots, table_title):
    for d in ultra_roots:
        n = safe_name(d.name)
        if is_temp_name(n):
            continue
        if n.lower().endswith(".ultradmd"):
            return n
        if "ultradmd" in n.lower() or "flexdmd" in n.lower():
            return n
    return safe_name(table_title) + ".UltraDMD"

def should_skip_file(f):
    text = str(f).lower()
    return "/already_extracted_" in text

def classify_and_install(extract_root, table_dir, rom):
    installed = {
        "root": [],
        "altsound": [],
        "cache": [],
        "medias": [],
        "music": [],
        "pinmame_cfg": [],
        "pinmame_ini": [],
        "pinmame_nvram": [],
        "pinmame_roms": [],
        "pinmame_altcolor": [],
        "pinmame_altsound": [],
        "pinmame_alias": [],
        "pupvideos": [],
        "scripts": [],
        "serum": [],
        "ultradmd": [],
        "user": [],
        "vni": [],
        "extras": [],
    }

    table_title = table_dir.name
    excluded_dirs = set()

    # 1) RÈGLE PRIORITAIRE:
    # Si un vrai dossier pupvideos existe dans l'archive,
    # on copie son contenu intact dans <table>/pupvideos/.
    literal_pupvideos_dirs = find_literal_pupvideos_dirs(extract_root)

    for pupvideos_dir in literal_pupvideos_dirs:
        installed["pupvideos"].extend(copy_dir_contents(pupvideos_dir, table_dir / "pupvideos"))
        excluded_dirs.add(pupvideos_dir.resolve())

    # 2) Fallback seulement si aucun dossier pupvideos explicite n'existe.
    # VPX Linux PUP cherche screens.pup, FONTS, PUPAlphas, etc. directement
    # dans <table>/pupvideos/. Le contenu doit donc rester à la racine.
    if not literal_pupvideos_dirs:
        pup_roots = find_roots(extract_root, looks_like_pup_dir)
        for pup in pup_roots:
            copied = copy_dir_contents(pup, table_dir / "pupvideos")
            if not copied:
                raise RuntimeError(f"PupPack détecté mais vide: {pup}")
            installed["pupvideos"].extend(copied)
            excluded_dirs.add(pup.resolve())

    music_roots = find_roots(extract_root, looks_like_music_dir)
    for mus in music_roots:
        if any(root == mus.resolve() or root in mus.resolve().parents for root in excluded_dirs):
            continue
        installed["music"].extend(copy_dir_contents(mus, table_dir / "music"))
        excluded_dirs.add(mus.resolve())

    altsound_roots = find_roots(extract_root, looks_like_altsound_dir)
    for alt in altsound_roots:
        if any(root == alt.resolve() or root in alt.resolve().parents for root in excluded_dirs):
            continue
        name = best_plugin_folder_name(alt, rom or table_title)
        dest = table_dir / "pinmame" / "altsound" / name
        installed["pinmame_altsound"].extend(copy_dir_contents(alt, dest))
        excluded_dirs.add(alt.resolve())

    ultra_roots = find_roots(extract_root, looks_like_ultradmd_dir)
    ultra_name = detect_ultradmd_folder_name(ultra_roots, table_title)

    for ultra in ultra_roots:
        if any(root == ultra.resolve() or root in ultra.resolve().parents for root in excluded_dirs):
            continue
        dest = table_dir / ultra_name
        installed["ultradmd"].extend(copy_dir_contents(ultra, dest))
        excluded_dirs.add(ultra.resolve())

    for f in sorted(list_files(extract_root)):
        if should_skip_file(f):
            continue

        if any(root == f.resolve() or root in f.resolve().parents for root in excluded_dirs):
            continue

        suffix = f.suffix.lower()
        kind = archive_kind(f) if suffix in ARCHIVE_EXTS else ""
        lname = f.name.lower()
        full = str(f).lower()

        if suffix == ".vpx":
            installed["root"].append(str(copy_file(f, table_dir, f.name)))
            continue

        if suffix in {".directb2s", ".vbs", ".scv", ".pov", ".res"}:
            installed["root"].append(str(copy_file(f, table_dir, f.name)))
            continue

        if suffix == ".ini":
            if lname == "pinupplayer.ini" or "pup" in full or "pinup" in full:
                dest = copy_file(f, table_dir / "pupvideos" / safe_name(table_title), f.name)
                installed["pupvideos"].append(str(dest))
                continue

            if "altsound" in full:
                dest = copy_file(f, table_dir / "pinmame" / "altsound" / safe_name(rom or table_title), f.name)
                installed["pinmame_altsound"].append(str(dest))
                continue

            # Si le .ini porte le nom d'un VPX, il reste à la racine comme override table.
            vpx_stems = {x.stem.lower() for x in list_files(extract_root) if x.suffix.lower() == ".vpx"}
            if f.stem.lower() in vpx_stems:
                installed["root"].append(str(copy_file(f, table_dir, f.name)))
                continue

            # Fallback PinMAME si le nom ressemble à la ROM.
            if rom and f.stem.lower().startswith(rom.lower()):
                installed["pinmame_ini"].append(str(copy_file(f, table_dir / "pinmame" / "ini", f.name)))
                continue

            installed["root"].append(str(copy_file(f, table_dir, f.name)))
            continue

        if suffix == ".cfg":
            installed["pinmame_cfg"].append(str(copy_file(f, table_dir / "pinmame" / "cfg", f.name)))
            continue

        if suffix in {".nv", ".nvram"}:
            installed["pinmame_nvram"].append(str(copy_file(f, table_dir / "pinmame" / "nvram", f.name)))
            continue

        if lname == "alias.txt":
            installed["pinmame_alias"].append(str(copy_file(f, table_dir / "pinmame", f.name)))
            continue

        if suffix == ".zip" and kind == "rom_zip":
            installed["pinmame_roms"].append(str(copy_file(f, table_dir / "pinmame" / "roms", f.name)))
            continue

        if suffix in VNI_EXTS:
            folder = safe_name(rom or f.stem or table_title)
            installed["pinmame_altcolor"].append(str(copy_file(f, table_dir / "pinmame" / "altcolor" / folder, f.name)))
            continue

        if suffix in SERUM_EXTS:
            folder = safe_name(rom or f.stem or table_title)
            installed["pinmame_altcolor"].append(str(copy_file(f, table_dir / "pinmame" / "altcolor" / folder, f.name)))
            continue

        if suffix in ALTCOLOR_MISC_EXTS:
            installed["pinmame_altcolor"].append(str(copy_file(f, table_dir / "pinmame" / "altcolor" / safe_name(rom or f.stem or table_title), f.name)))
            continue

        if suffix in AUDIO_EXTS:
            if "music" in full:
                installed["music"].append(str(copy_file(f, table_dir / "music", f.name)))
            elif "altsound" in full:
                installed["pinmame_altsound"].append(str(copy_file(f, table_dir / "pinmame" / "altsound" / safe_name(rom or table_title), f.name)))
            else:
                installed["medias"].append(str(copy_file(f, table_dir / "medias", normalize_media_name(f))))
            continue

        if suffix in IMAGE_EXTS or suffix in VIDEO_EXTS:
            if "pup" in full or "pinup" in full:
                installed["pupvideos"].append(str(copy_file(f, table_dir / "pupvideos" / safe_name(table_title), f.name)))
            elif "ultradmd" in full or "flexdmd" in full:
                installed["ultradmd"].append(str(copy_file(f, table_dir / ultra_name, f.name)))
            else:
                installed["medias"].append(str(copy_file(f, table_dir / "medias", normalize_media_name(f))))
            continue

        if suffix in FONT_EXTS or suffix in DOC_EXTS:
            installed["extras"].append(str(copy_file(f, table_dir / "extras", f.name)))
            continue

        if suffix in ARCHIVE_EXTS:
            if kind == "rom_zip":
                installed["pinmame_roms"].append(str(copy_file(f, table_dir / "pinmame" / "roms", f.name)))
            elif kind == "music_archive":
                # Normalement déjà extrait par extract_all_inputs.
                # Si on retombe ici, on garde une copie dans music/ au lieu de extras.
                installed["music"].append(str(copy_file(f, table_dir / "music", f.name)))
            elif kind == "altsound_archive":
                installed["pinmame_altsound"].append(str(copy_file(f, table_dir / "pinmame" / "altsound" / safe_name(rom or table_title), f.name)))
            else:
                installed["extras"].append(str(copy_file(f, table_dir / "extras", f.name)))
            continue

        installed["extras"].append(str(copy_file(f, table_dir / "extras", f.name)))

    return installed

def write_info_and_manifest(table_dir, title, manufacturer, year, rom, vpsid, ipdbid, installed):
    info = {
        "Info": {
            "Title": title,
            "Manufacturer": manufacturer,
            "Year": str(year or ""),
            "Rom": rom,
            "VPSId": vpsid,
            "IPDBId": ipdbid,
        }
    }

    info_path = table_dir / f"{safe_name(title)}.info"
    info_path.write_text(json.dumps(info, indent=2, ensure_ascii=False), encoding="utf-8")

    manifest = {
        "format": "PinCabOs portable VPX table",
        "format_version": 6,
        "model": "single-folder-portable-table",
        "title": title,
        "manufacturer": manufacturer,
        "year": str(year or ""),
        "rom": rom,
        "vpsid": vpsid,
        "ipdbid": ipdbid,
        "table_dir": str(table_dir),
        "layout": {
            "root": [
                "*.vpx",
                "*.directb2s",
                "*.info",
                "*.ini",
                "*.vbs",
                "*.scv",
                "*.pov",
                "*.res"
            ],
            "altsound": "altsound/<name>/",
            "cache": "cache/",
            "medias": "medias/",
            "music": "music/",
            "pinmame": {
                "roms": "pinmame/roms/",
                "nvram": "pinmame/nvram/",
                "cfg": "pinmame/cfg/",
                "ini": "pinmame/ini/",
                "alias": "pinmame/alias.txt"
            },
            "pupvideos": "pupvideos/",
            "scripts": "scripts/",
            "serum": "serum/<name>/",
            "ultradmd": "<Table Name>.UltraDMD/",
            "user": "user/",
            "vni": "vni/<name>/",
            "extras": "extras/"
        },
        "legacy_global_paths_used": False,
        "installed": installed,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    manifest_path = table_dir / "pincabos-table-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    log(f"META: {info_path}")
    log(f"META: {manifest_path}")


def write_import_tree_log(table_dir, title, rom, installed):
    IMPORT_LOGS_ROOT.mkdir(parents=True, exist_ok=True)

    stamp = time.strftime("%Y%m%d-%H%M%S")
    log_name = safe_name(title).replace(" ", "_")
    log_path = IMPORT_LOGS_ROOT / f"import-{stamp}-{log_name}.txt"

    try:
        tree = subprocess.run(
            ["find", str(table_dir), "-maxdepth", "8", "-print"],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        tree_output = tree.stdout.strip()
        tree_error = tree.stderr.strip()
    except Exception as e:
        tree_output = ""
        tree_error = str(e)

    lines = []
    lines.append("======================================================================")
    lines.append(" PinCabOS - Import table log")
    lines.append("======================================================================")
    lines.append(f"Date       : {time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"Title      : {title}")
    lines.append(f"ROM        : {rom or '(aucune)'}")
    lines.append(f"Table dir  : {table_dir}")
    lines.append("")
    lines.append("======================================================================")
    lines.append(" Résumé install")
    lines.append("======================================================================")
    for k, v in installed.items():
        lines.append(f"{k}: {len(v)}")
    lines.append("")
    lines.append("======================================================================")
    lines.append(" Fichiers installés par catégorie")
    lines.append("======================================================================")
    for k, v in installed.items():
        lines.append("")
        lines.append(f"--- {k} ({len(v)}) ---")
        for item in v:
            lines.append(str(item))
    lines.append("")
    lines.append("======================================================================")
    lines.append(" Résultat find")
    lines.append("======================================================================")
    lines.append(tree_output)
    if tree_error:
        lines.append("")
        lines.append("======================================================================")
        lines.append(" Erreurs find")
        lines.append("======================================================================")
        lines.append(tree_error)
    lines.append("")
    lines.append("======================================================================")
    lines.append(" FIN")
    lines.append("======================================================================")

    log_path.write_text("\\n".join(lines) + "\\n", encoding="utf-8")

    try:
        subprocess.run(["chown", "pinball:pinball", str(log_path)], timeout=10, check=False)
        subprocess.run(["chmod", "664", str(log_path)], timeout=10, check=False)
    except Exception:
        pass

    log(f"IMPORT LOG: {log_path}")
    return log_path



def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("batch_dir")
    ap.add_argument("--title", default="")
    ap.add_argument("--manufacturer", default="")
    ap.add_argument("--year", default="")
    ap.add_argument("--vpsid", default="")
    ap.add_argument("--rom", default="")
    ap.add_argument("--ipdbid", default="")
    args = ap.parse_args()

    batch_dir = Path(args.batch_dir)
    if not batch_dir.exists():
        raise SystemExit(f"Batch introuvable: {batch_dir}")

    title = standard_table_folder_name(safe_name(args.title or batch_dir.name))
    manufacturer = args.manufacturer.strip()
    year = str(args.year or "").strip()
    vpsid = args.vpsid.strip()
    ipdbid = args.ipdbid.strip()

    TABLES_ROOT.mkdir(parents=True, exist_ok=True)

    log("==================================================")
    log(" PinCabOs Import - Portable VPX table complete")
    log("==================================================")
    log(f"Batch       : {batch_dir}")
    log(f"Tables root : {TABLES_ROOT}")
    log(f"Title       : {title}")

    with tempfile.TemporaryDirectory(prefix="pincabos-portable-table-import-") as td:
        extract_root = Path(td) / "extract"
        extract_all_inputs(batch_dir, extract_root)

        main_vpx = choose_main_vpx(extract_root)
        if not main_vpx:
            raise SystemExit("ERREUR: aucun fichier .vpx trouvé après extraction. Import refusé.")

        rom = detect_rom_name(extract_root, args.rom, main_vpx=main_vpx)

        table_dir = TABLES_ROOT / title
        ensure_table_tree(table_dir)

        # PinCabOS portable: toujours créer le .vbs final à côté du .vpx.
        # Utilise VPinballX-BGFX -extractvbs et refuse les VBS vides.
        final_vbs = extract_vbs_from_vpx(main_vpx, table_dir)
        if final_vbs:
            log(f"VBS final extrait      : {final_vbs}")
        else:
            log("WARNING: VBS final non extrait. La table peut quand même fonctionner via script embarqué, mais l'import portable sera moins complet.")

        log("")
        log("==================================================")
        log(" Installation portable VPX")
        log("==================================================")
        log(f"VPX principal détecté : {main_vpx}")
        log(f"ROM détectée          : {rom or '(aucune)'}")
        log(f"Table dir             : {table_dir}")

        installed = classify_and_install(extract_root, table_dir, rom)

    write_info_and_manifest(table_dir, title, manufacturer, year, rom, vpsid, ipdbid, installed)

    import_log_path = write_import_tree_log(table_dir, title, rom, installed)

    try:
        subprocess.run(["chown", "-R", "pinball:pinball", str(table_dir)], timeout=60, check=False)
        subprocess.run(["chmod", "-R", "u+rwX,g+rwX,o+rX", str(table_dir)], timeout=60, check=False)
    except Exception:
        pass

    log("")
    log("==================================================")
    log(" Résumé")
    log("==================================================")
    for k, v in installed.items():
        log(f"{k}: {len(v)}")

    log("")
    log("=== Résultat table ===")
    subprocess.run(["find", str(table_dir), "-maxdepth", "5", "-print"], check=False)

    log("")
    log(f"LOG TXT: {import_log_path}")
    log("IMPORT OK - modèle portable VPX complet")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
