#!/usr/bin/env python3
from pathlib import Path
from datetime import datetime
import argparse
import json
import shutil
import os
import sys

TABLES_ROOT = Path("/home/pinball/Tables")

GLOBAL_PINMAME = Path("/home/pinball/.vpinball/pinmame")
GLOBAL_PUPVIDEOS = Path("/home/pinball/.vpinball/pupvideos")
GLOBAL_ULTRADMD = Path("/home/pinball/.vpinball/ultradmd")
GLOBAL_FLEXDMD = Path("/opt/pincabos/flexdmd")

REPORT = {
    "created_at": datetime.now().isoformat(timespec="seconds"),
    "standard": "VPinFE/VPX per-table portable layout",
    "tables": [],
}


def log(msg):
    print(msg, flush=True)


def read_json(path):
    try:
        return json.loads(path.read_text(errors="replace"))
    except Exception:
        return None


def normalize_rom(value):
    value = str(value or "").strip()
    if value.lower().endswith(".zip"):
        value = value[:-4]
    return value


def table_has_vpx(table_dir):
    return any(table_dir.glob("*.vpx"))


def detect_rom_from_info(table_dir):
    for info_file in sorted(table_dir.glob("*.info")):
        data = read_json(info_file)
        if not isinstance(data, dict):
            continue

        candidates = [
            data.get("Info", {}).get("Rom"),
            data.get("Info", {}).get("ROM"),
            data.get("Info", {}).get("rom"),
            data.get("Info", {}).get("Bios"),
            data.get("Info", {}).get("BIOS"),
            data.get("VPXFile", {}).get("rom"),
            data.get("VPXFile", {}).get("Rom"),
            data.get("rom"),
            data.get("Rom"),
            data.get("ROM"),
            data.get("bios"),
            data.get("Bios"),
        ]

        for c in candidates:
            rom = normalize_rom(c)
            if rom:
                return rom

    return ""


def ensure_layout(table_dir):
    dirs = [
        "medias",
        "pinmame/roms",
        "pinmame/cfg",
        "pinmame/ini",
        "pinmame/nvram",
        "altsound",
        "pupvideos",
        "serum",
        "vni",
        "music",
        "scripts",
        "cache",
        "user",
    ]

    for d in dirs:
        (table_dir / d).mkdir(parents=True, exist_ok=True)


def copy_file(src, dst, apply=False, move=False):
    dst.parent.mkdir(parents=True, exist_ok=True)

    if dst.exists():
        return "exists"

    if apply:
        shutil.copy2(src, dst)
        if move:
            try:
                src.unlink()
            except Exception:
                pass
        return "moved" if move else "copied"

    return "would-move" if move else "would-copy"


def copy_dir(src, dst, apply=False, move=False):
    dst.parent.mkdir(parents=True, exist_ok=True)

    if dst.exists():
        return "exists"

    if apply:
        shutil.copytree(src, dst)
        if move:
            try:
                shutil.rmtree(src)
            except Exception:
                pass
        return "moved" if move else "copied"

    return "would-move" if move else "would-copy"


def add_action(actions, typ, src, dst, action):
    actions.append({
        "type": typ,
        "src": str(src),
        "dst": str(dst),
        "action": action,
    })


def migrate_pinmame(table_dir, rom, apply=False, move=False):
    actions = []

    if not rom:
        return actions

    mappings = [
        (GLOBAL_PINMAME / "roms" / f"{rom}.zip", table_dir / "pinmame" / "roms" / f"{rom}.zip", "rom"),
        (GLOBAL_PINMAME / "cfg" / f"{rom}.cfg", table_dir / "pinmame" / "cfg" / f"{rom}.cfg", "cfg"),
        (GLOBAL_PINMAME / "ini" / f"{rom}.ini", table_dir / "pinmame" / "ini" / f"{rom}.ini", "ini"),
        (GLOBAL_PINMAME / "nvram" / f"{rom}.nv", table_dir / "pinmame" / "nvram" / f"{rom}.nv", "nvram"),
    ]

    for src, dst, typ in mappings:
        if src.exists():
            add_action(actions, typ, src, dst, copy_file(src, dst, apply, move))

    return actions


def migrate_altsound(table_dir, rom, apply=False, move=False):
    actions = []

    if not rom:
        return actions

    srcs = [
        GLOBAL_PINMAME / "altsound" / rom,
        Path("/opt/pincabos/altsound") / rom,
    ]

    for src in srcs:
        if src.exists() and src.is_dir():
            dst = table_dir / "altsound" / rom
            add_action(actions, "altsound", src, dst, copy_dir(src, dst, apply, move))

    return actions


def migrate_pupvideos(table_dir, rom, apply=False, move=False):
    actions = []

    if not rom:
        return actions

    srcs = [
        GLOBAL_PUPVIDEOS / rom,
        GLOBAL_PINMAME / "pupvideos" / rom,
    ]

    for src in srcs:
        if src.exists() and src.is_dir():
            dst = table_dir / "pupvideos" / rom
            add_action(actions, "pupvideos", src, dst, copy_dir(src, dst, apply, move))

    return actions


def migrate_altcolor(table_dir, rom, apply=False, move=False):
    actions = []

    if not rom:
        return actions

    srcs = [
        GLOBAL_PINMAME / "altcolor" / rom,
        Path("/opt/pincabos/altcolor") / rom,
    ]

    for src in srcs:
        if not src.exists() or not src.is_dir():
            continue

        files = [x for x in src.rglob("*") if x.is_file()]
        suffixes = {x.suffix.lower() for x in files}

        if ".crz" in suffixes:
            dst = table_dir / "serum" / rom
            add_action(actions, "serum", src, dst, copy_dir(src, dst, apply, move))

        elif ".pal" in suffixes or ".vni" in suffixes:
            dst = table_dir / "vni" / rom
            add_action(actions, "vni-pal", src, dst, copy_dir(src, dst, apply, move))

        elif ".pac" in suffixes or ".serum" in suffixes:
            dst = table_dir / "vni" / rom
            add_action(actions, "altcolor-other", src, dst, copy_dir(src, dst, apply, move))

        else:
            dst = table_dir / "vni" / rom
            add_action(actions, "altcolor-unknown", src, dst, copy_dir(src, dst, apply, move))

    return actions


def migrate_ultradmd(table_dir, apply=False, move=False):
    actions = []
    names = [
        table_dir.name,
        table_dir.name.replace(" ", "_"),
        table_dir.name.replace(" ", ""),
    ]

    for root in [GLOBAL_ULTRADMD, GLOBAL_FLEXDMD]:
        for name in names:
            src = root / name
            if src.exists() and src.is_dir():
                dst = table_dir / f"{table_dir.name}.UltraDMD"
                add_action(actions, "ultradmd-flexdmd", src, dst, copy_dir(src, dst, apply, move))

    return actions


def ensure_info_file(table_dir, rom, apply=False):
    actions = []

    info_files = sorted(table_dir.glob("*.info"))
    if info_files:
        return actions

    vpx_files = sorted(table_dir.glob("*.vpx"))
    title = table_dir.name
    info_path = table_dir / f"{table_dir.name}.info"

    data = {
        "Info": {
            "Title": title,
            "Manufacturer": "",
            "Year": "",
            "Rom": rom,
            "VPSId": "",
            "IPDBId": "",
        },
        "User": {
            "Rating": 0,
            "Favorite": 0,
            "Tags": []
        }
    }

    if apply:
        info_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    add_action(actions, "info", "generated", info_path, "created" if apply else "would-create")
    return actions


def normalize_table(table_dir, apply=False, move=False):
    rep = {
        "table": table_dir.name,
        "path": str(table_dir),
        "has_vpx": table_has_vpx(table_dir),
        "rom": "",
        "actions": [],
    }

    if not rep["has_vpx"]:
        rep["skipped"] = "no-vpx"
        return rep

    rom = detect_rom_from_info(table_dir)
    rep["rom"] = rom

    ensure_layout(table_dir)

    actions = []
    actions.extend(ensure_info_file(table_dir, rom, apply))
    actions.extend(migrate_pinmame(table_dir, rom, apply, move))
    actions.extend(migrate_altsound(table_dir, rom, apply, move))
    actions.extend(migrate_altcolor(table_dir, rom, apply, move))
    actions.extend(migrate_pupvideos(table_dir, rom, apply, move))
    actions.extend(migrate_ultradmd(table_dir, apply, move))

    rep["actions"] = actions
    return rep


def fix_symlink(apply=False):
    target = TABLES_ROOT
    link = Path("/home/pinball/tables")

    if not apply:
        log(f"SYMLINK: {link} -> {target}")
        return

    if link.exists() and not link.is_symlink():
        backup = link.with_name(f"tables.backup-before-pincabos-link-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
        link.rename(backup)
        log(f"BACKUP old ~/tables: {backup}")

    link.unlink(missing_ok=True)
    link.symlink_to(target)
    try:
        os.chown(link, 1000, 1000, follow_symlinks=False)
    except Exception:
        pass

    log(f"SYMLINK OK: {link} -> {target}")


def permissions(apply=False):
    if not apply:
        return

    os.system("chown -R pinball:pinball /home/pinball/Tables /home/pinball/tables 2>/dev/null || true")
    os.system("chmod -R u+rwX,g+rwX /home/pinball/Tables 2>/dev/null || true")
    os.system("find /home/pinball/Tables -type d -exec chmod 2775 {} \\; 2>/dev/null || true")


def main():
    parser = argparse.ArgumentParser(description="PinCabOs VPinFE/VPX standard per-table layout migration.")
    parser.add_argument("--apply", action="store_true", help="Apply changes.")
    parser.add_argument("--move-legacy", action="store_true", help="Move legacy global files after copying. Default is safe copy.")
    args = parser.parse_args()

    mode = "APPLY" if args.apply else "DRY-RUN"
    move = bool(args.move_legacy)

    log(f"=== PINCABOS VPINFE/VPX STANDARD: {mode} ===")
    log(f"Tables root: {TABLES_ROOT}")
    log(f"Legacy handling: {'MOVE' if move else 'COPY'}")

    if not TABLES_ROOT.exists():
        log(f"ERREUR: Tables root absent: {TABLES_ROOT}")
        return 1

    for table_dir in sorted([p for p in TABLES_ROOT.iterdir() if p.is_dir()]):
        rep = normalize_table(table_dir, apply=args.apply, move=move)
        REPORT["tables"].append(rep)

        if rep.get("skipped"):
            log(f"SKIP: {rep['table']} ({rep['skipped']})")
            continue

        log(f"TABLE: {rep['table']} | ROM: {rep.get('rom') or 'aucune'} | actions: {len(rep['actions'])}")
        for a in rep["actions"]:
            log(f"  - {a['type']}: {a['action']} -> {a['dst']}")

    fix_symlink(apply=args.apply)
    permissions(apply=args.apply)

    report_dir = Path("/home/pinball/Downloads/logs")
    report_dir.mkdir(parents=True, exist_ok=True)
    report = report_dir / f"vpinfe-vpx-standard-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    report.write_text(json.dumps(REPORT, indent=2, ensure_ascii=False))

    log(f"Rapport: {report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
