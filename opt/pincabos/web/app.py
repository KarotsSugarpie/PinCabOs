import urllib.error
import urllib.request
import sqlite3
import tempfile
import zipfile
import mimetypes
import urllib.parse
from flask import send_file, request, redirect, session
import shutil
import uuid
import shlex
from werkzeug.utils import secure_filename
from dashboard_plus import render_dashboard
from flask import Flask, redirect, url_for, jsonify, request
from routes.version import init_version_routes
from routes.update_status import init_update_status_routes
from pathlib import Path
from datetime import datetime
import socket
import subprocess
import psutil
import json
import time
import os
import html
import re

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


def webapp_screen_toggle_html():
    try:
        conf_path = Path("/opt/pincabos/config/webapp-screen-autostart.conf")
        state = {"playfield": "0", "backglass": "1"}

        if conf_path.exists():
            for line in conf_path.read_text(errors="replace").splitlines():
                line = line.strip()
                if not line or "=" not in line:
                    continue

                key, val = line.split("=", 1)
                key = key.strip().upper()
                val = "1" if val.strip() == "1" else "0"

                if key == "PLAYFIELD":
                    state["playfield"] = val
                elif key == "BACKGLASS":
                    state["backglass"] = val

        pf_on = state.get("playfield") == "1"
        bg_on = state.get("backglass") == "1"

        pf_class = "screen-toggle-on" if pf_on else "screen-toggle-off"
        bg_class = "screen-toggle-on" if bg_on else "screen-toggle-off"

        pf_label = "PlayField"
        bg_label = "BackGlass"

        return f"""
    <form action="/toggle-webapp-screen" method="post" class="nav-inline-form">
      <input type="hidden" name="screen" value="playfield">
      <button class="button nav-action screen-toggle-btn {pf_class}" type="submit">{pf_label}</button>
    </form>

    <form action="/toggle-webapp-screen" method="post" class="nav-inline-form">
      <input type="hidden" name="screen" value="backglass">
      <button class="button nav-action screen-toggle-btn {bg_class}" type="submit">{bg_label}</button>
    </form>
"""
    except Exception:
        return """
    <form action="/toggle-webapp-screen" method="post" class="nav-inline-form">
      <input type="hidden" name="screen" value="playfield">
      <button class="button nav-action screen-toggle-btn screen-toggle-off" type="submit">PlayField</button>
    </form>

    <form action="/toggle-webapp-screen" method="post" class="nav-inline-form">
      <input type="hidden" name="screen" value="backglass">
      <button class="button nav-action screen-toggle-btn screen-toggle-on" type="submit">BackGlass</button>
    </form>
"""


# PinCabOS config write audit helpers
def pincabos_modified_comment(function_name):
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return f"; Modifié {stamp} par PinCabOS fonction({function_name})"


def pincabos_modified_hash_comment(function_name):
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return f"# Modifié {stamp} par PinCabOS fonction({function_name})"


def pincabos_meta(function_name):
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return {
        "modified_at": stamp,
        "modified_by": "PinCabOS",
        "function": function_name
    }


def pincabos_backup_config_file(src, function_name="config"):
    src = Path(src)
    if not src.exists():
        return None

    safe_function = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(function_name)).strip("_") or "config"
    backup_dir = Path("/opt/pincabos/backups/config-writes") / safe_function
    backup_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dst = backup_dir / f"{src.name}.backup-{stamp}"
    shutil.copy2(src, dst)
    return dst


def pincabos_write_json_with_meta(path, data, function_name):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if isinstance(data, dict):
        data["_pincabos_meta"] = pincabos_meta(function_name)

    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def pincabos_read_ini_lines(path):
    path = Path(path)
    if path.exists():
        return path.read_text(errors="replace").splitlines()
    return []


def pincabos_write_ini_lines(path, lines):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n")


def pincabos_find_ini_section(lines, section):
    section_header = f"[{section}]"
    start = None
    end = len(lines)

    for i, line in enumerate(lines):
        if line.strip().lower() == section_header.lower():
            start = i
            break

    if start is None:
        return None, None

    for j in range(start + 1, len(lines)):
        stripped = lines[j].strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            end = j
            break

    return start, end


def pincabos_set_ini_key_with_comment(lines, section, key, value, function_name):
    comment = pincabos_modified_comment(function_name)
    start, end = pincabos_find_ini_section(lines, section)

    if start is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(comment)
        lines.append(f"[{section}]")
        lines.append(f"{key} = {value}")
        return lines

    key_lower = str(key).lower()
    key_index = None

    for i in range(start + 1, end):
        stripped = lines[i].strip()
        if not stripped or stripped.startswith(";") or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            continue

        existing_key = stripped.split("=", 1)[0].strip().lower()
        if existing_key == key_lower:
            key_index = i
            break

    if key_index is not None:
        if key_index > 0 and "par PinCabOS fonction(" in lines[key_index - 1]:
            lines[key_index - 1] = comment
        else:
            lines.insert(key_index, comment)
            key_index += 1

        lines[key_index] = f"{key} = {value}"
        return lines

    insert_at = end
    lines.insert(insert_at, comment)
    lines.insert(insert_at + 1, f"{key} = {value}")
    return lines


def pincabos_set_ini_section_with_comment(lines, section, values, function_name):
    comment = pincabos_modified_comment(function_name)
    start, end = pincabos_find_ini_section(lines, section)

    block = [comment, f"[{section}]"]
    for key, value in values.items():
        block.append(f"{key} = {value}")

    if start is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.extend(block)
        return lines

    return lines[:start] + block + lines[end:]


def shlex_quote(value):
    import shlex
    return shlex.quote(str(value))

app = Flask(__name__)
app.secret_key = os.environ.get("PINCABOS_SECRET_KEY", "pincabos-alpha-dev-secret")
app.config['MAX_CONTENT_LENGTH'] = 8 * 1024 * 1024 * 1024

BASE = Path("/opt/pincabos")
LOG_DIR = BASE / "logs" / "updates"
JOB_DIR = LOG_DIR / "jobs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
JOB_DIR.mkdir(parents=True, exist_ok=True)

UPDATE_COMMANDS = {
    "vpinfe": ["/usr/bin/sudo", "/opt/pincabos/tools/update-vpinfe.sh"],
    "vpx": ["/usr/bin/sudo", "/opt/pincabos/tools/update-vpx.sh"],
    "system": ["/usr/bin/sudo", "/opt/pincabos/tools/update-system.sh"],
    "all": ["/usr/bin/sudo", "/opt/pincabos/tools/update-all.sh"],
    "gpu": ["/usr/bin/sudo", "/opt/pincabos/tools/update-gpu-drivers.sh"],
}

# PINCABOS_FULL_UPDATE_OVERRIDE_START
def pincabos_build_full_update_command():
    import shlex
    from pathlib import Path as _PcoPath

    steps = []

    force_script = "/opt/pincabos/tools/pincabos-apply-update.sh"
    if _PcoPath(force_script).exists():
        steps.append(" ".join(shlex.quote(x) for x in [
            "/usr/bin/sudo",
            force_script,
            "--force"
        ]))

    for key in ["vpinfe", "vpx", "gpu", "system"]:
        if key in UPDATE_COMMANDS:
            steps.append(" ".join(shlex.quote(str(x)) for x in UPDATE_COMMANDS[key]))

    if not steps:
        steps.append("echo 'Aucune commande update disponible'")

    return ["/bin/bash", "-lc", " && ".join(steps)]


UPDATE_COMMANDS["all"] = pincabos_build_full_update_command()
# PINCABOS_FULL_UPDATE_OVERRIDE_END


def esc(x):
    return html.escape(str(x))

def get_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "inconnue"

def service_status(name):
    try:
        r = subprocess.run(
            ["systemctl", "is-active", name],
            capture_output=True,
            text=True,
            timeout=3
        )
        return r.stdout.strip()
    except Exception:
        return "unknown"

def latest_job_file():
    jobs = sorted(JOB_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return jobs[0] if jobs else None

def read_job(job_file):
    if not job_file or not job_file.exists():
        return None
    try:
        return json.loads(job_file.read_text())
    except Exception:
        return None

def get_job_status():
    job_file = latest_job_file()
    job = read_job(job_file)

    if not job:
        return {
            "has_job": False,
            "status": "idle",
            "target": "",
            "progress": 0,
            "message": "Aucune mise à jour lancée.",
            "log": "",
            "log_name": "aucun"
        }

    log_file = Path(job.get("log_file", ""))
    exit_file = Path(job.get("exit_file", ""))

    log_text = ""
    if log_file.exists():
        try:
            log_text = log_file.read_text(errors="replace")[-20000:]
        except Exception as e:
            log_text = f"Erreur lecture log: {e}"

    started = float(job.get("started", time.time()))
    elapsed = max(0, time.time() - started)

    if exit_file.exists():
        try:
            code = int(exit_file.read_text().strip())
        except Exception:
            code = 999

        if code == 0:
            status = "complete"
            progress = 100
            message = "Mises à jour terminée avec succès."
        else:
            status = "error"
            progress = 100
            message = f"Mises à jour terminée avec erreur. Code: {code}"
    else:
        status = "running"
        progress = min(95, int(8 + elapsed * 2))
        message = "Mises à jour en cours..."

    return {
        "has_job": True,
        "status": status,
        "target": job.get("target", ""),
        "progress": progress,
        "message": message,
        "log": log_text,
        "log_name": log_file.name if log_file.exists() else "log en attente"
    }


def pincabos_version():
    version_file = Path("/opt/pincabos/config/version.json")
    default = {
        "name": "PinCabOs",
        "version": "Development",
        "build": "dev",
        "author": "Karots Sugarpie",
        "update_channel": "SugarPiesNetwork",
        "update_base_url": "https://pincabos.cc/updates",
        "latest_json_url": "https://pincabos.cc/updates/latest.json"
    }

    try:
        if version_file.exists():
            data = json.loads(version_file.read_text())
            default.update(data)
    except Exception:
        pass

    return default


def run_cmd(cmd, timeout=8):
    try:
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return (r.stdout + r.stderr).strip()
    except Exception as e:
        return f"Erreur commande {' '.join(cmd)}: {e}"

def safe_file_text(path, fallback=""):
    try:
        f = Path(path)
        if f.exists():
            return f.read_text(errors="replace")
    except Exception as e:
        return f"Erreur lecture {path}: {e}"
    return fallback



# === Modular routes registration - PinCabOS START ===
init_version_routes(app, pincabos_version)
# === Modular routes registration - PinCabOS END ===

def pincabos_support_footer_html():
    import json
    from pathlib import Path

    ver = pincabos_version() if "pincabos_version" in globals() else {}
    qr_name = "pcbo_pay_qr_bbb5611b723f953dc3fad1e42e7dbd66fe9fa8d53de4293c.png"

    def v(key, fallback=""):
        try:
            return esc(str(ver.get(key, fallback) or fallback))
        except Exception:
            return esc(str(fallback))

    return f"""
<div class="footer pincabos-support-footer-safe" id="pincabos-support-footer-static">
  <div class="pincabos-release-notes-safe">
    <h2>Notes de version</h2>
    <div class="pincabos-release-grid-safe">
      <p><strong>Nom :</strong> {v("name", "PinCabOs")}</p>
      <p><strong>Version :</strong> {v("version", "Development")}</p>
      <p><strong>Build :</strong> {v("build", "dev")}</p>
      <p><strong>Canal :</strong> {v("channel", ver.get("update_channel", ""))}</p>
      <p><strong>Codename :</strong> {v("codename", "")}</p>
      <p><strong>Auteur :</strong> {v("author", "Karots Sugarpie")}</p>
      <p><strong>Update :</strong> {v("update_channel", "")}</p>
      <p><strong>Site :</strong> pincabos.cc</p>
    </div>
  </div>

  <div class="pincabos-footer-banner-safe">
    <img src="/static/branding/TopBanner.png?v=footer" alt="PinCabOS">
  </div>

  <div class="pincabos-support-text-safe">
    <h2>Soutenir PinCabOs</h2>
    <p>Si vous aimez PinCabOs, vous pouvez me le montrer en offrant ce que vous voulez. Merci pour votre soutien.</p>
    <div class="pincabos-paypal-form-safe">
      <form action="https://www.paypal.com/ncp/payment/SE79XX45T2NBG" method="post" target="_blank">
        <input class="pp-SE79XX45T2NBG-safe" type="submit" value="Acheter">
        <img class="pincabos-paypal-cards-safe" src="https://www.paypalobjects.com/images/Debit_Credit_APM.svg" alt="cards">
        <section class="pincabos-paypal-powered-safe">Optimisé par <img src="https://www.paypalobjects.com/paypal-ui/logos/svg/paypal-wordmark-color.svg" alt="paypal"></section>
      </form>
    </div>
  </div>

  <div class="pincabos-support-qr-safe">
    <img src="/static/pincabos-assets/{esc(qr_name)}" alt="QR Code PayPal PinCabOs">
    <div class="pincabos-support-qr-label-safe">QR Code PayPal PinCabOs</div>
  </div>
</div>
"""

def page(title, body):
    ip = get_ip()
    logo_html = ""
    if Path("/opt/pincabos/web/static/pincabos-logo.png").exists():
        logo_html = '<img src="/static/pincabos-logo.png" class="logo" alt="PinCabOs Logo">'

    return f"""<!doctype html>
<html>
<head>
  <title>PinCabOs - {esc(title)}</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body {{
      margin: 0;
      font-family: Arial, sans-serif;
      background:
        linear-gradient(rgba(0,0,0,0.72), rgba(0,0,0,0.72)),
        url('/static/pincabos-logo.png') center center / min(70vw, 760px) auto no-repeat fixed,
        #000000;
      color: #fff;
      padding: 30px;
    }}
    .top {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 20px;
      margin-bottom: 25px;
      background: rgba(29, 11, 46, 0.65);
      border: 1px solid rgba(255,122,0,0.65);
      border-radius: 18px;
      padding: 14px 18px;
      box-shadow: 0 0 25px rgba(255, 122, 0, 0.20);
    }}
    .brand-left {{
      display: flex;
      align-items: center;
      gap: 16px;
      min-width: 0;
    }}
    .logo {{
      max-width: 190px;
      width: 190px;
      height: auto;
      filter: drop-shadow(0 0 20px rgba(255,122,0,0.6));
      flex-shrink: 0;
    }}
    .brand-title {{
      color: #ffb000;
      font-size: 20px;
      font-weight: bold;
      text-shadow: 0 0 15px rgba(255,122,0,0.75);
      white-space: normal;
      line-height: 1.25;
    }}
    .brand-subtitle {{
      color: #d8b8ff;
      font-size: 15px;
      font-weight: normal;
      margin-top: 4px;
      text-shadow: 0 0 12px rgba(216,184,255,0.55);
    }}
    h1 {{
      display: none;
    }}
    .subtitle {{
      display: none;
    }}
    .nav {{
      text-align: right;
      margin-bottom: 0;
      flex-shrink: 0;
    }}
    @media (max-width: 850px) {{
      .top {{
        flex-direction: column;
        align-items: center;
        text-align: center;
      }}
      .brand-left {{
        flex-direction: column;
      }}
      .nav {{
        text-align: center;
      }}
    }}
    .nav a, .button {{
      display: inline-block;
      background: #ff7a00;
      color: #160020;
      padding: 10px 15px;
      border-radius: 10px;
      text-decoration: none;
      font-weight: bold;
      margin: 5px;
      border: none;
      cursor: pointer;
    }}
    .secondary {{
      background: #5f2a91 !important;
      color: white !important;
      border: 1px solid #ff7a00 !important;
    }}
    .nav a.active {{
      background: #ff7a00 !important;
      color: #160020 !important;
      border: 1px solid #ffb000 !important;
      box-shadow: 0 0 18px rgba(255,122,0,0.8);
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
      gap: 20px;
    }}
    .card {{
      background: rgba(29, 11, 46, 0.76);
      border: 1px solid #ff7a00;
      border-radius: 18px;
      padding: 22px;
      box-shadow: 0 0 25px rgba(255, 122, 0, 0.25);
    }}
    .card h2 {{
      margin-top: 0;
      color: #ffb000;
    }}
    .ok {{ color: #00ff99; font-weight: bold; }}
    .bad {{ color: #ff5555; font-weight: bold; }}
    .warn {{ color: #ffb000; font-weight: bold; }}
    code {{
      background: #000;
      color: #ffb000;
      padding: 4px 8px;
      border-radius: 6px;
      display: inline-block;
      margin: 2px 0;
    }}
    pre {{
      white-space: pre-wrap;
      background: #050007;
      color: #eee;
      padding: 15px;
      border-radius: 12px;
      border: 1px solid #5f2a91;
      height: 520px;
      overflow-y: scroll;
      font-size: 13px;
    }}
    .progress-wrap {{
      background: #050007;
      border: 1px solid #ff7a00;
      border-radius: 14px;
      overflow: hidden;
      height: 30px;
      margin: 15px 0;
      box-shadow: 0 0 15px rgba(255,122,0,0.4);
    }}
    .progress-bar {{
      height: 100%;
      width: 0%;
      background: linear-gradient(90deg, #ff7a00, #ff00cc, #00eaff);
      color: #000;
      font-weight: bold;
      text-align: center;
      line-height: 30px;
      transition: width 0.5s ease;
    }}
    .running {{
      animation: glow 1.2s infinite alternate;
    }}
    @keyframes glow {{
      from {{ filter: brightness(1); }}
      to {{ filter: brightness(1.5); }}
    }}
    .footer {{
      margin-top: 30px;
      color: #ffb000;
      font-size: 14px;
      opacity: 0.9;
      text-align: center;
    }}

    .nav-tools form {{
      display: inline-flex;
      gap: 6px;
      align-items: center;
      margin: 0;
    }}

    .nav-tools select {{
      padding: 8px;
      border-radius: 8px;
      border: 1px solid #ff7a00;
      background: #160020;
      color: #fff;
    }}

    .pincabos-nav a,
    .pincabos-nav button {{
      min-height: 38px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      line-height: 1;
    }}


    .pincabos-nav {{
      margin: 18px auto 0 auto;
      max-width: 1220px;
      display: flex;
      flex-direction: column;
      gap: 10px;
    }}

    .nav-row {{
      display: flex;
      flex-wrap: wrap;
      justify-content: center;
      align-items: center;
      gap: 8px;
    }}

    .nav-pages {{
      padding: 10px;
      border-radius: 18px;
      background: rgba(12, 0, 22, 0.58);
      border: 1px solid rgba(255, 122, 0, 0.25);
      box-shadow: 0 0 22px rgba(95, 42, 145, 0.22);
    }}

    .nav-tools-clean {{
      padding: 10px;
      border-radius: 18px;
      background: rgba(255, 122, 0, 0.07);
      border: 1px solid rgba(95, 42, 145, 0.45);
      box-shadow: inset 0 0 18px rgba(0, 0, 0, 0.18);
    }}

    .nav-inline-form {{
      margin: 0;
      display: inline-flex;
      align-items: center;
    }}

    .nav-label {{
      color: #ffb000;
      font-weight: 800;
      padding: 0 4px;
      text-shadow: 0 0 10px rgba(255, 122, 0, 0.45);
    }}

    .nav-action {{
      white-space: nowrap;
    }}

    .pincabos-nav a,
    .pincabos-nav button {{
      min-height: 38px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      line-height: 1;
    }}


    .top-language-widget {{
      position: absolute;
      top: 18px;
      right: 22px;
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 8px 10px;
      border-radius: 14px;
      background: rgba(10, 0, 20, 0.82);
      border: 1px solid rgba(255, 122, 0, 0.45);
      box-shadow: 0 0 18px rgba(255, 122, 0, 0.20);
      z-index: 999;
    }}

    .top-language-widget span {{
      color: #ffb000;
      font-weight: 800;
      font-size: 13px;
      white-space: nowrap;
      text-shadow: 0 0 10px rgba(255,122,0,0.45);
    }}

    .top-language-widget select {{
      padding: 7px 10px;
      border-radius: 10px;
      border: 1px solid #ff7a00;
      background: #160020;
      color: #fff;
      font-weight: 700;
      outline: none;
    }}

    #google_translate_element {{
      display: none;
    }}

    .goog-te-banner-frame.skiptranslate,
    iframe.goog-te-banner-frame {{
      display: none !important;
    }}

    body {{
      top: 0 !important;
    }}

    .goog-logo-link,
    .goog-te-gadget span {{
      display: none !important;
    }}

    .goog-te-gadget {{
      color: transparent !important;
      font-size: 0 !important;
    }}


    .import-progress-box {{
      display: none;
      margin-top: 14px;
      padding: 12px;
      border-radius: 14px;
      border: 1px solid rgba(255, 122, 0, 0.45);
      background: rgba(10, 0, 20, 0.72);
      box-shadow: 0 0 18px rgba(255, 122, 0, 0.18);
    }}

    .import-progress-label {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      color: #ffb000;
      font-weight: 800;
      margin-bottom: 8px;
    }}

    .import-progress-track {{
      height: 18px;
      background: #160020;
      border: 1px solid #5f2a91;
      border-radius: 999px;
      overflow: hidden;
    }}

    .import-progress-bar {{
      height: 100%;
      width: 0%;
      background: #ff7a00;
      box-shadow: 0 0 16px rgba(255,122,0,0.85);
      transition: width 0.25s ease;
    }}

    .import-progress-note {{
      margin-top: 8px;
      font-size: 13px;
      color: #ddd;
    }}

    .import-spinner {{
      display: inline-block;
      width: 14px;
      height: 14px;
      border: 2px solid rgba(255,255,255,0.25);
      border-top-color: #ff7a00;
      border-radius: 50%;
      animation: pincabSpin 0.9s linear infinite;
      vertical-align: middle;
      margin-right: 6px;
    }}

    @keyframes pincabSpin {{
      to {{ transform: rotate(360deg); }}
    }}


.np-grid-safe{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}
.np-panel-safe{{border:1px solid rgba(255,176,0,.25);border-radius:16px;padding:16px;background:rgba(0,0,0,.18)}}
.np-panel-safe h3{{margin-top:0;color:#ffb000}}
.nudge-scope-safe{{position:relative;width:240px;height:240px;margin:10px auto;border-radius:50%;border:2px solid rgba(255,176,0,.6);background:radial-gradient(circle,rgba(255,176,0,.12),rgba(0,0,0,.25))}}
.nudge-scope-safe:before,.nudge-scope-safe:after{{content:"";position:absolute;background:rgba(255,176,0,.35)}}
.nudge-scope-safe:before{{left:50%;top:0;width:1px;height:100%}}
.nudge-scope-safe:after{{top:50%;left:0;height:1px;width:100%}}
.nudge-dot-safe{{position:absolute;left:50%;top:50%;width:16px;height:16px;transform:translate(-50%,-50%);border-radius:50%;background:#ff2b2b;box-shadow:0 0 12px rgba(255,43,43,.9)}}
.plunger-track-safe{{position:relative;height:28px;margin:36px 8px;border-radius:999px;border:1px solid rgba(255,176,0,.45);background:rgba(0,0,0,.35)}}
.plunger-pointer-safe{{position:absolute;left:50%;top:-9px;width:10px;height:46px;transform:translateX(-50%);border-radius:8px;background:#ff2b2b;box-shadow:0 0 12px rgba(255,43,43,.9)}}
.np-fields-safe{{display:grid;grid-template-columns:repeat(2,minmax(160px,1fr));gap:10px}}
.np-fields-safe label{{display:flex;flex-direction:column;gap:5px;font-weight:700}}
.np-fields-safe .checkline{{flex-direction:row;align-items:center}}
.np-fields-safe input,.np-fields-safe select{{max-width:100%}}
@media(max-width:950px){{.np-grid-safe{{grid-template-columns:1fr}}}}


.np-grid-safe{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}
.np-panel-safe{{border:1px solid rgba(255,176,0,.25);border-radius:16px;padding:16px;background:rgba(0,0,0,.18)}}
.np-panel-safe h3{{margin-top:0;color:#ffb000}}
.nudge-scope-safe{{position:relative;width:240px;height:240px;margin:10px auto;border-radius:50%;border:2px solid rgba(255,176,0,.6);background:radial-gradient(circle,rgba(255,176,0,.12),rgba(0,0,0,.25))}}
.nudge-scope-safe:before,.nudge-scope-safe:after{{content:"";position:absolute;background:rgba(255,176,0,.35)}}
.nudge-scope-safe:before{{left:50%;top:0;width:1px;height:100%}}
.nudge-scope-safe:after{{top:50%;left:0;height:1px;width:100%}}
.nudge-dot-safe{{position:absolute;left:50%;top:50%;width:16px;height:16px;transform:translate(-50%,-50%);border-radius:50%;background:#ff2b2b;box-shadow:0 0 12px rgba(255,43,43,.9)}}
.plunger-track-safe{{position:relative;height:28px;margin:36px 8px;border-radius:999px;border:1px solid rgba(255,176,0,.45);background:rgba(0,0,0,.35)}}
.plunger-pointer-safe{{position:absolute;left:50%;top:-9px;width:10px;height:46px;transform:translateX(-50%);border-radius:8px;background:#ff2b2b;box-shadow:0 0 12px rgba(255,43,43,.9)}}
.np-fields-safe{{display:grid;grid-template-columns:repeat(2,minmax(160px,1fr));gap:10px}}
.np-fields-safe label{{display:flex;flex-direction:column;gap:5px;font-weight:700}}
.np-fields-safe .checkline{{flex-direction:row;align-items:center}}
.np-fields-safe input,.np-fields-safe select{{max-width:100%}}
@media(max-width:950px){{.np-grid-safe{{grid-template-columns:1fr}}}}


/* PINCABOS-LOG-NEWLINES-START */
pre,
#job-log,
.update-log,
.firstrun-log {{
  white-space: pre-wrap !important;
  overflow-wrap: anywhere !important;
  word-break: break-word !important;
}}
/* PINCABOS-LOG-NEWLINES-END */

</style>
<script 
  src="https://www.paypal.com/sdk/js?client-id=BAA5atlZ6zhL2iAHU4cMNpDOLyPpnZ4tBNxVfg_ZowsRSbQM5voDWVamM3F_Rw_vmwtMFrLxcT2kbgohM0&components=hosted-buttons&disable-funding=venmo&currency=CAD">
</script>


<script src="//translate.google.com/translate_a/element.js?cb=googleTranslateElementInit"></script>

<script src="/static/pincabos-i18n.js"></script>
<link rel="stylesheet" href="/static/pincabos-dashboard-compact.css">
<link rel="stylesheet" href="/static/pincabos-branding.css?v=branding">
<link rel="stylesheet" href="/static/pincabos-header-fix.css?v=20260515232444">
<link rel="stylesheet" href="/static/pincabos-global-compact.css">
<link rel="stylesheet" href="/static/pincabos-footer.css">
<link rel="stylesheet" href="/static/pincabos-support-footer.css">
<link rel="stylesheet" href="/static/pincabos-services-taskmanager.css">
<link rel="stylesheet" href="/static/pincabos-menu-icons.css">
<link rel="stylesheet" href="/static/pincabos-fulldmd-compact.css?v=20260515164207">
  <link rel="stylesheet" href="/static/pincabos-webapp-screen-toggle.css?v=20260519-final">
<link rel="icon" type="image/png" href="/static/branding/favicon.png?v=branding">
</head>
<body>

<div class="top-language-widget">
  <div id="google_translate_element"></div>
  <span>Langue :</span>
  <select id="pincabos_language_select" onchange="setPinCabOsLanguage(this.value)">
    <option value="fr">Français</option>
    <option value="en">English</option>
  </select>
</div>

  <div class="top">
    <div class="brand-left">
      {logo_html}
      <div class="brand-title">
<div class="brand-subtitle"></div>
      </div>
    </div>

    <div class="nav">
    

<nav class="pincabos-nav">
  <div class="nav-row nav-pages">
    <a href="/" class="{ 'active' if title == 'Tableau de bord' else 'secondary' }"><span class="menu-ico">📊</span> Tableau de bord</a> 
    <a href="/network" class="{ 'active' if title == 'Réseau' else 'secondary' }"><span class="menu-ico">🌐</span> Réseau / WiFi</a>

    <a href="/gpu" class="{ 'active' if title in ['GPU', 'GPU / Écrans', 'Écrans / GPU'] else 'secondary' }"><span class="menu-ico">🎮</span> Écrans / GPU</a>

    <a href="/audio-ssf" class="{ 'active' if title == 'Audio / SSF V2' else 'secondary' }"><span class="menu-ico">🔊</span> Audio / SSF V2</a>
    <a href="/inputs" class="{ 'active' if title == 'Inputs' else 'secondary' }"><span class="menu-ico">🎛️</span> Inputs</a>

    <a href="/dof" class="{ 'active' if title in ['DOF', 'Outputs', 'DOF Commander'] else 'secondary' }"><span class="menu-ico">💡</span> Outputs</a>

    <a href="/fulldmd" class="{ 'active' if title == 'FullDMD' else 'secondary' }"><span class="menu-ico">🖥️</span> FullDMD</a>

    <a href="/tools" class="{ 'active' if title == 'Outils' else 'secondary' }"><span class="menu-ico">🧰</span> Outils PinCabOS</a>

    <a href="/updates" class="{ 'active' if title == 'Mises à jour' else 'secondary' }"><span class="menu-ico">⬆️</span> Mises à jour</a>

    <a href="/about" class="{ 'active' if title == 'À propos' else 'secondary' }"><span class="menu-ico">ℹ️</span> À propos</a>
 </div>

  <div class="nav-row nav-tools-clean">
    <span class="nav-vpinfe-vps-group" style="display:inline-flex;align-items:center;gap:8px;flex:0 0 auto;">
      <a href="http://{ip}:8001" target="_blank" class="secondary nav-action">Ouvrir VPinFE</a>
      <a href="https://virtualpinballspreadsheet.github.io/" target="_blank" rel="noopener noreferrer" class="secondary nav-action">Ouvrir VPS</a>
    </span>

    <span class="nav-label" style="margin-left:auto;">Afficher PinCabOs WebApp sur :</span>

    {webapp_screen_toggle_html()}
  </div>
</nav>
  </div>

  </div>
  </div>

  {body}

  
{pincabos_support_footer_html()}

<script src="/static/pincabos-progress-reset.js"></script>
<script src="/static/pincabos-dashboard-compact.js"></script>
<script src="/static/pincabos-header-final.js?v=20260515232444"></script>
<!-- footer now rendered server-side; JS injection disabled -->
<script src="/static/pincabos-fulldmd-compact.js"></script>

  <div id="firstrun-popup" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.72);z-index:999999;align-items:center;justify-content:center;">
    <div style="max-width:620px;width:92%;border:1px solid rgba(255,176,0,.55);border-radius:20px;padding:22px;background:rgba(18,0,30,.96);box-shadow:0 0 35px rgba(255,122,0,.35);">
      <div style="text-align:center;margin-bottom:14px;">
        <img src="/static/branding/firstrun-welcome.png?v=welcome"
             alt="Bienvenue PinCabOS"
             style="max-width:260px;width:70%;height:auto;border-radius:14px;box-shadow:0 0 22px rgba(255,122,0,.28);">
      </div>
      <h2>🚀 Bienvenue dans PinCabOS</h2>
      <p>Avant d’utiliser PinCabOS, Jarvis recommande de compléter l’assistant Premier Démarrage.</p>
      <p>Checklist : mises à jour, réseau, GPU, écrans, audio, inputs, outputs, FullDMD et validation finale.</p>
      <p>
        <a class="button" href="/first-run">🚀 Démarrer l’assistant</a>
        <button class="button secondary" onclick="closeFirstRunPopup()">Plus tard</button>
      </p>
      <label>
        <input type="checkbox" id="firstrun-disable">
        Ne plus afficher automatiquement
      </label>
    </div>
  </div>

  <script>
  async function closeFirstRunPopup(){{
    var chk = document.getElementById("firstrun-disable");
    var disable = chk ? chk.checked : false;
    if(disable){{
      await fetch("/first-run/popup-disable", {{method:"POST"}});
    }}
    var p = document.getElementById("firstrun-popup");
    if(p) p.style.display = "none";
  }}

  window.addEventListener("load", function(){{
    var shouldShow = "{'1' if (title in ['Dashboard', 'Tableau de bord'] and firstrun_load_cfg().get('show_popup', True)) else '0'}";
    if(shouldShow === "1"){{
      setTimeout(function(){{
        var p = document.getElementById("firstrun-popup");
        if(p) p.style.display = "flex";
      }}, 650);
    }}
  }});
  </script>

</body>
</html>"""


# === FIRST RUN WIZARD - PINCABOS START ===
PINCABOS_FIRSTRUN_CFG = "/opt/pincabos/config/firstrun.json"

def firstrun_default_cfg():
    return {
        "show_popup": True,
        "updates": False,
        "network": False,
        "gpu": False,
        "screens": False,
        "audio": False,
    }

def firstrun_load_cfg():
    from pathlib import Path
    import json
    cfg = firstrun_default_cfg()
    p = Path(PINCABOS_FIRSTRUN_CFG)
    if p.exists():
        try:
            data = json.loads(p.read_text(errors="replace"))
            if isinstance(data, dict):
                cfg.update(data)
        except Exception:
            pass
    return cfg

def firstrun_save_cfg(cfg):
    from pathlib import Path
    import json, subprocess
    p = Path(PINCABOS_FIRSTRUN_CFG)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n")
    try:
        subprocess.run(["chown", "pinball:pinball", str(p)], timeout=5)
    except Exception:
        pass

def firstrun_card(key, icon, title, text, buttons, cfg):
    checked = "checked" if cfg.get(key) else ""
    done = "done" if cfg.get(key) else ""
    return f"""
<div class="firstrun-step {done}" style="position:relative;">
  <button class="button secondary firstrun-step-save"
          type="button"
          onclick="saveFirstRunStep('{esc(key)}')">
    💾 Sauvegarder
  </button>
  <div class="firstrun-left">
    <label class="firstrun-check">
      <input class="firstrun-step-check" type="checkbox" name="{esc(key)}" value="1" {checked}>
      <span>{icon}</span>
    </label>
  </div>
  <div class="firstrun-step-body">
    <h3>{esc(title)}</h3>
    <p>{text}</p>
    <div class="firstrun-buttons">{buttons}</div>
    <pre id="firstrun-log-{esc(key)}" class="firstrun-log">En attente.</pre>
  </div>
</div>
"""

@app.route("/first-run")
def firstrun_page():
    cfg = firstrun_load_cfg()
    remote_ip = get_ip()
    remote_url = "http://" + str(remote_ip or "127.0.0.1") + "/"
    keys = ["updates", "network", "gpu", "screens", "audio"]
    done = sum(1 for k in keys if cfg.get(k))
    pct = int((done / len(keys)) * 100)

    body = """
<style>
body {
  background-image:
    linear-gradient(rgba(8,0,18,.74), rgba(8,0,18,.84)),
    url("/static/branding/firstrun-welcome-bg.png?v=firstrun") !important;
  background-position: center center, center center !important;
  background-size: cover, 58% auto !important;
  background-attachment: fixed, fixed !important;
  background-repeat: no-repeat, no-repeat !important;
}


.pincabos-nav,
.nav,
.nav-row,
.nav-pages,
.nav-tools-clean,
.brand-title,
.brand-subtitle {
  display: none !important;
}

.top {
  justify-content: center !important;
}

.brand-left {
  justify-content: center !important;
}

.top {
  min-height: 135px !important;
  align-items: center !important;
}

.firstrun-banner {
  position: static;
  transform: none;
  margin: 0;
  z-index: 10;
  flex: 1 1 auto;
  text-align: left;
}

.firstrun-banner img {
  max-width: min(42vw, 625px);
  width: 100%;
  height: auto;
  border-radius: 14px;
  box-shadow: 0 0 24px rgba(255,122,0,.24);
}

.firstrun-network-remote {
  margin-left: auto;
  border: 1px solid rgba(0,255,120,.65);
  background: rgba(0,120,60,.24);
  border-radius: 14px;
  padding: 8px 12px;
  text-align: right;
  min-width: 260px;
}

.firstrun-network-remote .ip {
  font-size: 28px;
  font-weight: 900;
  color: #00ff78;
  text-shadow: 0 0 12px rgba(0,255,120,.55);
}

.firstrun-network-remote a {
  color: #ffb000;
  font-weight: 800;
}

.firstrun-hero {
  border: 1px solid rgba(255,176,0,.35);
  border-radius: 20px;
  padding: 18px;
  background: linear-gradient(135deg, rgba(255,122,0,.10), rgba(95,42,145,.18));
  box-shadow: 0 0 28px rgba(255,122,0,.13);
}
.firstrun-progress-wrap {
  margin: 16px 0;
  height: 20px;
  border-radius: 999px;
  overflow: hidden;
  background: rgba(0,0,0,.35);
  border: 1px solid rgba(255,176,0,.35);
}
.firstrun-progress {
  height: 100%;
  width: """ + str(pct) + """%;
  background: linear-gradient(90deg, #ff7a00, #ffb000);
  box-shadow: 0 0 14px rgba(255,176,0,.55);
}
.firstrun-list {
  display: grid;
  grid-template-columns: 1fr;
  gap: 14px;
}
.firstrun-step {
  display: flex;
  gap: 14px;
  position: relative;
  border: 1px solid rgba(255,70,70,.55);
  border-radius: 16px;
  padding: 14px;
  background: rgba(140,0,0,.16);
  box-shadow: 0 0 14px rgba(255,0,0,.12);
}
.firstrun-step.done {
  border-color: rgba(0,255,120,.95);
  background: rgba(0,180,80,.34);
  box-shadow: 0 0 24px rgba(0,255,120,.38);
}
.firstrun-check {
  font-size: 32px;
  min-width: 62px;
  text-align: center;
}
.firstrun-check input {
  width: 22px;
  height: 22px;
  display: block;
  margin: 0 auto 8px auto;
}
.firstrun-step-body {
  width: 100%;
}
.firstrun-step-body h3 {
  margin: 0 0 6px 0;
  color: #ffb000;
}
.firstrun-buttons {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin: 10px 0;
}
.firstrun-step-save {
  position: absolute;
  top: 12px;
  right: 12px;
  font-size: 12px !important;
  padding: 6px 10px !important;
  z-index: 5;
}

.firstrun-log {
  min-height: 80px;
  max-height: 280px;
  overflow: auto;
  background: rgba(0,0,0,.42);
  border: 1px solid rgba(255,176,0,.18);
  border-radius: 12px;
  padding: 10px;
  white-space: pre-wrap;
}
.firstrun-warning {
  border: 1px solid rgba(255,176,0,.42);
  border-radius: 14px;
  padding: 12px;
  background: rgba(255,176,0,.08);
  margin-top: 12px;
}
</style>

<script>
document.addEventListener("DOMContentLoaded", function() {
  const top = document.querySelector(".top");
  if (top && !document.querySelector(".firstrun-banner")) {
    const banner = document.createElement("div");
    banner.className = "firstrun-banner";
    banner.innerHTML = '<img src="/static/branding/FBBanner.png?v=firstrun" alt="PinCabOS First Run">';
    top.prepend(banner);
  }
});
</script>

<div class="card firstrun-hero">
  <h1>🚀 Assistant Premier Démarrage PinCabOS</h1>
  <p>
    Les 5 étapes essentielles à exécuter juste après l’installation.
    Les actions se lancent directement ici, sans quitter cette page sauf si un redémarrage est requis.
  </p>

  <div class="firstrun-progress-wrap">
    <div class="firstrun-progress" id="firstrun-progress-bar"></div>
  </div>

  <p><strong>Progression :</strong> <span id="firstrun-done-count">""" + str(done) + """</span> / """ + str(len(keys)) + """ étapes complétées — <span id="firstrun-pct">""" + str(pct) + """</span>%</p>

  <div class="firstrun-warning">
    ⚠️ Conseil PinCabOS : fais ces étapes directement sur le cab quand possible.
  </div>
</div>

<form method="post" action="/first-run/save">

<div class="card">
  <h2>Checklist de configuration</h2>
  <div class="firstrun-list">
"""

    body += firstrun_card(
        "updates", "🔄", "1 — Mise à jour système complète",
        "Met à jour Ubuntu, PinCabOS, VPX/VPinFE et dépendances. Redémarre si demandé.",
        '<button class="button" type="button" onclick="firstrunUpdateAll()">Exécuter mise à jour complète</button>'
        '<button class="button secondary" type="button" onclick="firstrunPollUpdate()">Voir progression</button>',
        cfg
    )

    body += firstrun_card(
        "network", "🌐", "2 — Vérification réseau",
        "Vérifie l’interface, l’IP, la passerelle, le DNS et l’accès réseau.",
        '<button class="button" type="button" onclick="firstrunAction(\'network\', \'network-check\')">Détection du réseau</button>'
        '<div class="firstrun-network-remote">'
        '<div>Adresse remote WebApp</div>'
        '<div class="ip">' + esc(remote_ip) + '</div>'
        '<a href="' + esc(remote_url) + '" target="_blank">' + esc(remote_url) + '</a>'
        '</div>',
        cfg
    )

    body += firstrun_card(
        "gpu", "🎮", "3 — GPU et pilotes",
        "Détecte le GPU et permet de lancer la mise à jour des pilotes.",
        '<button class="button" type="button" onclick="firstrunAction(\'gpu\', \'gpu-detect\')">Détecter GPU</button>'
        '<button class="button secondary" type="button" onclick="firstrunGpuUpdate()">Mettre à jour pilotes GPU</button>',
        cfg
    )

    body += firstrun_card(
        "screens", "🖥️", "4 — Détection et assignation des écrans",
        "Détecte les écrans disponibles et prépare Playfield / Backglass / FullDMD.",
        '<button class="button" type="button" onclick="firstrunAction(\'screens\', \'screens-detect\')">Détecter écrans</button>'
        '<button class="button secondary" type="button" onclick="firstrunAction(\'screens\', \'screens-apply-vpx\')">Appliquer à VPX</button>'
        '<button class="button secondary" type="button" onclick="firstrunAction(\'screens\', \'screens-apply-vpinfe\')">Appliquer à VPinFE</button>',
        cfg
    )

    body += firstrun_card(
        "audio", "🔊", "5 — Audio / SSF V2",
        "Détecte les cartes audio et prépare la configuration audio/SSF.",
        '<button class="button" type="button" onclick="firstrunAction(\'audio\', \'audio-detect\')">Détecter audio</button>'
        '<button class="button secondary" type="button" onclick="firstrunAction(\'audio\', \'audio-apply\')">Appliquer audio/SSF</button>',
        cfg
    )

    show_checked = "checked" if cfg.get("show_popup") else ""

    body += """
  </div>
</div>

<div class="card">
  <button class="button" type="submit">💾 Sauvegarder la checklist</button>
  <button class="button secondary" type="button" onclick="firstrunReboot()">🔄 Redémarrer</button>
  <label style="margin-left:12px;">
    <input id="firstrun-show-popup" type="checkbox" name="show_popup" value="1" """ + show_checked + """>
    Afficher automatiquement au démarrage
  </label>
</div>

</form>

<script>

async function firstrunReboot() {
  if (!false && confirm("Redémarrer PinCabOS maintenant ?")) return;

  try {
    await fetch("/first-run/reboot", {method:"POST"});
    document.body.innerHTML = "<div style='padding:40px;font-family:Arial;color:#ffb000;background:#080012;min-height:100vh;'><h1>🔄 Redémarrage PinCabOS...</h1><p>La WebApp sera temporairement indisponible.</p></div>";
  } catch(e) {
    alert("Erreur redémarrage: " + e);
  }
}

async function firstrunAction(step, action) {
  const log = document.getElementById("firstrun-log-" + step);
  if (log) log.textContent = "Exécution : " + action + "...";

  try {
    const r = await fetch("/first-run/action/" + action, {method:"POST"});
    const data = await r.json();
    if (log) log.textContent = data.output || data.error || "Terminé.";
  } catch(e) {
    if (log) log.textContent = "Erreur : " + e;
  }
}

async function firstrunUpdateAll() {
  const log = document.getElementById("firstrun-log-updates");
  if (log) log.textContent = "Lancement mise à jour complète...";
  await fetch("/run-update/all", {method:"POST"});
  firstrunPollUpdate();
}

async function firstrunGpuUpdate() {
  const log = document.getElementById("firstrun-log-gpu");
  if (log) log.textContent = "Lancement mise à jour pilotes GPU...";
  await fetch("/run-update/gpu", {method:"POST"});
  firstrunPollUpdate("gpu");
}

async function firstrunPollUpdate(targetStep) {
  const step = targetStep || "updates";
  const log = document.getElementById("firstrun-log-" + step);

  async function poll() {
    try {
      const r = await fetch("/api/update-status?t=" + Date.now());
      const data = await r.json();
      if (log) {
        log.textContent =
          "Statut: " + (data.status || "idle") + "\\n" +
          "Cible: " + (data.target || "aucune") + "\\n" +
          "Progression: " + (data.progress || 0) + "%\\n\\n" +
          (data.log || data.message || "");
        log.scrollTop = log.scrollHeight;
      }
      if (data.status === "running") setTimeout(poll, 2000);
    } catch(e) {
      if (log) log.textContent = "Erreur progression : " + e;
    }
  }
  poll();
}


function saveFirstRunStep(step) {
  const cb = document.querySelector('input[name="' + step + '"]');
  if (cb) cb.checked = true;

  updateFirstRunProgressUI();

  const form = document.querySelector('form[action="/first-run/save"]');
  if (form) {
    form.submit();
  } else {
    window.location.reload();
  }
}

function updateFirstRunProgressUI() {
  const checks = Array.from(document.querySelectorAll(".firstrun-step-check"));
  const done = checks.filter(c => c.checked).length;
  const total = checks.length || 5;
  const pct = Math.round((done / total) * 100);

  const bar = document.getElementById("firstrun-progress-bar");
  const count = document.getElementById("firstrun-done-count");
  const pctEl = document.getElementById("firstrun-pct");
  const popup = document.getElementById("firstrun-show-popup");

  if (bar) bar.style.width = pct + "%";
  if (count) count.textContent = done;
  if (pctEl) pctEl.textContent = pct;

  if (popup) {
    if (done < total) {
      popup.checked = true;
      popup.disabled = true;
      popup.title = "Les 5 étapes doivent être complétées avant de désactiver le popup.";
    } else {
      popup.disabled = false;
      popup.title = "";
    }
  }
}

document.addEventListener("DOMContentLoaded", function() {
  document.querySelectorAll(".firstrun-step-check").forEach(c => {
    c.addEventListener("change", updateFirstRunProgressUI);
  });
  updateFirstRunProgressUI();
});
</script>
"""
    return page("First Run", body)


@app.route("/first-run/reboot", methods=["POST"])
def firstrun_reboot():
    try:
        subprocess.Popen(
            ["/usr/bin/sudo", "/bin/systemctl", "reboot", "-i"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/first-run/action/<action>", methods=["POST"])
def firstrun_action(action):
    try:
        if action == "network-check":
            restart_log = run_cmd([
                "/usr/bin/sudo",
                "-n",
                "/opt/pincabos/tools/firstrun-network-detect.sh"
            ], timeout=90)

            return jsonify({
                "ok": True,
                "output": restart_log + "\n\n===== Résumé réseau PinCabOS =====\n" + network_info_text()
            })

        if action == "gpu-detect":
            return jsonify({"ok": True, "output": gpu_info_text()})

        if action == "screens-detect":
            out = run_cmd(["/usr/bin/sudo", "/opt/pincabos/tools/auto-detect-screens.sh"], timeout=30)
            extra = screens_layout_text()
            return jsonify({"ok": True, "output": out + "\\n\\n===== screens.json =====\\n" + extra})

        if action == "screens-apply-vpx":
            result = pincabos_gpu_apply_config_to_vpx()
            if isinstance(result, (list, tuple)):
                output = "Appliqué à VPX.\\n" + "\\n".join(str(x) for x in result)
            else:
                output = "Appliqué à VPX.\\n" + str(result)
            return jsonify({"ok": True, "output": output})

        if action == "screens-apply-vpinfe":
            result = pincabos_gpu_apply_config_to_vpinfe()
            if isinstance(result, (list, tuple)):
                output = "Appliqué à VPinFE.\\n" + "\\n".join(str(x) for x in result)
            else:
                output = "Appliqué à VPinFE.\\n" + str(result)
            return jsonify({"ok": True, "output": output})

        if action == "audio-detect":
            out = run_cmd(["bash", "--noprofile", "--norc", "-c", "echo '===== ALSA ====='; aplay -l 2>/dev/null || true; echo; echo '===== Pulse/PipeWire ====='; pactl info 2>/dev/null || true; echo; pactl list short sinks 2>/dev/null || true"], timeout=10)
            return jsonify({"ok": True, "output": out})

        if action == "audio-apply":
            out = audio_apply_to_vpx_vpinfe()
            return jsonify({"ok": True, "output": str(out)})

        return jsonify({"ok": False, "error": "Action inconnue: " + action}), 404

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/first-run/popup-disable", methods=["POST"])
def firstrun_popup_disable():
    cfg = firstrun_load_cfg()
    required = ["updates", "network", "gpu", "screens", "audio"]
    if not all(cfg.get(k) for k in required):
        cfg["show_popup"] = True
        firstrun_save_cfg(cfg)
        return jsonify({"ok": False, "error": "Les 5 étapes First Run doivent être complétées avant de désactiver le popup."}), 403
    cfg["show_popup"] = False
    firstrun_save_cfg(cfg)
    return jsonify({"ok": True})

@app.route("/first-run/save", methods=["POST"])
def firstrun_save():
    cfg = firstrun_default_cfg()
    for key in ["updates", "network", "gpu", "screens", "audio"]:
        cfg[key] = request.form.get(key) == "1"
    if all(cfg.get(k) for k in ["updates", "network", "gpu", "screens", "audio"]):
        cfg["show_popup"] = request.form.get("show_popup") == "1"
    else:
        cfg["show_popup"] = True
    firstrun_save_cfg(cfg)
    return redirect("/first-run")
# === FIRST RUN WIZARD - PINCABOS END ===


@app.route("/")
def dashboard():
    return render_dashboard(page, esc, get_ip, service_status, pincabos_version)


def gpu_info_text():
    return run_cmd(["/usr/bin/sudo", "/opt/pincabos/tools/detect-gpu.sh"], timeout=15)


def screens_layout_text():
    try:
        f = Path("/opt/pincabos/config/screens.json")
        if f.exists():
            return f.read_text(errors="replace")
    except Exception as e:
        return f"Erreur lecture screens.json: {e}"
    return "Aucune auto-détection écran sauvegardée pour le moment."


def dof_file_status():
    cfg = Path("/home/pinball/.local/share/VPinballX/10.8/directoutputconfig")

    files = [
        "GlobalConfig_B2SServer.xml",
        "cabinet.xml",
        "directoutputconfig.ini",
    ]

    rows = []
    for name in files:
        f = cfg / name
        if f.exists():
            size = f.stat().st_size
            rows.append(
                f'<tr><td><code>{esc(name)}</code></td>'
                f'<td><span class="ok">présent</span></td>'
                f'<td>{size} bytes</td></tr>'
            )
        else:
            rows.append(
                f'<tr><td><code>{esc(name)}</code></td>'
                f'<td><span class="bad">absent</span></td>'
                f'<td>-</td></tr>'
            )

    try:
        extra = sorted(cfg.glob("directoutputconfig*.ini"))
        for f in extra:
            if f.name == "directoutputconfig.ini":
                continue
            rows.append(
                f'<tr><td><code>{esc(f.name)}</code></td>'
                f'<td><span class="ok">présent</span></td>'
                f'<td>{f.stat().st_size} bytes</td></tr>'
            )
    except Exception:
        pass

    return str(cfg), "\n".join(rows)


def detect_dof_devices():
    usb = run_cmd(["bash", "--noprofile", "--norc", "-c", "lsusb 2>/dev/null || true"], timeout=5)
    tty = run_cmd(["bash", "--noprofile", "--norc", "-c", "ls -lah /dev/ttyUSB* /dev/ttyACM* 2>/dev/null || true"], timeout=5)
    hid = run_cmd(["bash", "--noprofile", "--norc", "-c", "ls -lah /dev/hidraw* 2>/dev/null || true"], timeout=5)

    combined = (usb + "\n" + tty + "\n" + hid).lower()

    checks = [
        ("Pinscape / KL25Z / NXP", ["pinscape", "kl25z", "freescale", "nxp", "kinetis"]),
        ("Pinscape Pico / RP2040", ["rp2040", "raspberry pi pico", "pico"]),
        ("Dude's Cab / Wemos / ESP", ["dudescab", "dude", "wemos", "esp32", "esp8266", "ch340", "1a86"]),
        ("PacLed / Ultimarc", ["ultimarc", "pacled", "pac-drive", "pacdrive", "d209"]),
        ("FTDI", ["ftdi", "0403:6001", "0403:6015", "0403:6010"]),
        ("Arduino / Leonardo / Micro", ["arduino", "2341:", "2a03:", "ttyacm"]),
        ("Serial USB détecté", ["ttyusb", "ttyacm"]),
        ("HID raw détecté", ["hidraw"]),
    ]

    found_rows = []
    found_any = False

    for label, patterns in checks:
        matched = any(pat in combined for pat in patterns)
        if matched:
            found_any = True
            found_rows.append(
                f'<tr><td>{esc(label)}</td><td><span class="ok">détecté / probable</span></td></tr>'
            )
        else:
            found_rows.append(
                f'<tr><td>{esc(label)}</td><td><span class="bad">non détecté</span></td></tr>'
            )

    if found_any:
        summary = '<span class="ok">Un ou plusieurs périphériques compatibles/probables ont été détectés.</span>'
    else:
        summary = '<span class="warn">Aucun contrôleur DOF évident détecté par le système.</span>'

    raw = f"""===== lsusb =====
{usb}

===== Serial devices =====
{tty}

===== HID raw devices =====
{hid}
"""
    return summary, "\n".join(found_rows), raw


def dof_logs():
    log = run_cmd(
        [
            "bash",
            "--noprofile",
            "--norc",
            "-c",
            "journalctl -u pincabos-frontend.service -n 260 --no-pager | "
            "grep -iE 'dof|directoutput|global config|cabinet|ini|framework|device|pinscape|pacled|pacdrive|dudes|ftdi|pinone' || true"
        ],
        timeout=8
    )
    return log[-20000:] if log else "Aucun log DOF trouvé."


@app.route("/gpu")
def gpu_page():
    from pathlib import Path

    gpu_text = gpu_info_text()
    screens, raw = pincabos_parse_xrandr_screens()
    roles = pincabos_load_screen_roles()

    def role_select(name, selected):
        html = f'<select name="{name}" style="width:95%; padding:8px; margin:6px 0;">'
        html += '<option value="">-- Aucun --</option>'

        for sc in screens:
            sel = "selected" if str(sc["id"]) == str(selected) else ""
            label = f'ID {sc["id"]} — {sc["name"]} — {sc["width"]}x{sc["height"]}+{sc["x"]}+{sc["y"]}'
            if sc.get("is_primary"):
                label += " — primary X11"
            html += f'<option value="{esc(sc["id"])}" {sel}>{esc(label)}</option>'

        html += "</select>"
        return html

    rows = ""
    for sc in screens:
        rows += f"""
<tr>
  <td><code>{esc(sc["id"])}</code></td>
  <td><strong>{esc(sc["name"])}</strong></td>
  <td>{esc(sc["width"])}x{esc(sc["height"])}</td>
  <td>{esc(sc["x"])},{esc(sc["y"])}</td>
  <td>{'oui' if sc.get("is_primary") else 'non'}</td>
</tr>
"""

    if not rows:
        rows = '<tr><td colspan="5" class="bad">Aucun écran détecté par xrandr. Vérifie que la session X11 est active.</td></tr>'

    screens_json = "{}"
    try:
        cfg = Path("/opt/pincabos/config/screens.json")
        if cfg.exists():
            screens_json = cfg.read_text(errors="replace")
    except Exception as e:
        screens_json = f"Erreur lecture screens.json: {e}"

    vpinfe_buttons = ""
    if "gpu_apply_vpinfe" in globals():
        vpinfe_buttons += """
      <form action="/gpu/apply-vpinfe" method="post" onsubmit="return confirm('Appliquer la configuration écran actuelle à VPinFE ?');">
        <button class="button secondary" type="submit">Appliquer la config à VPinFE</button>
      </form>
"""
    if "gpu_apply_vpx" in globals():
        vpinfe_buttons += """
      <form action="/gpu/apply-vpx" method="post" onsubmit="return confirm('Appliquer la configuration écran actuelle à VPX / VPinballX.ini ?');">
        <button class="button secondary" type="submit">Appliquer la config à VPX</button>
      </form>
"""

    body = f"""
<div class="card" style="margin-top:0;">
  <h2>Écrans détectés</h2>

  <style>
    .pincabos-screen-table-wrap {{
      width: 100%;
      overflow-x: auto;
      margin-top: 10px;
    }}

    .pincabos-screen-table {{
      width: 100%;
      border-collapse: collapse;
      table-layout: fixed;
      font-size: 0.95rem;
    }}

    .pincabos-screen-table th,
    .pincabos-screen-table td {{
      padding: 10px 12px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.12);
      vertical-align: middle;
      white-space: nowrap;
    }}

    .pincabos-screen-table th {{
      color: #ffb000;
      text-align: left;
      font-weight: 700;
    }}

    .pincabos-screen-table th:nth-child(1),
    .pincabos-screen-table td:nth-child(1) {{
      width: 70px;
      text-align: center;
    }}

    .pincabos-screen-table th:nth-child(2),
    .pincabos-screen-table td:nth-child(2) {{
      width: 34%;
      text-align: left;
    }}

    .pincabos-screen-table th:nth-child(3),
    .pincabos-screen-table td:nth-child(3),
    .pincabos-screen-table th:nth-child(4),
    .pincabos-screen-table td:nth-child(4),
    .pincabos-screen-table th:nth-child(5),
    .pincabos-screen-table td:nth-child(5) {{
      text-align: center;
    }}

    .pincabos-screen-table code {{
      display: inline-block;
      min-width: 28px;
      text-align: center;
    }}
  </style>

  <div class="pincabos-screen-table-wrap">
    <table class="pincabos-screen-table">
      <tr>
        <th>ID</th>
        <th>Nom xrandr</th>
        <th>Résolution</th>
        <th>Position X,Y</th>
        <th>Primary X11</th>
      </tr>
      {rows}
    </table>
  </div>
</div>

<div class="grid">
  <div class="card">
    <h2>GPU / Carte vidéo</h2>

    <p>
      Cette section affiche le modèle GPU, le driver actif et les informations utiles
      pour installer ou mettre à jour les pilotes NVIDIA, AMD ou Intel.
    </p>

    <form action="/run-update/gpu" method="post" style="display:inline;">
      <button class="button" type="submit">Installer / mettre à jour les pilotes GPU</button>
    </form>

    <form action="/restart-vpinfe" method="post" style="display:inline;">
      <button class="button secondary" type="submit">Redémarrer VPinFE</button>
    </form>

    <h3 style="margin-top:18px;">Détection GPU / driver</h3>
    <pre>{esc(gpu_text)}</pre>
  </div>

  <div class="card">
    <h2>Assignation écrans</h2>

    <p>
      Sélectionne manuellement quel écran est le
      <strong>Playfield / Primary</strong>, le
      <strong>Backglass / Secondary</strong> et le
      <strong>FullDMD / Tertiary</strong>.
    </p>

    <p class="warn">
      Si le playfield apparaît sur le FullDMD, corrige l’ordre ici,
      applique l’assignation, puis applique à VPinFE et redémarre VPinFE.
    </p>

    <form action="/gpu/apply-screens" method="post" onsubmit="return confirm('Appliquer cette assignation écran à PinCabOS et VPinFE ?');">
      <label>Playfield / Primary</label><br>
      {role_select("playfield", roles.get("playfield", ""))}<br>

      <label>Backglass / Secondary</label><br>
      {role_select("backglass", roles.get("backglass", ""))}<br>

      <label>FullDMD / Tertiary</label><br>
      {role_select("fulldmd", roles.get("fulldmd", ""))}<br>

      <button class="button" type="submit">Appliquer assignation écrans</button>
    </form>

    <div style="margin-top:12px; display:flex; gap:10px; flex-wrap:wrap;">
      {vpinfe_buttons}
    </div>
  </div>
</div>


<div class="grid" style="margin-top:20px;">
  <div class="card">
    <h2>Configuration écran PinCabOS actuelle</h2>
    <p>Source : <code>/opt/pincabos/config/screens.json</code></p>
    <pre>{esc(screens_json)}</pre>
  </div>

  <div class="card">
    <h2>xrandr brut</h2>
    <pre>{esc(raw)}</pre>
  </div>
</div>
"""
    return page("GPU", body)


def pincabos_parse_xrandr_screens():
    """
    Détecte les écrans connectés via xrandr.
    Retourne une liste stable avec id, name, x, y, width, height, primary.
    """
    import subprocess
    import re

    env = os.environ.copy()
    env.setdefault("DISPLAY", ":0")
    env.setdefault("XAUTHORITY", "/home/pinball/.Xauthority")
    env.setdefault("XDG_RUNTIME_DIR", "/run/user/1000")

    cmd = [
        "bash",
        "--noprofile",
        "--norc",
        "-lc",
        "DISPLAY=:0 XAUTHORITY=/home/pinball/.Xauthority xrandr --query"
    ]

    r = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
    text = (r.stdout or "") + "\n" + (r.stderr or "")

    screens = []
    idx = 0

    # Exemples:
    # HDMI-1 connected primary 1920x1080+0+0 ...
    # DP-1 connected 1280x720+1920+0 ...
    pat = re.compile(r'^(?P<name>\S+)\s+connected(?P<primary>\s+primary)?\s+(?P<w>\d+)x(?P<h>\d+)\+(?P<x>-?\d+)\+(?P<y>-?\d+)')

    for line in text.splitlines():
        m = pat.search(line.strip())
        if not m:
            continue

        w = int(m.group("w"))
        h = int(m.group("h"))
        x = int(m.group("x"))
        y = int(m.group("y"))

        screens.append({
            "id": idx,
            "name": m.group("name"),
            "x": x,
            "y": y,
            "width": w,
            "height": h,
            "area": w * h,
            "is_primary": bool(m.group("primary")),
            "raw": line.strip(),
        })
        idx += 1

    return screens, text


def pincabos_load_screen_roles():
    """
    Lit /opt/pincabos/config/screens.json et retourne les ids déjà assignés.
    """
    import json
    from pathlib import Path

    cfg = Path("/opt/pincabos/config/screens.json")
    roles = {"playfield": "", "backglass": "", "fulldmd": ""}

    try:
        data = json.loads(cfg.read_text(errors="replace"))
        for role in roles:
            item = data.get(role)
            if isinstance(item, dict) and "id" in item:
                roles[role] = str(item.get("id"))
    except Exception:
        pass

    return roles


def pincabos_write_manual_screen_roles(playfield_id, backglass_id, fulldmd_id):
    """
    Sauvegarde les rôles écran dans screens.json et met à jour VPinFE [Displays].
    """
    import json
    import subprocess
    from pathlib import Path

    screens, raw = pincabos_parse_xrandr_screens()

    by_id = {str(s["id"]): s for s in screens}

    if playfield_id not in by_id:
        raise ValueError("Playfield invalide ou non sélectionné.")

    playfield = by_id.get(playfield_id)
    backglass = by_id.get(backglass_id) if backglass_id in by_id else None
    fulldmd = by_id.get(fulldmd_id) if fulldmd_id in by_id else None

    layout = {
        "mode": "manual",
        "playfield": playfield,
        "backglass": backglass,
        "fulldmd": fulldmd,
        "all_screens": screens,
        "xrandr_raw": raw,
    }

    cfg = Path("/opt/pincabos/config/screens.json")
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(json.dumps(layout, indent=2, ensure_ascii=False), encoding="utf-8")

    # Mettre à jour VPinFE [Displays] sans toucher au reste.
    ini = Path("/home/pinball/.config/vpinfe/vpinfe.ini")
    lines = ini.read_text(errors="replace").splitlines() if ini.exists() else []

    def set_ini_key(lines, section, key, value):
        section_l = section.lower()
        key_l = key.lower()
        out = []
        in_sec = False
        found_sec = False
        found_key = False

        for line in lines:
            stripped = line.strip()

            if stripped.startswith("[") and stripped.endswith("]"):
                if in_sec and not found_key:
                    out.append(f"{key} = {value}")
                    found_key = True
                in_sec = stripped[1:-1].strip().lower() == section_l
                if in_sec:
                    found_sec = True
                out.append(line)
                continue

            if in_sec and "=" in line:
                k = line.split("=", 1)[0].strip().lower()
                if k == key_l:
                    out.append(f"{key} = {value}")
                    found_key = True
                    continue

            out.append(line)

        if not found_sec:
            if out and out[-1].strip():
                out.append("")
            out.append(f"[{section}]")
            out.append(f"{key} = {value}")
        elif in_sec and not found_key:
            out.append(f"{key} = {value}")

        return out

    lines = set_ini_key(lines, "Displays", "tablescreenid", str(playfield["id"]))

    if backglass:
        lines = set_ini_key(lines, "Displays", "bgscreenid", str(backglass["id"]))
    else:
        lines = set_ini_key(lines, "Displays", "bgscreenid", "")

    if fulldmd:
        lines = set_ini_key(lines, "Displays", "dmdscreenid", str(fulldmd["id"]))
    else:
        lines = set_ini_key(lines, "Displays", "dmdscreenid", "")

    lines = set_ini_key(lines, "Displays", "cabmode", "true")
    lines = set_ini_key(lines, "Displays", "tableorientation", "landscape")
    lines = set_ini_key(lines, "Displays", "tablerotation", "0")

    ini.parent.mkdir(parents=True, exist_ok=True)
    ini.write_text("\n".join(lines) + "\n", encoding="utf-8")

    try:
        subprocess.run(["/bin/chown", "pinball:pinball", str(cfg), str(ini)], timeout=5, check=False)
    except Exception:
        pass

    return layout

@app.route("/gpu/screens")
def gpu_screens_page():
    return redirect(url_for("gpu_page"), code=302)


@app.route("/gpu/apply-screens", methods=["POST"])
def gpu_screens_apply():
    playfield = request.form.get("playfield", "").strip()
    backglass = request.form.get("backglass", "").strip()
    fulldmd = request.form.get("fulldmd", "").strip()

    try:
        layout = pincabos_write_manual_screen_roles(playfield, backglass, fulldmd)
        output = json.dumps(layout, indent=2, ensure_ascii=False)
        cls = "ok"
        msg = "Assignation écran sauvegardée dans screens.json et VPinFE."
    except Exception as e:
        output = str(e)
        cls = "bad"
        msg = "Erreur assignation écran."

    try:
        log_path = Path("/opt/pincabos/logs/gpu-last-action.log")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(msg + "\n\n" + output + "\n", encoding="utf-8")
        subprocess.run(["/bin/chown", "pinball:pinball", str(log_path)], timeout=5, check=False)
    except Exception:
        pass

    return redirect(url_for("gpu_page", gpu_action="screens", gpu_cls=cls, gpu_title=msg), code=303)


def pincabos_gpu_read_screens_config_for_apply():
    import json
    from pathlib import Path

    cfg = Path("/opt/pincabos/config/screens.json")
    if not cfg.exists():
        raise ValueError("screens.json introuvable. Choisis d’abord les écrans dans GPU / Écrans.")

    data = json.loads(cfg.read_text(errors="replace"))

    playfield = data.get("playfield")
    backglass = data.get("backglass")
    fulldmd = data.get("fulldmd")

    if not isinstance(playfield, dict):
        raise ValueError("Playfield absent dans screens.json.")

    if not isinstance(backglass, dict):
        backglass = None

    if not isinstance(fulldmd, dict):
        fulldmd = None

    return data, playfield, backglass, fulldmd


def pincabos_gpu_ini_set_key_local(lines, section, key, value):
    section_l = section.lower()
    key_l = key.lower()

    out = []
    in_sec = False
    found_sec = False
    found_key = False

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("[") and stripped.endswith("]"):
            if in_sec and not found_key:
                out.append(f"{key} = {value}")
                found_key = True

            in_sec = stripped[1:-1].strip().lower() == section_l
            if in_sec:
                found_sec = True

            out.append(line)
            continue

        if in_sec and "=" in line:
            k = line.split("=", 1)[0].strip().lower()
            if k == key_l:
                out.append(f"{key} = {value}")
                found_key = True
                continue

        out.append(line)

    if not found_sec:
        if out and out[-1].strip():
            out.append("")
        out.append(f"[{section}]")
        out.append(f"{key} = {value}")
    elif in_sec and not found_key:
        out.append(f"{key} = {value}")

    return out


def pincabos_gpu_apply_config_to_vpinfe():
    from pathlib import Path
    from datetime import datetime
    import shutil
    import subprocess

    data, playfield, backglass, fulldmd = pincabos_gpu_read_screens_config_for_apply()

    ini = Path("/home/pinball/.config/vpinfe/vpinfe.ini")
    ini.parent.mkdir(parents=True, exist_ok=True)

    backup = ""
    if ini.exists():
        backup = str(ini) + ".backup-screens-" + datetime.now().strftime("%Y%m%d-%H%M%S")
        shutil.copy2(ini, backup)

    lines = ini.read_text(errors="replace").splitlines() if ini.exists() else []

    lines = pincabos_gpu_ini_set_key_local(lines, "Displays", "cabmode", "true")
    lines = pincabos_gpu_ini_set_key_local(lines, "Displays", "tablescreenid", str(playfield.get("id", "")))
    lines = pincabos_gpu_ini_set_key_local(lines, "Displays", "tableorientation", "landscape")
    lines = pincabos_gpu_ini_set_key_local(lines, "Displays", "tablerotation", "0")

    lines = pincabos_gpu_ini_set_key_local(
        lines, "Displays", "bgscreenid",
        str(backglass.get("id", "")) if backglass else ""
    )

    lines = pincabos_gpu_ini_set_key_local(
        lines, "Displays", "dmdscreenid",
        str(fulldmd.get("id", "")) if fulldmd else ""
    )

    lines = pincabos_gpu_ini_set_key_local(lines, "PinCabOs.Screens", "managed_by", "PinCabOS GPU Screens")
    lines = pincabos_gpu_ini_set_key_local(lines, "PinCabOs.Screens", "mode", str(data.get("mode", "manual")))
    lines = pincabos_gpu_ini_set_key_local(lines, "PinCabOs.Screens", "playfield_name", str(playfield.get("name", "")))
    lines = pincabos_gpu_ini_set_key_local(lines, "PinCabOs.Screens", "backglass_name", str(backglass.get("name", "")) if backglass else "")
    lines = pincabos_gpu_ini_set_key_local(lines, "PinCabOs.Screens", "fulldmd_name", str(fulldmd.get("name", "")) if fulldmd else "")

    ini.write_text("\n".join(lines) + "\n", encoding="utf-8")

    subprocess.run(["/bin/chown", "pinball:pinball", str(ini)], timeout=5, check=False)

    return f"""VPinFE appliqué.

Fichier:
{ini}

Backup:
{backup or "aucun, fichier créé"}

Valeurs écrites:
[Displays]
cabmode = true
tablescreenid = {playfield.get("id", "")}
bgscreenid = {backglass.get("id", "") if backglass else ""}
dmdscreenid = {fulldmd.get("id", "") if fulldmd else ""}
tableorientation = landscape
tablerotation = 0
"""


def pincabos_gpu_apply_config_to_vpx():
    from pathlib import Path
    from datetime import datetime
    import shutil
    import subprocess

    data, playfield, backglass, fulldmd = pincabos_gpu_read_screens_config_for_apply()

    ini = Path("/home/pinball/.local/share/VPinballX/10.8/VPinballX.ini")
    ini.parent.mkdir(parents=True, exist_ok=True)

    backup = ""
    if ini.exists():
        backup = str(ini) + ".backup-screens-" + datetime.now().strftime("%Y%m%d-%H%M%S")
        shutil.copy2(ini, backup)

    lines = ini.read_text(errors="replace").splitlines() if ini.exists() else []

    # Section de suivi PinCabOS. On ne force pas encore de clés VPX natives non validées.
    lines = pincabos_gpu_ini_set_key_local(lines, "PinCabOs.Screens", "managed_by", "PinCabOS GPU Screens")
    lines = pincabos_gpu_ini_set_key_local(lines, "PinCabOs.Screens", "mode", str(data.get("mode", "manual")))

    lines = pincabos_gpu_ini_set_key_local(lines, "PinCabOs.Screens", "playfield_id", str(playfield.get("id", "")))
    lines = pincabos_gpu_ini_set_key_local(lines, "PinCabOs.Screens", "playfield_name", str(playfield.get("name", "")))
    lines = pincabos_gpu_ini_set_key_local(
        lines,
        "PinCabOs.Screens",
        "playfield_geometry",
        f'{playfield.get("width")}x{playfield.get("height")}+{playfield.get("x")}+{playfield.get("y")}'
    )

    if backglass:
        lines = pincabos_gpu_ini_set_key_local(lines, "PinCabOs.Screens", "backglass_id", str(backglass.get("id", "")))
        lines = pincabos_gpu_ini_set_key_local(lines, "PinCabOs.Screens", "backglass_name", str(backglass.get("name", "")))
        lines = pincabos_gpu_ini_set_key_local(
            lines,
            "PinCabOs.Screens",
            "backglass_geometry",
            f'{backglass.get("width")}x{backglass.get("height")}+{backglass.get("x")}+{backglass.get("y")}'
        )
    else:
        lines = pincabos_gpu_ini_set_key_local(lines, "PinCabOs.Screens", "backglass_id", "")
        lines = pincabos_gpu_ini_set_key_local(lines, "PinCabOs.Screens", "backglass_name", "")
        lines = pincabos_gpu_ini_set_key_local(lines, "PinCabOs.Screens", "backglass_geometry", "")

    if fulldmd:
        lines = pincabos_gpu_ini_set_key_local(lines, "PinCabOs.Screens", "fulldmd_id", str(fulldmd.get("id", "")))
        lines = pincabos_gpu_ini_set_key_local(lines, "PinCabOs.Screens", "fulldmd_name", str(fulldmd.get("name", "")))
        lines = pincabos_gpu_ini_set_key_local(
            lines,
            "PinCabOs.Screens",
            "fulldmd_geometry",
            f'{fulldmd.get("width")}x{fulldmd.get("height")}+{fulldmd.get("x")}+{fulldmd.get("y")}'
        )

        lines = pincabos_gpu_ini_set_key_local(lines, "PinCabOs.FullDMD", "screenid", str(fulldmd.get("id", "")))
        lines = pincabos_gpu_ini_set_key_local(
            lines,
            "PinCabOs.FullDMD",
            "geometry",
            f'{fulldmd.get("x")},{fulldmd.get("y")},{fulldmd.get("width")},{fulldmd.get("height")}'
        )
        lines = pincabos_gpu_ini_set_key_local(lines, "PinCabOs.FullDMD", "managed_by", "PinCabOS GPU Screens")

    ini.write_text("\n".join(lines) + "\n", encoding="utf-8")

    subprocess.run(["/bin/chown", "pinball:pinball", str(ini)], timeout=5, check=False)

    return f"""VPX / VPinballX.ini appliqué.

Fichier:
{ini}

Backup:
{backup or "aucun, fichier créé"}

Sections écrites:
[PinCabOs.Screens]
[PinCabOs.FullDMD] si FullDMD est sélectionné

Note:
On écrit une section de suivi PinCabOS sécuritaire.
On ne force pas encore de clés natives VPX tant qu’elles ne sont pas validées sur ton build Linux.
"""


@app.route("/gpu/apply-vpinfe", methods=["POST"])
def gpu_apply_vpinfe():
    try:
        output = pincabos_gpu_apply_config_to_vpinfe()
        cls = "ok"
        title = "Configuration appliquée à VPinFE"
    except Exception as e:
        output = f"ERREUR: {e}"
        cls = "bad"
        title = "Erreur application VPinFE"

    body = f"""
<div class="card">
  <h2>{esc(title)}</h2>
  <pre class="{cls}">{esc(output)}</pre>
  <p>
    <a class="button" href="/gpu">Retour GPU / Écrans</a>
    <a class="button secondary" href="/gpu">Retour GPU / Écrans</a>
  </p>
</div>
"""
    return page("GPU", body)


@app.route("/gpu/apply-vpx", methods=["POST"])
def gpu_apply_vpx():
    try:
        output = pincabos_gpu_apply_config_to_vpx()
        cls = "ok"
        title = "Configuration appliquée à VPX"
    except Exception as e:
        output = f"ERREUR: {e}"
        cls = "bad"
        title = "Erreur application VPX"

    body = f"""
<div class="card">
  <h2>{esc(title)}</h2>
  <pre class="{cls}">{esc(output)}</pre>
  <p>
    <a class="button" href="/gpu">Retour GPU / Écrans</a>
    <a class="button secondary" href="/gpu">Retour GPU / Écrans</a>
  </p>
</div>
"""
    return page("GPU", body)


@app.route("/restart-vpinfe", methods=["POST"])
def restart_vpinfe():
    subprocess.Popen(
        ["/usr/bin/sudo", "/bin/systemctl", "restart", "pincabos-frontend.service"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return redirect(url_for("gpu_page"))

@app.route("/auto-screens", methods=["POST"])
def auto_screens():
    subprocess.Popen(
        ["/usr/bin/sudo", "/opt/pincabos/tools/auto-detect-screens.sh"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return redirect(url_for("gpu_page"))


def dof_check_cmd(cmd, timeout=6):
    try:
        r = subprocess.run(
            ["bash", "-lc", cmd],
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return (r.stdout or "").strip()
    except Exception:
        return ""


def dof_pkg_ok(pkg):
    return dof_check_cmd(f"dpkg -s {shlex_quote(pkg)} >/dev/null 2>&1 && echo yes || echo no") == "yes"


def dof_module_ok(module):
    return dof_check_cmd(f"lsmod | awk '{{print $1}}' | grep -qx {shlex_quote(module)} && echo yes || modinfo {shlex_quote(module)} >/dev/null 2>&1 && echo yes || echo no") == "yes"


def dof_udev_ok(pattern):
    return dof_check_cmd(f"grep -qi {shlex_quote(pattern)} /etc/udev/rules.d/99-pincabos-dof-controllers.rules 2>/dev/null && echo yes || echo no") == "yes"


def dof_component_definitions():
    return [
        {
            "key": "ledwiz",
            "name": "LedWiz32",
            "check": [
                ("Package libusb", lambda: dof_pkg_ok("libusb-1.0-0")),
                ("Package HIDAPI", lambda: dof_pkg_ok("libhidapi-hidraw0")),
                ("Module usbhid", lambda: dof_module_ok("usbhid")),
                ("udev LedWiz fafa", lambda: dof_udev_ok("fafa")),
            ],
            "notes": "libusb / hidraw / règles udev"
        },
        {
            "key": "pinscape-kl25z",
            "name": "Pinscape / KL25Z / NXP",
            "check": [
                ("Package libusb", lambda: dof_pkg_ok("libusb-1.0-0")),
                ("Package HIDAPI", lambda: dof_pkg_ok("libhidapi-hidraw0")),
                ("Module usbhid", lambda: dof_module_ok("usbhid")),
                ("udev NXP 15a2/1fc9", lambda: dof_udev_ok("15a2") or dof_udev_ok("1fc9")),
            ],
            "notes": "libusb / hidraw / udev"
        },
        {
            "key": "pinscape-pico",
            "name": "Pinscape Pico / RP2040",
            "check": [
                ("Package libusb", lambda: dof_pkg_ok("libusb-1.0-0")),
                ("Package HIDAPI", lambda: dof_pkg_ok("libhidapi-hidraw0")),
                ("Module usbhid", lambda: dof_module_ok("usbhid")),
                ("Module cdc_acm", lambda: dof_module_ok("cdc_acm")),
                ("udev RP2040 2e8a/1209", lambda: dof_udev_ok("2e8a") or dof_udev_ok("1209")),
            ],
            "notes": "libusb / hidraw / serial"
        },
        {
            "key": "dudes-esp",
            "name": "Dude's Cab / Wemos / ESP",
            "check": [
                ("Package python3-serial", lambda: dof_pkg_ok("python3-serial")),
                ("Module usbserial", lambda: dof_module_ok("usbserial")),
                ("Module ch341", lambda: dof_module_ok("ch341")),
                ("Module cp210x", lambda: dof_module_ok("cp210x")),
                ("udev ESP/CH340/CP210x", lambda: dof_udev_ok("303a") or dof_udev_ok("1a86") or dof_udev_ok("10c4")),
            ],
            "notes": "serial USB / CH340 / CP210x / ESP"
        },
        {
            "key": "pacled",
            "name": "PacLed / Ultimarc",
            "check": [
                ("Package libusb", lambda: dof_pkg_ok("libusb-1.0-0")),
                ("Package HIDAPI", lambda: dof_pkg_ok("libhidapi-hidraw0")),
                ("Module usbhid", lambda: dof_module_ok("usbhid")),
                ("udev Ultimarc d209", lambda: dof_udev_ok("d209")),
            ],
            "notes": "libusb / hidraw / udev"
        },
        {
            "key": "ftdi",
            "name": "FTDI",
            "check": [
                ("Package python3-serial", lambda: dof_pkg_ok("python3-serial")),
                ("Module usbserial", lambda: dof_module_ok("usbserial")),
                ("Module ftdi_sio", lambda: dof_module_ok("ftdi_sio")),
                ("udev FTDI 0403", lambda: dof_udev_ok("0403")),
            ],
            "notes": "serial USB / dialout / udev"
        },
        {
            "key": "arduino",
            "name": "Arduino / Leonardo / Micro",
            "check": [
                ("Package python3-serial", lambda: dof_pkg_ok("python3-serial")),
                ("Module cdc_acm", lambda: dof_module_ok("cdc_acm")),
                ("Module usbhid", lambda: dof_module_ok("usbhid")),
                ("udev Arduino 2341/2a03/1b4f", lambda: dof_udev_ok("2341") or dof_udev_ok("2a03") or dof_udev_ok("1b4f")),
            ],
            "notes": "serial USB / hidraw / udev"
        },
        {
            "key": "serial-usb",
            "name": "Serial USB détecté",
            "check": [
                ("Package python3-serial", lambda: dof_pkg_ok("python3-serial")),
                ("Module usbserial", lambda: dof_module_ok("usbserial")),
                ("Module cdc_acm", lambda: dof_module_ok("cdc_acm")),
                ("Module ch341", lambda: dof_module_ok("ch341")),
                ("Module cp210x", lambda: dof_module_ok("cp210x")),
                ("Module ftdi_sio", lambda: dof_module_ok("ftdi_sio")),
            ],
            "notes": "ttyACM / ttyUSB / serial"
        },
    ]


def dof_component_status_html(component):
    results = []
    ok_count = 0

    for label, fn in component["check"]:
        try:
            ok = bool(fn())
        except Exception:
            ok = False

        if ok:
            ok_count += 1
            results.append(f'<div><span style="color:#2fff7f;">●</span> {esc(label)}</div>')
        else:
            results.append(f'<div><span style="color:#ff3333;">●</span> {esc(label)}</div>')

    total = len(component["check"])
    installed = ok_count == total

    dot = '<span style="color:#2fff7f; font-size:22px;">●</span>' if installed else '<span style="color:#ff3333; font-size:22px;">●</span>'
    state = "installé / prêt" if installed else f"incomplet ({ok_count}/{total})"

    return dot, state, "".join(results)


def dof_utils_card_html():
    rows = []

    for comp in dof_component_definitions():
        dot, state, details = dof_component_status_html(comp)

        rows.append(f"""
        <tr>
          <td>{dot}</td>
          <td>
            <strong>{esc(comp["name"])}</strong><br>
            <small>{esc(comp["notes"])}</small>
          </td>
          <td>{esc(state)}<br><small>{details}</small></td>
          <td style="white-space:nowrap;">
            <form method="post" action="/dof/install-utils/{esc(comp["key"])}" style="display:inline;">
              <button class="button secondary" type="submit">Installer</button>
            </form>
            <a class="button secondary" href="/dof">Vérifier</a>
          </td>
        </tr>
        """)

    return f"""
<div class="card" style="margin-top:20px;">
  <h2>Utilitaires / Drivers DOF</h2>

  <p>
    Installe et vérifie les dépendances Linux nécessaires pour les contrôleurs DOF :
    LedWiz32, Pinscape / KL25Z / NXP, Pinscape Pico / RP2040, Dude's Cab / Wemos / ESP,
    PacLed / Ultimarc, FTDI, Arduino / Leonardo / Micro et Serial USB.
  </p>

  <table style="width:100%; border-collapse:collapse;">
    <tr>
      <th style="text-align:left;">État</th>
      <th style="text-align:left;">Famille</th>
      <th style="text-align:left;">Vérification noyau / paquets / udev</th>
      <th style="text-align:left;">Action</th>
    </tr>
    {''.join(rows)}
  </table>

  <form method="post" action="/dof/install-utils/all" style="margin-top:14px;">
    <button class="button" type="submit">Tout installer / mettre à jour</button>
  </form>

  <p class="warn">
    Après installation : débranche/rebranche les cartes USB ou redémarre PinCabOS.
  </p>
</div>
"""


@app.route("/dof/install-utils", methods=["POST"])
@app.route("/dof/install-utils/<component>", methods=["POST"])
def dof_install_utils(component="all"):
    allowed = {c["key"] for c in dof_component_definitions()}
    allowed.add("all")

    component = (component or "all").strip()

    if component not in allowed:
        component = "all"

    job_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_file = Path(f"/opt/pincabos/logs/dof-utils-install-{component}-{job_id}.log")
    script = "/opt/pincabos/tools/install-dof-component.sh"

    cmd = f"sudo {script} {shlex_quote(component)} > {log_file} 2>&1"

    subprocess.Popen(
        ["bash", "-lc", cmd],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True
    )

    body = f"""
<div class="card">
  <h2>Installation DOF lancée</h2>
  <p class="ok">Installation / mise à jour lancée pour : <code>{esc(component)}</code></p>

  <table>
    <tr><td>Script</td><td><code>{esc(script)}</code></td></tr>
    <tr><td>Composant</td><td><code>{esc(component)}</code></td></tr>
    <tr><td>Log</td><td><code>{esc(log_file)}</code></td></tr>
    <tr><td>Règles udev</td><td><code>/etc/udev/rules.d/99-pincabos-dof-controllers.rules</code></td></tr>
  </table>

  <p>
    <a class="button" href="/dof">Retour DOF / Vérifier</a>
    <a class="button secondary" href="/tools/commander">Ouvrir Commander</a>
  </p>

  <p class="warn">
    Après l’installation, débranche/rebranche les cartes USB ou redémarre PinCabOS.
  </p>
</div>
"""
    return page("Outputs", body)


def dof_simple_cmd(cmd, timeout=6):
    try:
        r = subprocess.run(
            ["bash", "-lc", cmd],
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return (r.stdout or "").strip()
    except Exception:
        return ""


def dof_usb_present(vendors):
    if isinstance(vendors, str):
        vendors = [vendors]
    raw = dof_simple_cmd("lsusb || true")
    raw_l = raw.lower()
    return any(v.lower() in raw_l for v in vendors)


def dof_path_exists(path):
    return Path(path).exists()


def dof_support_ready(kind):
    udev = Path("/etc/udev/rules.d/99-pincabos-dof-controllers.rules").exists()

    libusb_ok = dof_simple_cmd(
        "dpkg -s libusb-1.0-0 >/dev/null 2>&1 && "
        "dpkg -s libhidapi-hidraw0 >/dev/null 2>&1 && echo yes || echo no"
    ) == "yes"

    serial_ok = dof_simple_cmd(
        "dpkg -s python3-serial >/dev/null 2>&1 && echo yes || echo no"
    ) == "yes"

    # Après installation, PinCabOS prépare aussi /opt/pincabos/apps/dof-tools/<famille>.
    # Si la famille est prête côté dossier + udev, on considère le support prêt.
    if kind in ["serial", "dudes-esp", "ftdi", "arduino", "serial-usb"]:
        return udev and serial_ok

    return udev and libusb_ok


def dof_configurator_status(kind):
    base = Path("/opt/pincabos/apps/dof-tools") / kind
    if not base.exists():
        return "non installé", False

    # Pour l’instant, dossier préparé = installé côté PinCabOS.
    return "préparé", True


def dof_status_badge(ok, good="actif", bad="non détecté"):
    if ok:
        return f'<span style="color:#2fff7f;font-weight:bold;">● {esc(good)}</span>'
    return f'<span style="color:#ff3333;font-weight:bold;">● {esc(bad)}</span>'


def dof_manager_families():
    return [
        {
            "key": "ledwiz",
            "name": "LedWiz32",
            "vendors": ["fafa"],
            "support_kind": "hid",
            "configurator": "Outils USB/HID PinCabOS"
        },
        {
            "key": "pinscape-kl25z",
            "name": "Pinscape / KL25Z / NXP",
            "vendors": ["15a2", "1fc9"],
            "support_kind": "hid",
            "configurator": "Dossier configurateur Pinscape"
        },
        {
            "key": "pinscape-pico",
            "name": "Pinscape Pico / RP2040",
            "vendors": ["2e8a", "1209"],
            "support_kind": "hid",
            "configurator": "Dossier configurateur Pico"
        },
        {
            "key": "dudes-esp",
            "name": "Dude's Cab / Wemos / ESP",
            "vendors": ["303a", "1a86", "10c4"],
            "support_kind": "serial",
            "configurator": "Dossier configurateur Dude's Cab"
        },
        {
            "key": "pacled",
            "name": "PacLed / Ultimarc",
            "vendors": ["d209"],
            "support_kind": "hid",
            "configurator": "Outils USB/HID PinCabOS"
        },
        {
            "key": "ftdi",
            "name": "FTDI",
            "vendors": ["0403"],
            "support_kind": "serial",
            "configurator": "Outils serial"
        },
        {
            "key": "arduino",
            "name": "Arduino / Leonardo / Micro",
            "vendors": ["2341", "2a03", "1b4f"],
            "support_kind": "serial",
            "configurator": "Outils serial/HID"
        },
        {
            "key": "serial-usb",
            "name": "Serial USB",
            "vendors": ["0403", "10c4", "1a86", "303a", "2341", "2a03", "1b4f"],
            "support_kind": "serial",
            "configurator": "Outils serial génériques"
        },
    ]


def dof_simple_manager_card_friendly():
    rows = []

    for fam in dof_manager_families():
        detected = dof_usb_present(fam["vendors"])
        support = dof_support_ready(fam["key"]) or dof_support_ready(fam["support_kind"])

        hardware_html = dof_status_badge(detected, "détecté", "non détecté")
        support_html = dof_status_badge(support, "prêt", "à installer")

        if detected and support:
            status_hint = '<span class="ok">Actif et prêt</span>'
        elif support:
            status_hint = '<span class="warn">Support prêt, carte non branchée</span>'
        else:
            status_hint = '<span class="bad">Support à installer</span>'

        key = esc(fam["key"])

        rows.append(f"""
        <tr>
          <td>
            <strong>{esc(fam["name"])}</strong><br>
            {status_hint}
          </td>
          <td>{hardware_html}</td>
          <td>{support_html}</td>
          <td style="white-space:nowrap;">
            <button class="button secondary dof-live-btn" type="button" data-action="install" data-family="{key}">
              Installer / réparer
            </button>
          </td>
        </tr>
        """)

    html = """
<div class="card" style="margin-top:20px;">
  <h2>Gestionnaire DOF automatique</h2>

  <p>
    PinCabOS détecte les cartes branchées et prépare automatiquement le support Linux nécessaire :
    USB, HID, Serial, permissions et règles udev.
  </p>

  <table style="width:100%; border-collapse:collapse;">
    <tr>
      <th style="text-align:left;">Périphérique</th>
      <th style="text-align:left;">Matériel</th>
      <th style="text-align:left;">Support PinCabOS</th>
      <th style="text-align:left;">Action</th>
    </tr>
    __ROWS__
  </table>

  <p style="margin-top:14px;">
    <button class="button dof-live-btn" type="button" data-action="install" data-family="all">
      Installer / préparer tout
    </button>
  </p>

  <p class="warn">
    Le matériel reste rouge tant qu’aucune vraie carte n’est branchée.
    Le support PinCabOS doit devenir vert après installation des dépendances et règles udev.
  </p>

  <div id="dof-live-panel" class="card" style="margin-top:18px; display:none; border-color:#ffb000;">
    <h2>Installation DOF en direct</h2>

    <table>
      <tr><td>Composant</td><td><code id="dof-live-family">-</code></td></tr>
      <tr><td>Action</td><td><code id="dof-live-action">-</code></td></tr>
      <tr><td>Commande</td><td><code id="dof-live-command">-</code></td></tr>
      <tr><td>Log</td><td><code id="dof-live-logfile">-</code></td></tr>
    </table>

    <p id="dof-live-status" class="warn">En attente...</p>

    <pre id="dof-live-log" style="max-height:420px; overflow:auto; background:#050007; border:1px solid #5f2a91; border-radius:12px; padding:12px;">Aucune commande lancée.</pre>

    <p>
      <a class="button secondary" href="/dof">Vérifier / rafraîchir DOF</a>
    </p>
  </div>


<script>
function pcoUserBallSetPreview(imgId, url) {
  const img = document.getElementById(imgId);
  const empty = document.getElementById(imgId + "-empty");
  if (!img) return;

  if (url) {
    img.onload = function() {
      img.style.display = "block";
      if (empty) empty.style.display = "none";
    };
    img.onerror = function() {
      img.removeAttribute("src");
      img.style.display = "none";
      if (empty) {
        empty.style.display = "block";
        empty.textContent = "Aperçu indisponible";
      }
    };
    img.src = url;
  } else {
    img.removeAttribute("src");
    img.style.display = "none";
    if (empty) {
      empty.style.display = "block";
      empty.textContent = "Aperçu";
    }
  }
}

function pcoUserBallPreview(selectId, imgId) {
  const sel = document.getElementById(selectId);
  if (!sel) return;

  const opt = sel.options[sel.selectedIndex];
  const url = opt ? (opt.getAttribute("data-url") || "") : "";

  if (url) {
    pcoUserBallSetPreview(imgId, url + "?v=" + Date.now());
  } else {
    pcoUserBallSetPreview(imgId, "");
  }
}

function pcoUserBallUploadPreview(input, imgId) {
  if (!input || !input.files || !input.files[0]) {
    return;
  }

  const file = input.files[0];
  const url = URL.createObjectURL(file);
  pcoUserBallSetPreview(imgId, url);
}

document.addEventListener("DOMContentLoaded", function() {
  pcoUserBallPreview("pco-ball-existing", "pco-ball-preview");
  pcoUserBallPreview("pco-decal-existing", "pco-decal-preview");
});
</script>

  
<script>
function pcoUserBallSetPreview(imgId, url) {
  const img = document.getElementById(imgId);
  const empty = document.getElementById(imgId + "-empty");
  if (!img) return;

  if (!url) {
    img.removeAttribute("src");
    img.style.display = "none";
    if (empty) {
      empty.style.display = "block";
      empty.textContent = "Aperçu";
    }
    return;
  }

  img.onload = function() {
    img.style.display = "block";
    if (empty) empty.style.display = "none";
  };

  img.onerror = function() {
    img.removeAttribute("src");
    img.style.display = "none";
    if (empty) {
      empty.style.display = "block";
      empty.textContent = "Aperçu indisponible";
    }
  };

  img.src = url;
}

function pcoUserBallPreview(selectId, imgId) {
  const sel = document.getElementById(selectId);
  if (!sel) return;

  const opt = sel.options[sel.selectedIndex];
  const url = opt ? (opt.getAttribute("data-url") || "") : "";

  if (url) {
    pcoUserBallSetPreview(imgId, url + "?v=" + Date.now());
  } else {
    pcoUserBallSetPreview(imgId, "");
  }
}

function pcoUserBallUploadPreview(input, imgId) {
  if (!input || !input.files || !input.files[0]) return;
  const file = input.files[0];
  const url = URL.createObjectURL(file);
  pcoUserBallSetPreview(imgId, url);
}

document.addEventListener("DOMContentLoaded", function() {
  pcoUserBallPreview("pco-ball-existing", "pco-ball-preview");
  pcoUserBallPreview("pco-decal-existing", "pco-decal-preview");
});
</script>

<details style="margin-top:12px;">
    <summary>Notes sur les configurateurs</summary>
    <p>
      Certains configurateurs, comme Dude’s Cab Configurator, sont des outils Windows.
      PinCabOS préparera le support Linux et pourra plus tard lancer ces outils localement via Wine,
      mais ils ne s’ouvrent pas directement dans la page Web.
    </p>
  </details>
</div>

<script>
(function() {
  let dofPollTimer = null;

  async function pollDofLog(logUrl) {
    try {
      const r = await fetch(logUrl + '?t=' + Date.now());
      const data = await r.json();

      const logBox = document.getElementById('dof-live-log');
      const status = document.getElementById('dof-live-status');

      logBox.textContent = data.log || 'Log vide...';
      logBox.scrollTop = logBox.scrollHeight;

      if (data.done) {
        status.textContent = 'Installation terminée ou arrêtée. Clique “Vérifier / rafraîchir DOF” pour mettre à jour les statuts.';
        status.className = 'ok';
        if (dofPollTimer) {
          clearInterval(dofPollTimer);
          dofPollTimer = null;
        }
      } else {
        status.textContent = 'Installation en cours...';
        status.className = 'warn';
      }
    } catch (e) {
      const status = document.getElementById('dof-live-status');
      status.textContent = 'Erreur lecture log : ' + e;
      status.className = 'bad';
    }
  }

  async function startDofAction(action, family) {
    const panel = document.getElementById('dof-live-panel');
    const logBox = document.getElementById('dof-live-log');
    const status = document.getElementById('dof-live-status');

    panel.style.display = 'block';
    document.getElementById('dof-live-family').textContent = family;
    document.getElementById('dof-live-action').textContent = action;
    document.getElementById('dof-live-command').textContent = 'Préparation...';
    document.getElementById('dof-live-logfile').textContent = '-';

    status.textContent = 'Lancement de la commande...';
    status.className = 'warn';
    logBox.textContent = 'Lancement...';

    panel.scrollIntoView({ behavior: 'smooth', block: 'start' });

    try {
      const r = await fetch('/api/dof/manager/' + encodeURIComponent(action) + '/' + encodeURIComponent(family), {
        method: 'POST',
        headers: { 'Cache-Control': 'no-cache' }
      });
      const data = await r.json();

      if (!data.ok) {
        status.textContent = 'Erreur au lancement.';
        status.className = 'bad';
        logBox.textContent = JSON.stringify(data, null, 2);
        return;
      }

      document.getElementById('dof-live-command').textContent = data.command || '-';
      document.getElementById('dof-live-logfile').textContent = data.log_file || '-';

      if (dofPollTimer) clearInterval(dofPollTimer);
      await pollDofLog(data.log_url);
      dofPollTimer = setInterval(function() {
        pollDofLog(data.log_url);
      }, 1500);

    } catch (e) {
      status.textContent = 'Erreur lancement : ' + e;
      status.className = 'bad';
      logBox.textContent = String(e);
    }
  }

  document.querySelectorAll('.dof-live-btn').forEach(function(btn) {
    btn.addEventListener('click', function() {
      const action = btn.getAttribute('data-action') || 'install';
      const family = btn.getAttribute('data-family') || 'all';
      startDofAction(action, family);
    });
  });
})();
</script>
"""
    return html.replace("__ROWS__", "".join(rows))


def dof_detection_summary_card(summary, raw_devices, logs, file_rows):
    usb_count = dof_simple_cmd("lsusb | grep -vc 'root hub' || true")
    hid_count = dof_simple_cmd("ls /dev/hidraw* 2>/dev/null | wc -l || true")
    serial_count = dof_simple_cmd("ls /dev/ttyACM* /dev/ttyUSB* 2>/dev/null | wc -l || true")

    return f"""
<div class="grid" style="margin-top:20px;">
  <div class="card">
    <h2>Résumé détection DOF</h2>
    <p>État : {summary}</p>
    <table>
      <tr><td>USB non-root détectés</td><td><code>{esc(usb_count)}</code></td></tr>
      <tr><td>HID raw</td><td><code>{esc(hid_count)}</code></td></tr>
      <tr><td>Serial USB</td><td><code>{esc(serial_count)}</code></td></tr>
    </table>
  </div>

  <div class="card">
    <h2>Chemins DOF</h2>
    <table style="width:100%; border-collapse:collapse;">
      <tr><th style="text-align:left;">Fichier</th><th style="text-align:left;">État</th><th style="text-align:left;">Taille</th></tr>
      {file_rows}
    </table>
  </div>
</div>

<div class="card" style="margin-top:20px;">
  <h2>Détails techniques DOF</h2>

  <details>
    <summary>Périphériques bruts USB / HID / Serial</summary>
    <pre>{esc(raw_devices)}</pre>
  </details>

  <details style="margin-top:12px;">
    <summary>Logs DOF / VPinFE</summary>
    <pre>{esc(logs)}</pre>
  </details>

  <details style="margin-top:12px;">
    <summary>Informations utiles</summary>
    <p>
      Dossier outils : <code>/opt/pincabos/apps/dof-tools</code><br>
      Règles udev : <code>/etc/udev/rules.d/99-pincabos-dof-controllers.rules</code><br>
      Log actions : <code>/opt/pincabos/logs/dof-manager-action.log</code>
    </p>
  </details>
</div>
"""


def dof_simple_manager_card():
    rows = []
    for fam in dof_manager_families():
        detected = dof_usb_present(fam["vendors"])
        support = dof_support_ready(fam["support_kind"])
        cfg_label, cfg_ok = dof_configurator_status(fam["key"])

        hardware_html = dof_status_badge(detected, "détecté", "non détecté")
        support_html = dof_status_badge(support, "prêt", "à installer")
        cfg_html = dof_status_badge(cfg_ok, cfg_label, "non installé")

        key = esc(fam["key"])

        rows.append(f"""
        <tr>
          <td><strong>{esc(fam["name"])}</strong><br><small>{esc(fam["configurator"])}</small></td>
          <td>{hardware_html}</td>
          <td>{support_html}</td>
          <td>{cfg_html}</td>
          <td style="white-space:nowrap;">
            <form method="post" action="/dof/manager/install/{key}" style="display:inline;">
              <button class="button secondary" type="submit">Installer</button>
            </form>
            <form method="post" action="/dof/manager/update/{key}" style="display:inline;">
              <button class="button secondary" type="submit">Mettre à jour</button>
            </form>
            <form method="post" action="/dof/manager/reinstall/{key}" style="display:inline;">
              <button class="button secondary" type="submit">Réinstaller</button>
            </form>
          </td>
        </tr>
        """)

    return f"""
<div class="card" style="margin-top:20px;">
  <h2>Gestionnaire DOF automatique</h2>

  <p>
    PinCabOS détecte les périphériques branchés, prépare les ressources nécessaires
    et installe le dossier/utilitaire de configuration correspondant quand disponible.
  </p>

  <table style="width:100%; border-collapse:collapse;">
    <tr>
      <th style="text-align:left;">Famille</th>
      <th style="text-align:left;">Matériel</th>
      <th style="text-align:left;">Support système</th>
      <th style="text-align:left;">Configurateur</th>
      <th style="text-align:left;">Actions</th>
    </tr>
    {''.join(rows)}
  </table>

  <form method="post" action="/dof/manager/install/all" style="margin-top:14px;">
    <button class="button" type="submit">Installer / préparer tout</button>
  </form>

  <p class="warn">
    Vert = prêt côté PinCabOS. Pour le matériel, vert seulement si le périphérique est réellement branché et visible par Linux.
  </p>

  <p>
    Dossier outils : <code>/opt/pincabos/apps/dof-tools</code><br>
    Règles udev : <code>/etc/udev/rules.d/99-pincabos-dof-controllers.rules</code><br>
    Log : <code>/opt/pincabos/logs/dof-manager-action.log</code>
  </p>
</div>
"""


@app.route("/dof/manager/<action>/<family>", methods=["POST"])
def dof_manager_action(action, family):
    return redirect(url_for("dof_page"))


PINCABOS_DOF_API_KEY_FILE = Path("/opt/pincabos/config/dof/configtool-api-key.txt")

def pincabos_dof_get_saved_api_key():
    try:
        return PINCABOS_DOF_API_KEY_FILE.read_text(errors="replace").strip()
    except Exception:
        return ""

def pincabos_dof_save_api_key(api_key):
    api_key = (api_key or "").strip()
    if not api_key:
        return
    try:
        PINCABOS_DOF_API_KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
        PINCABOS_DOF_API_KEY_FILE.write_text(api_key + "\n")
        os.chmod(PINCABOS_DOF_API_KEY_FILE, 0o600)
        try:
            shutil.chown(str(PINCABOS_DOF_API_KEY_FILE), user="pinball", group="pinball")
        except Exception:
            pass
    except Exception as e:
        try:
            app.logger.warning("Unable to save DOF API key: %s", e)
        except Exception:
            pass


DOF_CONFIG_DIRS = [
    Path("/home/pinball/.local/share/VPinballX/10.8/directoutputconfig"),
    Path("/opt/pincabos/config/dof"),
    Path("/opt/pincabos/vpinball/directoutputconfig"),
]


def dof_commander_find_configs():
    files = []

    for base in DOF_CONFIG_DIRS:
        if not base.exists():
            continue

        for pattern in ["*.xml", "*.ini", "*.cab", "*.json"]:
            for f in base.glob(pattern):
                if f.is_file():
                    files.append(f)

    return sorted(set(files), key=lambda p: str(p).lower())


def dof_commander_read_text(path):
    try:
        return Path(path).read_text(errors="replace")
    except Exception:
        return ""


def dof_commander_parse_xml_outputs(path):
    import xml.etree.ElementTree as ET

    outputs = []
    controllers = set()

    try:
        root = ET.parse(path).getroot()
    except Exception as e:
        return [], [], f"Erreur XML: {e}"

    # Recherche large : DOF XML peut avoir plusieurs structures.
    # On extrait tout élément qui ressemble à Controller / Toy / Output.
    for elem in root.iter():
        tag = elem.tag.split("}")[-1].lower()
        attrs = {k.lower(): v for k, v in elem.attrib.items()}

        if "controller" in tag or "ledwiz" in tag or "pacled" in tag or "pinscape" in tag:
            name = attrs.get("name") or attrs.get("id") or attrs.get("number") or elem.tag
            controllers.add(str(name))

        if any(word in tag for word in ["output", "toy", "led", "contact", "flasher", "solenoid"]):
            name = attrs.get("name") or attrs.get("id") or attrs.get("number") or attrs.get("output") or elem.tag
            number = attrs.get("number") or attrs.get("output") or attrs.get("led") or attrs.get("id") or ""
            controller = attrs.get("controller") or attrs.get("ledwiznumber") or attrs.get("device") or ""

            text_value = (elem.text or "").strip()
            outputs.append({
                "source": str(path),
                "type": elem.tag.split("}")[-1],
                "name": str(name),
                "number": str(number),
                "controller": str(controller),
                "value": text_value[:120],
            })

    return sorted(controllers), outputs, ""


def dof_commander_parse_ini_outputs(path):
    outputs = []
    controllers = set()

    raw = dof_commander_read_text(path)
    for idx, line in enumerate(raw.splitlines(), start=1):
        s = line.strip()
        if not s or s.startswith("#") or s.startswith(";"):
            continue

        # directoutputconfig.ini est souvent table=value,value,value...
        if "=" in s:
            key, value = s.split("=", 1)
            key = key.strip()
            value = value.strip()

            # Crée un résumé par table/config, pas 300 colonnes détaillées.
            outputs.append({
                "source": str(path),
                "type": "INI",
                "name": key,
                "number": str(idx),
                "controller": "directoutputconfig",
                "value": value[:160],
            })
            controllers.add("directoutputconfig")

    return sorted(controllers), outputs, ""


def dof_commander_load_inventory():
    configs = dof_commander_find_configs()

    all_controllers = set()
    all_outputs = []
    errors = []

    for f in configs:
        suffix = f.suffix.lower()

        if suffix == ".xml":
            controllers, outputs, err = dof_commander_parse_xml_outputs(f)
        elif suffix == ".ini":
            controllers, outputs, err = dof_commander_parse_ini_outputs(f)
        else:
            controllers, outputs, err = [], [], ""

        for c in controllers:
            all_controllers.add(c)

        all_outputs.extend(outputs)

        if err:
            errors.append(f"{f}: {err}")

    return configs, sorted(all_controllers), all_outputs, errors


def dof_commander_devices_summary():
    raw_usb = dof_simple_cmd("lsusb || true")
    raw_hid = dof_simple_cmd("ls -l /dev/hidraw* 2>/dev/null || true")
    raw_serial = dof_simple_cmd("ls -l /dev/ttyACM* /dev/ttyUSB* 2>/dev/null || true")

    devices = []

    vendor_map = [
        ("LedWiz32", ["fafa"]),
        ("PacLed / Ultimarc", ["d209"]),
        ("Pinscape / KL25Z / NXP", ["15a2", "1fc9"]),
        ("Pinscape Pico / RP2040", ["2e8a", "1209"]),
        ("Dude's Cab / Wemos / ESP", ["303a", "1a86", "10c4"]),
        ("FTDI", ["0403"]),
        ("Arduino / Leonardo / Micro", ["2341", "2a03", "1b4f"]),
    ]

    raw_l = raw_usb.lower()

    for name, vendors in vendor_map:
        found = any(v in raw_l for v in vendors)
        devices.append({
            "name": name,
            "found": found,
            "vendors": ", ".join(vendors),
        })

    return devices, raw_usb, raw_hid, raw_serial


PINCABOS_DOF_CABINET_DIR = Path("/opt/pincabos/config/dof/cabinets")
PINCABOS_DOF_ACTIVE_CABINET = Path("/opt/pincabos/config/dof/active-cabinet.txt")


def dof_commander_get_active_cabinet_json_path_pcb():
    PINCABOS_DOF_CABINET_DIR.mkdir(parents=True, exist_ok=True)

    # Source prioritaire : pointeur actif.
    if PINCABOS_DOF_ACTIVE_CABINET.exists():
        raw = PINCABOS_DOF_ACTIVE_CABINET.read_text(errors="replace").strip()
        if raw:
            p = Path(raw)
            if p.exists() and p.suffix.lower() == ".json":
                return p

    # Fallback : dernier JSON importé avec nom original.
    candidates = sorted(
        PINCABOS_DOF_CABINET_DIR.glob("*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True
    )

    if candidates:
        return candidates[0]

    # Ancien fallback : ancien cabinet.json, si encore présent.
    old = Path("/opt/pincabos/config/dof/cabinet.json")
    if old.exists():
        return old

    return None


def dof_commander_load_cabinet_json_pcb():
    p = dof_commander_get_active_cabinet_json_path_pcb()

    if not p:
        return None, "Aucun cabinet JSON importé."

    try:
        raw = p.read_text(errors="replace").strip()
        data = json.loads(raw)
        return data, ""
    except Exception as e:
        return None, f"Erreur lecture JSON cabinet actif {p}: {e}"


def dof_commander_inventory_from_cabinet_json_pcb(data):
    cabinet_name = str(data.get("name") or data.get("Name") or "Cabinet sans nom")

    controllers = []
    outputs = []

    combos = data.get("combos") or {}
    devices = data.get("devices") or []

    if isinstance(devices, dict):
        devices = list(devices.values())

    def device_type_from_controller_id(controller_id, dev_name):
        cid = str(controller_id)
        name_l = str(dev_name).lower()

        if cid == "1" or "ledwiz" in name_l:
            return "LedWiz"
        if cid == "30" or "ws2811" in name_l or "ws2812" in name_l:
            return "Addressable LED / MX"
        if cid == "90" or "dude" in name_l:
            return "Dude's Cab"
        return f"Controller {cid}"

    def combo_label(toy_id):
        toy_key = str(toy_id)

        if toy_key in combos and isinstance(combos[toy_key], dict):
            combo = combos[toy_key]
            combo_name = combo.get("name") or combo.get("Name") or f"Combo {toy_id}"
            combo_toys = combo.get("toys") or []

            if combo_toys:
                return f"Combo {toy_id} — {combo_name} / toys={combo_toys}"

            return f"Combo {toy_id} — {combo_name}"

        return f"Toy ID {toy_id}"

    for dev in devices:
        if not isinstance(dev, dict):
            continue

        dev_name = str(dev.get("name") or dev.get("Name") or "Device")
        controller_id = dev.get("controller_id") or dev.get("ControllerId") or dev.get("id") or ""
        total_outputs = dev.get("outputs") or dev.get("Outputs") or ""
        assignments = dev.get("assignments") or dev.get("Assignments") or {}

        if not isinstance(assignments, dict):
            assignments = {}

        device_type = device_type_from_controller_id(controller_id, dev_name)
        assigned_count = len(assignments)

        controllers.append(
            f"{dev_name} — {device_type} — controller_id={controller_id}, outputs={total_outputs}, assignés={assigned_count}"
        )

        outputs.append({
            "source": "cabinet-json-original",
            "type": "Device Summary",
            "name": dev_name,
            "number": "",
            "controller": dev_name,
            "value": f"{device_type} / controller_id={controller_id} / outputs={total_outputs} / assignés={assigned_count}",
            "testable": False,
            "device_name": dev_name,
            "device_type": device_type,
            "controller_id": str(controller_id),
            "local_output": "",
            "assigned_toy": "",
        })

        if not assignments:
            outputs.append({
                "source": "cabinet-json-original",
                "type": "No Assignment",
                "name": f"{dev_name} — aucun toy assigné",
                "number": "",
                "controller": dev_name,
                "value": f"{device_type} présent dans le JSON, mais aucun output assigné",
                "testable": False,
                "device_name": dev_name,
                "device_type": device_type,
                "controller_id": str(controller_id),
                "local_output": "",
                "assigned_toy": "",
            })
            continue

        for local_output, toy_id in sorted(assignments.items(), key=lambda kv: int(kv[0]) if str(kv[0]).isdigit() else str(kv[0])):
            label = combo_label(toy_id)

            outputs.append({
                "source": "cabinet-json-original",
                "type": "Physical Output",
                "name": label,
                "number": str(local_output),
                "controller": dev_name,
                "value": f"{device_type} / controller_id={controller_id} / output local={local_output} / toy={toy_id}",
                "testable": True,
                "device_name": dev_name,
                "device_type": device_type,
                "controller_id": str(controller_id),
                "local_output": str(local_output),
                "assigned_toy": str(toy_id),
            })

    return cabinet_name, controllers, outputs


def dof_commander_load_inventory_active_pcb():
    configs = dof_commander_find_configs()
    errors = []

    active_path = dof_commander_get_active_cabinet_json_path_pcb()
    data, err = dof_commander_load_cabinet_json_pcb()

    if data:
        cabinet_name, controllers, outputs = dof_commander_inventory_from_cabinet_json_pcb(data)
        source = str(active_path) if active_path else "cabinet json"
        return configs, controllers, outputs, errors, source, cabinet_name

    errors.append(err)

    # Important : on ne retombe plus sur directoutputconfig.ini pour les tests.
    return configs, [], [], errors, "aucun cabinet JSON actif", "Cabinet non importé"


@app.route("/dof/import-api", methods=["POST"])
def dof_import_api_pincabos():
    import subprocess

    submitted_api_key = (request.form.get("apikey") or "").strip()
    saved_api_key = pincabos_dof_get_saved_api_key()
    api_key = submitted_api_key or saved_api_key
    force = "force" if request.form.get("force") == "1" else "noforce"

    if submitted_api_key:
        pincabos_dof_save_api_key(submitted_api_key)

    if not api_key:
        body = """
<div class="card">
  <h2>Import DOF via API échoué</h2>
  <p class="warn">La clé API est vide.</p>
  <p><a class="button" href="/dof">Retour DOF</a></p>
</div>
"""
        return page("DOF", body)

    try:
        cmd = ["/usr/local/sbin/pincabos-dof-online-api-import", api_key, force]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=420)

        ok = proc.returncode == 0
        status = "Import DOF via API terminé" if ok else "Import DOF via API échoué"
        cls = "" if ok else "warn"
        safe_cmd = "/usr/local/sbin/pincabos-dof-online-api-import ****** " + force
        out = esc(proc.stdout or "")

        body = f"""
<div class="card">
  <h2>{esc(status)}</h2>
  <p class="{cls}">Commande : <code>{esc(safe_cmd)}</code></p>
  <pre style="max-height:560px; overflow:auto; background:#050007; border:1px solid #5f2a91; border-radius:12px; padding:12px;">{out}</pre>
  <p><a class="button" href="/dof">Retour DOF</a></p>
</div>
"""
        return page("DOF", body)

    except Exception as e:
        body = f"""
<div class="card">
  <h2>Import DOF via API échoué</h2>
  <p class="warn">{esc(str(e))}</p>
  <p><a class="button" href="/dof">Retour DOF</a></p>
</div>
"""
        return page("DOF", body)

@app.route("/dof/import-config", methods=["POST"])
def dof_import_config():
    import zipfile
    import shutil
    import traceback
    from werkzeug.utils import secure_filename

    target_dir = Path("/home/pinball/.local/share/VPinballX/10.8/directoutputconfig")
    upload_dir = Path("/opt/pincabos/uploads/dof")
    backup_dir = Path("/opt/pincabos/backups/dof-import")
    log_dir = Path("/opt/pincabos/logs")

    target_dir.mkdir(parents=True, exist_ok=True)
    upload_dir.mkdir(parents=True, exist_ok=True)
    backup_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_file = log_dir / f"dof-import-{stamp}.log"

    def log(line):
        with log_file.open("a", encoding="utf-8") as f:
            f.write(str(line) + "\n")

    def response_card(title, message, ok=False, extra=""):
        css = "ok" if ok else "bad"
        body = f"""
<div class="card">
  <h2>{esc(title)}</h2>
  <p class="{css}">{message}</p>

  {extra}

  <p>Log import : <code>{esc(str(log_file))}</code></p>

  <p>
    <a class="button" href="/dof/commander">Retour DOF Commander</a>
    <a class="button secondary" href="/dof">Retour DOF</a>
  </p>
</div>
"""
        return page("DOF Commander", body)

    try:
        log("==================================================")
        log(f"# Modifié {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} par PinCabOS fonction(DOF Import Config Tool)")
        log("Import configuration DOF Config Tool")
        log("==================================================")

        log(f"request.files keys = {list(request.files.keys())}")

        upload_key = None
        if "dof_file" in request.files:
            upload_key = "dof_file"
        elif "dofzip" in request.files:
            # Compatibilité avec ancien formulaire PinCabOS.
            upload_key = "dofzip"
        elif len(request.files.keys()) > 0:
            # Fallback safe : premier fichier envoyé.
            upload_key = list(request.files.keys())[0]

        if not upload_key:
            log("ERREUR: aucun fichier uploadé.")
            return response_card("Import DOF", "Aucun fichier reçu. Le champ attendu est <code>dof_file</code>.", ok=False)

        log(f"Champ upload utilisé : {upload_key}")
        uploaded = request.files[upload_key]

        if uploaded is None or not uploaded.filename:
            log("ERREUR: fichier vide ou nom absent.")
            return response_card("Import DOF", "Nom de fichier invalide ou fichier vide.", ok=False)

        original_name = uploaded.filename
        filename = secure_filename(original_name)
        suffix = Path(filename).suffix.lower()

        log(f"Nom original : {original_name}")
        log(f"Nom sécurisé : {filename}")
        log(f"Extension : {suffix}")

        if suffix not in [".zip", ".ini", ".xml"]:
            log(f"ERREUR: format non supporté : {suffix}")
            return response_card(
                "Import DOF",
                f"Format non supporté : <code>{esc(filename)}</code><br>Formats acceptés : <code>.zip</code>, <code>.ini</code>, <code>.xml</code>.",
                ok=False
            )

        upload_path = upload_dir / f"{stamp}-{filename}"
        uploaded.save(str(upload_path))

        log(f"Fichier reçu : {upload_path}")
        log(f"Taille : {upload_path.stat().st_size if upload_path.exists() else 0} octets")

        backup_path = backup_dir / f"directoutputconfig.backup-{stamp}"

        if target_dir.exists():
            shutil.copytree(target_dir, backup_path, dirs_exist_ok=True)
            log(f"Backup créé : {backup_path}")

        imported = []

        def safe_copy(src, dest_name=None):
            src = Path(src)
            dest_name = dest_name or src.name

            # Empêche les chemins dangereux.
            dest_name = Path(dest_name).name

            dest = target_dir / dest_name
            dest.parent.mkdir(parents=True, exist_ok=True)

            shutil.copy2(src, dest)
            imported.append(dest)
            log(f"Copié : {src} -> {dest}")

        if suffix == ".zip":
            extract_dir = upload_dir / f"extract-{stamp}"
            extract_dir.mkdir(parents=True, exist_ok=True)

            try:
                with zipfile.ZipFile(upload_path, "r") as z:
                    bad = z.testzip()
                    if bad:
                        log(f"ERREUR ZIP: fichier corrompu : {bad}")
                        return response_card("Import DOF", f"ZIP invalide ou corrompu : <code>{esc(bad)}</code>", ok=False)

                    for member in z.namelist():
                        log(f"ZIP contient : {member}")

                    z.extractall(extract_dir)

            except Exception as e:
                log("ERREUR extraction ZIP:")
                log(traceback.format_exc())
                return response_card("Import DOF", f"Erreur extraction ZIP : <code>{esc(str(e))}</code>", ok=False)

            log(f"ZIP extrait dans : {extract_dir}")

            for f in extract_dir.rglob("*"):
                if not f.is_file():
                    continue

                name_l = f.name.lower()

                # On importe seulement les fichiers DOF utiles.
                if name_l.endswith(".xml") or name_l.endswith(".ini"):
                    safe_copy(f, f.name)

        elif suffix == ".ini":
            # Le fichier principal attendu par DOF.
            dest_name = "directoutputconfig.ini" if filename.lower() != "directoutputconfig.ini" else filename
            safe_copy(upload_path, dest_name)

        elif suffix == ".xml":
            safe_copy(upload_path, filename)

        try:
            subprocess.run(["chown", "-R", "pinball:pinball", str(target_dir)], timeout=15)
        except Exception as e:
            log(f"WARNING chown target_dir: {e}")

        meta = target_dir / "pincabos-dof-import.json"
        meta.write_text(json.dumps({
            "modified_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "modified_by": "PinCabOS",
            "function": "DOF Import Config Tool",
            "uploaded_file": filename,
            "target_dir": str(target_dir),
            "imported": [str(p) for p in imported],
            "backup": str(backup_path),
            "log": str(log_file)
        }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

        try:
            subprocess.run(["chown", "pinball:pinball", str(meta)], timeout=10)
        except Exception:
            pass

        rows = ""
        for p in imported:
            size = p.stat().st_size if p.exists() else 0
            rows += f"<tr><td><code>{esc(str(p))}</code></td><td>{size} octets</td></tr>"

        if not rows:
            rows = '<tr><td colspan="2"><span class="warn">Aucun fichier .ini/.xml importé depuis ce fichier.</span></td></tr>'

        extra = f"""
<table>
  <tr><td>Fichier envoyé</td><td><code>{esc(filename)}</code></td></tr>
  <tr><td>Dossier cible</td><td><code>{esc(str(target_dir))}</code></td></tr>
  <tr><td>Backup</td><td><code>{esc(str(backup_path))}</code></td></tr>
</table>

<h3>Fichiers importés</h3>
<table>
  <tr>
    <th style="text-align:left;">Fichier</th>
    <th style="text-align:left;">Taille</th>
  </tr>
  {rows}
</table>
"""
        log("Import terminé OK.")
        return response_card("Import DOF terminé", "Configuration DOF importée vers le dossier VPX.", ok=True, extra=extra)

    except Exception as e:
        log("ERREUR INTERNE IMPORT DOF:")
        log(traceback.format_exc())

        return response_card(
            "Import DOF — erreur",
            f"Erreur interne : <code>{esc(str(e))}</code>",
            ok=False,
            extra="<p>Le détail complet est dans le log ci-dessous.</p>"
        )


@app.route("/dof/import-cabinet-json", methods=["POST"])
def dof_import_cabinet_json():
    import shutil
    import traceback

    cabinet_dir = PINCABOS_DOF_CABINET_DIR
    active_pointer = PINCABOS_DOF_ACTIVE_CABINET
    upload_dir = Path("/opt/pincabos/uploads/dof")
    backup_dir = Path("/opt/pincabos/backups/dof-import")
    log_dir = Path("/opt/pincabos/logs")

    cabinet_dir.mkdir(parents=True, exist_ok=True)
    active_pointer.parent.mkdir(parents=True, exist_ok=True)
    upload_dir.mkdir(parents=True, exist_ok=True)
    backup_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_file = log_dir / f"dof-import-cabinet-json-{stamp}.log"

    def log(line):
        with log_file.open("a", encoding="utf-8") as f:
            f.write(str(line) + "\n")

    def page_msg(title, msg, ok=False, extra=""):
        css = "ok" if ok else "bad"
        body = f"""
<div class="card">
  <h2>{esc(title)}</h2>
  <p class="{css}">{msg}</p>
  {extra}
  <p>Log : <code>{esc(str(log_file))}</code></p>
  <p>
    <a class="button" href="/dof/commander">Retour DOF Commander</a>
    <a class="button secondary" href="/dof">Retour DOF</a>
  </p>
</div>
"""
        return page("DOF Commander", body)

    try:
        log("==================================================")
        log(f"# Modifié {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} par PinCabOS fonction(DOF Import Cabinet JSON)")
        log("Import cabinet JSON robuste : extraction devices seulement")
        log("==================================================")

        if "cabinet_json_file" not in request.files:
            return page_msg("Import cabinet JSON", "Aucun fichier reçu.", ok=False)

        uploaded = request.files["cabinet_json_file"]
        original_name = Path(uploaded.filename or "").name

        if not original_name.lower().endswith(".json"):
            return page_msg("Import cabinet JSON", f"Format invalide : <code>{esc(original_name)}</code>", ok=False)

        upload_path = upload_dir / f"{stamp}-{original_name}"
        uploaded.save(str(upload_path))

        raw = upload_path.read_text(errors="replace").lstrip()

        # Important : raw_decode lit le premier objet JSON valide et permet d'ignorer le texte en trop.
        decoder = json.JSONDecoder()
        data, end = decoder.raw_decode(raw)
        extra = raw[end:].strip()

        if extra:
            log(f"WARNING: contenu en trop ignoré après le premier JSON valide : {len(extra)} caractères")
            log("Début extra:")
            log(repr(extra[:500]))

        cab_type = str(data.get("type") or "").lower()
        cab_name = str(data.get("name") or "Cabinet sans nom")
        devices = data.get("devices") or []

        if cab_type and cab_type != "cabinet":
            log(f"WARNING: type JSON inattendu: {cab_type}")

        if not isinstance(devices, list):
            return page_msg(
                "Import cabinet JSON",
                "Le JSON ne contient pas une liste <code>devices</code> valide.",
                ok=False
            )

        # On garde seulement les champs utiles au DOF Commander local.
        clean = {
            "type": data.get("type", "cabinet"),
            "name": cab_name,
            "created": data.get("created", ""),
            "devices": [],
            "combos": data.get("combos") or {},
            "variables": data.get("variables") or {},
            "mx": data.get("mx") or [],
            "pincabos_import": {
                "modified_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "modified_by": "PinCabOS",
                "function": "DOF Import Cabinet JSON",
                "source_file": original_name,
                "ignored_extra_after_json": bool(extra),
                "ignored_extra_chars": len(extra),
            }
        }

        for dev in devices:
            if not isinstance(dev, dict):
                continue

            clean["devices"].append({
                "name": dev.get("name") or dev.get("Name") or "Device",
                "outputs": dev.get("outputs") or dev.get("Outputs") or 0,
                "controller_id": dev.get("controller_id") or dev.get("ControllerId") or dev.get("id") or "",
                "assignments": dev.get("assignments") or dev.get("Assignments") or {},
            })

        cabinet_name, controllers, outputs = dof_commander_inventory_from_cabinet_json_pcb(clean)

        target = cabinet_dir / original_name

        if target.exists():
            backup = backup_dir / f"{original_name}.backup-{stamp}"
            shutil.copy2(target, backup)
            log(f"Backup ancien JSON : {backup}")

        # Écriture propre : un seul JSON valide.
        target.write_text(json.dumps(clean, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        active_pointer.write_text(str(target) + "\n", encoding="utf-8")

        try:
            subprocess.run(["chown", "pinball:pinball", str(target), str(active_pointer)], timeout=10)
        except Exception:
            pass

        log(f"Nom original : {original_name}")
        log(f"Cabinet : {cabinet_name}")
        log(f"Fichier actif : {target}")
        log(f"Pointeur actif : {active_pointer}")
        log(f"Devices reconnus : {len(clean['devices'])}")
        log(f"Outputs/Toys reconnus : {len(outputs)}")

        rows = ""
        for d in clean["devices"]:
            assignments = d.get("assignments") or {}
            rows += f"""
<tr>
  <td><code>{esc(str(d.get("name")))}</code></td>
  <td><code>{esc(str(d.get("controller_id")))}</code></td>
  <td><code>{esc(str(d.get("outputs")))}</code></td>
  <td><code>{len(assignments)}</code></td>
</tr>
"""

        warning = ""
        if extra:
            warning = f"""
<p class="warn">
  Le fichier contenait du texte en trop après le JSON principal.
  PinCabOS l’a ignoré et a sauvegardé une version propre.
</p>
"""

        extra_html = f"""
{warning}
<table>
  <tr><td>Nom du cab</td><td><code>{esc(cabinet_name)}</code></td></tr>
  <tr><td>Nom du fichier conservé</td><td><code>{esc(original_name)}</code></td></tr>
  <tr><td>Fichier PinCabOS</td><td><code>{esc(str(target))}</code></td></tr>
  <tr><td>Contenu extra ignoré</td><td><code>{len(extra)} caractères</code></td></tr>
</table>

<h3>Périphériques importés</h3>
<table>
  <tr>
    <th style="text-align:left;">Device</th>
    <th style="text-align:left;">Controller ID</th>
    <th style="text-align:left;">Outputs</th>
    <th style="text-align:left;">Assignments</th>
  </tr>
  {rows}
</table>
"""
        return page_msg(
            "Cabinet JSON importé",
            "La configuration du cabinet a été analysée et nettoyée pour DOF Commander.",
            ok=True,
            extra=extra_html
        )

    except Exception as e:
        log("ERREUR IMPORT CABINET JSON:")
        log(traceback.format_exc())

        return page_msg(
            "Erreur import Cabinet JSON",
            f"Erreur : <code>{esc(str(e))}</code>",
            ok=False
        )


@app.route("/dof/commander")
def dof_commander_page():
    configs, controllers, outputs, errors, inventory_source, cabinet_name = dof_commander_load_inventory_active_pcb()
    devices, raw_usb, raw_hid, raw_serial = dof_commander_devices_summary()

    config_rows = []
    for f in configs:
        config_rows.append(f"""
        <tr>
          <td><code>{esc(str(f))}</code></td>
          <td>{esc(f.suffix.lower())}</td>
          <td>{f.stat().st_size if f.exists() else 0} octets</td>
        </tr>
        """)

    if not config_rows:
        config_rows.append("""
        <tr><td colspan="3"><span class="warn">Aucun fichier DOF XML/INI trouvé.</span></td></tr>
        """)

    device_rows = []
    for d in devices:
        badge = '<span style="color:#2fff7f;font-weight:bold;">● détecté</span>' if d["found"] else '<span style="color:#ff3333;font-weight:bold;">● non détecté</span>'
        device_rows.append(f"""
        <tr>
          <td>{esc(d["name"])}</td>
          <td>{badge}</td>
          <td><code>{esc(d["vendors"])}</code></td>
        </tr>
        """)

    controller_rows = []
    for c in controllers:
        controller_rows.append(f"<tr><td><code>{esc(c)}</code></td></tr>")

    if not controller_rows:
        controller_rows.append('<tr><td><span class="warn">Aucun contrôleur trouvé dans les configs.</span></td></tr>')

    output_rows = []
    max_rows = 250

    for i, o in enumerate(outputs[:max_rows], start=1):
        output_id = o.get("local_output") or o.get("number") or ""
        controller = o.get("controller") or "auto"
        testable = bool(o.get("testable", True))

        device_type = o.get("device_type", "")
        assigned_toy = o.get("assigned_toy", "")

        if testable:
            action_html = f"""
            <label class="dof-toggle-wrap">
              <input class="dof-output-toggle"
                type="checkbox"
                data-controller="{esc(controller)}"
                data-output="{esc(str(output_id))}"
                data-name="{esc(o.get("name", ""))}">
              <span class="dof-toggle-slider"></span>
              <span class="dof-toggle-label">OFF</span>
            </label>
            """
        else:
            action_html = '<span class="warn">non testable</span>'

        output_rows.append(f"""
        <tr>
          <td><span class="dof-output-code">{esc(str(i))}</span></td>
          <td>
            <span class="dof-badge {('dof-badge-testable' if testable else 'dof-badge-info')}">{esc(o.get("type", ""))}</span>
          </td>
          <td>
            <span class="dof-output-name">{esc(o.get("name", ""))}</span>
            <span class="dof-output-meta">{esc(device_type)}</span>
          </td>
          <td><span class="dof-output-code">{esc(str(output_id))}</span></td>
          <td>
            <span class="dof-device-name">{esc(controller)}</span>
            <span class="dof-device-sub">{esc(o.get("source", ""))}</span>
          </td>
          <td>
            <span class="dof-output-meta">{esc(o.get("value", ""))}</span>
            {('<span class="dof-output-meta">Assigned toy : <code>' + esc(str(assigned_toy)) + '</code></span>') if assigned_toy else ''}
          </td>
          <td style="white-space:nowrap;">{action_html}</td>
        </tr>
        """)

    if not output_rows:
        output_rows.append('<tr><td colspan="7"><span class="warn">Aucun output/toy trouvé dans les configs.</span></td></tr>')

    error_html = ""
    if errors:
        error_html = "<div class='card' style='margin-top:20px;'><h2>Erreurs lecture config</h2><pre>" + esc("\\n".join(errors)) + "</pre></div>"

    more_note = ""
    if len(outputs) > max_rows:
        more_note = f"<p class='warn'>Affichage limité à {max_rows} outputs sur {len(outputs)} trouvés.</p>"

    body = f"""
<div class="grid">
  <div class="card">
    <h2>DOF Commander</h2>
    <p>
      Analyse la configuration réelle du cabinet, affiche les contrôleurs et outputs physiques,
      puis permet de lancer des tests contrôlés.
    </p>
    <table>
      <tr><td>Cabinet actif</td><td><code>{esc(cabinet_name)}</code></td></tr>
      <tr><td>Source inventaire outputs</td><td><code>{esc(inventory_source)}</code></td></tr>
    </table>

    <p>
      <a class="button" href="https://configtool.vpuniverse.com/" target="_blank">Ouvrir DOF Config Tool</a>
      <a class="button secondary" href="/dof">Retour DOF</a>
    </p>

    <p class="warn">
      Les tests sont limités en durée pour éviter de laisser un toy activé trop longtemps.
    </p>
  </div>

  

    </div>

    <p>
      Dossier cible : <code>/home/pinball/.local/share/VPinballX/10.8/directoutputconfig</code>
    </p>
  </div>
</div>

<div class="grid" style="margin-top:20px;">
  <div class="card">
    <h2>Périphériques branchés</h2>
    <table>
      <tr><th style="text-align:left;">Famille</th><th style="text-align:left;">État</th><th style="text-align:left;">Vendor IDs</th></tr>
      {''.join(device_rows)}
    </table>
  </div>

  <div class="card">
    <h2>Contrôleurs dans les configs</h2>
    <table>
      {''.join(controller_rows)}
    </table>
  </div>
</div>

<div class="card" style="margin-top:20px;">
  <h2>Fichiers DOF trouvés</h2>
  <table>
    <tr><th style="text-align:left;">Fichier</th><th style="text-align:left;">Type</th><th style="text-align:left;">Taille</th></tr>
    {''.join(config_rows)}
  </table>
</div>

<div class="card" style="margin-top:20px;">
  <div class="dof-section-title">
    <h2>Outputs / Toys configurés — {esc(cabinet_name)}</h2>
    <span class="dof-badge dof-badge-info">{esc(inventory_source)}</span>
  </div>

  <div class="dof-test-panel dof-cabinet-json-import">
    <h3>Importer cabinet JSON</h3>

    <p>
      Le fichier <code>.json</code> du cabinet sert à associer les tests DOF Commander
      aux bonnes sorties physiques de vos périphériques : LedWiz, WS2811, Dude’s Cab,
      Pinscape, PacLed, etc.
    </p>

    <p><strong>Pour le télécharger depuis DOF Config Tool V3 :</strong></p>

    <ol>
      <li>Va sur <a href="https://configtool.vpuniverse.com/app/cabinets" target="_blank">DOF Config Tool V3 — Cabinets</a>.</li>
      <li>Sélectionne ton cabinet.</li>
      <li>Clique sur <strong>Action</strong>.</li>
      <li>Clique sur <strong>Export Cabinet</strong>.</li>
      <li>Importe le fichier <code>.json</code> ici.</li>
    </ol>

    <form method="post" action="/dof/import-cabinet-json" enctype="multipart/form-data">
      <input type="file" name="cabinet_json_file" accept=".json" required>
      <button class="button secondary" type="submit">Importer cabinet JSON</button>
    </form>
  </div>


  


  {more_note}
<div class="dof-test-panel dof-test-panel-compact">
    <div class="dof-test-head">
      <div>
        <h3>Réglages de test</h3>
        <span class="dof-muted">Appliqués aux toggles ON. OFF coupe immédiatement.</span>
      </div>
    </div>

    <div class="dof-test-controls">
      <div class="dof-control">
        <label>Durée</label>
        <div class="dof-range-line">
          <input id="dof-test-duration" type="range" min="50" max="5000" value="500" step="50"
            oninput="document.getElementById('dof-test-duration-label').textContent=this.value + ' ms'">
          <code id="dof-test-duration-label">500 ms</code>
        </div>
      </div>

      <div class="dof-control dof-control-small">
        <label>Mode</label>
        <select id="dof-test-mode">
          <option value="onoff">ON / OFF</option>
          <option value="pulse">Pulse / Strobe</option>
          <option value="doublepulse">Double Pulse</option>
          <option value="fadein">Fade in</option>
          <option value="fadeout">Fade out</option>
          <option value="sine">Sine</option>
        </select>
      </div>

      <div class="dof-control dof-control-auto">
        <label>Auto repeat</label>
        <label class="dof-mini-check">
          <input id="dof-test-auto-repeat" type="checkbox">
          <span>Répéter tant que le toggle est ON</span>
        </label>
      </div>

      <div class="dof-control">
        <label>Pause repeat</label>
        <div class="dof-range-line">
          <input id="dof-test-repeat-delay" type="range" min="50" max="5000" value="500" step="50"
            oninput="document.getElementById('dof-test-repeat-delay-label').textContent=this.value + ' ms'">
          <code id="dof-test-repeat-delay-label">500 ms</code>
        </div>
      </div>

      <div class="dof-control">
        <label>Intensité</label>
        <div class="dof-range-line">
          <input id="dof-test-intensity" type="range" min="1" max="255" value="255" step="1"
            oninput="document.getElementById('dof-test-intensity-label').textContent=this.value">
          <code id="dof-test-intensity-label">255</code>
        </div>
      </div>
    </div>
  </div>

  <table class="dof-output-table">
    <tr>
      <th style="text-align:left;">#</th>
      <th style="text-align:left;">Type</th>
      <th style="text-align:left;">Nom</th>
      <th style="text-align:left;">Output local</th>
      <th style="text-align:left;">Périphérique</th>
      <th style="text-align:left;">Association JSON</th>
      <th style="text-align:left;">Action</th>
    </tr>
    {''.join(output_rows)}
  </table>
</div>

<div id="dof-commander-log-panel" class="card" style="margin-top:20px; display:none; border-color:#ffb000;">
  <h2>Log test output</h2>
  <table>
    <tr><td>Contrôleur</td><td><code id="dof-cmd-controller">-</code></td></tr>
    <tr><td>Output</td><td><code id="dof-cmd-output">-</code></td></tr>
    <tr><td>Action</td><td><code id="dof-cmd-action">-</code></td></tr>
    <tr><td>Mode</td><td><code id="dof-cmd-mode">-</code></td></tr>
    <tr><td>Durée</td><td><code id="dof-cmd-duration">-</code></td></tr>
  </table>
  <pre id="dof-commander-log" style="max-height:360px; overflow:auto; background:#050007; border:1px solid #5f2a91; border-radius:12px; padding:12px;">Aucun test lancé.</pre>
</div>

<div class="card" style="margin-top:20px;">
  <h2>Détails techniques</h2>
  <details>
    <summary>USB brut</summary>
    <pre>{esc(raw_usb)}</pre>
  </details>
  <details>
    <summary>HID raw</summary>
    <pre>{esc(raw_hid)}</pre>
  </details>
  <details>
    <summary>Serial</summary>
    <pre>{esc(raw_serial)}</pre>
  </details>
</div>

{error_html}

<link rel="stylesheet" href="/static/dof-commander-pro.css?v=20260518-toggle-css-pure">
<script src="/static/dof-commander-onoff.js?v=20260518-toggle-css-pure"></script>
"""
    return page("DOF Commander", body)


@app.route("/api/dof/commander/test", methods=["POST"])
def api_dof_commander_test():
    try:
        data = request.get_json(force=True) or {}
    except Exception:
        data = {}

    controller = str(data.get("controller", "auto"))[:80]
    output = str(data.get("output", "0"))[:80]
    action = str(data.get("action", "on"))[:20]
    mode = str(data.get("mode", "onoff"))[:40]
    duration_ms = str(data.get("duration_ms", "500"))[:20]
    intensity = str(data.get("intensity", "255"))[:20]

    if action not in ["on", "off"]:
        action = "on"

    script = "/opt/pincabos/tools/dof-commander-test-output.sh"
    cmd = [
        script,
        controller,
        output,
        action,
        mode,
        duration_ms,
        intensity,
    ]

    try:
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10
        )
        log = (r.stdout or "") + (r.stderr or "")
    except Exception as e:
        log = f"Erreur exécution test: {e}"

    payload = {
        "ok": True,
        "controller": controller,
        "output": output,
        "action": action,
        "mode": mode,
        "duration_ms": duration_ms,
        "intensity": intensity,
        "log": log,
    }

    return app.response_class(json.dumps(payload), mimetype="application/json")


def dof_driver_pack_status_html():
    tools = Path("/opt/pincabos/tools")
    config = Path("/opt/pincabos/config/dof")

    def read_json(path):
        try:
            if path.exists():
                return json.loads(path.read_text(errors="replace"))
        except Exception:
            pass
        return {}

    def usb_detected(vendors, keywords=""):
        try:
            out = subprocess.run(
                ["/usr/bin/lsusb"],
                capture_output=True,
                text=True,
                timeout=3
            ).stdout.lower()
        except Exception:
            out = ""

        for v in vendors:
            if str(v).lower() in out:
                return True

        for k in str(keywords).lower().split("|"):
            k = k.strip()
            if k and k in out:
                return True

        return False

    def serial_detected():
        return bool(list(Path("/dev").glob("ttyUSB*")) or list(Path("/dev").glob("ttyACM*")))

    drivers = [
        {
            "name": "LedWiz",
            "exe": "pincabos-ledwizctl",
            "transport": "USB HID/libusb",
            "config": None,
            "vendors": ["fafa"],
            "keywords": "ledwiz|groovy",
            "real_if_installed": True
        },
        {
            "name": "WS2811 / MX",
            "exe": "pincabos-ws2811ctl",
            "transport": "Serial / UDP / protocole à configurer",
            "config": "ws2811.json",
            "vendors": ["1a86", "10c4", "303a"],
            "keywords": "wch|cp210|espressif|wemos|esp"
        },
        {
            "name": "Dude’s Cab",
            "exe": "pincabos-dudescabctl",
            "transport": "ESP / Wemos / Serial / WiFi",
            "config": "dudescab.json",
            "vendors": ["1a86", "10c4", "303a"],
            "keywords": "wch|cp210|espressif|wemos|esp"
        },
        {
            "name": "Pinscape / KL25Z",
            "exe": "pincabos-pinscapectl",
            "transport": "USB HID custom",
            "config": "pinscape.json",
            "vendors": ["15a2", "1fc9"],
            "keywords": "freescale|nxp|kl25z|pinscape"
        },
        {
            "name": "Pinscape Pico / RP2040",
            "exe": "pincabos-pinscape-picoctl",
            "transport": "USB HID custom",
            "config": "pinscape-pico.json",
            "vendors": ["2e8a", "1209"],
            "keywords": "raspberry|rp2040|pico"
        },
        {
            "name": "Ultimarc / PacDrive / PacLed / Ultimate I/O",
            "exe": "pincabos-ultimarcctl",
            "transport": "USB HID",
            "config": "ultimarc.json",
            "vendors": ["d209"],
            "keywords": "ultimarc|pacdrive|pacled"
        },
        {
            "name": "SainSmart",
            "exe": "pincabos-sainsmartctl",
            "transport": "USB relay / Serial selon modèle",
            "config": "sainsmart.json",
            "vendors": [],
            "keywords": "sainsmart|relay"
        },
        {
            "name": "PinOne",
            "exe": "pincabos-pinonectl",
            "transport": "USB HID / Serial",
            "config": "pinone.json",
            "vendors": [],
            "keywords": "pinone"
        },
        {
            "name": "Pincontrol1 / Pincontrol2",
            "exe": "pincabos-pinctl",
            "transport": "USB HID / Serial",
            "config": "pincontrol.json",
            "vendors": [],
            "keywords": "pincontrol"
        },
        {
            "name": "Philips Hue",
            "exe": "pincabos-huectl",
            "transport": "Bridge Hue API",
            "config": "hue.json",
            "vendors": [],
            "keywords": "",
            "network": True
        },
        {
            "name": "ArtNet",
            "exe": "pincabos-artnetctl",
            "transport": "UDP Art-Net",
            "config": None,
            "vendors": [],
            "keywords": "",
            "network": True,
            "real_if_installed": True
        },
    ]

    rows = []
    installed_count = 0
    real_count = 0

    for d in drivers:
        path = tools / d["exe"]
        installed = path.exists() and path.is_file()
        executable = installed and bool(path.stat().st_mode & 0o111)

        cfg_enabled = False
        cfg_file = None

        if d.get("config"):
            cfg_file = config / d["config"]
            cfg_data = read_json(cfg_file)
            cfg_enabled = bool(cfg_data.get("enabled", False))

        if d.get("network"):
            detected = True
        elif d["name"] in ["WS2811 / MX", "Dude’s Cab", "SainSmart", "PinOne", "Pincontrol1 / Pincontrol2"]:
            detected = usb_detected(d.get("vendors", []), d.get("keywords", "")) or serial_detected()
        else:
            detected = usb_detected(d.get("vendors", []), d.get("keywords", ""))

        if executable:
            installed_count += 1
            status = '<span class="ok">● installé</span>'
        elif installed:
            status = '<span class="warn">● présent / non exécutable</span>'
        else:
            status = '<span class="bad">● absent</span>'

        if not executable:
            mode = '<span class="bad">absent</span>'
        elif d.get("real_if_installed"):
            real_count += 1
            mode = '<span class="ok">driver réel minimal</span>'
        elif cfg_enabled:
            real_count += 1
            mode = '<span class="ok">driver réel minimal</span>'
        elif detected:
            mode = '<span class="warn">détecté / safe mode</span>'
        else:
            mode = '<span class="warn">safe mode</span>'

        if d.get("network"):
            hw = '<span class="ok">réseau</span>'
        elif detected:
            hw = '<span class="ok">détecté</span>'
        else:
            hw = '<span class="bad">non détecté</span>'

        cfg_note = ""
        if cfg_file:
            cfg_note = f'<br><small>Config : <code>{esc(str(cfg_file))}</code> / enabled=<code>{str(cfg_enabled).lower()}</code></small>'

        rows.append(f"""
        <tr>
          <td><strong>{esc(d["name"])}</strong><br><small>{esc(d["transport"])}</small>{cfg_note}</td>
          <td>{status}</td>
          <td>{hw}</td>
          <td><code>{esc(str(path))}</code></td>
          <td>{mode}</td>
        </tr>
        """)

    pack_file = config / "driver-pack.json"
    pack_status = '<span class="ok">installé</span>' if pack_file.exists() else '<span class="bad">absent</span>'

    return f"""
<div class="card" id="dof-driver-pack-status-card">
  <h2>État DOF Driver Pack</h2>
  <p>
    Pack : {pack_status}<br>
    Drivers détectés : <code>{installed_count}/{len(drivers)}</code><br>
    Drivers en mode réel minimal : <code>{real_count}/{len(drivers)}</code>
  </p>

  <p class="warn">
    Le mode est dynamique : si le driver est installé mais que la config reste désactivée,
    PinCabOS affiche <strong>safe mode</strong>. Quand <code>enabled=true</code> est confirmé
    pour une famille, le mode devient <strong>driver réel minimal</strong>.
  </p>

  <table>
    <tr>
      <th style="text-align:left;">Famille</th>
      <th style="text-align:left;">Driver</th>
      <th style="text-align:left;">Matériel</th>
      <th style="text-align:left;">Module PinCabOS</th>
      <th style="text-align:left;">Mode</th>
    </tr>
    {''.join(rows)}
  </table>

  <p>
    Outil diagnostic : <code>/opt/pincabos/tools/pincabos-dof-driver-status.sh</code>
  </p>
</div>
"""


@app.route("/api/dof/driver-pack-status")
def api_dof_driver_pack_status():
    try:
        return jsonify({
            "ok": True,
            "html": dof_driver_pack_status_html(),
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
    except Exception as e:
        return jsonify({
            "ok": False,
            "error": str(e),
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }), 500


@app.route("/dof")
def dof_page():
    cfg_path, file_rows = dof_file_status()
    summary, device_rows, raw_devices = detect_dof_devices()
    logs = dof_logs()

    body = f"""
<div class="grid">
  <div class="card">
<h2>DOF — État général</h2>
    <p>Service VPinFE : <code>{esc(service_status("pincabos-frontend.service"))}</code></p>
    <p>Dossier config DOF :</p>
    <p><code>{esc(cfg_path)}</code></p>
    <p>Détection : {summary}</p>
    <p>

    <!-- PINCABOS_DOF_STATIC_ASSETS_START -->
    <link rel="stylesheet" href="/static/pincabos-dof-pro.css?v=20260528">
    <script defer src="/static/pincabos-dof-pro.js?v=20260528"></script>
    <!-- PINCABOS_DOF_STATIC_ASSETS_END -->

      <a class="button secondary" href="/dof/commander">Ouvrir DOF Commander</a>
      <a class="button secondary" href="https://configtool.vpuniverse.com/" target="_blank">DOF Config Tool V3</a>

    <div id="pincabos-dof-import-manual-card" class="card" style="margin-top:20px; border-color:#ffb000;">
      <h2>Import manuel DOF Config Tool</h2>
      <p>
        Si l'import en ligne VPinFE retourne <code>403 Forbidden / Cloudflare</code>,
        exporte le ZIP DOF avec ton navigateur, puis importe-le ici.
      </p>

      <form method="post" action="/dof/import-config" enctype="multipart/form-data" style="margin-top:12px;">
        <input type="hidden" name="mode" value="upload">
        <input type="file" name="dof_file" accept=".zip,.ini,.xml" style="display:block; margin:8px 0; width:100%;">
        <button class="button" type="submit">Importer ZIP DOF</button>
      </form>

      <form method="post" action="/dof/import-config" style="margin-top:10px;">
        <input type="hidden" name="mode" value="share">
        <button class="button secondary" type="submit">Importer dernier ZIP depuis /home/pinball/Share</button>
      </form>

      <hr style="border:0; border-top:1px solid #5f2a91; margin:16px 0;">

      <h3>Import automatique via API DOF Config Tool</h3>
      <p>
        Entre ta clé API DOF Config Tool. PinCabOS lancera <code>ledcontrol_pull.py</code>
        et placera les fichiers directement au bon endroit.
      </p>

      <form method="post" action="/dof/import-api" style="margin-top:12px;">
        <label for="dof-api-key"><strong>Clé API DOF Config Tool</strong></label>
        <input id="dof-api-key" type="text" name="apikey" value="{esc(pincabos_dof_get_saved_api_key())}" placeholder="Clé API DOF Config Tool" autocomplete="off" style="display:block; margin:8px 0; width:100%; padding:10px; border-radius:10px; border:1px solid #5f2a91; background:#050007; color:white;">
        <label style="display:block; margin:8px 0;">
          <input type="checkbox" name="force" value="1" checked>
          Forcer le téléchargement / remplacement
        </label>
        <button class="button" type="submit">Importer via API</button>
      </form>

      <p class="warn" style="margin-top:10px;">
        Destination : <code>/home/pinball/.local/share/VPinballX/10.8/directoutputconfig</code>
      </p>
    </div>

</p>
  </div>

  <div class="card">
    <h2>À quoi sert cette page ?</h2>
    <p>
      Cette section prépare PinCabOS pour les contrôleurs de feedback :
      LedWiz, Pinscape, Dude's Cab, PacLed, FTDI, Arduino, Serial USB, ArtNet et Hue.
    </p>
    <p>
      Le Driver Pack installe les modules PinCabOS nécessaires au routage DOF Commander.
      Les modules en safe mode restent inactifs côté matériel tant que leur protocole n’est pas activé.
    </p>
  </div>
</div>

{dof_driver_pack_status_html()}


<script>
(function() {{
  async function refreshDofDriverPackStatus() {{
    const card = document.getElementById('dof-driver-pack-status-card');
    if (!card) return;

    try {{
      const r = await fetch('/api/dof/driver-pack-status?t=' + Date.now(), {{
        cache: 'no-store'
      }});

      const data = await r.json();

      if (!data.ok) {{
        const err = document.createElement('p');
        err.className = 'bad';
        err.textContent = 'Erreur rafraîchissement Driver Pack : ' + (data.error || 'inconnue');
        card.appendChild(err);
        return;
      }}

      const temp = document.createElement('div');
      temp.innerHTML = data.html.trim();

      const newCard = temp.querySelector('#dof-driver-pack-status-card');
      if (newCard) {{
        card.replaceWith(newCard);

        const stamp = document.createElement('p');
        stamp.className = 'dof-muted';
        stamp.innerHTML = 'Dernier rafraîchissement : <code>' + data.updated_at + '</code>';
        newCard.appendChild(stamp);
      }}
    }} catch (e) {{
      const current = document.getElementById('dof-driver-pack-status-card');
      if (current) {{
        const err = document.createElement('p');
        err.className = 'bad';
        err.textContent = 'Erreur refresh Driver Pack : ' + e;
        current.appendChild(err);
      }}
    }}
  }}

  refreshDofDriverPackStatus();
  setInterval(refreshDofDriverPackStatus, 3000);
}})();
</script>

"""

    body = body + dof_detection_summary_card(summary, raw_devices, logs, file_rows)

    return page("Outputs", body)


@app.route("/service-control", methods=["POST"])
def service_control():
    """
    Contrôle sécurisé des services PinCabOS depuis le dashboard.
    Accepte: service + action.
    Actions supportées: start, stop, restart, reload, kill.
    """
    service = request.form.get("service", "").strip()
    action = request.form.get("action", "").strip().lower()

    allowed_services = {
        "pincabos-frontend.service",
        "pincabos-web.service",
        "pincabos-console.service",
        "pincabos-auto-timezone.service",
    }

    action_map = {
        "start": "start",
        "stop": "stop",
        "restart": "restart",
        "reload": "restart",
        "kill": "kill",
    }

    if service not in allowed_services:
        return f"Service non autorisé: {esc(service)}", 400

    if action not in action_map:
        return f"Action non autorisée: {esc(action)}", 400

    cmd_action = action_map[action]

    try:
        if cmd_action == "kill":
            subprocess.Popen(
                ["/usr/bin/sudo", "/bin/systemctl", "kill", service],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            subprocess.Popen(
                ["/usr/bin/sudo", "/bin/systemctl", cmd_action, service],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    except Exception as e:
        return f"Erreur contrôle service: {esc(str(e))}", 500

    return redirect(request.referrer or "/")


@app.route("/service-control/<service_key>/<action>", methods=["GET", "POST"])
def service_control_path(service_key, action):
    """
    Route générique pour les boutons Services du dashboard PinCabOS.
    Supporte les URLs du genre:
      /service-control/web/start
      /service-control/web/restart
      /service-control/frontend/stop
      /service-control/frontend/reload
      /service-control/console/kill
      /service-control/timezone/start
    """
    service_map = {
        # VPinFE / frontend
        "frontend": "pincabos-frontend.service",
        "vpinfe": "pincabos-frontend.service",
        "front": "pincabos-frontend.service",

        # Web manager
        "web": "pincabos-web.service",
        "web-manager": "pincabos-web.service",
        "manager": "pincabos-web.service",

        # Console web
        "console": "pincabos-console.service",
        "webconsole": "pincabos-console.service",
        "web-console": "pincabos-console.service",

        # Auto timezone
        "timezone": "pincabos-auto-timezone.service",
        "auto-timezone": "pincabos-auto-timezone.service",
        "autotimezone": "pincabos-auto-timezone.service",
    }

    action_map = {
        "start": "start",
        "play": "start",
        "stop": "stop",
        "restart": "restart",
        "reload": "restart",
        "refresh": "restart",
        "kill": "kill",
    }

    service_key = str(service_key or "").strip().lower()
    action = str(action or "").strip().lower()

    if service_key not in service_map:
        return f"Service non autorisé: {esc(service_key)}", 400

    if action not in action_map:
        return f"Action non autorisée: {esc(action)}", 400

    service = service_map[service_key]
    systemctl_action = action_map[action]

    try:
        subprocess.Popen(
            ["/usr/bin/sudo", "/bin/systemctl", systemctl_action, service],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as e:
        return f"Erreur contrôle service: {esc(str(e))}", 500

    return redirect(request.referrer or "/")


@app.route("/updates")
def updates():
    import json
    from pathlib import Path

    ver = pincabos_version()

    version_path = Path("/opt/pincabos/config/version.json")
    try:
        if version_path.exists():
            version_json = json.dumps(
                json.loads(version_path.read_text(errors="replace")),
                indent=2,
                ensure_ascii=False
            )
        else:
            version_json = json.dumps(ver, indent=2, ensure_ascii=False)
    except Exception as e:
        version_json = (
            "Erreur lecture version.json: "
            + str(e)
            + chr(10)
            + chr(10)
            + json.dumps(ver, indent=2, ensure_ascii=False)
        )

    version_card = """
  <div class="card">
    <h2>Version PinCabOS</h2>
    <p>Contenu complet de <code>/opt/pincabos/config/version.json</code></p>
    <pre style="white-space:pre-wrap;max-height:360px;overflow:auto;background:rgba(0,0,0,.35);border:1px solid rgba(255,176,0,.25);border-radius:12px;padding:12px;">__VERSION_JSON__</pre>
  </div>
""".replace("__VERSION_JSON__", esc(version_json))

    body = """
<div class="grid">
  <div class="card">
    <h2>Mises à jour</h2>
    <p>Utilise ces boutons pour mettre à jour les composants PinCabOS.</p>

    <div class="card" style="border:1px solid rgba(255,176,0,.45);background:rgba(255,176,0,.07);margin-bottom:14px;">
      <h2>⬆️ Mise à jour PinCabOS</h2>
      <p>Met à jour la WebApp, les outils et services PinCabOS sans écraser les tables, VPX, VPinFE ou la configuration utilisateur.</p>
      <p><a class="button" href="/pincabos-update">Ouvrir la mise à jour PinCabOS</a></p>
    </div>

    <form action="/run-update/vpinfe" method="post">
      <button class="button" type="submit">Mettre à jour VPinFE</button>
    </form>

    <form action="/run-update/vpx" method="post">
      <button class="button" type="submit">Mettre à jour VPX Linux</button>
    </form>

    <form action="/run-update/gpu" method="post">
      <button class="button secondary" type="submit">Mises à jour pilotes GPU</button>
    </form>

    <form action="/run-update/system" method="post">
      <button class="button secondary" type="submit">Mettre à jour Ubuntu</button>
    </form>

    <hr style="border:0;border-top:1px solid rgba(255,176,0,.25);margin:18px 0;">

    <form action="/run-update/all" method="post" onsubmit="return confirm('Lancer la mise à jour complète ? Cela lance PinCabOS FORCE, VPinFE, VPX Linux, GPU et Ubuntu.');">
      <button class="button secondary" type="submit" style="border-color:#ffb000;color:#fff;background:rgba(255,122,0,.25);">Mise à jour complète</button>
    </form>
  </div>

  <div class="card">
    <h2>Progression</h2>
    <p>Composant : <code id="job-target">aucun</code></p>
    <p>Statut : <span id="job-status" class="warn">idle</span></p>
    <p id="job-message">Aucune opération en cours.</p>

    <div class="progress-wrap">
      <div id="progress-bar" class="progress-bar" style="background:linear-gradient(90deg,#ff7a00,#ffb000);box-shadow:0 0 14px rgba(255,176,0,.35);">0%</div>
    </div>

    <p>Log : <code id="log-name">aucun</code></p>
  </div>
</div>

<div class="card" style="margin-top:20px;">
  <h2>Log en direct</h2>
  <pre id="live-log">Aucun log pour le moment.</pre>
</div>

<script>

function normalizePcoUpdateLog(text) {
  let s = (text || "").toString();

  const LF = String.fromCharCode(10);
  const CR = String.fromCharCode(13);
  const BS = String.fromCharCode(92);
  const ESC = String.fromCharCode(27);

  // Retours de ligne réels.
  s = s.split(CR + LF).join(LF);
  s = s.split(CR).join(LF);

  // Retours de ligne échappés.
  s = s.split(BS + "r" + BS + "n").join(LF);
  s = s.split(BS + "n").join(LF);
  s = s.split(BS + "r").join(LF);

  // Enlever codes ANSI simples sans regex dangereuse.
  while (s.indexOf(ESC + "[") !== -1) {
    const a = s.indexOf(ESC + "[");
    let b = a + 2;
    while (b < s.length && "0123456789;?".indexOf(s[b]) !== -1) b++;
    if (b < s.length) {
      s = s.substring(0, a) + s.substring(b + 1);
    } else {
      s = s.substring(0, a);
    }
  }

  // Séparateurs plus lisibles.
  const sep = "==================================================";
  s = s.split(sep).join(LF + sep + LF);

  return s.trimStart();
}

async function refreshStatus() {
  try {
    const r = await fetch('/api/update-status?t=' + Date.now(), {cache:'no-store'});
    const data = await r.json();

    const status = data.status || 'idle';
    const running = status === 'running';

    document.getElementById('job-target').textContent = running ? (data.target || 'aucun') : 'aucun';
    document.getElementById('job-status').textContent = running ? status : 'idle';
    document.getElementById('job-message').textContent = running ? (data.message || 'Mise à jour en cours...') : 'Aucune opération en cours.';
    document.getElementById('log-name').textContent = running ? (data.log_name || 'log en attente') : 'aucun';

    const bar = document.getElementById('progress-bar');
    const progress = running ? Math.max(0, Math.min(100, Number(data.progress || 0))) : 0;

    bar.classList.remove('running');
    bar.style.background = 'linear-gradient(90deg,#ff7a00,#ffb000)';
    bar.style.boxShadow = '0 0 14px rgba(255,176,0,.35)';
    bar.style.width = progress + '%';
    bar.textContent = progress + '%';

    const statusEl = document.getElementById('job-status');

    if (status === 'error') {
      statusEl.className = 'bad';
      document.getElementById('job-target').textContent = data.target || 'aucun';
      document.getElementById('job-status').textContent = status;
      document.getElementById('job-message').textContent = data.message || 'Erreur pendant la mise à jour.';
      document.getElementById('log-name').textContent = data.log_name || 'aucun';
      bar.style.width = '100%';
      bar.textContent = 'Erreur';
    } else if (running) {
      statusEl.className = 'warn';
    } else {
      statusEl.className = 'ok';
    }

    const log = document.getElementById('live-log');
    if (running || status === 'error') {
      log.textContent = normalizePcoUpdateLog(data.log || data.message || 'Log en attente...');
    } else {
      log.textContent = 'Aucune opération en cours.';
    }
    log.scrollTop = log.scrollHeight;

  } catch (e) {
    document.getElementById('job-message').textContent = 'Erreur de rafraîchissement: ' + e;
  }
}

refreshStatus();
setInterval(refreshStatus, 2000);
</script>
"""
    body = body.replace('<div class="grid">', '<div class="grid">' + version_card, 1)
    return page("Mises à jour", body)


# === Modular route: update status - PinCabOS START ===
init_update_status_routes(app, get_job_status)
# === Modular route: update status - PinCabOS END ===

@app.route("/run-update/<target>", methods=["POST"])
def run_update(target):
    if target not in UPDATE_COMMANDS:
        return "Update inconnu", 404

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    job_id = f"{target}-{stamp}"

    job_log = JOB_DIR / f"{job_id}.log"
    exit_file = JOB_DIR / f"{job_id}.exit"
    job_file = JOB_DIR / f"{job_id}.json"

    import shlex
    cmd = shlex.join(str(x) for x in UPDATE_COMMANDS[target])

    wrapper = f"""
set -o pipefail
if [ "{target}" = "all" ]; then
  export PINCABOS_DEFER_REBOOT=1
fi
rm -f /run/pincabos-reboot-required 2>/dev/null || true
echo "=================================================="
echo "PinCabOs Web Update"
echo "Target: {target}"
echo "Started: $(date)"
echo "Command: {cmd}"
echo "=================================================="
{cmd}
RC=$?
if [ "$RC" = "0" ] && [ "{target}" = "all" ] && [ -f /run/pincabos-reboot-required ]; then
python3 - <<'PY2'
import json, pathlib, datetime
p = pathlib.Path("/opt/pincabos/logs/updates/pincabos-update-status.json")
now = datetime.datetime.now().isoformat(timespec="seconds")
data = dict(
  ok=True,
  running=False,
  state="awaiting_reboot",
  percent=100,
  step="Redémarrage requis",
  message="Mise à jour complète terminée. Redémarrage requis, en attente de confirmation.",
  reboot_required=True,
  awaiting_reboot=True,
  target="all",
  updated_at=now,
  events=["[" + now + "] all - mise à jour complète terminée, reboot requis"]
)
p.parent.mkdir(parents=True, exist_ok=True)
p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
PY2
fi
echo "=================================================="
echo "Finished: $(date)"
echo "Exit code: $RC"
echo "=================================================="
echo $RC > "{exit_file}"
exit $RC
"""

    # Reset status PinCabOS interne au début d'un nouveau job Web update.
    try:
        pcos_status_path = Path("/opt/pincabos/logs/updates/pincabos-update-status.json")
        pcos_status_path.parent.mkdir(parents=True, exist_ok=True)
        pcos_status_path.write_text(json.dumps({
            "ok": True,
            "running": True,
            "state": "running",
            "percent": 1,
            "step": "Web update",
            "message": "Mise à jour Web lancée.",
            "reboot_required": False,
            "awaiting_reboot": False,
            "target": target,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "events": []
        }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except Exception:
        pass

    job = {
        "id": job_id,
        "target": target,
        "started": time.time(),
        "log_file": str(job_log),
        "exit_file": str(exit_file),
    }

    pincabos_write_json_with_meta(job_file, job, f"Run Update {target}")

    subprocess.Popen(
        ["/bin/bash", "-lc", wrapper],
        stdout=open(job_log, "w"),
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )

    return redirect(url_for("updates"))


def load_fulldmd_calibration():
    cfg = Path("/opt/pincabos/config/fulldmd-calibration.json")
    default = {
        "screen_id": "",
        "x": 0,
        "y": 0,
        "width": 800,
        "height": 300,
        "note": "PinCabOs FullDMD calibration"
    }

    try:
        if cfg.exists():
            data = json.loads(cfg.read_text())
            default.update(data)
    except Exception:
        pass

    return default

def save_fulldmd_to_configs(data):
    function_name = "FullDMD Save"

    screen_id = str(data.get("screen_id", "0"))
    x = int(data.get("x", 0))
    y = int(data.get("y", 0))
    w = int(data.get("width", 0))
    h = int(data.get("height", 0))
    geometry = f"{x},{y},{w},{h}"

    Path("/opt/pincabos/config").mkdir(parents=True, exist_ok=True)

    # JSON PinCabOS avec meta
    fulldmd_json = Path("/opt/pincabos/config/fulldmd-calibration.json")
    pincabos_backup_config_file(fulldmd_json, function_name)
    pincabos_write_json_with_meta(fulldmd_json, {
        "screen_id": screen_id,
        "x": x,
        "y": y,
        "width": w,
        "height": h,
        "geometry": geometry,
        "note": "PinCabOs FullDMD visible area calibration"
    }, function_name)

    # VPinFE : structure existante [Displays]
    vpinfe_ini = Path("/home/pinball/.config/vpinfe/vpinfe.ini")
    pincabos_backup_config_file(vpinfe_ini, function_name)

    vpinfe_lines = pincabos_read_ini_lines(vpinfe_ini)
    vpinfe_lines = pincabos_set_ini_key_with_comment(vpinfe_lines, "Displays", "dmdscreenid", screen_id, function_name)
    vpinfe_lines = pincabos_set_ini_key_with_comment(vpinfe_lines, "Displays", "dmdwindowoverride", geometry, function_name)
    vpinfe_lines = pincabos_set_ini_section_with_comment(vpinfe_lines, "PinCabOs.FullDMD", {
        "screenid": screen_id,
        "x": x,
        "y": y,
        "width": w,
        "height": h,
        "geometry": geometry,
        "managed_by": "PinCabOS FullDMD",
        "updated_at": datetime.now().isoformat(timespec="seconds")
    }, function_name)
    pincabos_write_ini_lines(vpinfe_ini, vpinfe_lines)

    # VPX : garde la section PinCabOs.FullDMD déjà utilisée par PinCabOS
    vpx_ini = Path("/home/pinball/.local/share/VPinballX/10.8/VPinballX.ini")
    pincabos_backup_config_file(vpx_ini, function_name)

    vpx_lines = pincabos_read_ini_lines(vpx_ini)
    vpx_lines = pincabos_set_ini_section_with_comment(vpx_lines, "PinCabOs.FullDMD", {
        "screenid": screen_id,
        "x": x,
        "y": y,
        "width": w,
        "height": h,
        "geometry": geometry,
        "managed_by": "PinCabOS FullDMD",
        "updated_at": datetime.now().isoformat(timespec="seconds")
    }, function_name)
    pincabos_write_ini_lines(vpx_ini, vpx_lines)

    subprocess.run(["/bin/chown", "-R", "pinball:pinball", "/opt/pincabos/config"], timeout=5)
    subprocess.run(["/bin/chown", "pinball:pinball", str(vpinfe_ini)], timeout=5)
    subprocess.run(["/bin/chown", "pinball:pinball", str(vpx_ini)], timeout=5)


@app.route("/fulldmd")
def fulldmd_page():
    cal = load_fulldmd_calibration()

    screens_json = "{}"
    try:
        f = Path("/opt/pincabos/config/screens.json")
        if f.exists():
            screens_json = f.read_text(errors="replace")
    except Exception:
        pass

    body = """
<div class="grid">
  <div class="card">
    <h2>Calibration FullDMD</h2>
    <p>Déplace et étire le rectangle pour représenter la zone visible du FullDMD.</p>
    <p>Config sauvegardée dans :</p>
    <p><code>/opt/pincabos/config/fulldmd-calibration.json</code></p>
    <p><code>/home/pinball/.config/vpinfe/vpinfe.ini</code></p>
    <p><code>/home/pinball/.local/share/VPinballX/10.8/VPinballX.ini</code></p>

    <label class="fulldmd-section-label">Écran FullDMD / DMD Screen ID</label>

    <div class="fulldmd-config-layout">
      <div class="fulldmd-fields-row">
        <div class="fulldmd-field">
          <label for="screen_id">Écran / Screen ID</label>
          <input id="screen_id" type="text" value="__SCREEN_ID__">
        </div>

        <div class="fulldmd-field">
          <label for="x">X</label>
          <input id="x" type="number" value="__X__">
        </div>

        <div class="fulldmd-field">
          <label for="y">Y</label>
          <input id="y" type="number" value="__Y__">
        </div>

        <div class="fulldmd-field">
          <label for="w">Largeur</label>
          <input id="w" type="number" value="__W__">
        </div>

        <div class="fulldmd-field">
          <label for="h">Hauteur</label>
          <input id="h" type="number" value="__H__">
        </div>
      </div>

      <div class="fulldmd-actions-column">
        __FULLDMD_TOGGLE_BUTTON__

        <form action="/restart-vpinfe" method="post">
          <button class="button secondary fulldmd-action-btn" type="submit">Appliquer FullDMD</button>
        </form>

        <a class="button secondary fulldmd-action-btn" href="/fulldmd">Rafraîchir</a>

        <button class="button fulldmd-action-btn" onclick="saveCal()">Sauvegarder FullDMD</button>
      </div>
    </div>

    <p id="save-status" class="warn"></p>
  </div>

  <div class="card">
    <h2>Écrans détectés</h2>
    <pre>__SCREENS_JSON__</pre>
  </div>
</div>

<div class="card" style="margin-top:20px;">
  <h2>Log temps réel FullDMD</h2>
  <p>Cette section affiche les dernières opérations de calibration FullDMD.</p>
  <iframe src="/fulldmd-log-page" style="width:100%; height:520px; border:1px solid #5f2a91; border-radius:12px; background:#050007;"></iframe>
</div>

<script>
async function refreshFullDmdLog() {
  const el = document.getElementById('fulldmd-live-log');
  if (!el) {
    return;
  }

  try {
    const r = await fetch('/api/fulldmd/status?ts=' + Date.now());
    const data = await r.json();

    const now = new Date().toLocaleTimeString();
    el.textContent =
      "[Dernier rafraîchissement: " + now + "]\\n\\n" +
      (data.log || "Aucun log FullDMD pour le moment.");

    el.scrollTop = el.scrollHeight;
  } catch (e) {
    el.textContent = "Erreur lecture log FullDMD: " + e;
  }
}

refreshFullDmdLog();
setInterval(refreshFullDmdLog, 1000);
</script>
</div>

<script>
const stage = document.getElementById('stage');
const rect = document.getElementById('rect');
const handle = document.getElementById('handle');

let dragging = false;
let resizing = false;
let startX = 0;
let startY = 0;
let startLeft = 0;
let startTop = 0;
let startW = 0;
let startH = 0;

function num(id) {
  return parseInt(document.getElementById(id).value || '0', 10);
}

function syncInputs() {
  document.getElementById('x').value = parseInt(rect.style.left, 10) || 0;
  document.getElementById('y').value = parseInt(rect.style.top, 10) || 0;
  document.getElementById('w').value = parseInt(rect.style.width, 10) || 0;
  document.getElementById('h').value = parseInt(rect.style.height, 10) || 0;
}

function applyInputs() {
  rect.style.left = num('x') + 'px';
  rect.style.top = num('y') + 'px';
  rect.style.width = num('w') + 'px';
  rect.style.height = num('h') + 'px';
}

['x','y','w','h'].forEach(id => {
  document.getElementById(id).addEventListener('input', applyInputs);
});

rect.addEventListener('mousedown', e => {
  if (e.target === handle) return;
  dragging = true;
  startX = e.clientX;
  startY = e.clientY;
  startLeft = parseInt(rect.style.left, 10) || 0;
  startTop = parseInt(rect.style.top, 10) || 0;
  e.preventDefault();
});

handle.addEventListener('mousedown', e => {
  resizing = true;
  startX = e.clientX;
  startY = e.clientY;
  startW = parseInt(rect.style.width, 10) || 0;
  startH = parseInt(rect.style.height, 10) || 0;
  e.preventDefault();
  e.stopPropagation();
});

document.addEventListener('mousemove', e => {
  if (dragging) {
    let left = startLeft + (e.clientX - startX);
    let top = startTop + (e.clientY - startY);
    left = Math.max(0, Math.min(left, stage.clientWidth - rect.offsetWidth));
    top = Math.max(0, Math.min(top, stage.clientHeight - rect.offsetHeight));
    rect.style.left = left + 'px';
    rect.style.top = top + 'px';
    syncInputs();
  }

  if (resizing) {
    let w = startW + (e.clientX - startX);
    let h = startH + (e.clientY - startY);
    w = Math.max(40, Math.min(w, stage.clientWidth - (parseInt(rect.style.left, 10) || 0)));
    h = Math.max(30, Math.min(h, stage.clientHeight - (parseInt(rect.style.top, 10) || 0)));
    rect.style.width = w + 'px';
    rect.style.height = h + 'px';
    syncInputs();
  }
});

document.addEventListener('mouseup', () => {
  dragging = false;
  resizing = false;
});

function centerRect() {
  const w = parseInt(rect.style.width, 10) || 800;
  const h = parseInt(rect.style.height, 10) || 300;
  rect.style.left = Math.max(0, Math.floor((stage.clientWidth - w) / 2)) + 'px';
  rect.style.top = Math.max(0, Math.floor((stage.clientHeight - h) / 2)) + 'px';
  syncInputs();
}

function fitRect() {
  rect.style.left = '0px';
  rect.style.top = '0px';
  rect.style.width = stage.clientWidth + 'px';
  rect.style.height = stage.clientHeight + 'px';
  syncInputs();
}

async function saveCal() {
  const payload = {
    screen_id: document.getElementById('screen_id').value,
    x: num('x'),
    y: num('y'),
    width: num('w'),
    height: num('h')
  };

  const r = await fetch('/api/fulldmd/save', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload)
  });

  const data = await r.json();
  document.getElementById('save-status').textContent = data.message || 'Sauvegardé';
}
</script>
</div>
"""
    body = body.replace("__SCREEN_ID__", esc(cal.get("screen_id", "")))
    body = body.replace("__X__", esc(cal.get("x", 0)))
    body = body.replace("__Y__", esc(cal.get("y", 0)))
    body = body.replace("__W__", esc(cal.get("width", 800)))
    body = body.replace("__H__", esc(cal.get("height", 300)))
    body = body.replace("__SCREENS_JSON__", esc(screens_json))
    body = body.replace("__FULLDMD_TOGGLE_BUTTON__", pincabos_fulldmd_toggle_button())

    return page("FullDMD", body)


@app.route("/api/fulldmd/status")
def api_fulldmd_status():
    parts = []

    parts.append("===== Log temps réel FullDMD =====")
    live_log = Path("/opt/pincabos/logs/fulldmd-live.log")
    try:
        if live_log.exists():
            parts.append(live_log.read_text(errors="replace")[-12000:])
        else:
            parts.append("Aucun log live FullDMD trouvé.")
    except Exception as e:
        parts.append(f"Erreur lecture live log: {e}")

    parts.append("")
    parts.append("===== Calibration sauvegardée =====")
    cfg = Path("/opt/pincabos/config/fulldmd-calibration.json")
    try:
        if cfg.exists():
            parts.append(cfg.read_text(errors="replace"))
        else:
            parts.append("Aucune calibration FullDMD sauvegardée.")
    except Exception as e:
        parts.append(f"Erreur lecture calibration: {e}")

    parts.append("")
    parts.append("===== VPinFE Displays =====")
    try:
        ini = Path("/home/pinball/.config/vpinfe/vpinfe.ini")
        lines = ini.read_text(errors="replace").splitlines()
        in_displays = False

        for line in lines:
            s = line.strip()

            if s.lower() == "[displays]":
                in_displays = True
                parts.append(line)
                continue

            if in_displays and s.startswith("[") and s.endswith("]"):
                break

            if in_displays:
                if any(k in line.lower() for k in [
                    "dmdscreenid",
                    "dmdwindowoverride",
                    "bgscreenid",
                    "tablescreenid",
                    "cabmode"
                ]):
                    parts.append(line)

    except Exception as e:
        parts.append(f"Erreur lecture vpinfe.ini: {e}")

    parts.append("")
    parts.append("===== VPX PinCabOs.FullDMD =====")
    try:
        ini = Path("/home/pinball/.local/share/VPinballX/10.8/VPinballX.ini")
        lines = ini.read_text(errors="replace").splitlines()
        in_section = False

        for line in lines:
            s = line.strip()

            if s.lower() == "[pincabos.fulldmd]":
                in_section = True
                parts.append(line)
                continue

            if in_section and s.startswith("[") and s.endswith("]"):
                break

            if in_section:
                parts.append(line)

    except Exception as e:
        parts.append(f"Erreur lecture VPinballX.ini: {e}")

    parts.append("")
    parts.append("===== Process calibration =====")
    parts.append(
        run_cmd(
            ["bash", "--noprofile", "--norc", "-c", "ps aux | grep -Ei 'pincabos-fulldmd-calibrator|fulldmd-screen' | grep -v grep || true"],
            timeout=5
        )
    )

    return jsonify({"ok": True, "log": "\n".join(parts)})


@app.route("/api/fulldmd/save", methods=["POST"])
def api_fulldmd_save():
    try:
        data = request.get_json(force=True)
        save_fulldmd_to_configs(data)
        try:
            live_log = Path("/opt/pincabos/logs/fulldmd-live.log")
            live_log.parent.mkdir(parents=True, exist_ok=True)
            with live_log.open("a") as f:
                f.write("\n==================================================\n")
                f.write("Sauvegarde FullDMD depuis calibrateur Web\n")
                f.write(f"screen_id={data.get('screen_id', '')}\n")
                f.write(f"x={data.get('x', 0)}\n")
                f.write(f"y={data.get('y', 0)}\n")
                f.write(f"width={data.get('width', 0)}\n")
                f.write(f"height={data.get('height', 0)}\n")
                f.write(f"geometry={data.get('x', 0)},{data.get('y', 0)},{data.get('width', 0)},{data.get('height', 0)}\n")
                f.write("==================================================\n")
        except Exception:
            pass
        try:
            log = Path("/opt/pincabos/logs/fulldmd-calibration.log")
            log.parent.mkdir(parents=True, exist_ok=True)
            log.write_text(
                "Dernière sauvegarde FullDMD\\n"
                f"screen_id={data.get('screen_id', '')}\\n"
                f"x={data.get('x', 0)}\\n"
                f"y={data.get('y', 0)}\\n"
                f"width={data.get('width', 0)}\\n"
                f"height={data.get('height', 0)}\\n"
                f"geometry={data.get('x', 0)},{data.get('y', 0)},{data.get('width', 0)},{data.get('height', 0)}\\n"
            )
        except Exception:
            pass
        return jsonify({"ok": True, "message": "Calibration FullDMD sauvegardée."})
    except Exception as e:
        return jsonify({"ok": False, "message": f"Erreur: {e}"}), 500


# === PINCABOS FULLDMD TOGGLE BUTTON START ===
FULLDMD_ACTIVE_STATE = Path("/run/pincabos-fulldmd-calibrator.active")

def pincabos_fulldmd_calibrator_running():
    """
    Détection calibrateur FullDMD.

    1) Fichier runtime créé au lancement Web.
    2) Process avec /fulldmd-screen.
    3) Fenêtre X11 avec titre FullDMD si disponible.
    """
    import os
    import subprocess
    import time
    from pathlib import Path

    # État WebApp : créé quand /launch-fulldmd-calibrator est appelé,
    # supprimé quand /close-fulldmd-calibrator est appelé.
    try:
        if FULLDMD_ACTIVE_STATE.exists():
            age = time.time() - FULLDMD_ACTIVE_STATE.stat().st_mtime
            # Évite un état éternel si la machine reste ouverte très longtemps.
            if age < 86400:
                return True
            else:
                FULLDMD_ACTIVE_STATE.unlink(missing_ok=True)
    except Exception:
        pass

    my_pid = os.getpid()

    try:
        for proc in Path("/proc").iterdir():
            if not proc.name.isdigit():
                continue

            pid = int(proc.name)
            if pid == my_pid:
                continue

            try:
                raw = (proc / "cmdline").read_bytes()
            except Exception:
                continue

            if not raw:
                continue

            cmd = raw.replace(b"\x00", b" ").decode("utf-8", "replace")
            low = cmd.lower()

            if "pincabos-fulldmd-calibrator" in low:
                return True

            if "fulldmd-screen" in low:
                return True

            if ("chromium" in low or "chrome" in low) and "fulldmd" in low:
                return True

    except Exception:
        pass

    # Fallback fenêtre X11.
    try:
        env = os.environ.copy()
        env["DISPLAY"] = ":0"
        env["XAUTHORITY"] = "/home/pinball/.Xauthority"

        r = subprocess.run(
            ["/bin/bash", "--noprofile", "--norc", "-c",
             "wmctrl -l 2>/dev/null | grep -Ei 'FullDMD|fulldmd|PinCabOs FullDMD'"],
            capture_output=True,
            text=True,
            timeout=4,
            env=env
        )
        if r.returncode == 0 and r.stdout.strip():
            return True
    except Exception:
        pass

    return False

def pincabos_fulldmd_toggle_button():
    if pincabos_fulldmd_calibrator_running():
        return """
        <form action="/close-fulldmd-calibrator" method="post">
          <button class="button fulldmd-action-btn fulldmd-toggle-active" type="submit"
                  style="background:#ff7a00 !important;color:#160020 !important;border:1px solid #ffb000 !important;box-shadow:0 0 18px rgba(255,122,0,.9),0 0 28px rgba(255,176,0,.45) !important;">
            Fermer calibration
          </button>
        </form>
        """
    return """
        <form action="/launch-fulldmd-calibrator" method="post">
          <button class="button secondary fulldmd-action-btn fulldmd-toggle-inactive" type="submit">
            Ouvrir calibration
          </button>
        </form>
        """


@app.route("/close-fulldmd-calibrator", methods=["POST"])
def close_fulldmd_calibrator():
    import time
    import subprocess
    from pathlib import Path
    from datetime import datetime
    from flask import redirect, url_for

    live_log = Path("/opt/pincabos/logs/fulldmd-live.log")
    live_log.parent.mkdir(parents=True, exist_ok=True)

    try:
        with live_log.open("a") as f:
            f.write("\\n==================================================\\n")
            f.write(datetime.now().strftime("%F %T") + " - Fermeture calibration FullDMD demandée depuis WebApp\\n")
            f.write("==================================================\\n")
    except Exception:
        pass

    subprocess.run(
        ["/bin/bash", "--noprofile", "--norc", "-c",
         "pkill -f 'pincabos-fulldmd-calibrator|/fulldmd-screen' 2>/dev/null || true"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=8
    )

    try:
        FULLDMD_ACTIVE_STATE.unlink(missing_ok=True)
    except Exception:
        pass

    time.sleep(3)
    return redirect(url_for("fulldmd_page"))
# === PINCABOS FULLDMD TOGGLE BUTTON END ===


@app.route("/launch-fulldmd-calibrator", methods=["POST"])
def launch_fulldmd_calibrator():
    import time
    from datetime import datetime
    subprocess.Popen(
        ["/usr/bin/sudo", "/opt/pincabos/tools/launch-fulldmd-calibrator.sh"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        FULLDMD_ACTIVE_STATE.write_text(datetime.now().isoformat(timespec="seconds") + "\n", encoding="utf-8")
        FULLDMD_ACTIVE_STATE.chmod(0o666)
    except Exception:
        pass

    time.sleep(3)
    return redirect(url_for("fulldmd_page"))


@app.route("/fulldmd-screen")
def fulldmd_screen():
    cal = load_fulldmd_calibration()

    body = """
<!doctype html>
<html>
<head>
  <title>PinCabOs FullDMD Calibration</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">

  <style>
    html, body {
      margin: 0;
      padding: 0;
      overflow: hidden;
      width: 100%;
      height: 100%;
      background: #000;
      font-family: Arial, sans-serif;
      color: white;
    }

    #stage {
      position: relative;
      width: 100vw;
      height: 100vh;
      overflow: hidden;
      background:
        linear-gradient(45deg, rgba(255,255,255,0.06) 25%, transparent 25%),
        linear-gradient(-45deg, rgba(255,255,255,0.06) 25%, transparent 25%),
        linear-gradient(45deg, transparent 75%, rgba(255,255,255,0.06) 75%),
        linear-gradient(-45deg, transparent 75%, rgba(255,255,255,0.06) 75%);
      background-size: 40px 40px;
      background-position: 0 0, 0 20px, 20px -20px, -20px 0px;
    }

    #stage::before {
      content: "";
      position: absolute;
      inset: 0;
      background-image: url('/static/pincabos-logo.png');
      background-repeat: no-repeat;
      background-position: center center;
      background-size: min(60vw, 700px) auto;
      opacity: 0.10;
      pointer-events: none;
      z-index: 1;
    }

    #rect {
      position: absolute;
      left: __X__px;
      top: __Y__px;
      width: __W__px;
      height: __H__px;
      min-width: 360px;
      min-height: 250px;
      border: 4px solid #00eaff;
      background: rgba(0,234,255,0.14);
      box-shadow: 0 0 28px rgba(0,234,255,0.95);
      cursor: move;
      box-sizing: border-box;
      z-index: 200;
      overflow: visible;
    }

    #edge-label {
      position: absolute;
      left: 10px;
      top: 10px;
      color: #fff;
      background: rgba(0,0,0,0.65);
      padding: 5px 8px;
      border-radius: 8px;
      font-weight: bold;
      border: 1px solid #00eaff;
      z-index: 220;
      pointer-events: none;
    }

    #inside-panel {
      position: absolute;
      left: 50%;
      top: 50%;
      transform: translate(-50%, -50%);
      min-width: 320px;
      max-width: 92%;
      background: rgba(10,0,20,0.88);
      border: 1px solid #ff7a00;
      border-radius: 14px;
      padding: 12px;
      box-shadow: 0 0 25px rgba(255,122,0,0.55);
      text-align: center;
      z-index: 230;
      cursor: default;
    }

    #title {
      font-weight: bold;
      color: #ffb000;
      margin-bottom: 6px;
      text-shadow: 0 0 12px rgba(255,122,0,0.7);
    }

    #hint {
      font-size: 12px;
      color: #d8b8ff;
      margin-bottom: 8px;
    }

    input {
      width: 70px;
      padding: 5px;
      margin: 3px;
      background: #111;
      color: #fff;
      border: 1px solid #ff7a00;
      border-radius: 6px;
      text-align: center;
    }

    button {
      background: #ff7a00;
      color: #160020;
      border: none;
      padding: 8px 10px;
      margin: 4px 2px;
      border-radius: 8px;
      font-weight: bold;
      cursor: pointer;
    }

    button.secondary {
      background: #5f2a91;
      color: white;
      border: 1px solid #ff7a00;
    }

    #status {
      color: #00ff99;
      font-weight: bold;
      margin-top: 6px;
      min-height: 18px;
      font-size: 13px;
    }

    #handle {
      position:absolute;
      right:-12px;
      bottom:-12px;
      width:26px;
      height:26px;
      background:#ff7a00;
      border:3px solid white;
      border-radius:50%;
      cursor:nwse-resize;
      z-index: 250;
      box-shadow: 0 0 15px rgba(255,122,0,0.9);
    }
  </style>
<link rel="icon" type="image/png" href="/static/branding/favicon.png?v=branding">
</head>

<body>
  <div id="stage">
    <div id="rect">
      <div id="edge-label">FullDMD Visible Area</div>

      <div id="inside-panel">
        <div id="title">PinCabOs FullDMD Calibration</div>
        <div id="hint">Déplace la zone bleue. Étire avec le point orange.</div>

        <div>
          X <input id="x" type="number" value="__X__">
          Y <input id="y" type="number" value="__Y__">
        </div>

        <div>
          W <input id="w" type="number" value="__W__">
          H <input id="h" type="number" value="__H__">
        </div>

        <div>
          Screen ID <input id="screen_id" type="text" value="__SCREEN_ID__">
        </div>

        <button onclick="saveCal()">Sauvegarder</button>
        <button class="secondary" onclick="centerRect()">Centrer</button>
        <button class="secondary" onclick="fitRect()">Plein écran</button>
        <button class="secondary" onclick="window.close()">Fermer</button>

        <div id="status"></div>
      </div>

      <div id="handle"></div>
    </div>
  </div>

<script>
const stage = document.getElementById('stage');
const rect = document.getElementById('rect');
const handle = document.getElementById('handle');
const panel = document.getElementById('inside-panel');

let dragging = false;
let resizing = false;
let startX = 0;
let startY = 0;
let startLeft = 0;
let startTop = 0;
let startW = 0;
let startH = 0;

function num(id) {
  return parseInt(document.getElementById(id).value || '0', 10);
}

function syncInputs() {
  document.getElementById('x').value = parseInt(rect.style.left, 10) || 0;
  document.getElementById('y').value = parseInt(rect.style.top, 10) || 0;
  document.getElementById('w').value = parseInt(rect.style.width, 10) || 0;
  document.getElementById('h').value = parseInt(rect.style.height, 10) || 0;
}

function applyInputs() {
  rect.style.left = num('x') + 'px';
  rect.style.top = num('y') + 'px';
  rect.style.width = num('w') + 'px';
  rect.style.height = num('h') + 'px';
}

['x','y','w','h'].forEach(id => {
  document.getElementById(id).addEventListener('input', applyInputs);
});

panel.addEventListener('mousedown', e => {
  e.stopPropagation();
});

rect.addEventListener('mousedown', e => {
  if (e.target === handle) return;
  if (panel.contains(e.target)) return;

  dragging = true;
  startX = e.clientX;
  startY = e.clientY;
  startLeft = parseInt(rect.style.left, 10) || 0;
  startTop = parseInt(rect.style.top, 10) || 0;
  e.preventDefault();
});

handle.addEventListener('mousedown', e => {
  resizing = true;
  startX = e.clientX;
  startY = e.clientY;
  startW = parseInt(rect.style.width, 10) || 0;
  startH = parseInt(rect.style.height, 10) || 0;
  e.preventDefault();
  e.stopPropagation();
});

document.addEventListener('mousemove', e => {
  if (dragging) {
    let left = startLeft + (e.clientX - startX);
    let top = startTop + (e.clientY - startY);

    left = Math.max(0, Math.min(left, stage.clientWidth - rect.offsetWidth));
    top = Math.max(0, Math.min(top, stage.clientHeight - rect.offsetHeight));

    rect.style.left = left + 'px';
    rect.style.top = top + 'px';
    syncInputs();
  }

  if (resizing) {
    let w = startW + (e.clientX - startX);
    let h = startH + (e.clientY - startY);

    w = Math.max(360, Math.min(w, stage.clientWidth - (parseInt(rect.style.left, 10) || 0)));
    h = Math.max(250, Math.min(h, stage.clientHeight - (parseInt(rect.style.top, 10) || 0)));

    rect.style.width = w + 'px';
    rect.style.height = h + 'px';
    syncInputs();
  }
});

document.addEventListener('mouseup', () => {
  dragging = false;
  resizing = false;
});

function centerRect() {
  const w = parseInt(rect.style.width, 10) || 800;
  const h = parseInt(rect.style.height, 10) || 300;

  rect.style.left = Math.max(0, Math.floor((stage.clientWidth - w) / 2)) + 'px';
  rect.style.top = Math.max(0, Math.floor((stage.clientHeight - h) / 2)) + 'px';

  syncInputs();
}

function fitRect() {
  rect.style.left = '0px';
  rect.style.top = '0px';
  rect.style.width = stage.clientWidth + 'px';
  rect.style.height = stage.clientHeight + 'px';

  syncInputs();
}

async function saveCal() {
  const payload = {
    screen_id: document.getElementById('screen_id').value,
    x: num('x'),
    y: num('y'),
    width: num('w'),
    height: num('h')
  };

  const r = await fetch('/api/fulldmd/save', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload)
  });

  const data = await r.json();

  document.getElementById('status').textContent =
    data.message || 'Calibration FullDMD sauvegardée.';
}
</script>
</body>
</html>
"""

    body = body.replace("__SCREEN_ID__", esc(cal.get("screen_id", "")))
    body = body.replace("__X__", esc(cal.get("x", 0)))
    body = body.replace("__Y__", esc(cal.get("y", 0)))
    body = body.replace("__W__", esc(cal.get("width", 800)))
    body = body.replace("__H__", esc(cal.get("height", 300)))

    return body

@app.route("/fulldmd-log-page")
def fulldmd_log_page():
    parts = []

    parts.append("===== Log temps réel FullDMD =====")
    live_log = Path("/opt/pincabos/logs/fulldmd-live.log")
    try:
        if live_log.exists():
            parts.append(live_log.read_text(errors="replace")[-12000:])
        else:
            parts.append("Aucun log live FullDMD trouvé.")
    except Exception as e:
        parts.append(f"Erreur lecture live log: {e}")

    parts.append("")
    parts.append("===== Calibration sauvegardée =====")
    cfg = Path("/opt/pincabos/config/fulldmd-calibration.json")
    try:
        if cfg.exists():
            parts.append(cfg.read_text(errors="replace"))
        else:
            parts.append("Aucune calibration FullDMD sauvegardée.")
    except Exception as e:
        parts.append(f"Erreur lecture calibration: {e}")

    parts.append("")
    parts.append("===== VPinFE Displays =====")
    try:
        ini = Path("/home/pinball/.config/vpinfe/vpinfe.ini")
        lines = ini.read_text(errors="replace").splitlines()
        in_displays = False
        for line in lines:
            s = line.strip()
            if s.lower() == "[displays]":
                in_displays = True
                parts.append(line)
                continue
            if in_displays and s.startswith("[") and s.endswith("]"):
                break
            if in_displays and any(k in line.lower() for k in ["dmdscreenid", "dmdwindowoverride", "bgscreenid", "tablescreenid", "cabmode"]):
                parts.append(line)
    except Exception as e:
        parts.append(f"Erreur lecture vpinfe.ini: {e}")

    parts.append("")
    parts.append("===== VPX PinCabOs.FullDMD =====")
    try:
        ini = Path("/home/pinball/.local/share/VPinballX/10.8/VPinballX.ini")
        lines = ini.read_text(errors="replace").splitlines()
        in_section = False
        for line in lines:
            s = line.strip()
            if s.lower() == "[pincabos.fulldmd]":
                in_section = True
                parts.append(line)
                continue
            if in_section and s.startswith("[") and s.endswith("]"):
                break
            if in_section:
                parts.append(line)
    except Exception as e:
        parts.append(f"Erreur lecture VPinballX.ini: {e}")

    parts.append("")
    parts.append("===== Process calibration =====")
    try:
        parts.append(run_cmd(["bash", "--noprofile", "--norc", "-c", "ps aux | grep -Ei 'pincabos-fulldmd-calibrator|fulldmd-screen' | grep -v grep || true"], timeout=5))
    except Exception as e:
        parts.append(f"Erreur process check: {e}")

    log_text = esc("\n".join(parts))

    return f"""<!doctype html>
<html>
<head>
  <meta http-equiv="refresh" content="1">
  <style>
    html, body {{
      margin: 0;
      padding: 0;
      background: #050007;
      color: #eee;
      font-family: monospace;
      font-size: 13px;
    }}
    pre {{
      white-space: pre-wrap;
      margin: 0;
      padding: 15px;
    }}
    .top {{
      color: #ffb000;
      padding: 8px 15px;
      border-bottom: 1px solid #5f2a91;
      font-family: Arial, sans-serif;
    }}
  </style>
<link rel="icon" type="image/png" href="/static/branding/favicon.png?v=branding">
</head>
<body>
  <div class="top">Dernier rafraîchissement automatique</div>
  <pre>{log_text}</pre>
</body>
</html>"""


@app.route("/console")
def console_page():
    ip = get_ip()

    body = f"""
<div class="grid">
  <div class="card">
    <h2>PinCab Console</h2>
    <p>Terminal Web PinCabOs.</p>
    <p>La console est protégée par un identifiant séparé.</p>
    <p>URL directe :</p>
    <p><code>http://{ip}:8090</code></p>
    <p>
      <a class="button" href="http://{ip}:8090" target="_blank">
        Ouvrir la console dans un nouvel onglet
      </a>
    </p>
    <p>Pour obtenir root dans la console :</p>
    <p><code>sudo -i</code></p>
  </div>
</div>

<div class="card" style="margin-top:20px;">
  <h2>Terminal</h2>
  <iframe
    src="http://{ip}:8090"
    style="width:100%; height:680px; border:1px solid #5f2a91; border-radius:12px; background:#000;">
  </iframe>
</div>
"""
    return page("Console", body)


@app.route("/root-password", methods=["POST"])
def root_password():
    p1 = request.form.get("password1", "")
    p2 = request.form.get("password2", "")

    if not p1 or not p2:
        body = """
<div class="card">
  <h2>Erreur</h2>
  <p class="bad">Le mot de passe ne peut pas être vide.</p>
  <p><a class="button" href="/console">Retour console</a></p>
</div>
"""
        return page("Console", body)

    if p1 != p2:
        body = """
<div class="card">
  <h2>Erreur</h2>
  <p class="bad">Les deux mots de passe ne correspondent pas.</p>
  <p><a class="button" href="/console">Retour console</a></p>
</div>
"""
        return page("Console", body)

    try:
        r = subprocess.run(
            ["/usr/bin/sudo", "/opt/pincabos/tools/change-root-password.sh"],
            input=p1 + "\\n",
            capture_output=True,
            text=True,
            timeout=10
        )

        if r.returncode == 0:
            msg = esc(r.stdout.strip() or "Mot de passe root changé.")
            body = f"""
<div class="card">
  <h2>Mot de passe root</h2>
  <p class="ok">{msg}</p>
  <p><a class="button" href="/console">Retour console</a></p>
</div>
"""
        else:
            msg = esc((r.stdout + r.stderr).strip())
            body = f"""
<div class="card">
  <h2>Erreur</h2>
  <p class="bad">Impossible de changer le mot de passe root.</p>
  <pre>{msg}</pre>
  <p><a class="button" href="/console">Retour console</a></p>
</div>
"""

    except Exception as e:
        body = f"""
<div class="card">
  <h2>Erreur</h2>
  <p class="bad">{esc(str(e))}</p>
  <p><a class="button" href="/console">Retour console</a></p>
</div>
"""

    return page("Console", body)


def network_info_text():
    return run_cmd(["/usr/bin/sudo", "/opt/pincabos/tools/network-info.sh"], timeout=15)


def network_current_mode():
    out = run_cmd(["/usr/bin/sudo", "/opt/pincabos/tools/network-current-mode.sh"], timeout=8)
    data = {}
    for line in out.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            data[k.strip()] = v.strip()
    return data


def network_main_iface():
    data = network_current_mode()
    return data.get("interface", "") or "non détectée"


def wifi_options_html():
    out = run_cmd(["/usr/bin/sudo", "/opt/pincabos/tools/wifi-scan.sh"], timeout=15)
    rows = []

    if not out.strip():
        return '<option value="">Aucun réseau WiFi détecté</option>'

    seen = set()
    for line in out.splitlines():
        parts = line.split("|")
        ssid = parts[0].strip() if len(parts) >= 1 else ""
        signal = parts[1].strip() if len(parts) >= 2 else ""
        security = parts[2].strip() if len(parts) >= 3 else ""

        if not ssid or ssid in seen:
            continue

        seen.add(ssid)
        label = ssid
        if signal:
            label += f" — signal {signal}%"
        if security:
            label += f" — {security}"

        rows.append(f'<option value="{esc(ssid)}">{esc(label)}</option>')

    return "\n".join(rows) if rows else '<option value="">Aucun réseau WiFi détecté</option>'


@app.route("/network")
def network_page():
    info = network_info_text()
    mode_data = network_current_mode()

    iface = mode_data.get("interface", "non détectée")
    current_mode = mode_data.get("mode", "inconnu")
    current_ipcidr = mode_data.get("ipcidr", "")
    current_gateway = mode_data.get("gateway", "")
    current_dns = mode_data.get("dns", "")

    wifi_options = wifi_options_html()

    dhcp_selected = "selected" if current_mode != "static" else ""
    static_selected = "selected" if current_mode == "static" else ""

    body = f"""
<div class="grid">
  
<div class="card" style="margin-top:20px;">
  <h2>Nom du système</h2>

  <p>
    Modifie le nom Linux du système et le nom NetBIOS/SMB visible sur le réseau.
  </p>

  <form action="/network/hostname" method="post"
        onsubmit="return confirm('Changer le nom du système peut nécessiter quelques minutes avant d’être visible sur le réseau. Continuer ?');">

    <label>Nom système / hostname</label><br>
    <input name="hostname" value="__CURRENT_HOSTNAME__" placeholder="exemple: pincabos"
           style="width:90%; padding:8px;"><br><br>

    <label>Nom NetBIOS / SMB</label><br>
    <input name="netbios" value="__CURRENT_NETBIOS__" maxlength="15" placeholder="exemple: PINCABOS"
           style="width:90%; padding:8px;"><br>

    <p class="warn">
      NetBIOS est limité à 15 caractères. Utilise idéalement lettres, chiffres et tirets.
    </p>

    <button class="button" type="submit">Appliquer le nom du système</button>
  </form>
</div>


<div class="card">
    <h2>État réseau</h2>

    <p>
      Interface principale détectée :
      <code>{esc(iface)}</code>
    </p>

    <p>
      Mode détecté :
      <code>{esc(current_mode)}</code>
    </p>

    <p>
      IPv4 actuelle :
      <code>{esc(current_ipcidr or "non détectée")}</code>
    </p>

    <p>
      Passerelle :
      <code>{esc(current_gateway or "non détectée")}</code>
    </p>

    <p>
      DNS :
      <code>{esc(current_dns or "non détecté")}</code>
    </p>

    <p class="warn">
      Si tu appliques une IP fixe, la WebApp sera ensuite accessible à la nouvelle IP.
      Un avertissement apparaîtra avant l’application.
    </p>
  </div>

  <div class="card">
    
<h2>Mode réseau</h2>

    <p>
      Interface utilisée :
      <code>{esc(iface)}</code>
    </p>

    <form action="/network/apply-mode" method="post" onsubmit="return confirmNetworkChange(this);">
      <input type="hidden" name="iface" value="{esc(iface)}">

      <label>Mode</label><br>
      <select name="mode" id="network_mode" onchange="toggleStaticFields()" style="width:90%; padding:8px; margin:6px 0;">
        <option value="dhcp" {dhcp_selected}>DHCP automatique</option>
        <option value="static" {static_selected}>IP fixe</option>
      </select><br>

      <div id="static_fields" style="display:none;">
        <label>Adresse IP/CIDR</label><br>
        <input name="ipcidr" value="{esc(current_ipcidr or "192.168.254.213/24")}" style="width:90%; padding:8px; margin:6px 0;"><br>

        <label>Passerelle</label><br>
        <input name="gateway" value="{esc(current_gateway or "192.168.254.1")}" style="width:90%; padding:8px; margin:6px 0;"><br>

        <label>DNS</label><br>
        <input name="dns" value="{esc(current_dns or "1.1.1.1,8.8.8.8")}" style="width:90%; padding:8px; margin:6px 0;"><br>
      </div>

      <button class="button" type="submit">Appliquer la configuration réseau</button>
    </form>

    <script>
      function toggleStaticFields() {{
        const mode = document.getElementById("network_mode").value;
        const box = document.getElementById("static_fields");
        box.style.display = mode === "static" ? "block" : "none";
      }}

      function confirmNetworkChange(form) {{
        const mode = document.getElementById("network_mode").value;

        if (mode === "dhcp") {{
          return confirm(
            "Tu vas configurer PinCabOs en DHCP.\\n\\n" +
            "L'adresse IP pourrait changer selon ton routeur.\\n" +
            "Après l'application, vérifie la nouvelle IP dans ton routeur ou avec la console PinCabOs.\\n\\n" +
            "Continuer?"
          );
        }}

        const ipcidr = form.querySelector('input[name="ipcidr"]').value || "";
        const ip = ipcidr.split("/")[0];

        return confirm(
          "Tu vas appliquer une IP fixe à PinCabOs.\\n\\n" +
          "Nouvelle IP : " + ip + "\\n" +
          "Nouvelle URL WebApp probable : http://" + ip + ":8080\\n\\n" +
          "Si l'adresse, le masque ou la passerelle sont incorrects, tu pourrais perdre l'accès réseau.\\n\\n" +
          "Continuer?"
        );
      }}

      toggleStaticFields();
    </script>
  </div>
</div>

<div class="grid" style="margin-top:20px;">
  <div class="card">
    <h2>WiFi — joindre un réseau</h2>

    <p>
      Sélectionne un réseau WiFi détecté par PinCabOs.
    </p>

    <form action="/network/wifi-join" method="post">
      <label>Réseau WiFi</label><br>
      <select name="ssid" style="width:90%; padding:8px; margin:6px 0;">
        {wifi_options}
      </select><br>

      <label>Mot de passe WiFi</label><br>
      <input name="password" type="password" placeholder="Mot de passe du réseau" style="width:90%; padding:8px; margin:6px 0;"><br>

      <button class="button" type="submit">Joindre le réseau WiFi</button>
      <a class="button secondary" href="/network" style="display:inline-block; text-decoration:none;">Rafraîchir scan WiFi</a>
    </form>
  </div>

  <div class="card">
    <h2>WiFi — Hotspot PinCabOs</h2>

    <p>
      Permet de créer un réseau WiFi temporaire pour configurer PinCabOs.
      Nécessite une carte WiFi compatible mode AP/hotspot.
    </p>

    <form action="/network/wifi-hotspot" method="post">
      <label>SSID hotspot</label><br>
      <input name="ssid" value="PinCabOs_WiFi" style="width:90%; padding:8px; margin:6px 0;"><br>

      <label>Mot de passe hotspot</label><br>
      <input name="password" type="password" value="Pinball123$" style="width:90%; padding:8px; margin:6px 0;"><br>

      <button class="button" type="submit">Activer le hotspot</button>
    </form>

    <form action="/network/wifi-hotspot-stop" method="post" style="margin-top:10px;">
      <button class="button secondary" type="submit">Désactiver le hotspot</button>
    </form>
  </div>
</div>

<div class="card" style="margin-top:20px;">
  <h2>Détails réseau complets</h2>
  <pre>{esc(info)}</pre>
</div>
"""
    current_hostname = subprocess.run(["hostname"], capture_output=True, text=True).stdout.strip() or "pincabos"
    current_netbios = current_hostname.upper()[:15]
    try:
        cfg = Path("/etc/pincabos/system-name.conf")
        if cfg.exists():
            for line in cfg.read_text(errors="replace").splitlines():
                if line.startswith("netbios="):
                    current_netbios = line.split("=", 1)[1].strip() or current_netbios
    except Exception:
        pass

    body = body.replace("__CURRENT_HOSTNAME__", esc(current_hostname))
    body = body.replace("__CURRENT_NETBIOS__", esc(current_netbios))

    return page("Réseau", body)


def network_action_result(title, output):
    body = f"""
<div class="card">
  <h2>{esc(title)}</h2>
  <pre>{esc(output)}</pre>
  <p><a class="button" href="/network">Retour Réseau</a></p>
</div>
"""
    return page("Réseau", body)


@app.route("/network/apply-mode", methods=["POST"])
def network_apply_mode():
    iface = request.form.get("iface", "").strip()
    mode = request.form.get("mode", "dhcp").strip()

    if mode == "dhcp":
        out = run_cmd(
            ["/usr/bin/sudo", "/opt/pincabos/tools/network-set-dhcp.sh", iface],
            timeout=30
        )
        return network_action_result("Configuration réseau — DHCP", out)

    if mode == "static":
        ipcidr = request.form.get("ipcidr", "").strip()
        gateway = request.form.get("gateway", "").strip()
        dns = request.form.get("dns", "").strip() or "1.1.1.1,8.8.8.8"

        out = run_cmd(
            ["/usr/bin/sudo", "/opt/pincabos/tools/network-set-static.sh", iface, ipcidr, gateway, dns],
            timeout=30
        )
        return network_action_result("Configuration réseau — IP fixe", out)

    return network_action_result("Configuration réseau", "Mode invalide.")


@app.route("/network/wifi-join", methods=["POST"])
def network_wifi_join():
    ssid = request.form.get("ssid", "").strip()
    password = request.form.get("password", "")

    out = run_cmd(
        ["/usr/bin/sudo", "/opt/pincabos/tools/wifi-join.sh", ssid, password],
        timeout=40
    )
    return network_action_result("Connexion WiFi", out)


@app.route("/network/wifi-hotspot", methods=["POST"])
def network_wifi_hotspot():
    ssid = request.form.get("ssid", "PinCabOs_WiFi").strip() or "PinCabOs_WiFi"
    password = request.form.get("password", "Pinball123$") or "Pinball123$"

    out = run_cmd(
        ["/usr/bin/sudo", "/opt/pincabos/tools/wifi-hotspot.sh", ssid, password],
        timeout=40
    )
    return network_action_result("Hotspot WiFi — activation", out)


@app.route("/network/wifi-hotspot-stop", methods=["POST"])
def network_wifi_hotspot_stop():
    out = run_cmd(
        ["/usr/bin/sudo", "/opt/pincabos/tools/wifi-hotspot-stop.sh"],
        timeout=30
    )
    return network_action_result("Hotspot WiFi — désactivation", out)


@app.route("/toggle-webapp-screen", methods=["POST"])
def toggle_webapp_screen():
    try:
        screen = request.form.get("screen", "").strip().lower()

        if screen not in ["playfield", "backglass"]:
            return redirect(request.referrer or url_for("dashboard"))

        conf_path = Path("/opt/pincabos/config/webapp-screen-autostart.conf")
        conf_path.parent.mkdir(parents=True, exist_ok=True)

        state = {"playfield": "0", "backglass": "1"}

        if conf_path.exists():
            for line in conf_path.read_text(errors="replace").splitlines():
                line = line.strip()
                if "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip().upper()
                v = "1" if v.strip() == "1" else "0"

                if k == "PLAYFIELD":
                    state["playfield"] = v
                elif k == "BACKGLASS":
                    state["backglass"] = v

        state[screen] = "0" if state.get(screen) == "1" else "1"

        conf_path.write_text(
            f"PLAYFIELD={state['playfield']}\nBACKGLASS={state['backglass']}\n"
        )

        subprocess.Popen(
            ["/usr/bin/sudo", "/opt/pincabos/tools/close-webapp-screen.sh"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

        if state["playfield"] == "1":
            subprocess.Popen(
                ["/usr/bin/bash", "-lc", "sleep 1; /usr/bin/sudo /opt/pincabos/tools/launch-webapp-screen.sh 0 http://127.0.0.1/"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )

        if state["backglass"] == "1":
            subprocess.Popen(
                ["/usr/bin/bash", "-lc", "sleep 1; /usr/bin/sudo /opt/pincabos/tools/launch-webapp-screen.sh 1 http://127.0.0.1/"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )

        return redirect(request.referrer or url_for("dashboard"))

    except Exception as e:
        return f"Erreur toggle écran WebApp: {e}", 500


@app.route("/launch-webapp-screen", methods=["POST"])
def launch_webapp_screen():
    screen = request.form.get("screen", "0").strip()

    if screen not in ["0", "1", "2"]:
        screen = "0"

    subprocess.Popen(
        ["/usr/bin/sudo", "/opt/pincabos/tools/launch-webapp-screen.sh", screen, "http://127.0.0.1/"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    return redirect(request.referrer or url_for("dashboard"))


@app.route("/close-webapp-screen", methods=["POST"])
def close_webapp_screen():
    subprocess.Popen(
        ["/usr/bin/sudo", "/opt/pincabos/tools/close-webapp-screen.sh"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    return redirect(request.referrer or url_for("dashboard"))


AUDIO_ROUTER_CONFIG = Path("/opt/pincabos/config/audio-router.json")

AUDIO_ROUTER_DEFAULT_CONFIG = {
    "audio_mode": "dual",
    "audio_backend": "alsa",
    "backbox_device": "",
    "playfield_device": "",
    "surround_device": "",
    "bass_device": "",
    "ssf_mode": "7.1",
    "invert_lr": False,
    "invert_front_rear": False,
    "enable_bass": True,
    "night_mode": False
}


def audio_run_cmd(cmd, timeout=5):
    try:
        r = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return (r.stdout or "").strip()
    except Exception as e:
        return str(e)


def audio_load_config():
    cfg = AUDIO_ROUTER_DEFAULT_CONFIG.copy()

    if not AUDIO_ROUTER_CONFIG.exists():
        return cfg

    try:
        data = json.loads(AUDIO_ROUTER_CONFIG.read_text(errors="replace"))
        if isinstance(data, dict):
            cfg.update(data)
    except Exception:
        pass

    return cfg


def audio_save_config(cfg):
    pincabos_backup_config_file(AUDIO_ROUTER_CONFIG, "Audio / SSF V2 Save")
    pincabos_write_json_with_meta(AUDIO_ROUTER_CONFIG, cfg, "Audio / SSF V2 Save")


def audio_detect_alsa_devices():
    devices = []
    output = audio_run_cmd("aplay -l || true")

    for line in output.splitlines():
        line = line.strip()

        if not line.startswith("card "):
            continue

        m = re.match(
            r"card\s+(\d+):\s+(.+?)\s+\[(.+?)\],\s+device\s+(\d+):\s+(.+?)\s+\[(.+?)\]",
            line
        )

        if not m:
            continue

        card_num = m.group(1).strip()
        card_short = m.group(2).strip()
        card_name = m.group(3).strip()
        device_num = m.group(4).strip()
        device_short = m.group(5).strip()
        device_name = m.group(6).strip()

        devices.append({
            "id": f"hw:{card_num},{device_num}",
            "card": card_num,
            "device": device_num,
            "name": f"{card_name} / {device_name}",
            "description": f"{card_short} / {device_short}",
        })

    return devices, output


def audio_device_options(selected):
    devices, _raw = audio_detect_alsa_devices()
    rows = ['<option value="">Non configuré</option>']

    for dev in devices:
        dev_id = dev["id"]
        label = f'{dev["name"]} — {dev_id}'
        sel = "selected" if selected == dev_id else ""
        rows.append(f'<option value="{esc(dev_id)}" {sel}>{esc(label)}</option>')

    return "\n".join(rows)


def audio_bool_checked(cfg, key):
    return "checked" if cfg.get(key) else ""


def audio_selected(cfg, key, value):
    return "selected" if cfg.get(key) == value else ""


def audio_config_rows():
    cfg = audio_load_config()

    labels = [
        ("Mode audio", "audio_mode"),
        ("Backend", "audio_backend"),
        ("Backbox / ROM / Musique", "backbox_device"),
        ("Playfield / SSF", "playfield_device"),
        ("Surround VPX", "surround_device"),
        ("Bass shaker", "bass_device"),
        ("Mode SSF", "ssf_mode"),
        ("Inverser gauche / droite", "invert_lr"),
        ("Inverser avant / arrière", "invert_front_rear"),
        ("Bass activé", "enable_bass"),
        ("Mode nuit", "night_mode"),
    ]

    rows = []
    for label, key in labels:
        rows.append(f"<tr><td>{esc(label)}</td><td><code>{esc(cfg.get(key, '-'))}</code></td></tr>")

    return "\n".join(rows)


def audio_test_device(device_id, channels=2):
    if not device_id:
        return

    cmd = f"speaker-test -D {shlex_quote(device_id)} -c {int(channels)} -t wav -l 1"
    subprocess.Popen(
        cmd,
        shell=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


AUDIO_VPX_INI = Path("/home/pinball/.local/share/VPinballX/10.8/VPinballX.ini")
AUDIO_VPINFE_INI = Path("/home/pinball/.config/vpinfe/vpinfe.ini")
AUDIO_BACKUP_DIR = Path("/opt/pincabos/backups/audio-ssf")


def audio_backup_file(src):
    if not src.exists():
        return None

    AUDIO_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dst = AUDIO_BACKUP_DIR / f"{src.name}.backup-{stamp}"
    shutil.copy2(src, dst)
    return dst


def audio_comment(function_name):
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return f"; Modifié {stamp} par PinCabOS fonction({function_name})"


def audio_read_lines(path):
    if path.exists():
        return path.read_text(errors="replace").splitlines()
    return []


def audio_write_lines(path, lines):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n")


def audio_find_section(lines, section):
    section_header = f"[{section}]"
    start = None
    end = len(lines)

    for i, line in enumerate(lines):
        if line.strip().lower() == section_header.lower():
            start = i
            break

    if start is None:
        return None, None

    for j in range(start + 1, len(lines)):
        stripped = lines[j].strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            end = j
            break

    return start, end


def audio_set_ini_key_with_comment(lines, section, key, value, function_name):
    """
    Modifie une clé INI en conservant la structure existante.
    Ajoute toujours un commentaire timestamp juste au-dessus de la clé modifiée.
    """
    comment = audio_comment(function_name)
    start, end = audio_find_section(lines, section)

    if start is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(comment)
        lines.append(f"[{section}]")
        lines.append(f"{key} = {value}")
        return lines

    key_lower = key.lower()
    key_index = None

    for i in range(start + 1, end):
        stripped = lines[i].strip()
        if not stripped or stripped.startswith("#") or stripped.startswith(";"):
            continue

        if "=" in stripped:
            existing_key = stripped.split("=", 1)[0].strip().lower()
            if existing_key == key_lower:
                key_index = i
                break

    if key_index is not None:
        # Retire uniquement l'ancien commentaire PinCabOS directement au-dessus,
        # pour éviter d'empiler 50 timestamps sur la même clé.
        if key_index > 0 and "par PinCabOS fonction(" in lines[key_index - 1]:
            lines[key_index - 1] = comment
        else:
            lines.insert(key_index, comment)
            key_index += 1

        lines[key_index] = f"{key} = {value}"
        return lines

    # Clé absente : ajoute en fin de section.
    insert_at = end
    lines.insert(insert_at, comment)
    lines.insert(insert_at + 1, f"{key} = {value}")
    return lines


def audio_set_pincabos_section(lines, section, values, function_name):
    """
    Section de suivi PinCabOS.
    Toutes les lignes écrites ont un commentaire timestamp avant le bloc.
    """
    comment = audio_comment(function_name)
    start, end = audio_find_section(lines, section)

    block = [comment, f"[{section}]"]
    for key, value in values.items():
        block.append(f"{key} = {value}")

    if start is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.extend(block)
        return lines

    # Remplace seulement la section PinCabOS dédiée.
    return lines[:start] + block + lines[end:]


def audio_vpx_sound3d_value(ssf_mode):
    """
    VPX possède Sound3D dans [Player].
    On garde une logique prudente :
    - off / 2.1 = 0
    - 4.1 / 5.1 / 7.1 = 1
    """
    ssf_mode = str(ssf_mode or "").strip().lower()
    if ssf_mode in ["4.1", "5.1", "7.1"]:
        return "1"
    return "0"


def audio_apply_to_vpx_vpinfe():
    cfg = audio_load_config()

    function_name = "Audio / SSF V2 Apply"

    audio_mode = cfg.get("audio_mode", "dual")
    backbox_device = cfg.get("backbox_device", "")
    playfield_device = cfg.get("playfield_device", "")
    surround_device = cfg.get("surround_device", "")
    bass_device = cfg.get("bass_device", "")
    ssf_mode = cfg.get("ssf_mode", "off")
    backend = cfg.get("audio_backend", "alsa")

    # VPX : structure native = [Player]
    # SoundDeviceBG = backbox / musique / ROM
    # SoundDevice   = effets / playfield / surround
    # Sound3D       = active le mode surround/SSF quand nécessaire
    if audio_mode == "surround" and surround_device:
        vpx_main_device = surround_device
    elif playfield_device:
        vpx_main_device = playfield_device
    else:
        vpx_main_device = surround_device

    vpx_sound3d = audio_vpx_sound3d_value(ssf_mode)

    tracking_values = {
        "enabled": "true",
        "audio_mode": audio_mode,
        "audio_backend": backend,
        "backbox_device": backbox_device,
        "playfield_device": playfield_device,
        "surround_device": surround_device,
        "bass_device": bass_device,
        "ssf_mode": ssf_mode,
        "invert_lr": str(bool(cfg.get("invert_lr", False))).lower(),
        "invert_front_rear": str(bool(cfg.get("invert_front_rear", False))).lower(),
        "enable_bass": str(bool(cfg.get("enable_bass", False))).lower(),
        "night_mode": str(bool(cfg.get("night_mode", False))).lower(),
        "managed_by": "PinCabOS Audio / SSF V2",
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }

    results = []

    # -------- VPX --------
    try:
        backup = audio_backup_file(AUDIO_VPX_INI)
        lines = audio_read_lines(AUDIO_VPX_INI)

        if backbox_device:
            lines = audio_set_ini_key_with_comment(
                lines, "Player", "SoundDeviceBG", backbox_device, function_name
            )

        if vpx_main_device:
            lines = audio_set_ini_key_with_comment(
                lines, "Player", "SoundDevice", vpx_main_device, function_name
            )

        lines = audio_set_ini_key_with_comment(
            lines, "Player", "Sound3D", vpx_sound3d, function_name
        )

        # Section PinCabOS de suivi, comme tu as déjà PinCabOs.FullDMD dans VPX.
        lines = audio_set_pincabos_section(
            lines, "PinCabOs.Audio", tracking_values, function_name
        )

        audio_write_lines(AUDIO_VPX_INI, lines)

        if backup:
            results.append(f"VPX: OK — [Player] mis à jour + backup: {backup}")
        else:
            results.append("VPX: OK — fichier créé avec structure PinCabOS")
    except Exception as e:
        results.append(f"VPX: ERREUR — {e}")

    # -------- VPinFE --------
    try:
        backup = audio_backup_file(AUDIO_VPINFE_INI)
        lines = audio_read_lines(AUDIO_VPINFE_INI)

        # VPinFE ne possède pas de clé native pour choisir la carte audio.
        # On respecte sa structure : on ne force pas de SoundDevice inexistant.
        # On ajoute seulement une section PinCabOS de suivi.
        tracking_values_vpinfe = dict(tracking_values)
        tracking_values_vpinfe["note"] = "VPinFE ne possède pas de sélection native de carte audio; suivi PinCabOS seulement."

        lines = audio_set_pincabos_section(
            lines, "PinCabOs.Audio", tracking_values_vpinfe, function_name
        )

        audio_write_lines(AUDIO_VPINFE_INI, lines)

        if backup:
            results.append(f"VPinFE: OK — suivi PinCabOS ajouté + backup: {backup}")
        else:
            results.append("VPinFE: OK — fichier créé avec section PinCabOS")
    except Exception as e:
        results.append(f"VPinFE: ERREUR — {e}")

    # Journal PinCabOS
    log_path = Path("/opt/pincabos/logs/audio-ssf-apply.log")
    log_path.parent.mkdir(parents=True, exist_ok=True)

    with log_path.open("a") as f:
        f.write("===== Apply Audio / SSF V2 =====\n")
        f.write(audio_comment(function_name) + "\n")
        f.write(f"VPX_INI={AUDIO_VPX_INI}\n")
        f.write(f"VPINFE_INI={AUDIO_VPINFE_INI}\n")
        for line in results:
            f.write(line + "\n")
        f.write("\n")

    return results


# === PINCABOS AUDIO ALSA QUICK TEST START ===
def audio_alsa_test_card():
    devices, raw = audio_detect_alsa_devices()

    options = []
    for dev in devices:
        card = str(dev.get("card", "")).strip()
        device = str(dev.get("device", "")).strip()
        name = str(dev.get("name", "")).strip()
        desc = str(dev.get("description", "")).strip()

        if not card or not device:
            continue

        hw = "hw:" + card + "," + device
        plughw = "plughw:" + card + "," + device
        label_base = name + " — " + desc

        options.append(
            '<option value="' + esc(plughw) + '">' + esc(label_base + " — " + plughw + " recommandé") + '</option>'
        )
        options.append(
            '<option value="' + esc(hw) + '">' + esc(label_base + " — " + hw + " direct") + '</option>'
        )

    if not options:
        options.append('<option value="">Aucun périphérique ALSA détecté</option>')

    options_html = "\n".join(options)

    html = """
<div class="card" id="pincabos-alsa-test-card">
  <h2>Test audio ALSA rapide</h2>

  <p>
    Cette carte liste les sorties ALSA et lance un test court avec <code>speaker-test</code>.
    Utilise d’abord <code>plughw:X,Y</code>, plus compatible que <code>hw:X,Y</code>.
  </p>

  <table>
    <tr>
      <td>Périphérique ALSA</td>
      <td>
        <select id="pco-alsa-device" style="width:50%;max-width:420px;min-width:240px;padding:8px;">
          __OPTIONS__
        </select>
      </td>
    </tr>
    <tr>
      <td>Canaux</td>
      <td>
        <select id="pco-alsa-channels" style="padding:8px;">
          <option value="2">2 canaux stéréo</option>
          <option value="4">4 canaux</option>
          <option value="6">5.1 / 6 canaux</option>
          <option value="8">7.1 / 8 canaux</option>
        </select>
      </td>
    </tr>
  </table>

  <p style="margin-top:14px;">
    <button class="button" type="button" id="pco-alsa-test-btn">Tester 2 secondes</button>
    <button class="button secondary" type="button" id="pco-alsa-refresh-btn">Rafraîchir la page</button>
  </p>

  <p class="warn">
    Si <code>hw:X,Y</code> retourne <code>Bad address</code>, essaie le même périphérique en <code>plughw:X,Y</code>.
  </p>

  <details style="margin-top:12px;" open>
    <summary>Log test audio</summary>
    <pre id="pco-alsa-test-log" style="white-space:pre-wrap;max-height:520px;overflow:auto;background:rgba(0,0,0,.45);border:1px solid rgba(255,176,0,.25);border-radius:12px;padding:12px;">Prêt.</pre>
  </details>
</div>

<script>
(function(){
  if (window.pincabosAlsaTestBound) return;
  window.pincabosAlsaTestBound = true;

  async function runAlsaTest(){
    const dev = document.getElementById("pco-alsa-device");
    const ch = document.getElementById("pco-alsa-channels");
    const log = document.getElementById("pco-alsa-test-log");

    if (!dev || !log) return;

    log.textContent = "Test audio ALSA en cours...";

    try {
      const r = await fetch("/audio-ssf/test-alsa-quick", {
        method: "POST",
        headers: {"Content-Type": "application/json", "Cache-Control": "no-cache"},
        body: JSON.stringify({
          device: dev.value || "",
          channels: ch ? ch.value : "2"
        })
      });

      const data = await r.json();
      let text = "";
      text += "Device: " + (data.device || "") + String.fromCharCode(10);
      text += "Channels: " + (data.channels || "") + String.fromCharCode(10);
      text += "Exit code: " + (data.returncode ?? "") + String.fromCharCode(10);
      text += String.fromCharCode(10);
      text += data.log || data.error || "Aucun log.";

      if (data.hint) {
        text += String.fromCharCode(10) + String.fromCharCode(10) + "Suggestion: " + data.hint;
      }

      log.textContent = text;
      log.scrollTop = log.scrollHeight;
    } catch(e) {
      log.textContent = "Erreur test audio: " + e;
    }
  }

  document.addEventListener("click", function(e){
    if (e.target && e.target.id === "pco-alsa-test-btn") runAlsaTest();
    if (e.target && e.target.id === "pco-alsa-refresh-btn") window.location.href = "/audio-ssf";
  });
})();
</script>
"""
    return html.replace("__OPTIONS__", options_html)


@app.route("/audio-ssf/test-alsa-quick", methods=["POST"])
def audio_ssf_test_alsa_quick():
    import re
    import shutil
    import subprocess
    from flask import request, jsonify

    data = request.get_json(silent=True) or {}
    device = str(data.get("device", "")).strip()

    try:
        channels = int(data.get("channels", 2))
    except Exception:
        channels = 2

    if channels not in [1, 2, 4, 6, 8]:
        channels = 2

    if not re.match(r"^(plug)?hw:[0-9]+,[0-9]+$", device):
        return jsonify({
            "ok": False,
            "error": "Périphérique ALSA invalide.",
            "device": device
        }), 400

    speaker = shutil.which("speaker-test") or "/usr/bin/speaker-test"
    timeout_bin = shutil.which("timeout") or "/usr/bin/timeout"

    cmd = [
        timeout_bin,
        "4",
        speaker,
        "-D", device,
        "-c", str(channels),
        "-r", "48000",
        "-t", "wav",
        "-l", "1"
    ]

    header = []
    header.append("=== Test audio ALSA rapide ===")
    header.append("Commande: " + " ".join(cmd))
    header.append("")
    header.append("Devices ALSA:")
    try:
        aplay = subprocess.run(
            ["aplay", "-l"],
            capture_output=True,
            text=True,
            timeout=5
        )
        header.append((aplay.stdout or "") + (aplay.stderr or ""))
    except Exception as e:
        header.append("Erreur aplay -l: " + str(e))

    header.append("")
    header.append("Test audio " + device + ", 2 secondes...")
    header.append("")

    try:
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=6
        )
        output = (r.stdout or "") + (r.stderr or "")
        full_log = "\n".join(header) + "\n" + output

        hint = ""
        if "Bad address" in output and device.startswith("hw:"):
            hint = "Le mode hw direct refuse ce format. Essaie le même périphérique en plughw, par exemple " + device.replace("hw:", "plughw:", 1) + "."

        return jsonify({
            "ok": r.returncode == 0,
            "device": device,
            "channels": channels,
            "returncode": r.returncode,
            "log": full_log,
            "hint": hint
        })
    except Exception as e:
        return jsonify({
            "ok": False,
            "device": device,
            "channels": channels,
            "error": str(e),
            "log": "\n".join(header) + "\nErreur: " + str(e)
        }), 500
# === PINCABOS AUDIO ALSA QUICK TEST END ===


# === PINCABOS AUDIO WAV TEST PACK START ===
AUDIO_WAV_TEST_DIR = Path("/opt/pincabos/media/audio-tests")

def audio_wav_test_card():
    wavs = []
    try:
        if AUDIO_WAV_TEST_DIR.exists():
            wavs = sorted([x.name for x in AUDIO_WAV_TEST_DIR.glob("*.wav")])
    except Exception:
        wavs = []

    if wavs:
        wav_options = "\n".join(
            '<option value="' + esc(name) + '">' + esc(name) + '</option>'
            for name in wavs
        )
    else:
        wav_options = '<option value="">Aucun fichier WAV installé</option>'

    devices, raw = audio_detect_alsa_devices()
    dev_options = []

    for dev in devices:
        card = str(dev.get("card", "")).strip()
        device = str(dev.get("device", "")).strip()
        name = str(dev.get("name", "")).strip()
        desc = str(dev.get("description", "")).strip()

        if not card or not device:
            continue

        hw = "hw:" + card + "," + device
        plughw = "plughw:" + card + "," + device
        label_base = name + " — " + desc

        dev_options.append(
            '<option value="' + esc(plughw) + '">' + esc(label_base + " — " + plughw + " recommandé") + '</option>'
        )
        dev_options.append(
            '<option value="' + esc(hw) + '">' + esc(label_base + " — " + hw + " direct") + '</option>'
        )

    if not dev_options:
        dev_options.append('<option value="">Aucun périphérique ALSA détecté</option>')

    dev_options_html = "\n".join(dev_options)

    html = """
<div class="card" id="pincabos-audio-wav-test-card">
  <h2>Tests WAV PinCabOS</h2>

  <p>
    Tests audio plus utiles que le simple <code>speaker-test</code> :
    bass shaker, sweep basses fréquences, gauche/droite et test 4 canaux.
  </p>

  <table>
    <tr>
      <td>Fichier WAV</td>
      <td>
        <select id="pco-wav-file" style="width:50%;max-width:420px;min-width:240px;padding:8px;">
          __WAV_OPTIONS__
        </select>
      </td>
    </tr>
    <tr>
      <td>Sortie ALSA</td>
      <td>
        <select id="pco-wav-device" style="width:50%;max-width:420px;min-width:240px;padding:8px;">
          __DEV_OPTIONS__
        </select>
      </td>
    </tr>
  </table>

  <p style="margin-top:14px;">
    <button class="button" type="button" id="pco-wav-test-btn">Jouer le WAV</button>
    <button class="button secondary" type="button" id="pco-wav-stop-btn">Stop audio</button>
  </p>

  <p class="warn">
    Pour le bass shaker, commence avec <code>pincabos_bass_sweep_20-120hz_8s.wav</code>
    ou <code>pincabos_bass_thump_42hz_pulses.wav</code>.
  </p>

  <details style="margin-top:12px;" open>
    <summary>Log test WAV</summary>
    <pre id="pco-wav-test-log" style="white-space:pre-wrap;max-height:520px;overflow:auto;background:rgba(0,0,0,.45);border:1px solid rgba(255,176,0,.25);border-radius:12px;padding:12px;">Prêt.</pre>
  </details>
</div>

<script>
(function(){
  if (window.pincabosWavAudioTestBound) return;
  window.pincabosWavAudioTestBound = true;

  async function runWavTest(){
    const file = document.getElementById("pco-wav-file");
    const dev = document.getElementById("pco-wav-device");
    const log = document.getElementById("pco-wav-test-log");

    if (!file || !dev || !log) return;

    log.textContent = "Lecture WAV en cours...";

    try {
      const r = await fetch("/audio-ssf/test-wav", {
        method: "POST",
        headers: {"Content-Type": "application/json", "Cache-Control": "no-cache"},
        body: JSON.stringify({
          file: file.value || "",
          device: dev.value || ""
        })
      });

      const data = await r.json();
      let text = "";
      text += "Fichier: " + (data.file || "") + String.fromCharCode(10);
      text += "Device: " + (data.device || "") + String.fromCharCode(10);
      text += "Exit code: " + (data.returncode ?? "") + String.fromCharCode(10);
      text += String.fromCharCode(10);
      text += data.log || data.error || "Aucun log.";

      if (data.hint) {
        text += String.fromCharCode(10) + String.fromCharCode(10) + "Suggestion: " + data.hint;
      }

      log.textContent = text;
      log.scrollTop = log.scrollHeight;
    } catch(e) {
      log.textContent = "Erreur lecture WAV: " + e;
    }
  }

  async function stopWavTest(){
    const log = document.getElementById("pco-wav-test-log");
    try {
      const r = await fetch("/audio-ssf/test-wav-stop", {method:"POST", headers: {"Cache-Control":"no-cache"}});
      const data = await r.json();
      log.textContent = data.log || data.message || "Stop demandé.";
    } catch(e) {
      log.textContent = "Erreur stop audio: " + e;
    }
  }

  document.addEventListener("click", function(e){
    if (e.target && e.target.id === "pco-wav-test-btn") runWavTest();
    if (e.target && e.target.id === "pco-wav-stop-btn") stopWavTest();
  });
})();
</script>
"""
    return html.replace("__WAV_OPTIONS__", wav_options).replace("__DEV_OPTIONS__", dev_options_html)


@app.route("/audio-ssf/test-wav", methods=["POST"])
def audio_ssf_test_wav():
    import os
    import re
    import shutil
    import subprocess
    from flask import request, jsonify

    data = request.get_json(silent=True) or {}
    filename = str(data.get("file", "")).strip()
    device = str(data.get("device", "")).strip()

    if "/" in filename or "\\" in filename or not filename.endswith(".wav"):
        return jsonify({"ok": False, "error": "Nom de fichier WAV invalide.", "file": filename}), 400

    wav_path = AUDIO_WAV_TEST_DIR / filename
    if not wav_path.exists():
        return jsonify({"ok": False, "error": "Fichier WAV introuvable.", "file": filename}), 404

    if not re.match(r"^(plug)?hw:[0-9]+,[0-9]+$", device):
        return jsonify({"ok": False, "error": "Périphérique ALSA invalide.", "device": device}), 400

    aplay = shutil.which("aplay") or "/usr/bin/aplay"

    # Stop un ancien test lancé depuis cette carte.
    subprocess.run(["/usr/bin/pkill", "-f", "aplay.*pincabos_"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    cmd = [
        aplay,
        "-D", device,
        str(wav_path)
    ]

    header = []
    header.append("=== Test WAV PinCabOS ===")
    header.append("Commande: " + " ".join(cmd))
    header.append("")
    header.append("Fichiers disponibles:")
    try:
        for f in sorted(AUDIO_WAV_TEST_DIR.glob("*.wav")):
            header.append("- " + f.name)
    except Exception:
        pass
    header.append("")
    header.append("Lecture...")
    header.append("")

    try:
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=20
        )

        output = (r.stdout or "") + (r.stderr or "")
        full_log = "\n".join(header) + output

        hint = ""
        if r.returncode != 0 and device.startswith("hw:"):
            hint = "Essaie le même périphérique en plughw, par exemple " + device.replace("hw:", "plughw:", 1) + "."

        return jsonify({
            "ok": r.returncode == 0,
            "file": filename,
            "device": device,
            "returncode": r.returncode,
            "log": full_log,
            "hint": hint
        })
    except subprocess.TimeoutExpired:
        return jsonify({
            "ok": True,
            "file": filename,
            "device": device,
            "returncode": 124,
            "log": "\n".join(header) + "Lecture arrêtée par timeout de sécurité."
        })
    except Exception as e:
        return jsonify({
            "ok": False,
            "file": filename,
            "device": device,
            "error": str(e),
            "log": "\n".join(header) + "\nErreur: " + str(e)
        }), 500


@app.route("/audio-ssf/test-wav-stop", methods=["POST"])
def audio_ssf_test_wav_stop():
    import subprocess
    from flask import jsonify

    subprocess.run(
        ["/usr/bin/pkill", "-f", "aplay.*pincabos_"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    return jsonify({
        "ok": True,
        "message": "Stop audio demandé.",
        "log": "Stop audio demandé pour les tests WAV PinCabOS."
    })
# === PINCABOS AUDIO WAV TEST PACK END ===


@app.route("/audio-ssf/apply", methods=["POST"])
def audio_ssf_apply():
    results = audio_apply_to_vpx_vpinfe()

    rows = "".join(f"<li>{esc(line)}</li>" for line in results)

    body = f"""
<div class="card">
  <h2>Audio / SSF V2 appliqué</h2>
  <p class="ok">La configuration audio a été appliquée en respectant la structure des fichiers INI.</p>

  <ul>
    {rows}
  </ul>

  <p>
    <a class="button" href="/audio-ssf">Retour Audio / SSF V2</a>
    <a class="button secondary" href="/">Retour Dashboard</a>
  </p>
</div>

<div class="card" style="margin-top:20px;">
  <h2>Règles appliquées</h2>
  <table>
    <tr><td>VPX</td><td><code>[Player] SoundDeviceBG / SoundDevice / Sound3D</code></td></tr>
    <tr><td>VPX suivi</td><td><code>[PinCabOs.Audio]</code></td></tr>
    <tr><td>VPinFE</td><td><code>[PinCabOs.Audio]</code> seulement, car pas de carte audio native dans sa structure</td></tr>
    <tr><td>Commentaires</td><td><code>; Modifié DATE HEURE par PinCabOS fonction(Audio / SSF V2 Apply)</code></td></tr>
    <tr><td>Backups</td><td><code>/opt/pincabos/backups/audio-ssf/</code></td></tr>
    <tr><td>Log</td><td><code>/opt/pincabos/logs/audio-ssf-apply.log</code></td></tr>
  </table>
</div>
"""
    return page("Audio / SSF V2", body)


@app.route("/audio-ssf")
def audio_ssf_page():
    cfg = audio_load_config()

    def esc_audio(value):
        import html
        return html.escape(str(value or ""), quote=True)

    def selected_cfg(key, value):
        return " selected" if str(cfg.get(key, "")) == str(value) else ""

    def options_for(key):
        # Fonction native déjà existante dans PinCabOS.
        # Elle respecte le vrai format retourné par audio_detect_alsa_devices().
        return audio_device_options(cfg.get(key, ""))

    body = f"""
<div class="card">
  <h1>Audio / SSF V2</h1>
  <p>
    Configuration native PinCabOS pour le choix des cartes de son :
    <strong>Backbox / ROM / musique</strong>,
    <strong>effets sous playfield / SSF</strong>,
    <strong>surround VPX</strong> et
    <strong>bass shaker</strong>.
  </p>

  <p>
    <a class="button" href="/audio-ssf/commander">🎚️ Ouvrir SSF Commander</a>
    <a class="button secondary" href="/audio-ssf">Rafraîchir</a>
  </p>

  <p class="warn">
    Les réglages <strong>Sons seulement / Mécanique seulement / Sons + mécanique</strong>
    ne sont plus dans cette page. Ils sont maintenant dans <strong>SSF Commander</strong>.
  </p>
</div>

<div class="card">
  <h2>Cartes de son détectées</h2>
  <p>
    Les cartes de son détectées sont disponibles dans les listes déroulantes ci-dessous.
  </p>

  <details>
    <summary>Voir sortie brute <code>aplay -l</code></summary>
    <pre>{esc_audio(audio_run_cmd("aplay -l 2>/dev/null || true", timeout=5))}</pre>
  </details>
</div>

{audio_alsa_test_card()}

{audio_wav_test_card()}

<form method="post" action="/audio-ssf/save" class="card">
  <h2>Mode audio</h2>

  <table>
    <tr>
      <td>Mode général</td>
      <td>
        <select name="audio_mode">
          <option value="single"{selected_cfg("audio_mode", "single")}>Une carte de son</option>
          <option value="dual"{selected_cfg("audio_mode", "dual")}>Deux cartes de son</option>
          <option value="advanced"{selected_cfg("audio_mode", "advanced")}>Avancé</option>
        </select>
      </td>
    </tr>
    <tr>
      <td>Moteur audio</td>
      <td>
        <select name="audio_backend">
          <option value="alsa"{selected_cfg("audio_backend", "alsa")}>ALSA direct - recommandé</option>
          <option value="pipewire"{selected_cfg("audio_backend", "pipewire")}>PipeWire / PulseAudio</option>
        </select>
      </td>
    </tr>
  </table>

  <h2>Attribution des sorties</h2>

  <table>
    <tr>
      <td>Backbox / ROM / Musique</td>
      <td>
        <select name="backbox_device">
          {options_for("backbox_device")}
        </select>
      </td>
    </tr>
    <tr>
      <td>Effets sous playfield / SSF</td>
      <td>
        <select name="playfield_device">
          {options_for("playfield_device")}
        </select>
      </td>
    </tr>
    <tr>
      <td>Surround VPX 5.1 / 7.1</td>
      <td>
        <select name="surround_device">
          {options_for("surround_device")}
        </select>
      </td>
    </tr>
    <tr>
      <td>Bass shaker</td>
      <td>
        <select name="bass_device">
          {options_for("bass_device")}
        </select>
      </td>
    </tr>
  </table>

  <p style="margin-top:16px;">
    <button class="button" type="submit">Sauvegarder configuration audio</button>
    <a class="button secondary" href="/audio-ssf/commander">🎚️ SSF Commander</a>
    <a class="button secondary" href="/audio-ssf">Rafraîchir</a>
  </p>
</form>

<div class="card">
  <h2>Configuration sauvegardée</h2>
  <table>
    <tr><td>Mode audio</td><td><code>{esc_audio(cfg.get("audio_mode", ""))}</code></td></tr>
    <tr><td>Backend</td><td><code>{esc_audio(cfg.get("audio_backend", ""))}</code></td></tr>
    <tr><td>Backbox / ROM / Musique</td><td><code>{esc_audio(cfg.get("backbox_device", ""))}</code></td></tr>
    <tr><td>Playfield / SSF</td><td><code>{esc_audio(cfg.get("playfield_device", ""))}</code></td></tr>
    <tr><td>Surround VPX</td><td><code>{esc_audio(cfg.get("surround_device", ""))}</code></td></tr>
    <tr><td>Bass shaker</td><td><code>{esc_audio(cfg.get("bass_device", ""))}</code></td></tr>
  </table>
  <p>Fichier : <code>/opt/pincabos/config/audio-router.json</code></p>
</div>
"""
    return page("Audio / SSF V2", body)


@app.route("/audio-ssf/save", methods=["POST"])
def audio_ssf_save():
    cfg = audio_load_config()

    # Page audio simplifiée :
    # on sauvegarde seulement les choix de devices et de backend.
    # Les réglages Sounds / Mechanical / Both sont dans SSF Commander.
    for key in [
        "audio_mode",
        "audio_backend",
        "backbox_device",
        "playfield_device",
        "surround_device",
        "bass_device",
    ]:
        cfg[key] = request.form.get(key, "").strip()

    # Gardés seulement pour compatibilité avec les anciennes configs.
    # Ils ne sont plus affichés dans /audio-ssf.
    cfg.setdefault("ssf_mode", "")
    cfg.setdefault("swap_lr", False)
    cfg.setdefault("swap_front_rear", False)
    cfg.setdefault("bass_enabled", False)
    cfg.setdefault("night_mode", False)

    audio_save_config(cfg)
    return redirect(url_for("audio_ssf_page"))


@app.route("/audio-ssf/test/<role>", methods=["POST"])
def audio_ssf_test(role):
    cfg = audio_load_config()

    role = (role or "").strip().lower()

    if role == "backbox":
        audio_test_device(cfg.get("backbox_device", ""), 2)
    elif role == "playfield":
        mode = cfg.get("ssf_mode", "4.1")
        channels = 2
        if mode == "4.1":
            channels = 4
        elif mode == "5.1":
            channels = 6
        elif mode == "7.1":
            channels = 8
        audio_test_device(cfg.get("playfield_device", ""), channels)
    elif role == "surround":
        audio_test_device(cfg.get("surround_device", ""), 8)
    elif role == "bass":
        audio_test_device(cfg.get("bass_device", ""), 2)

    return redirect(url_for("audio_ssf_page"))


# ---------------------------------------------------------------------
# PinCabOs Dev form login protection
# ---------------------------------------------------------------------

PINCABOS_DEV_USER = "PinCabOsDev"
PINCABOS_DEV_PASS = "Dev43po3$"


def pincabos_dev_is_logged():
    return session.get("pincabos_dev_logged") == True


def pincabos_dev_login_page(error=""):
    return page("Connexion développeur", f"""
<div class="card">
  <h2>Connexion développeur PinCabOs</h2>

  <p>
    Cette section est réservée aux testeurs autorisés du projet PinCabOs.
  </p>

  <form method="post" action="/dev/login">
    <label>Login</label><br>
    <input name="username" autocomplete="username" required style="width:320px; max-width:95%; padding:10px; margin:6px 0;"><br>

    <label>Mot de passe</label><br>
    <input name="password" type="password" autocomplete="current-password" required style="width:320px; max-width:95%; padding:10px; margin:6px 0;"><br>

    <button class="button" type="submit">Entrer</button>
    <a class="button secondary" href="/about">Retour À propos</a>
  </form>

  <p class="bad">{esc(error)}</p>
</div>
""")


# === SSF COMMANDER V1 - PINCABOS START ===
PINCABOS_SSF_CONTROLLER_INI = "/home/pinball/.local/share/VPinballX/10.8/VPinballX.ini"

PINCABOS_SSF_EFFECTS = [
    ("DOFKnocker", "Knocker"),
    ("DOFContactors", "Contacteurs"),
    ("DOFFlippers", "Flippers"),
    ("DOFShaker", "Shaker"),
    ("DOFTargets", "Targets"),
    ("DOFDropTargets", "Drop Targets"),
    ("DOFChimes", "Chimes"),
    ("DOFBell", "Bell"),
    ("DOFGear", "Gear Motor"),
]

PINCABOS_SSF_LABELS = {
    "": "Non configuré",
    "0": "Sons seulement",
    "1": "Mécanique seulement",
    "2": "Sons + mécanique",
}

def ssf_commander_escape(value):
    import html
    return html.escape(str(value), quote=True)

def ssf_commander_read_controller():
    from pathlib import Path

    ini = Path(PINCABOS_SSF_CONTROLLER_INI)
    values = {"ForceDisableB2S": ""}
    for key, label in PINCABOS_SSF_EFFECTS:
        values[key] = ""

    if not ini.exists():
        return values, f"Fichier introuvable: {ini}"

    lines = ini.read_text(errors="replace").splitlines()
    in_controller = False

    for line in lines:
        stripped = line.strip()
        if stripped.lower() == "[controller]":
            in_controller = True
            continue
        if stripped.startswith("[") and stripped.endswith("]") and in_controller:
            break
        if not in_controller:
            continue
        if "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        key = key.strip()
        if key in values:
            values[key] = raw_value.strip()

    return values, ""

def ssf_commander_write_controller(new_values, function_name="SSF Commander"):
    from pathlib import Path
    from datetime import datetime
    import shutil
    import subprocess

    ini = Path(PINCABOS_SSF_CONTROLLER_INI)
    if not ini.exists():
        raise FileNotFoundError(str(ini))

    backup_dir = Path("/opt/pincabos/backups/ssf-commander")
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = backup_dir / f"VPinballX.ini.backup-ssf-commander-{stamp}"
    shutil.copy2(ini, backup)

    lines = ini.read_text(errors="replace").splitlines()

    managed_keys = ["ForceDisableB2S"] + [key for key, label in PINCABOS_SSF_EFFECTS]
    allowed = {"", "0", "1", "2"}

    normalized = {}

    normalized["ForceDisableB2S"] = str(new_values.get("ForceDisableB2S", "0")).strip()
    if normalized["ForceDisableB2S"] not in {"0", "1"}:
        normalized["ForceDisableB2S"] = "0"

    for key, label in PINCABOS_SSF_EFFECTS:
        value = str(new_values.get(key, "")).strip()
        if value not in allowed:
            value = ""
        normalized[key] = value

    stamp_human = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    comment = f"; Modifié {stamp_human} par PinCabOS fonction({function_name})"

    start = None
    end = None

    for i, line in enumerate(lines):
        if line.strip().lower() == "[controller]":
            start = i
            end = len(lines)
            for j in range(i + 1, len(lines)):
                s = lines[j].strip()
                if s.startswith("[") and s.endswith("]"):
                    end = j
                    break
            break

    if start is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append("[Controller]")
        start = len(lines) - 1
        end = len(lines)

    before = lines[:start + 1]
    section = lines[start + 1:end]
    after = lines[end:]

    cleaned = []

    for line in section:
        stripped = line.strip()

        if "PinCabOS fonction(SSF Commander" in line:
            continue

        if "=" in line and not stripped.startswith((";", "#")):
            key = line.split("=", 1)[0].strip()
            if key in managed_keys:
                continue

        cleaned.append(line)

    while cleaned and not cleaned[-1].strip():
        cleaned.pop()

    if cleaned:
        cleaned.append("")

    new_managed = [comment]

    for key in managed_keys:
        new_managed.append(f"{key} = {normalized[key]}")

    new_lines = before + cleaned + new_managed + after

    ini.write_text(chr(10).join(new_lines) + chr(10))

    try:
        subprocess.run(["chown", "pinball:pinball", str(ini)], timeout=10)
    except Exception:
        pass

    return str(backup)


def ssf_commander_select_html(key, current):
    current = str(current or "").strip()
    options = [
        ("", "Non configuré"),
        ("0", "Sons seulement"),
        ("1", "Mécanique seulement"),
        ("2", "Sons + mécanique"),
    ]
    html_options = []
    for value, label in options:
        selected = " selected" if value == current else ""
        html_options.append(f'<option value="{value}"{selected}>{label}</option>')
    return f'<select name="{ssf_commander_escape(key)}">' + "".join(html_options) + "</select>"

@app.route("/audio-ssf/commander", methods=["GET"])
def audio_ssf_commander_page():
    values, err = ssf_commander_read_controller()
    ini = PINCABOS_SSF_CONTROLLER_INI

    rows = []
    for key, label in PINCABOS_SSF_EFFECTS:
        current = values.get(key, "")
        rows.append(f"""
        <tr>
          <td><strong>{ssf_commander_escape(label)}</strong><br><small><code>{ssf_commander_escape(key)}</code></small></td>
          <td>{ssf_commander_select_html(key, current)}</td>
          <td><code>{ssf_commander_escape(current)}</code> — {ssf_commander_escape(PINCABOS_SSF_LABELS.get(current, "Inconnu"))}</td>
        </tr>
        """)

    force_checked = "checked" if str(values.get("ForceDisableB2S", "")).strip() == "1" else ""

    err_html = f'<p class="bad">Erreur: {ssf_commander_escape(err)}</p>' if err else ""

    body = f"""
<div class="card">
  <h1>SSF Commander</h1>
  <p>
    Cette page règle la logique <strong>Sounds / Mechanical / Both</strong> utilisée par
    <code>controller.vbs</code> / VPX Standalone pour les effets DOF.
  </p>
  <p>
    Fichier modifié :
    <code>{ssf_commander_escape(ini)}</code>
  </p>
  {err_html}
</div>

<div class="card">
  <h2>Modes disponibles</h2>
  <table>
    <tr><th>Valeur</th><th>Mode</th><th>Effet</th></tr>
    <tr><td><code>0</code></td><td>Sons seulement</td><td>Garde le son SSF/audio, pas de mécanique forcée.</td></tr>
    <tr><td><code>1</code></td><td>Mécanique seulement</td><td>Mute le son lorsque la table utilise SoundFX/DOF, pour laisser le vrai hardware travailler.</td></tr>
    <tr><td><code>2</code></td><td>Sons + mécanique</td><td>Garde le son et le déclenchement mécanique.</td></tr>
  </table>
</div>

<form method="post" action="/audio-ssf/commander/save" class="card">
  <h2>Effets DOF / SSF</h2>

  <table>
    <tr>
      <th>Effet</th>
      <th>Mode</th>
      <th>Valeur actuelle</th>
    </tr>
    {''.join(rows)}
  </table>

  <p style="margin-top:16px;">
    <label>
      <input type="checkbox" name="ForceDisableB2S" value="1" {force_checked}>
      Forcer la désactivation B2S / Controller B2S
    </label>
  </p>

  <p class="warn">
    Note : SSF Commander v1 ne modifie pas les fichiers <code>.vpx</code>, <code>.vbs</code>,
    <code>directoutputconfig.ini</code> ou <code>cabinet.xml</code>.
    Il modifie seulement la section <code>[Controller]</code> de <code>VPinballX.ini</code>.
  </p>

  <button class="button" type="submit">Sauvegarder SSF Commander</button>
  <a class="button secondary" href="/audio-ssf">Retour Audio / SSF V2</a>
</form>

<div class="card">
  <h2>Preset rapide</h2>
  <form method="post" action="/audio-ssf/commander/defaults" onsubmit="return confirm('Mettre tous les effets en Sons + mécanique ?');">
    <input type="hidden" name="preset" value="both">
    <button class="button secondary" type="submit">Tout mettre en Sons + mécanique</button>
  </form>
</div>
"""
    return page("Audio / SSF V2", body)

@app.route("/audio-ssf/commander/save", methods=["POST"])
def audio_ssf_commander_save():
    new_values = {}
    new_values["ForceDisableB2S"] = "1" if request.form.get("ForceDisableB2S") == "1" else "0"

    for key, label in PINCABOS_SSF_EFFECTS:
        new_values[key] = request.form.get(key, "").strip()

    try:
        backup = ssf_commander_write_controller(new_values, "SSF Commander Save")
        body = f"""
<div class="card">
  <h1>SSF Commander sauvegardé</h1>
  <p class="good">Configuration écrite dans <code>{ssf_commander_escape(PINCABOS_SSF_CONTROLLER_INI)}</code>.</p>
  <p>Backup créé : <code>{ssf_commander_escape(backup)}</code></p>
  <a class="button" href="/audio-ssf/commander">Retour SSF Commander</a>
  <a class="button secondary" href="/audio-ssf">Retour Audio / SSF V2</a>
</div>
"""
        return page("Audio / SSF V2", body)
    except Exception as e:
        body = f"""
<div class="card">
  <h1>Erreur SSF Commander</h1>
  <p class="bad"><code>{ssf_commander_escape(e)}</code></p>
  <a class="button" href="/audio-ssf/commander">Retour</a>
</div>
"""
        return page("Audio / SSF V2", body)

@app.route("/audio-ssf/commander/defaults", methods=["POST"])
def audio_ssf_commander_defaults():
    preset = request.form.get("preset", "both")
    value = "2" if preset == "both" else ""
    new_values = {"ForceDisableB2S": "0"}
    for key, label in PINCABOS_SSF_EFFECTS:
        new_values[key] = value

    try:
        backup = ssf_commander_write_controller(new_values, "SSF Commander Defaults")
        body = f"""
<div class="card">
  <h1>Preset appliqué</h1>
  <p class="good">Tous les effets ont été mis en <strong>Sons + mécanique</strong>.</p>
  <p>Backup créé : <code>{ssf_commander_escape(backup)}</code></p>
  <a class="button" href="/audio-ssf/commander">Retour SSF Commander</a>
</div>
"""
        return page("Audio / SSF V2", body)
    except Exception as e:
        body = f"""
<div class="card">
  <h1>Erreur preset SSF Commander</h1>
  <p class="bad"><code>{ssf_commander_escape(e)}</code></p>
  <a class="button" href="/audio-ssf/commander">Retour</a>
</div>
"""
        return page("Audio / SSF V2", body)
# === SSF COMMANDER V1 - PINCABOS END ===



@app.route("/dev/login", methods=["POST"])
def pincabos_dev_login():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()

    if username == PINCABOS_DEV_USER and password == PINCABOS_DEV_PASS:
        session["pincabos_dev_logged"] = True
        return redirect("/dev")

    return pincabos_dev_login_page("Login ou mot de passe invalide.")


@app.route("/dev/logout")
def pincabos_dev_logout():
    session.pop("pincabos_dev_logged", None)
    return redirect("/about")


# ---------------------------------------------------------------------
# PinCabOs Developer / Tester Feedback - Remote API only
# No local feedback database is stored on PinCabOs.
# ---------------------------------------------------------------------

DEV_FEEDBACK_ENV = Path("/opt/pincabos/config/dev-feedback.env")


def pincabos_feedback_config():
    cfg = {
        "PINCABOS_FEEDBACK_URL": "",
        "PINCABOS_FEEDBACK_TOKEN": "",
        "PINCABOS_FEEDBACK_PROJECT": "PinCabOs __PINCABOS_VERSION_LABEL__",
    }

    try:
        if DEV_FEEDBACK_ENV.exists():
            for line in DEV_FEEDBACK_ENV.read_text(errors="replace").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip()
    except Exception:
        pass

    return cfg


def pincabos_dev_cmd(c, timeout=8):
    try:
        return run_cmd(c, timeout=timeout).strip()
    except Exception as e:
        return f"Erreur: {e}"


def pincabos_dev_sysinfo_remote():
    os_version = ""
    try:
        os_release = Path("/etc/os-release").read_text(errors="replace")
        for line in os_release.splitlines():
            if line.startswith("PRETTY_NAME="):
                os_version = line.split("=", 1)[1].strip().strip('"')
                break
    except Exception:
        os_version = pincabos_dev_cmd(["lsb_release", "-ds"])

    hostname = pincabos_dev_cmd(["hostname"])
    ip_address = pincabos_dev_cmd(["hostname", "-I"])
    kernel_version = pincabos_dev_cmd(["uname", "-r"]) + " / " + pincabos_dev_cmd(["uname", "-m"])
    uptime = pincabos_dev_cmd(["uptime", "-p"])
    timezone = pincabos_dev_cmd(["timedatectl", "show", "-p", "Timezone", "--value"])
    local_time = pincabos_dev_cmd(["date"])

    ver = pincabos_version()
    pincabos_version_str = str(ver.get("version", "Development"))

    vpx_version = pincabos_dev_cmd([
        "bash", "-lc",
        "/opt/pincabos/apps/vpx/VPinballX -version 2>/dev/null || "
        "/opt/pincabos/apps/vpx/VPinballX --version 2>/dev/null || "
        "echo 'non détectée'"
    ])

    vpinfe_version = pincabos_dev_cmd([
        "bash", "-lc",
        "/opt/pincabos/apps/frontend/vpinfe/vpinfe --version 2>/dev/null || echo 'non détectée'"
    ])

    dof_status = pincabos_dev_cmd([
        "bash", "-lc",
        "find /opt/pincabos -iname '*dof*' -o -iname '*libdof*' 2>/dev/null | head -n 40"
    ])

    gpu_info = pincabos_dev_cmd([
        "bash", "-lc",
        "lspci | grep -Ei 'vga|3d|display' || echo 'non détecté'"
    ])

    screens_info = pincabos_dev_cmd([
        "bash", "-lc",
        "xrandr --query 2>/dev/null || cat /opt/pincabos/config/screens.json 2>/dev/null || echo 'non détecté'"
    ])

    services_info = pincabos_dev_cmd([
        "bash", "-lc",
        "systemctl --no-pager --plain status pincabos-web.service 2>/dev/null | head -n 25"
    ])

    dashboard_snapshot = "\n".join([
        "=== PinCabOs Dashboard Snapshot ===",
        f"Hostname: {hostname}",
        f"IP: {ip_address}",
        f"OS: {os_version}",
        f"Kernel: {kernel_version}",
        f"Uptime: {uptime}",
        f"Timezone: {timezone}",
        f"Heure locale: {local_time}",
        "",
        "=== Versions ===",
        f"PinCabOs: {pincabos_version_str}",
        f"VPX: {vpx_version}",
        f"VPinFE: {vpinfe_version}",
        "",
        "=== GPU ===",
        gpu_info,
        "",
        "=== Écrans ===",
        screens_info,
        "",
        "=== DOF / libdof ===",
        dof_status,
        "",
        "=== Services ===",
        services_info,
    ])

    return {
        "hostname": hostname,
        "ip_address": ip_address,
        "os_version": os_version,
        "kernel_version": kernel_version,
        "uptime": uptime,
        "timezone": timezone,
        "local_time": local_time,
        "pincabos_version": pincabos_version_str,
        "vpx_version": vpx_version,
        "vpinfe_version": vpinfe_version,
        "dof_status": dof_status,
        "gpu_info": gpu_info,
        "screens_info": screens_info,
        "dashboard_snapshot": dashboard_snapshot,
    }


def pincabos_feedback_watchdog():
    """
    Vérifie si le serveur feedback central répond.
    Retourne: (online_bool, message)
    """
    cfg = pincabos_feedback_config()
    url = cfg.get("PINCABOS_FEEDBACK_URL", "").strip()

    if not url:
        return False, "Aucune URL configurée"

    # Pour vérifier le serveur, on teste la racine au lieu de poster un rapport.
    test_url = url
    if test_url.endswith("/api/report"):
        test_url = test_url[:-len("/api/report")]
    elif "/api/report" in test_url:
        test_url = test_url.split("/api/report", 1)[0]

    try:
        req = urllib.request.Request(
            test_url,
            headers={
                "Accept": "application/json",
                "User-Agent": f"PinCabOs-Feedback-Watchdog/{str(pincabos_version().get('version', 'Development')).replace(' ', '-')} (+https://pincabos.cc)",
            },
            method="GET",
        )

        with urllib.request.urlopen(req, timeout=5) as resp:
            code = getattr(resp, "status", 0)
            if 200 <= code < 400:
                return True, f"Online HTTP {code}"
            return False, f"Réponse HTTP {code}"

    except Exception as e:
        return False, str(e)


def pincabos_send_feedback_remote(payload):
    cfg = pincabos_feedback_config()
    url = cfg.get("PINCABOS_FEEDBACK_URL", "").strip()
    token = cfg.get("PINCABOS_FEEDBACK_TOKEN", "").strip()

    if not url:
        return False, "Aucune URL feedback configurée."

    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": f"PinCabOs-Feedback-Agent/{str(pincabos_version().get('version', 'Development')).replace(' ', '-')} (+https://pincabos.cc)",
            "X-PinCabOs-Token": token,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return True, raw
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}: {e.read().decode('utf-8', errors='replace')}"
    except Exception as e:
        return False, str(e)


@app.route("/dev/cleanup-nosnap", methods=["POST"])
def pincabos_dev_cleanup_nosnap():
    if not pincabos_dev_is_logged():
        return pincabos_dev_login_page()

    import subprocess
    from pathlib import Path

    cmd = ["/usr/bin/sudo", "/usr/local/sbin/pincabos-cleanup-nosnap"]

    try:
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=3600,
            check=False
        )
        output = (r.stdout or "") + "\n" + (r.stderr or "")
        rc = r.returncode
    except Exception as e:
        output = str(e)
        rc = 1

    reports = sorted(Path("/home/pinball/Share").glob("cleanup-nosnap-*.txt"), key=lambda x: x.stat().st_mtime, reverse=True)
    report = str(reports[0]) if reports else "Aucun rapport trouvé"

    cls = "ok" if rc == 0 else "bad"

    body = """
<div class="card">
  <h2>Cleanup PinCabOS terminé</h2>
  <p class="__CLS__">Code retour : <strong>__RC__</strong></p>
  <p>Rapport : <code>__REPORT__</code></p>

  <h3>Sortie technique</h3>
  <pre style="white-space:pre-wrap;max-height:640px;overflow:auto;background:rgba(0,0,0,.45);border:1px solid rgba(255,176,0,.25);border-radius:12px;padding:12px;">__OUTPUT__</pre>

  <p>
    <a class="button" href="/dev">Retour Développeur</a>
    <a class="button secondary" href="/about">Retour À propos</a>
  </p>
</div>
"""
    body = body.replace("__CLS__", cls)
    body = body.replace("__RC__", esc(str(rc)))
    body = body.replace("__REPORT__", esc(report))
    body = body.replace("__OUTPUT__", esc(output[-30000:]))

    return page("Développeur", body)

@app.route("/dev", methods=["GET"])
def pincabos_dev_page_remote():
    if not pincabos_dev_is_logged():
        return pincabos_dev_login_page()

    info = pincabos_dev_sysinfo_remote()
    cfg = pincabos_feedback_config()
    feedback_online, feedback_status = pincabos_feedback_watchdog()
    feedback_color = "#00ff99" if feedback_online else "#ff4444"
    feedback_dot = "🟢" if feedback_online else "🔴"
    feedback_label = "Online" if feedback_online else "Offline"

    return page("Développeur", f"""
<div class="card">
  <h2>Rapport testeur PinCabOs</h2>

  <p>
    Utilise ce formulaire pour signaler un problème, partager une idée ou proposer une solution
    pendant les tests de PinCabOs.
  </p>

  <p class="warn">
    Les réponses sont envoyées vers le serveur central du projet.
    Aucune base de données de rapports n’est distribuée avec PinCabOs.
  </p>

  <p>
    <strong>Serveur feedback :</strong>
    <code>{esc(cfg.get("PINCABOS_FEEDBACK_URL", "non configuré"))}</code>
  </p>

  <div style="margin:12px 0; padding:12px; border-radius:12px; background:rgba(0,0,0,0.25); border:1px solid rgba(255,255,255,0.12);">
    <strong>État serveur :</strong>
    <span style="color:{feedback_color}; font-weight:bold;">
      {feedback_dot} {feedback_label}
    </span>
    <br>
    <small style="opacity:0.85;">{esc(feedback_status)}</small>
  </div>

  <p>
    <a class="button secondary" href="/about">Retour À propos</a>

    <form method="post" action="/dev/cleanup-nosnap" style="display:inline;" onsubmit="return confirm('Détruire les fichiers inutiles maintenant ? Aucun snapshot ne sera créé. Continuer ?');">
      <button class="button" type="submit" style="background:#b00020;border-color:#ff4d4d;color:white;">
        Détruire les fichiers inutiles
      </button>
    </form>
  </p>
</div>

<div class="card" style="margin-top:20px;">
  <h2>Version PinCabOS</h2>
  <p>Cette section met à jour le fichier maître <code>/opt/pincabos/config/version.json</code>.</p>

  <form method="post" action="/dev/version/save">
    <div style="display:grid; grid-template-columns:repeat(2,minmax(220px,1fr)); gap:12px;">
      <label>Nom<br><input name="name" value="{esc(pincabos_version().get("name", "PinCabOs"))}" style="width:95%; padding:10px;"></label>
      <label>Version<br><input name="version" value="{esc(pincabos_version().get("version", ""))}" style="width:95%; padding:10px;"></label>
      <label>Build<br><input name="build" value="{esc(pincabos_version().get("build", ""))}" style="width:95%; padding:10px;"></label>
      <label>Canal<br><input name="channel" value="{esc(pincabos_version().get("channel", ""))}" style="width:95%; padding:10px;"></label>
      <label>Codename<br><input name="codename" value="{esc(pincabos_version().get("codename", ""))}" style="width:95%; padding:10px;"></label>
      <label>Auteur<br><input name="author" value="{esc(pincabos_version().get("author", "Karots Sugarpie"))}" style="width:95%; padding:10px;"></label>
      <label>Update channel<br><input name="update_channel" value="{esc(pincabos_version().get("update_channel", ""))}" style="width:95%; padding:10px;"></label>
      <label>Update base URL<br><input name="update_base_url" value="{esc(pincabos_version().get("update_base_url", ""))}" style="width:95%; padding:10px;"></label>
      <label>Latest JSON URL<br><input name="latest_json_url" value="{esc(pincabos_version().get("latest_json_url", ""))}" style="width:95%; padding:10px;"></label>
    </div>

    <p style="margin-top:14px;">
      <button class="button" type="submit">💾 Sauvegarder la version</button>
    </p>
  </form>
</div>


<div class="card" style="margin-top:20px;">
  <h2>Informations système détectées</h2>

  <p><strong>Hostname :</strong> <code>{esc(info["hostname"])}</code></p>
  <p><strong>IP :</strong> <code>{esc(info["ip_address"])}</code></p>
  <p><strong>OS :</strong> <code>{esc(info["os_version"])}</code></p>
  <p><strong>Kernel :</strong> <code>{esc(info["kernel_version"])}</code></p>
  <p><strong>Uptime :</strong> <code>{esc(info["uptime"])}</code></p>
  <p><strong>Timezone :</strong> <code>{esc(info["timezone"])}</code></p>
  <p><strong>Heure locale :</strong> <code>{esc(info["local_time"])}</code></p>
  <p><strong>PinCabOs :</strong> <code>{esc(info["pincabos_version"])}</code></p>
  <p><strong>VPX :</strong> <code>{esc(info["vpx_version"])}</code></p>
  <p><strong>VPinFE :</strong> <code>{esc(info["vpinfe_version"])}</code></p>
</div>

<div class="card" style="margin-top:20px;">
  <h2>Formulaire</h2>

  <form method="post" action="/dev/submit">
    <label>Prénom réel *</label><br>
    <input name="first_name" required style="width:95%; padding:10px; margin:6px 0;"><br>

    <label>Nom réel *</label><br>
    <input name="last_name" required style="width:95%; padding:10px; margin:6px 0;"><br>

    <label>Surnom / pseudo optionnel</label><br>
    <input name="nickname" style="width:95%; padding:10px; margin:6px 0;"><br>

    <label>Courriel optionnel</label><br>
    <input name="email" type="email" style="width:95%; padding:10px; margin:6px 0;"><br>

    <label>Type de rapport</label><br>
    <select name="report_type" style="width:95%; padding:10px; margin:6px 0;">
      <option value="Problème">Problème</option>
      <option value="Idée">Idée</option>
      <option value="Amélioration">Amélioration</option>
      <option value="Solution">Solution</option>
      <option value="Autre">Autre</option>
    </select><br>

    <label>Fonction concernée</label><br>
    <select name="affected_area" style="width:95%; padding:10px; margin:6px 0;">
      <option value="Dashboard">Dashboard</option>
      <option value="Import table">Import table</option>
      <option value="Export table">Export table</option>
      <option value="PinCab Explorer">PinCab Explorer</option>
      <option value="FullDMD">FullDMD</option>
      <option value="GPU / Écrans">GPU / Écrans</option>
      <option value="DOF">DOF</option>
      <option value="Réseau">Réseau</option>
      <option value="VPinFE">VPinFE</option>
      <option value="VPX">VPX</option>
      <option value="Installation / Rufus">Installation / Rufus</option>
      <option value="Autre">Autre</option>
    </select><br>

    <label>Gravité</label><br>
    <select name="severity" style="width:95%; padding:10px; margin:6px 0;">
      <option value="Info">Info</option>
      <option value="Mineur">Mineur</option>
      <option value="Moyen">Moyen</option>
      <option value="Bloquant">Bloquant</option>
      <option value="Crash">Crash</option>
    </select><br>

    <label>Titre court *</label><br>
    <input name="title" required style="width:95%; padding:10px; margin:6px 0;"><br>

    <label>Commentaires / détails *</label><br>
    <textarea name="comments" required rows="8" style="width:95%; padding:10px; margin:6px 0;"></textarea><br>

    <label>
      <input type="checkbox" name="has_solution" value="1">
      J’ai une solution ou une piste pour ce problème
    </label><br><br>

    <label>Solution proposée / piste</label><br>
    <textarea name="solution_text" rows="5" style="width:95%; padding:10px; margin:6px 0;"></textarea><br>

    <label>
      <input type="checkbox" name="consent_alpha" value="1" required>
      Je comprends que PinCabOs est en développement Alpha, que certaines fonctions peuvent changer,
      et j’accepte que ce rapport technique soit envoyé au serveur central PinCabOs pour améliorer le projet.
    </label><br><br>

    <button class="button" type="submit">Envoyer le rapport</button>
  </form>
</div>

<div class="card" style="margin-top:20px;">
  <h2>Snapshot technique envoyé avec le rapport</h2>
  <pre>{esc(info["dashboard_snapshot"])}</pre>
</div>
""")


@app.route("/dev/version/save", methods=["POST"])
def pincabos_dev_version_save():
    if not pincabos_dev_is_logged():
        return redirect("/dev")

    version_file = Path("/opt/pincabos/config/version.json")
    version_file.parent.mkdir(parents=True, exist_ok=True)

    current = pincabos_version()
    fields = [
        "name", "version", "build", "channel", "codename", "author",
        "update_channel", "update_base_url", "latest_json_url"
    ]

    for field in fields:
        val = request.form.get(field, "").strip()
        if val:
            current[field] = val

    version_file.write_text(json.dumps(current, indent=2, ensure_ascii=False) + "\n")
    try:
        subprocess.run(["chown", "pinball:pinball", str(version_file)], timeout=5)
    except Exception:
        pass

    return redirect("/dev")

@app.route("/dev/submit", methods=["POST"])
def pincabos_dev_submit_remote():
    if not pincabos_dev_is_logged():
        return redirect("/dev")

    info = pincabos_dev_sysinfo_remote()
    cfg = pincabos_feedback_config()

    payload = {
        "project": cfg.get("PINCABOS_FEEDBACK_PROJECT", "PinCabOs"),
        "created_local": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),

        "tester_first_name": request.form.get("first_name", "").strip(),
        "tester_last_name": request.form.get("last_name", "").strip(),
        "tester_nickname": request.form.get("nickname", "").strip(),
        "tester_email": request.form.get("email", "").strip(),

        "report_type": request.form.get("report_type", "").strip(),
        "affected_area": request.form.get("affected_area", "").strip(),
        "severity": request.form.get("severity", "").strip(),
        "title": request.form.get("title", "").strip(),
        "comments": request.form.get("comments", "").strip(),
        "has_solution": True if request.form.get("has_solution") == "1" else False,
        "solution_text": request.form.get("solution_text", "").strip(),
        "consent_alpha": True if request.form.get("consent_alpha") == "1" else False,
    }

    payload.update(info)

    ok, response = pincabos_send_feedback_remote(payload)

    if ok:
        return page("Rapport envoyé", f"""
<div class="card">
  <h2>Rapport envoyé</h2>
  <p class="ok">Merci. Le rapport a été envoyé au serveur central PinCabOs.</p>
  <pre>{esc(response)}</pre>

  <p>
    <a class="button" href="/dev">Envoyer un autre rapport</a>
    <a class="button secondary" href="/about">Retour À propos</a>
  </p>
</div>
""")

    return page("Erreur envoi rapport", f"""
<div class="card">
  <h2>Erreur d’envoi</h2>
  <p class="bad">Impossible d’envoyer le rapport au serveur central.</p>
  <p>Vérifie la connexion réseau ou la configuration du serveur feedback.</p>
  <pre>{esc(response)}</pre>

  <p>
    <a class="button" href="/dev">Retour au formulaire</a>
    <a class="button secondary" href="/about">Retour À propos</a>
  </p>
</div>
""")


@app.route("/help")
def help_page():
    body = r"""
<style>
.help-search{width:100%;padding:14px;font-size:18px;border-radius:14px;border:1px solid #ff9f1c;background:#14001f;color:#ffb000}
.help-card h2,.help-card h3{color:#ffb000}
.help-card pre{white-space:pre-wrap;background:rgba(0,0,0,.42);border:1px solid rgba(255,176,0,.22);border-radius:12px;padding:12px;overflow:auto}
.help-item ul,.help-item ol{line-height:1.6}
.help-step{border-left:4px solid #ffb000;padding-left:14px;margin:14px 0}
.help-tag{display:inline-block;margin:3px;padding:5px 8px;border-radius:999px;background:rgba(255,176,0,.12);border:1px solid rgba(255,176,0,.25)}
</style>

<div class="card">
  <h1>📖 Aide & Documentation PinCabOS</h1>
  <p>Manuel rapide pour installer, configurer, administrer et dépanner PinCabOS.</p>
  <input id="helpSearch" class="help-search" placeholder="🔎 Rechercher : remote, iPad, IP fixe, DHCP, DOF, SSF, VPX, VPinFE...">
</div>

<div class="card help-card help-item">
<h2>1. Comprendre PinCabOS</h2>
<ul>
<li><strong>PinCabOS</strong> est le système/backend : réseau, mises à jour, fichiers, services, outils, WebApp.</li>
<li><strong>VPinFE</strong> est le frontend : liste des tables, médias, wheels, collections et lancement.</li>
<li><strong>VPX Linux</strong> est le moteur de jeu : il exécute les tables <code>.vpx</code>.</li>
</ul>
<pre>PinCabOS WebApp
  ├── Configure le système
  ├── Prépare audio, réseau, GPU, écrans, inputs, DOF
  └── Aide à importer et maintenir les fichiers

VPinFE
  ├── Affiche les tables
  ├── Gère médias et collections
  └── Lance VPX

VPX Linux
  └── Fait rouler la table</pre>
</div>

<div class="card help-card help-item">
<h2>2. Accéder à PinCabOS WebApp en remote</h2>
<p>La plupart des configurations peuvent être faites depuis un autre appareil : PC, laptop, iPad, tablette Android ou téléphone.</p>

<h3>Étapes générales</h3>
<ol>
<li>Allume le pincab.</li>
<li>Attends que PinCabOS démarre.</li>
<li>Va sur le Dashboard ou First Run pour voir l’adresse IP.</li>
<li>Sur ton autre appareil, ouvre un navigateur.</li>
<li>Entre l’adresse affichée, par exemple :</li>
</ol>
<pre>http://192.168.254.213/</pre>

<h3>Exemple avec un iPad</h3>
<ol>
<li>Connecte l’iPad au même WiFi ou réseau que le pincab.</li>
<li>Ouvre Safari.</li>
<li>Tape l’adresse IP du pincab dans la barre d’adresse.</li>
<li>Exemple : <code>http://192.168.254.213/</code></li>
<li>La WebApp PinCabOS s’ouvre et tu peux configurer le cab sans clavier branché dessus.</li>
</ol>

<h3>Exemple avec un PC Windows</h3>
<ol>
<li>Ouvre Edge, Chrome ou Firefox.</li>
<li>Tape <code>http://IP_DU_PINCAB/</code>.</li>
<li>Exemple : <code>http://192.168.254.213/</code>.</li>
</ol>

<h3>Important</h3>
<ul>
<li>L’appareil remote doit être sur le même réseau local.</li>
<li>Si l’adresse IP change, l’ancienne adresse ne fonctionnera plus.</li>
<li>C’est pour ça qu’une IP fixe est recommandée.</li>
</ul>
</div>

<div class="card help-card help-item">
<h2>3. Comprendre 127.0.0.1, IP locale, DHCP et IP fixe</h2>

<h3>127.0.0.1</h3>
<p><code>127.0.0.1</code> veut dire <strong>cet ordinateur lui-même</strong>.</p>
<ul>
<li>Sur le pincab, <code>http://127.0.0.1/</code> ouvre PinCabOS sur le pincab.</li>
<li>Sur un iPad, <code>127.0.0.1</code> pointe vers l’iPad, pas vers le pincab.</li>
<li>Donc pour accéder depuis un autre appareil, il faut utiliser l’IP réseau du pincab.</li>
</ul>

<h3>DHCP</h3>
<p>DHCP veut dire que le routeur donne automatiquement une adresse IP.</p>
<ul>
<li>Avantage : simple, fonctionne sans configuration.</li>
<li>Désavantage : l’adresse peut changer après un reboot.</li>
<li>Exemple : aujourd’hui <code>192.168.254.213</code>, demain peut-être <code>192.168.254.214</code>.</li>
</ul>

<h3>IP fixe</h3>
<p>Une IP fixe est une adresse permanente assignée au pincab.</p>
<ul>
<li>Avantage : toujours la même adresse pour accéder à PinCabOS.</li>
<li>Idéal pour les testeurs, le support et les favoris navigateur.</li>
<li>Exemple : <code>http://192.168.254.213/</code> reste toujours pareil.</li>
</ul>

<h3>Recommandation</h3>
<p>Utilise DHCP au premier démarrage, puis configure une IP fixe quand le réseau est validé.</p>
</div>

<div class="card help-card help-item">
<h2>4. Premier démarrage : quoi faire</h2>
<ol>
<li><strong>Mise à jour système :</strong> met à jour Ubuntu, PinCabOS, VPX, VPinFE et dépendances.</li>
<li><strong>Réseau :</strong> vérifie Internet, DNS, IP et accès remote.</li>
<li><strong>GPU :</strong> détecte la carte vidéo et installe le pilote recommandé.</li>
<li><strong>Écrans :</strong> assigne Playfield, Backglass et FullDMD.</li>
<li><strong>Audio :</strong> détecte les cartes audio et prépare SSF V2.</li>
</ol>
<p>Ces étapes sont obligatoires parce qu’un pincab dépend fortement des pilotes vidéo, du réseau, des écrans et du son.</p>
</div>

<div class="card help-card help-item">
<h2>5. Écrans : Playfield, Backglass, FullDMD</h2>
<ul>
<li><strong>Playfield :</strong> écran principal où la table est affichée.</li>
<li><strong>Backglass :</strong> écran arrière avec le visuel de la machine.</li>
<li><strong>FullDMD :</strong> écran dédié au DMD ou aux médias DMD.</li>
</ul>
<pre>Écran 1 : Playfield
Écran 2 : Backglass
Écran 3 : FullDMD</pre>
<p>Si un écran est inversé ou mal placé, VPX peut s’ouvrir au mauvais endroit.</p>
</div>

<div class="card help-card help-item">
<h2>6. Audio / SSF V2</h2>
<p>SSF signifie Surround Sound Feedback. Il permet de simuler les sons mécaniques de la bille dans le cab.</p>
<ul>
<li>Backglass : sons classiques et ROM.</li>
<li>Playfield avant : effets de bille avant.</li>
<li>Playfield arrière : effets de bille arrière.</li>
<li>Bass shaker : vibration basse fréquence.</li>
</ul>
<p>Utilise la page Audio / SSF V2 pour détecter les cartes audio, tester les sorties et appliquer la configuration.</p>
</div>

<div class="card help-card help-item">
<h2>7. Inputs / boutons</h2>
<ul>
<li>Configure flippers, start, coin, exit, launch ball, nudge et plunger.</li>
<li>Map Commander peut détecter les touches ou entrées brutes.</li>
<li>PinCabOS recommande un mapping clavier quand possible pour réduire la latence.</li>
<li>Pour un vrai cab, fais la configuration directement sur le cab avec les vrais boutons.</li>
</ul>
</div>

<div class="card help-card help-item">
<h2>8. DOF / Outputs</h2>
<p>DOF contrôle les toys physiques.</p>
<ul>
<li>Contacteurs</li>
<li>Knocker</li>
<li>Shaker</li>
<li>Beacon</li>
<li>Strobes</li>
<li>LedWiz</li>
<li>WS2811 / MX</li>
<li>Sainsmart</li>
<li>Pinscape</li>
</ul>
<p>Si DOF ne réagit pas, vérifie les permissions USB, le périphérique, le mapping et les profils.</p>
</div>

<div class="card help-card help-item">
<h2>9. Importation des tables</h2>
<ul>
<li><code>.vpx</code> : fichier principal de la table.</li>
<li><code>.zip</code> : ROM.</li>
<li><code>PupPack</code> : pack vidéo/audio.</li>
<li><code>Wheel</code> : logo dans le frontend.</li>
<li><code>Backglass</code> : média écran arrière.</li>
<li><code>FullDMD</code> : média DMD.</li>
</ul>
<p>PinCabOS aide à préparer les fichiers, mais VPinFE garde son rôle de frontend.</p>
</div>

<div class="card help-card help-item">
<h2>10. Arborescences importantes</h2>
<h3>PinCabOS</h3>
<pre>/opt/pincabos/
├── web/                    # WebApp PinCabOS
├── tools/                  # scripts PinCabOS
├── config/                 # configurations JSON
├── apps/
│   ├── vpx/                # VPX Linux
│   └── frontend/vpinfe/    # VPinFE
└── logs/                   # journaux</pre>

<h3>VPX Linux</h3>
<pre>/opt/pincabos/apps/vpx/
├── current/
├── backups/
└── downloads/

~/.local/share/VPinballX/10.8/
└── VPinballX.ini</pre>

<h3>VPinFE</h3>
<pre>/opt/pincabos/apps/frontend/vpinfe/
├── main.py
├── common/
├── frontend/
├── managerui/
├── themes/
├── chromium/
└── .venv/</pre>
</div>

<div class="card help-card help-item">
<h2>11. Dépannage rapide</h2>
<ul>
<li><strong>Écran noir :</strong> vérifier GPU, pilotes, OpenGL, assignation des écrans.</li>
<li><strong>Pas de son :</strong> vérifier Audio / SSF, volumes et périphériques.</li>
<li><strong>Table ne démarre pas :</strong> vérifier .vpx, ROM, PupPack et logs VPX.</li>
<li><strong>DOF inactif :</strong> vérifier périphérique, USB, permissions et mapping.</li>
<li><strong>WebApp inaccessible :</strong> vérifier IP, réseau, service PinCabOS Web.</li>
<li><strong>VPinFE boucle :</strong> vérifier Chromium VPinFE et service frontend.</li>
</ul>
</div>

<div class="card help-card help-item">
<h2>12. Lexique</h2>
<span class="help-tag">Backend : services système</span>
<span class="help-tag">Frontend : interface de lancement</span>
<span class="help-tag">VPX : moteur Visual Pinball</span>
<span class="help-tag">VPinFE : frontend PinCab</span>
<span class="help-tag">DOF : Direct Output Framework</span>
<span class="help-tag">SSF : Surround Sound Feedback</span>
<span class="help-tag">ROM : programme original</span>
<span class="help-tag">PupPack : pack multimédia</span>
<span class="help-tag">DMD : affichage matriciel</span>
<span class="help-tag">FullDMD : écran DMD complet</span>
<span class="help-tag">Playfield : écran principal</span>
<span class="help-tag">Backglass : écran arrière</span>
<span class="help-tag">DHCP : IP automatique</span>
<span class="help-tag">IP fixe : IP permanente</span>
<span class="help-tag">127.0.0.1 : cet ordinateur</span>
</div>

<script>
document.getElementById("helpSearch").addEventListener("input", function(){
  const q = this.value.toLowerCase().trim();
  document.querySelectorAll(".help-item").forEach(function(card){
    card.style.display = card.innerText.toLowerCase().includes(q) ? "" : "none";
  });
});
</script>
"""
    return page("Aide PinCabOS", body)

@app.route("/about")
def about_page():
    ver = pincabos_version()
    version_label = esc(str(ver.get("version", "Alpha 1.3")))
    build_label = esc(str(ver.get("build", "")))

    body = """
<div class="about-page">

<style>
.about-page h3 { color:#ff9f1c; margin-top:18px; }
.about-page .about-pill {
  display:inline-block;
  padding:6px 10px;
  margin:4px 6px 4px 0;
  border:1px solid rgba(255,176,0,.35);
  border-radius:999px;
  background:rgba(255,176,0,.08);
  color:#ffb000;
  font-weight:800;
}
.about-page .about-note {
  border-left:4px solid #ffb000;
  padding:10px 14px;
  background:rgba(255,176,0,.06);
  border-radius:10px;
}
.about-page code { color:#ffb000; }
</style>

<div class="card">
  <div style="display:flex; align-items:center; justify-content:space-between; gap:14px; flex-wrap:wrap;">
    <h2 style="margin:0;">À propos de PinCabOs</h2>
    <div style="display:flex; gap:10px; flex-wrap:wrap;">
      <a class="button" href="/help">📖 Aide / Documentation</a>
      <a class="button" href="/dev">Développeur / rapport testeur</a>
    </div>
  </div>

  <p>
    <strong>PinCabOs __PINCABOS_VERSION_LABEL__</strong> est un système Linux spécialisé pour les pincabs virtuels,
    créé, assemblé et personnalisé par <strong>Karots Sugarpie</strong>.
    Il complète l’écosystème <strong>VPX Linux</strong> et <strong>VPinFE</strong> avec une couche système,
    une WebApp centrale, des outils de maintenance, des fonctions d’import/export et une logique de mise à jour.
  </p>

  <p>
    <strong>VPinFE</strong> reste le frontend principal : tables, médias, collections, wheels, vidéos et lancement.
    <strong>PinCabOs</strong> agit comme backend système : services, réseau, fichiers, écrans, audio, inputs,
    outputs, DOF, FullDMD, updates et automatisations.
  </p>

  <p>
    <span class="about-pill">Alpha 1.3</span>
    <span class="about-pill">VPX BGFX</span>
    <span class="about-pill">VPinFE</span>
    <span class="about-pill">DOF Commander</span>
    <span class="about-pill">PinCab Explorer</span>
    <span class="about-pill">Update intelligent</span>
  </p>
</div>

<div class="card">
  <h2>État actuel Alpha 1.3</h2>
  <ul>
    <li>WebApp PinCabOs nettoyée, stabilisée et centralisée dans <code>/opt/pincabos/web/app.py</code>.</li>
    <li>VPX migré vers <strong>VPinballX_BGFX</strong>.</li>
    <li>Compatibilité conservée : <code>VPinballX_GL</code> pointe vers <code>VPinballX_BGFX</code>.</li>
    <li>VPinFE intégré et conservé comme frontend principal.</li>
    <li>Nettoyage système effectué : anciens backups, fichiers broken, caches temporaires, vieux packages et dossiers de build retirés.</li>
    <li>Scripts essentiels vérifiés : updater, publish, update-vpx et build-update.</li>
  </ul>
</div>

<div class="card">
  <h2>Fonctions principales</h2>

  <h3>Système et tableau de bord</h3>
  <ul>
    <li>Affichage hostname, IP, OS, kernel, uptime, timezone et heure locale.</li>
    <li>Suivi CPU, mémoire, disques, GPU, versions et chemins essentiels.</li>
    <li>Contrôle des services principaux depuis l’interface.</li>
    <li>Interface compacte adaptée à un pincab.</li>
  </ul>

  <h3>VPX Linux / BGFX</h3>
  <ul>
    <li>VPX Linux installé dans <code>/opt/pincabos/apps/vpx</code>.</li>
    <li>Moteur courant : <strong>BGFX</strong>.</li>
    <li>Configuration moteur dans <code>/opt/pincabos/config/vpx-engine.json</code>.</li>
    <li>Script <code>update-vpx.sh</code> pour mettre à jour VPX BGFX depuis la source configurée.</li>
  </ul>

  <h3>VPinFE</h3>
  <ul>
    <li>Frontend principal de PinCabOs.</li>
    <li>Gestion des tables, médias, collections, wheels, vidéos et lancement.</li>
    <li>Configuration utilisateur VPinFE préservée.</li>
    <li>Association VPinFE/VPSdb utilisée lors de l’importation lorsque disponible.</li>
  </ul>

  <h3>Mises à jour PinCabOS</h3>
  <ul>
    <li>Page dédiée <strong>Mise à jour PinCabOS</strong>.</li>
    <li>Vérification du serveur <code>update.pincabos.cc</code>.</li>
    <li>Update normal pour WebApp, outils, services et configurations.</li>
    <li>Force update pour dépendances, apps, migrations, services systemd, nginx et fichiers système.</li>
    <li>Paquets <code>.tar.zst</code> avec <code>latest.json</code>, <code>manifest.json</code> et vérification SHA256.</li>
    <li>Archivage automatique des anciennes versions publiées.</li>
    <li>Progression, logs, état <code>awaiting_reboot</code> et redémarrage contrôlé.</li>
  </ul>

  <h3>Écrans / GPU / FullDMD</h3>
  <ul>
    <li>Détection et assignation Playfield, Backglass et FullDMD.</li>
    <li>Page GPU / Écrans pour vérifier et appliquer les rôles.</li>
    <li>Calibration FullDMD depuis la WebApp.</li>
    <li>Sauvegarde des géométries vers les configurations PinCabOs, VPinFE et VPinballX.</li>
  </ul>

  <h3>Audio / SSF V2</h3>
  <ul>
    <li>Page Audio / SSF V2 intégrée.</li>
    <li>Préparation des rôles audio : backbox, ROM, musique, effets sous playfield, surround VPX et bass shaker.</li>
    <li>Tests audio par rôle.</li>
  </ul>

  <h3>Inputs / Map Commander</h3>
  <ul>
    <li>Mapping des touches VPX.</li>
    <li>Map Commander séparé pour organiser les mappings principaux.</li>
    <li>Détection ponctuelle des entrées et retour aux valeurs par défaut.</li>
  </ul>

  <h3>Outputs / DOF Commander</h3>
  <ul>
    <li>Import des fichiers DOF classiques : <code>.zip</code>, <code>.ini</code>, <code>.xml</code>.</li>
    <li>Import du Cabinet JSON exporté depuis DOF Config Tool V3.</li>
    <li>Support du cab réel <strong>Ultimate VPinball</strong> avec LedWiz 1, WS2811 1 et DudesCab 1.</li>
    <li>DOF Commander pour visualiser périphériques, outputs physiques, toys et combos.</li>
    <li>Tests avec toggle OFF/ON, durée, intensité, modes de test, auto-repeat et journal intégré.</li>
    <li>Driver Pack DOF : LedWiz réel minimal, ArtNet préparé, autres familles en safe mode.</li>
  </ul>

  <h3>PinCab Explorer</h3>
  <ul>
    <li>Explorateur de fichiers Web intégré.</li>
    <li>Vue liste et grille, recherche, tri, sélection et rafraîchissement.</li>
    <li>Création de dossiers, upload, download, renommage, duplication, suppression et extraction ZIP.</li>
    <li>Accès aux dossiers Tables, Médias, Exports, Imports, Share, USB et lecteurs SMB.</li>
  </ul>

  <h3>Import / Export de tables</h3>
  <ul>
    <li>Analyse des tables <code>.vpx</code> et archives <code>.zip</code>, <code>.rar</code>, <code>.7z</code>.</li>
    <li>Détection DirectB2S, ROM PinMAME, AltSound, AltColor, PupPack, UltraDMD/FlexDMD, POV, INI et VBS.</li>
    <li>Normalisation vers une structure portable VPinFE/VPX.</li>
    <li>Export complet avec manifest <code>pincabos-export-manifest.json</code>.</li>
  </ul>

  <h3>Réseau / SMB / USB / Share</h3>
  <ul>
    <li>Mode DHCP ou IP fixe, WiFi et hotspot temporaire.</li>
    <li>Montage de partages SMB/NAS dans <code>/home/pinball/NetworkDrives</code>.</li>
    <li>Zone USB dédiée : <code>/mnt/pincab-usb</code>.</li>
    <li>Dossier local permanent : <code>/home/pinball/Share</code>.</li>
  </ul>

  <h3>Rapports testeurs / développement</h3>
  <ul>
    <li>Page développeur protégée.</li>
    <li>Formulaire pour problème, idée, amélioration ou solution.</li>
    <li>Collecte d’informations système utiles pour diagnostiquer les tests.</li>
    <li>Watchdog indiquant si le serveur de rapports est online ou offline.</li>
  </ul>
</div>

<div class="card">
  <h2>Chemins importants</h2>
  <table>
    <tr><th>Élément</th><th>Chemin</th></tr>
    <tr><td>Base PinCabOs</td><td><code>/opt/pincabos</code></td></tr>
    <tr><td>WebApp</td><td><code>/opt/pincabos/web</code></td></tr>
    <tr><td>Outils</td><td><code>/opt/pincabos/tools</code></td></tr>
    <tr><td>VPX</td><td><code>/opt/pincabos/apps/vpx</code></td></tr>
    <tr><td>VPX courant</td><td><code>/opt/pincabos/apps/vpx/current</code></td></tr>
    <tr><td>VPinFE</td><td><code>/opt/pincabos/apps/frontend/vpinfe</code></td></tr>
    <tr><td>Tables VPX</td><td><code>/opt/pincabos/vpinball/Tables</code></td></tr>
    <tr><td>PupVideos</td><td><code>/opt/pincabos/pupvideos</code></td></tr>
    <tr><td>Imports</td><td><code>/opt/pincabos/imports</code></td></tr>
    <tr><td>Exports</td><td><code>/opt/pincabos/exports</code></td></tr>
    <tr><td>PinCabShare</td><td><code>/home/pinball/Share</code></td></tr>
    <tr><td>Lecteurs SMB</td><td><code>/home/pinball/NetworkDrives</code></td></tr>
    <tr><td>Clés USB</td><td><code>/mnt/pincab-usb</code></td></tr>
  </table>
</div>

<div class="card">
  <h2>Ce qui reste à faire</h2>
  <ul>
    <li>Valider Alpha 1.3 chez les testeurs avec update normal et force update.</li>
    <li>Tester VPX BGFX sur vrais cabs avec plusieurs GPU/écrans.</li>
    <li>Continuer les tests réels DOF, SSF V2, FullDMD, Inputs et import/export de tables.</li>
    <li>Optimiser la taille des paquets update pour éviter les caches ou dossiers inutiles.</li>
    <li>Documenter installation, premier démarrage, update et fonctions principales.</li>
    <li><strong>Alpha 1.3 = UEFI seulement.</strong></li>
    <li><strong>Alpha 1.4 ou Beta :</strong> ajouter le support Legacy / CSM pour les machines plus anciennes.</li>
    <li>Préparer une distribution publique plus propre pour les prochaines versions.</li>
    <li>Faire plus tard une vraie internationalisation FR/EN complète de toute la WebApp.</li>
  </ul>
</div>

<div class="card">
  <h2>Auteur</h2>
  <p>
    <strong>Karots Sugarpie</strong><br>
    Projet développé autour de VPX Linux, VPinFE, PinCabOs Web, DOF, GPU auto-config,
    calibration multi-écrans, console Web, réseau, partage de fichiers et automatisation pour pincabs.
  </p>
  <p><a href="https://pincabos.cc" target="_blank" rel="noopener">https://pincabos.cc</a></p>
</div>


<div class="card">
  <h2>Testeurs / Soutiens fondateurs</h2>
  <p>
    Merci aux personnes qui aident à tester PinCabOs, rapporter les problèmes,
    proposer des idées et soutenir le développement du projet.
  </p>

  <style>
    .pco-supporters {
      display:flex;
      flex-wrap:wrap;
      gap:12px;
      margin-top:12px;
    }
    .pco-supporter {
      display:inline-flex;
      align-items:center;
      gap:8px;
      padding:10px 14px;
      border-radius:999px;
      border:1px solid rgba(210,210,210,.55);
      background:linear-gradient(135deg,rgba(255,255,255,.10),rgba(180,180,180,.08));
      color:#e6e6e6;
      font-weight:900;
      letter-spacing:.2px;
      box-shadow:0 0 16px rgba(220,220,220,.12);
    }
    .pco-silver-star {
      color:#d8d8d8;
      text-shadow:0 0 8px rgba(255,255,255,.65);
      font-size:18px;
    }
  </style>

  <div class="pco-supporters">
    <span class="pco-supporter"><span class="pco-silver-star">★</span> Strung Flo <span class="pco-silver-star">★</span></span>
    <span class="pco-supporter"><span class="pco-silver-star">★</span> Nicolas Prou <span class="pco-silver-star">★</span></span>
  </div>
</div>


</div>
"""
    body = body.replace("__PINCABOS_VERSION_LABEL__", version_label)
    if build_label:
        body = body.replace("Alpha 1.3</span>", "Alpha 1.3</span><span class=\"about-pill\">Build " + build_label + "</span>", 1)
    return page("À propos", body)

def pincabos_import_safe_job_id():
    import datetime
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]


def pincabos_list_archive_files(path):
    try:
        r = subprocess.run(
            ["7z", "l", "-slt", str(path)],
            capture_output=True,
            text=True,
            timeout=45
        )
        data = (r.stdout + "\n" + r.stderr)
        out = []
        for line in data.splitlines():
            line = line.strip()
            if line.startswith("Path = "):
                value = line.split("=", 1)[1].strip()
                if value and value != str(path):
                    out.append(value)
        return out
    except Exception:
        return []


def pincabos_is_zip_rom(path):
    if not str(path).lower().endswith(".zip"):
        return False

    files = [x.lower() for x in pincabos_list_archive_files(path)]
    joined = "\n".join(files)

    markers = [
        ".vpx",
        ".directb2s",
        ".pov",
        ".vbs",
        "pinupplayer.ini",
        ".pup",
        ".ultradmd",
        "altsound.ini",
        "altsound.csv",
        ".ogg",
        ".wav",
        ".pac",
        ".pal",
        ".vni",
        ".serum",
    ]

    if any(m in joined for m in markers):
        return False

    return True


def pincabos_detect_batch(batch_dir):
    import re
    from pathlib import Path

    batch = Path(batch_dir)
    files = [p for p in batch.rglob("*") if p.is_file()]
    archive_virtual_files = []

    for f in files:
        if f.suffix.lower() in [".zip", ".rar", ".7z"]:
            for inner in pincabos_list_archive_files(f):
                archive_virtual_files.append((f, inner))

    detected = {
        "main_vpx": "",
        "table_name": "",
        "rom": "",
        "has_b2s": False,
        "has_pov": False,
        "has_ini": False,
        "has_vbs": False,
        "has_rom": False,
        "has_altsound": False,
        "has_altcolor": False,
        "has_puppack": False,
        "has_ultradmd": False,
        "files": [str(x) for x in files],
    }

    vpx_files = [f for f in files if f.suffix.lower() == ".vpx"]
    if vpx_files:
        vpx_files.sort(key=lambda x: x.stat().st_size if x.exists() else 0, reverse=True)
        detected["main_vpx"] = str(vpx_files[0])
        detected["table_name"] = re.sub(r"[_]+", " ", vpx_files[0].stem).strip()

    if not detected["table_name"]:
        for archive, inner in archive_virtual_files:
            if inner.lower().endswith(".vpx"):
                detected["table_name"] = re.sub(r"[_]+", " ", Path(inner).stem).strip()
                detected["main_vpx"] = str(archive) + "::" + inner
                break

    for f in files:
        if pincabos_is_zip_rom(f):
            detected["rom"] = f.stem
            detected["has_rom"] = True
            break

    # Détection AltSound et indice ROM
    for f in files:
        if f.suffix.lower() in [".rar", ".7z", ".zip"]:
            inner_files = [x.lower() for x in pincabos_list_archive_files(f)]
            names = [Path(x).name.lower() for x in inner_files]
            if "altsound.ini" in names or "altsound.csv" in names or sum(1 for x in inner_files if x.endswith(".ogg")) > 10:
                detected["has_altsound"] = True
                if not detected["rom"]:
                    detected["rom"] = f.stem

    for f in files:
        suffix = f.suffix.lower()

        if suffix == ".directb2s":
            detected["has_b2s"] = True
        elif suffix == ".pov":
            detected["has_pov"] = True
        elif suffix == ".ini":
            detected["has_ini"] = True
        elif suffix == ".vbs":
            detected["has_vbs"] = True
        elif suffix in [".pac", ".pal", ".vni", ".serum"]:
            detected["has_altcolor"] = True

        if suffix in [".zip", ".rar", ".7z"]:
            inner = "\n".join([x.lower() for x in pincabos_list_archive_files(f)])
            if "pinupplayer.ini" in inner or ".pup" in inner or inner.count(".mp4") >= 3:
                detected["has_puppack"] = True
            if ".ultradmd" in inner:
                detected["has_ultradmd"] = True
            if ".directb2s" in inner:
                detected["has_b2s"] = True
            if ".pov" in inner:
                detected["has_pov"] = True
            if ".vbs" in inner:
                detected["has_vbs"] = True
            if ".pac" in inner or ".pal" in inner or ".vni" in inner or ".serum" in inner:
                detected["has_altcolor"] = True

    if not detected["table_name"]:
        detected["table_name"] = batch.name

    return detected


def pincabos_vpsdb_matches(table_name, rom):
    try:
        r = subprocess.run(
            ["/opt/pincabos/tools/vpinfe-vpsdb-match.py", table_name, rom or ""],
            capture_output=True,
            text=True,
            timeout=30
        )
        data = json.loads(r.stdout)
        return data.get("matches", []) if data.get("ok") else []
    except Exception:
        return []


def pincabos_get_vpinfe_paths_for_tools():
    """
    Chemins utilisés par VPinFE / PinCabOs.
    On lit tablerootdir si disponible, sinon on utilise le chemin PinCabOs standard.
    """
    from pathlib import Path

    cfg_path = Path("/home/pinball/.config/vpinfe/vpinfe.ini")

    result = {
        "config": str(cfg_path),
        "tables": "/opt/pincabos/vpinball/Tables",
        "roms": "/opt/pincabos/vpinball/PinMAME/roms",
        "altcolor": "/opt/pincabos/vpinball/PinMAME/altcolor",
        "altsound": "/opt/pincabos/vpinball/PinMAME/altsound",
        "pupvideos": "/opt/pincabos/pupvideos",
        "ultradmd": "/opt/pincabos/ultradmd",
        "exports": "/opt/pincabos/exports",
    }

    if cfg_path.exists():
        try:
            for line in cfg_path.read_text(errors="replace").splitlines():
                if "=" not in line:
                    continue

                key, value = [x.strip() for x in line.split("=", 1)]

                if key.lower() == "tablerootdir" and value:
                    result["tables"] = value
        except Exception:
            pass

    tables = Path(result["tables"])
    root = tables.parent if tables.exists() else Path("/opt/pincabos/vpinball")

    result["roms"] = str(root / "PinMAME" / "roms")
    result["altcolor"] = str(root / "PinMAME" / "altcolor")
    result["altsound"] = str(root / "PinMAME" / "altsound")

    return result


def pincabos_list_installed_tables_for_export():
    """
    Liste les tables installées pour le menu Export.
    Une table = un dossier dans Tables qui contient au moins un fichier .vpx.
"""
    import json
    from pathlib import Path

    paths = pincabos_get_vpinfe_paths_for_tools()
    tables_root = Path(paths["tables"])

    tables = []

    if not tables_root.exists():
        return tables

    for folder in sorted([x for x in tables_root.iterdir() if x.is_dir()], key=lambda x: x.name.lower()):
        vpx_files = sorted(folder.glob("*.vpx"))

        if not vpx_files:
            continue

        info_files = sorted(folder.glob("*.info"))

        title = folder.name
        rom = ""
        vpsid = ""
        manufacturer = ""
        year = ""

        if info_files:
            try:
                data = json.loads(info_files[0].read_text(errors="replace"))
                info = data.get("Info", {})
                title = info.get("Title") or title
                rom = info.get("Rom") or ""
                vpsid = info.get("VPSId") or ""
                manufacturer = info.get("Manufacturer") or ""
                year = info.get("Year") or ""
            except Exception:
                pass

        extra = []
        if manufacturer:
            extra.append(str(manufacturer))
        if year:
            extra.append(str(year))
        if rom:
            extra.append("ROM " + str(rom))

        label = title
        if extra:
            label += " — " + " — ".join(extra)

        tables.append({
            "folder": folder.name,
            "title": title,
            "rom": rom,
            "vpsid": vpsid,
            "label": label,
        })

    return tables


# === PINCABOS VPX BALL CABINET TOOLS START ===
VPX_BALLCAB_PRIMARY_INI = Path("/home/pinball/.local/share/VPinballX/10.8/VPinballX.ini")
VPX_BALLCAB_SECONDARY_INI = Path("/home/pinball/.vpinball/VPinballX.ini")
VPX_BALLCAB_BACKUP_DIR = Path("/opt/pincabos/backups/vpx-ball-cabinet")

VPX_BALLCAB_KEYS = {
    "Player": [
        ("CabinetAutofitMode", "Mode Cabinet Autofit"),
        ("CabinetAutofitPos", "Position Cabinet Autofit"),
        ("BallAntiStretch", "Ball Anti-Stretch"),
        ("DisableLightingForBalls", "Désactiver lighting sur les billes"),
        ("BallTrail", "Ball Trail"),
        ("BallTrailStrength", "Force Ball Trail"),
        ("OverwriteBallImage", "Utiliser image personnalisée de bille"),
        ("BallImage", "Nom image bille"),
        ("DecalImage", "Nom image décalque"),
        ("TouchOverlay", "Touch Overlay"),
    ],
    "DefaultProps\\Ball": [
        ("ForceReflection", "Force Reflection"),
        ("DecalMode", "Decal Mode"),
        ("Image", "Image bille par défaut"),
        ("DecalImage", "Décalque bille par défaut"),
        ("BulbIntensityScale", "Bulb Intensity Scale"),
        ("PFReflStrength", "Playfield Reflection Strength"),
        ("Color", "Couleur"),
        ("SphereMap", "Sphere Map"),
        ("ReflectionEnabled", "Reflection Enabled"),
    ],
}

def vpx_ballcab_ini_path():
    if VPX_BALLCAB_PRIMARY_INI.exists():
        return VPX_BALLCAB_PRIMARY_INI
    return VPX_BALLCAB_SECONDARY_INI

def vpx_ballcab_read_lines(path):
    if path.exists():
        return path.read_text(errors="replace").splitlines()
    return []

def vpx_ballcab_write_lines(path, lines):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

def vpx_ballcab_backup(path):
    VPX_BALLCAB_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dst = VPX_BALLCAB_BACKUP_DIR / (path.name + ".backup-vpx-ball-cabinet-" + stamp)
    if path.exists():
        shutil.copy2(path, dst)
        return dst
    return None

def vpx_ballcab_find_section(lines, section):
    header = "[" + section + "]"
    start = None
    end = len(lines)

    for i, line in enumerate(lines):
        if line.strip().lower() == header.lower():
            start = i
            break

    if start is None:
        return None, None

    for j in range(start + 1, len(lines)):
        s = lines[j].strip()
        if s.startswith("[") and s.endswith("]"):
            end = j
            break

    return start, end

def vpx_ballcab_get_value(lines, section, key):
    start, end = vpx_ballcab_find_section(lines, section)
    if start is None:
        return ""

    key_l = key.lower()
    for line in lines[start + 1:end]:
        s = line.strip()
        if not s or s.startswith(";") or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        if k.strip().lower() == key_l:
            return v.strip()
    return ""

def vpx_ballcab_set_value(lines, section, key, value):
    comment = "; Modifié " + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + " par PinCabOS fonction(VPX Ball / Cabinet)"
    header = "[" + section + "]"
    start, end = vpx_ballcab_find_section(lines, section)

    if start is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(header)
        lines.append(comment)
        lines.append(key + " = " + value)
        return lines

    key_l = key.lower()
    key_index = None

    for i in range(start + 1, end):
        s = lines[i].strip()
        if not s or s.startswith(";") or s.startswith("#") or "=" not in s:
            continue
        k, _v = s.split("=", 1)
        if k.strip().lower() == key_l:
            key_index = i
            break

    if key_index is not None:
        if key_index > 0 and "par PinCabOS fonction(VPX Ball / Cabinet)" in lines[key_index - 1]:
            lines[key_index - 1] = comment
        else:
            lines.insert(key_index, comment)
            key_index += 1
        lines[key_index] = key + " = " + value
        return lines

    insert_at = end
    lines.insert(insert_at, comment)
    lines.insert(insert_at + 1, key + " = " + value)
    return lines

def vpx_ballcab_form_name(section, key):
    return section.replace("\\", "__BS__").replace(" ", "__SP__") + "___" + key

def vpx_ballcab_rows(lines):
    rows = []
    for section, keys in VPX_BALLCAB_KEYS.items():
        rows.append('<tr><th colspan="3" style="text-align:left;color:#ffb000;">[' + esc(section) + ']</th></tr>')
        for key, label in keys:
            val = vpx_ballcab_get_value(lines, section, key)
            name = vpx_ballcab_form_name(section, key)

            hint = ""
            if key in ["BallTrail", "OverwriteBallImage", "BallAntiStretch", "DisableLightingForBalls", "TouchOverlay", "ReflectionEnabled", "ForceReflection"]:
                hint = "0/1"
            elif key in ["BallTrailStrength", "BulbIntensityScale", "PFReflStrength"]:
                hint = "nombre"
            elif key in ["BallImage", "DecalImage", "Image", "SphereMap"]:
                hint = "nom image VPX"

            rows.append(
                '<tr>'
                '<td><strong>' + esc(label) + '</strong><br><code>' + esc(key) + '</code></td>'
                '<td><input name="' + esc(name) + '" value="' + esc(val) + '" placeholder="' + esc(hint) + '" style="width:50%;max-width:420px;min-width:240px;padding:8px;"></td>'
                '<td><code>' + esc(val if val else "vide") + '</code></td>'
                '</tr>'
            )
    return "\n".join(rows)

def vpx_ballcab_current_preview(lines):
    out = []
    for section, keys in VPX_BALLCAB_KEYS.items():
        out.append("[" + section + "]")
        for key, _label in keys:
            out.append(key + " = " + vpx_ballcab_get_value(lines, section, key))
        out.append("")
    return "\n".join(out).strip()

@app.route("/tools/vpx-ball-cabinet")
def tools_vpx_ball_cabinet():
    ini = vpx_ballcab_ini_path()
    lines = vpx_ballcab_read_lines(ini)

    other = VPX_BALLCAB_SECONDARY_INI if ini == VPX_BALLCAB_PRIMARY_INI else VPX_BALLCAB_PRIMARY_INI
    other_info = "Présent" if other.exists() else "Absent"

    body = """
<div class="card">
  <h2>VPX Ball / Cabinet</h2>

  <p>
    Gestion des options globales VPX liées à la bille, au trail, au mode cabinet,
    à l’image de bille personnalisée et au décalque.
  </p>

  <p>
    Fichier actif : <code>__INI__</code><br>
    Autre fichier détecté : <code>__OTHER__</code> — __OTHER_INFO__
  </p>

  <p class="warn">
    Les champs vides restent vides dans <code>VPinballX.ini</code>.
    Pour les booléens VPX, utilise généralement <code>0</code> ou <code>1</code>.
    Pour <code>BallImage</code> et <code>DecalImage</code>, utilise le nom de l’image connue par VPX/table.
  </p>

  <form method="post" action="/tools/vpx-ball-cabinet/apply">
    <table style="width:100%;border-collapse:collapse;">
      <tr>
        <th style="text-align:left;">Option</th>
        <th style="text-align:left;">Nouvelle valeur</th>
        <th style="text-align:left;">Valeur actuelle</th>
      </tr>
      __ROWS__
    </table>

    <p style="margin-top:16px;">
      <button class="button" type="submit">Appliquer dans VPinballX.ini</button>
      <a class="button secondary" href="/tools">Retour Outils</a>
    </p>
  </form>
</div>

<div class="card" style="margin-top:20px;">
  <h2>Résumé technique actuel</h2>
  <pre style="white-space:pre-wrap;max-height:460px;overflow:auto;background:rgba(0,0,0,.45);border:1px solid rgba(255,176,0,.25);border-radius:12px;padding:12px;">__PREVIEW__</pre>
</div>
"""
    body = body.replace("__INI__", esc(str(ini)))
    body = body.replace("__OTHER__", esc(str(other)))
    body = body.replace("__OTHER_INFO__", esc(other_info))
    body = body.replace("__ROWS__", vpx_ballcab_rows(lines))
    body = body.replace("__PREVIEW__", esc(vpx_ballcab_current_preview(lines)))

    return page("Outils", body)

@app.route("/tools/vpx-ball-cabinet/apply", methods=["POST"])
def tools_vpx_ball_cabinet_apply():
    ini = vpx_ballcab_ini_path()
    lines = vpx_ballcab_read_lines(ini)
    backup = vpx_ballcab_backup(ini)

    changed = []

    for section, keys in VPX_BALLCAB_KEYS.items():
        for key, label in keys:
            form_name = vpx_ballcab_form_name(section, key)
            value = request.form.get(form_name, "").strip()
            old_value = vpx_ballcab_get_value(lines, section, key)

            lines = vpx_ballcab_set_value(lines, section, key, value)

            if value != old_value:
                changed.append("[" + section + "] " + key + " : " + old_value + " -> " + value)

    # Section de suivi PinCabOS
    lines = vpx_ballcab_set_value(lines, "PinCabOs.BallCabinet", "managed_by", "PinCabOS VPX Ball / Cabinet")
    lines = vpx_ballcab_set_value(lines, "PinCabOs.BallCabinet", "updated_at", datetime.now().isoformat(timespec="seconds"))

    vpx_ballcab_write_lines(ini, lines)

    preview = "\n".join(changed) if changed else "Aucune valeur différente détectée, fichier réécrit avec suivi PinCabOS."
    backup_text = str(backup) if backup else "Aucun backup, fichier créé."

    body = """
<div class="card">
  <h2>VPX Ball / Cabinet appliqué</h2>
  <p class="ok">Configuration écrite dans <code>VPinballX.ini</code>.</p>

  <table>
    <tr><td>Fichier</td><td><code>__INI__</code></td></tr>
    <tr><td>Backup</td><td><code>__BACKUP__</code></td></tr>
  </table>

  <h3>Changements</h3>
  <pre style="white-space:pre-wrap;max-height:460px;overflow:auto;background:rgba(0,0,0,.45);border:1px solid rgba(255,176,0,.25);border-radius:12px;padding:12px;">__CHANGED__</pre>

  <p>
    <a class="button" href="/tools/vpx-ball-cabinet">Retour VPX Ball / Cabinet</a>
    <a class="button secondary" href="/tools">Retour Outils</a>
  </p>
</div>
"""
    body = body.replace("__INI__", esc(str(ini)))
    body = body.replace("__BACKUP__", esc(backup_text))
    body = body.replace("__CHANGED__", esc(preview))

    return page("Outils", body)
# === PINCABOS VPX BALL CABINET TOOLS END ===


# === PINCABOS SIMPLE VPX BALL CARD START ===
VPX_SIMPLE_BALL_INI = Path("/home/pinball/.local/share/VPinballX/10.8/VPinballX.ini")
VPX_SIMPLE_BALL_USERBALLS_DIR = Path("/opt/pincabos/userdata/UserBalls")
VPX_SIMPLE_BALL_IMAGE_DIR = VPX_SIMPLE_BALL_USERBALLS_DIR / "balls"
VPX_SIMPLE_BALL_DECAL_DIR = VPX_SIMPLE_BALL_USERBALLS_DIR / "decals"
VPX_SIMPLE_BALL_BACKUP_DIR = Path("/opt/pincabos/backups/vpx-ball-cabinet")

def vpx_simple_ball_read_lines():
    if VPX_SIMPLE_BALL_INI.exists():
        return VPX_SIMPLE_BALL_INI.read_text(errors="replace").splitlines()
    return []

def vpx_simple_ball_write_lines(lines):
    VPX_SIMPLE_BALL_INI.parent.mkdir(parents=True, exist_ok=True)
    VPX_SIMPLE_BALL_INI.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

def vpx_simple_ball_find_section(lines, section):
    header = "[" + section + "]"
    start = None
    end = len(lines)

    for i, line in enumerate(lines):
        if line.strip().lower() == header.lower():
            start = i
            break

    if start is None:
        return None, None

    for j in range(start + 1, len(lines)):
        s = lines[j].strip()
        if s.startswith("[") and s.endswith("]"):
            end = j
            break

    return start, end

def vpx_simple_ball_get(lines, section, key):
    start, end = vpx_simple_ball_find_section(lines, section)
    if start is None:
        return ""

    key_l = key.lower()
    for line in lines[start + 1:end]:
        s = line.strip()
        if not s or s.startswith(";") or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        if k.strip().lower() == key_l:
            return v.strip()
    return ""

def vpx_simple_ball_set(lines, section, key, value):
    comment = "; Modifié " + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + " par PinCabOS fonction(VPX Ball Image)"
    header = "[" + section + "]"
    start, end = vpx_simple_ball_find_section(lines, section)

    if start is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(header)
        lines.append(comment)
        lines.append(key + " = " + value)
        return lines

    key_l = key.lower()
    key_index = None

    for i in range(start + 1, end):
        s = lines[i].strip()
        if not s or s.startswith(";") or s.startswith("#") or "=" not in s:
            continue
        k, _v = s.split("=", 1)
        if k.strip().lower() == key_l:
            key_index = i
            break

    if key_index is not None:
        if key_index > 0 and "par PinCabOS fonction(VPX Ball Image)" in lines[key_index - 1]:
            lines[key_index - 1] = comment
        else:
            lines.insert(key_index, comment)
            key_index += 1
        lines[key_index] = key + " = " + value
        return lines

    insert_at = end
    lines.insert(insert_at, comment)
    lines.insert(insert_at + 1, key + " = " + value)
    return lines

def vpx_simple_ball_backup():
    VPX_SIMPLE_BALL_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dst = VPX_SIMPLE_BALL_BACKUP_DIR / ("VPinballX.ini.backup-simple-ball-" + stamp)
    if VPX_SIMPLE_BALL_INI.exists():
        shutil.copy2(VPX_SIMPLE_BALL_INI, dst)
        return dst
    return None

def vpx_simple_ball_image_options(selected, folder=None):
    from urllib.parse import quote

    if folder is None:
        folder = VPX_SIMPLE_BALL_IMAGE_DIR

    folder.mkdir(parents=True, exist_ok=True)
    files = []
    for ext in ["*.png", "*.jpg", "*.jpeg", "*.webp", "*.bmp"]:
        files.extend(folder.glob(ext))

    files = sorted(set(files), key=lambda x: x.name.lower())

    opts = ['<option value="" data-url="">Ne pas changer / vide</option>']
    for f in files:
        val = str(f)
        sel = " selected" if val == selected else ""
        kind = "decals" if str(folder).endswith("/decals") else "balls"
        url = "/userdata/UserBalls/" + kind + "/" + quote(f.name, safe="")
        opts.append(
            '<option value="' + esc(val) + '" data-url="' + esc(url) + '"' + sel + '>' + esc(f.name) + '</option>'
        )

    return "\n".join(opts)

def vpx_simple_ball_card():
    lines = vpx_simple_ball_read_lines()

    overwrite = vpx_simple_ball_get(lines, "Player", "OverwriteBallImage")
    ball = vpx_simple_ball_get(lines, "Player", "BallImage")
    decal = vpx_simple_ball_get(lines, "Player", "DecalImage")

    ball_trail = vpx_simple_ball_get(lines, "Player", "BallTrail")
    ball_trail_strength = vpx_simple_ball_get(lines, "Player", "BallTrailStrength")
    cabinet_autofit_mode = vpx_simple_ball_get(lines, "Player", "CabinetAutofitMode")
    cabinet_autofit_pos = vpx_simple_ball_get(lines, "Player", "CabinetAutofitPos")
    ball_antistretch = vpx_simple_ball_get(lines, "Player", "BallAntiStretch")

    checked = "checked" if overwrite == "1" else ""

    html = """
<div class="card" style="margin-top:20px;">
  <h2>VPX Ball / Cabinet</h2>

  <p>
    Carte simple pour appliquer une image personnalisée de bille et un décalque dans
    <code>[Player]</code> du fichier <code>VPinballX.ini</code>.
  </p>

  <p>
    Fichier INI : <code>__INI__</code><br>
    Dossier billes : <code>__BALL_DIR__</code><br>\n    Dossier décalques : <code>__DECAL_DIR__</code>
  </p>

  <form method="post" action="/tools/vpx-ball-simple/apply" enctype="multipart/form-data">
    <table style="width:100%;">
      <tr>
        <td>Activer image personnalisée</td>
        <td>
          <label>
            <input type="checkbox" name="overwrite_ball_image" value="1" __CHECKED__>
            Écrire <code>OverwriteBallImage = 1</code>
          </label>
        </td>
      </tr>

      <tr>
        <td>Importer image bille</td>
        <td>
          <input type="file" id="pco-ball-upload" name="ball_upload" accept=".png,.jpg,.jpeg,.webp,.bmp" onchange="pcoUserBallUploadPreview(this, 'pco-ball-preview')">
        </td>
      </tr>

      <tr>
        <td>Ou choisir image bille existante</td>
        <td>
          <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;">
            <select name="ball_existing" id="pco-ball-existing" onchange="pcoUserBallPreview('pco-ball-existing','pco-ball-preview')" style="width:50%;max-width:420px;min-width:240px;padding:8px;">
              __BALL_OPTIONS__
            </select>
            <div style="width:74px;height:74px;border:1px solid rgba(255,122,0,.45);border-radius:12px;background:rgba(0,0,0,.35);display:flex;align-items:center;justify-content:center;overflow:hidden;">
              <img id="pco-ball-preview" alt="Aperçu bille" style="max-width:72px;max-height:72px;display:none;">
              <span id="pco-ball-preview-empty" style="font-size:11px;color:#aaa;text-align:center;padding:4px;">Aperçu</span>
            </div>
          </div>
        </td>
      </tr>

      <tr>
        <td>Importer image décalque</td>
        <td>
          <input type="file" id="pco-decal-upload" name="decal_upload" accept=".png,.jpg,.jpeg,.webp,.bmp" onchange="pcoUserBallUploadPreview(this, 'pco-decal-preview')">
        </td>
      </tr>

      <tr>
        <td>Ou choisir décalque existant</td>
        <td>
          <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;">
            <select name="decal_existing" id="pco-decal-existing" onchange="pcoUserBallPreview('pco-decal-existing','pco-decal-preview')" style="width:50%;max-width:420px;min-width:240px;padding:8px;">
              __DECAL_OPTIONS__
            </select>
            <div style="width:74px;height:74px;border:1px solid rgba(255,122,0,.45);border-radius:12px;background:rgba(0,0,0,.35);display:flex;align-items:center;justify-content:center;overflow:hidden;">
              <img id="pco-decal-preview" alt="Aperçu décalque" style="max-width:72px;max-height:72px;display:none;">
              <span id="pco-decal-preview-empty" style="font-size:11px;color:#aaa;text-align:center;padding:4px;">Aperçu</span>
            </div>
          </div>
        </td>
      </tr>

      <tr>
        <td colspan="2"><h3 style="margin-top:18px;">Trail / effet de traînée</h3></td>
      </tr>

      <tr>
        <td>Ball Trail</td>
        <td>
          <select name="ball_trail" style="width:220px;padding:8px;">
            <option value="">Ne pas changer / vide</option>
            <option value="0" __BALL_TRAIL_0__>Désactivé</option>
            <option value="1" __BALL_TRAIL_1__>Activé</option>
          </select>
        </td>
      </tr>

      <tr>
        <td>Force Ball Trail</td>
        <td>
          <input name="ball_trail_strength" value="__BALL_TRAIL_STRENGTH__" placeholder="ex: 0.5, 1.0, 2.0" style="width:220px;padding:8px;">
        </td>
      </tr>

      <tr>
        <td colspan="2"><h3 style="margin-top:18px;">Cabinet / déformation bille</h3></td>
      </tr>

      <tr>
        <td>Cabinet Autofit Mode</td>
        <td>
          <input name="cabinet_autofit_mode" value="__CABINET_AUTOFIT_MODE__" placeholder="valeur VPX" style="width:220px;padding:8px;">
        </td>
      </tr>

      <tr>
        <td>Cabinet Autofit Pos</td>
        <td>
          <input name="cabinet_autofit_pos" value="__CABINET_AUTOFIT_POS__" placeholder="valeur VPX" style="width:220px;padding:8px;">
        </td>
      </tr>

      <tr>
        <td>Ball Anti-Stretch</td>
        <td>
          <select name="ball_antistretch" style="width:220px;padding:8px;">
            <option value="">Ne pas changer / vide</option>
            <option value="0" __BALL_ANTISTRETCH_0__>Désactivé</option>
            <option value="1" __BALL_ANTISTRETCH_1__>Activé</option>
          </select>
          <p class="warn" style="margin:6px 0 0 0;">
            Utile si la bille semble étirée/déformée en mode cabinet.
          </p>
        </td>
      </tr>
    </table>

    <p style="margin-top:14px;">
      <button class="button" type="submit">Appliquer dans VPinballX.ini</button>
    </p>
  </form>


<script>
function pcoUserBallSetPreview(imgId, url) {
  const img = document.getElementById(imgId);
  const empty = document.getElementById(imgId + "-empty");

  if (!img) return;

  if (!url) {
    img.removeAttribute("src");
    img.style.display = "none";
    if (empty) {
      empty.style.display = "block";
      empty.textContent = "Aperçu";
    }
    return;
  }

  img.onload = function() {
    img.style.display = "block";
    if (empty) empty.style.display = "none";
  };

  img.onerror = function() {
    img.removeAttribute("src");
    img.style.display = "none";
    if (empty) {
      empty.style.display = "block";
      empty.textContent = "Aperçu indisponible";
    }
  };

  img.src = url + (url.includes("?") ? "&" : "?") + "v=" + Date.now();
}

function pcoUserBallPreview(selectId, imgId) {
  const sel = document.getElementById(selectId);
  if (!sel) return;

  const opt = sel.options[sel.selectedIndex];
  const url = opt ? (opt.getAttribute("data-url") || "") : "";

  pcoUserBallSetPreview(imgId, url);
}

function pcoUserBallUploadPreview(input, imgId) {
  if (!input || !input.files || !input.files[0]) return;

  const url = URL.createObjectURL(input.files[0]);
  pcoUserBallSetPreview(imgId, url);
}

document.addEventListener("DOMContentLoaded", function() {
  pcoUserBallPreview("pco-ball-existing", "pco-ball-preview");
  pcoUserBallPreview("pco-decal-existing", "pco-decal-preview");
});
</script>

  <details style="margin-top:12px;">
    <summary>Valeurs actuelles [Player]</summary>
    <pre style="white-space:pre-wrap;max-height:260px;overflow:auto;background:rgba(0,0,0,.45);border:1px solid rgba(255,176,0,.25);border-radius:12px;padding:12px;">OverwriteBallImage = __OVERWRITE__
BallImage = __BALL__
DecalImage = __DECAL__
BallTrail = __BALL_TRAIL_VALUE__
BallTrailStrength = __BALL_TRAIL_STRENGTH_VALUE__
CabinetAutofitMode = __CABINET_AUTOFIT_MODE_VALUE__
CabinetAutofitPos = __CABINET_AUTOFIT_POS_VALUE__
BallAntiStretch = __BALL_ANTISTRETCH_VALUE__</pre>
  </details>
</div>
"""
    html = html.replace("__INI__", esc(str(VPX_SIMPLE_BALL_INI)))
    html = html.replace("__BALL_DIR__", esc(str(VPX_SIMPLE_BALL_IMAGE_DIR)))
    html = html.replace("__DECAL_DIR__", esc(str(VPX_SIMPLE_BALL_DECAL_DIR)))
    html = html.replace("__CHECKED__", checked)
    html = html.replace("__BALL_OPTIONS__", vpx_simple_ball_image_options(ball, VPX_SIMPLE_BALL_IMAGE_DIR))
    html = html.replace("__DECAL_OPTIONS__", vpx_simple_ball_image_options(decal, VPX_SIMPLE_BALL_DECAL_DIR))
    html = html.replace("__OVERWRITE__", esc(overwrite if overwrite else ""))
    html = html.replace("__BALL__", esc(ball if ball else ""))
    html = html.replace("__DECAL__", esc(decal if decal else ""))

    html = html.replace("__BALL_TRAIL_0__", "selected" if ball_trail == "0" else "")
    html = html.replace("__BALL_TRAIL_1__", "selected" if ball_trail == "1" else "")
    html = html.replace("__BALL_TRAIL_STRENGTH__", esc(ball_trail_strength if ball_trail_strength else ""))
    html = html.replace("__CABINET_AUTOFIT_MODE__", esc(cabinet_autofit_mode if cabinet_autofit_mode else ""))
    html = html.replace("__CABINET_AUTOFIT_POS__", esc(cabinet_autofit_pos if cabinet_autofit_pos else ""))
    html = html.replace("__BALL_ANTISTRETCH_0__", "selected" if ball_antistretch == "0" else "")
    html = html.replace("__BALL_ANTISTRETCH_1__", "selected" if ball_antistretch == "1" else "")

    html = html.replace("__BALL_TRAIL_VALUE__", esc(ball_trail if ball_trail else ""))
    html = html.replace("__BALL_TRAIL_STRENGTH_VALUE__", esc(ball_trail_strength if ball_trail_strength else ""))
    html = html.replace("__CABINET_AUTOFIT_MODE_VALUE__", esc(cabinet_autofit_mode if cabinet_autofit_mode else ""))
    html = html.replace("__CABINET_AUTOFIT_POS_VALUE__", esc(cabinet_autofit_pos if cabinet_autofit_pos else ""))
    html = html.replace("__BALL_ANTISTRETCH_VALUE__", esc(ball_antistretch if ball_antistretch else ""))

    return html


@app.route("/userdata/UserBalls/<kind>/<path:filename>")
def pincabos_userballs_static(kind, filename):
    from flask import send_from_directory, abort

    if kind not in ["balls", "decals"]:
        abort(404)

    if not filename or "/" in filename or "\\" in filename or ".." in filename:
        abort(404)

    base = VPX_SIMPLE_BALL_IMAGE_DIR if kind == "balls" else VPX_SIMPLE_BALL_DECAL_DIR
    f = base / filename

    if not f.exists() or not f.is_file():
        abort(404)

    return send_from_directory(str(base), filename)

@app.route("/tools/vpx-ball-simple/apply", methods=["POST"])
def tools_vpx_ball_simple_apply():
    from werkzeug.utils import secure_filename

    allowed = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
    VPX_SIMPLE_BALL_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    VPX_SIMPLE_BALL_DECAL_DIR.mkdir(parents=True, exist_ok=True)

    lines = vpx_simple_ball_read_lines()
    backup = vpx_simple_ball_backup()

    overwrite = "1" if request.form.get("overwrite_ball_image") == "1" else "0"

    ball_path = request.form.get("ball_existing", "").strip()
    decal_path = request.form.get("decal_existing", "").strip()

    def save_upload(field, folder):
        f = request.files.get(field)
        if not f or not f.filename:
            return ""
        name = secure_filename(f.filename)
        ext = Path(name).suffix.lower()
        if ext not in allowed:
            raise ValueError("Extension non supportée: " + ext)
        folder.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        final = folder / (Path(name).stem + "-" + stamp + ext)
        f.save(final)
        final.chmod(0o644)
        try:
            shutil.chown(final, user="pinball", group="pinball")
        except Exception:
            pass
        return str(final)

    try:
        uploaded_ball = save_upload("ball_upload", VPX_SIMPLE_BALL_IMAGE_DIR)
        uploaded_decal = save_upload("decal_upload", VPX_SIMPLE_BALL_DECAL_DIR)
    except Exception as e:
        return page("Outils", """
<div class="card">
  <h2>Erreur import image VPX Ball</h2>
  <p class="bad">__ERR__</p>
  <p><a class="button" href="/tools">Retour Outils</a></p>
</div>
""".replace("__ERR__", esc(str(e))))

    if uploaded_ball:
        ball_path = uploaded_ball
    if uploaded_decal:
        decal_path = uploaded_decal

    ball_trail = request.form.get("ball_trail", "").strip()
    ball_trail_strength = request.form.get("ball_trail_strength", "").strip()
    cabinet_autofit_mode = request.form.get("cabinet_autofit_mode", "").strip()
    cabinet_autofit_pos = request.form.get("cabinet_autofit_pos", "").strip()
    ball_antistretch = request.form.get("ball_antistretch", "").strip()

    lines = vpx_simple_ball_set(lines, "Player", "OverwriteBallImage", overwrite)

    if ball_path:
        lines = vpx_simple_ball_set(lines, "Player", "BallImage", ball_path)

    if decal_path:
        lines = vpx_simple_ball_set(lines, "Player", "DecalImage", decal_path)

    if ball_trail in ["0", "1"]:
        lines = vpx_simple_ball_set(lines, "Player", "BallTrail", ball_trail)

    if ball_trail_strength:
        lines = vpx_simple_ball_set(lines, "Player", "BallTrailStrength", ball_trail_strength)

    if cabinet_autofit_mode:
        lines = vpx_simple_ball_set(lines, "Player", "CabinetAutofitMode", cabinet_autofit_mode)

    if cabinet_autofit_pos:
        lines = vpx_simple_ball_set(lines, "Player", "CabinetAutofitPos", cabinet_autofit_pos)

    if ball_antistretch in ["0", "1"]:
        lines = vpx_simple_ball_set(lines, "Player", "BallAntiStretch", ball_antistretch)

    lines = vpx_simple_ball_set(lines, "PinCabOs.BallCabinet", "managed_by", "PinCabOS VPX Ball Image")
    lines = vpx_simple_ball_set(lines, "PinCabOs.BallCabinet", "ball_dir", str(VPX_SIMPLE_BALL_IMAGE_DIR))
    lines = vpx_simple_ball_set(lines, "PinCabOs.BallCabinet", "decal_dir", str(VPX_SIMPLE_BALL_DECAL_DIR))
    lines = vpx_simple_ball_set(lines, "PinCabOs.BallCabinet", "updated_at", datetime.now().isoformat(timespec="seconds"))

    vpx_simple_ball_write_lines(lines)

    backup_txt = str(backup) if backup else "Aucun backup, fichier créé."

    body = """
<div class="card">
  <h2>VPX Ball / Cabinet appliqué</h2>
  <p class="ok">Les valeurs ont été écrites dans <code>[Player]</code>.</p>

  <table>
    <tr><td>INI</td><td><code>__INI__</code></td></tr>
    <tr><td>Backup</td><td><code>__BACKUP__</code></td></tr>
    <tr><td>OverwriteBallImage</td><td><code>__OVERWRITE__</code></td></tr>
    <tr><td>BallImage</td><td><code>__BALL__</code></td></tr>
    <tr><td>DecalImage</td><td><code>__DECAL__</code></td></tr>
    <tr><td>BallTrail</td><td><code>__BALL_TRAIL_RESULT__</code></td></tr>
    <tr><td>BallTrailStrength</td><td><code>__BALL_TRAIL_STRENGTH_RESULT__</code></td></tr>
    <tr><td>CabinetAutofitMode</td><td><code>__CABINET_AUTOFIT_MODE_RESULT__</code></td></tr>
    <tr><td>CabinetAutofitPos</td><td><code>__CABINET_AUTOFIT_POS_RESULT__</code></td></tr>
    <tr><td>BallAntiStretch</td><td><code>__BALL_ANTISTRETCH_RESULT__</code></td></tr>
  </table>

  <p>
    <a class="button" href="/tools">Retour Outils</a>
  </p>
</div>
"""
    body = body.replace("__INI__", esc(str(VPX_SIMPLE_BALL_INI)))
    body = body.replace("__BACKUP__", esc(backup_txt))
    body = body.replace("__OVERWRITE__", esc(overwrite))
    body = body.replace("__BALL__", esc(ball_path))
    body = body.replace("__DECAL__", esc(decal_path))
    body = body.replace("__BALL_TRAIL_RESULT__", esc(ball_trail))
    body = body.replace("__BALL_TRAIL_STRENGTH_RESULT__", esc(ball_trail_strength))
    body = body.replace("__CABINET_AUTOFIT_MODE_RESULT__", esc(cabinet_autofit_mode))
    body = body.replace("__CABINET_AUTOFIT_POS_RESULT__", esc(cabinet_autofit_pos))
    body = body.replace("__BALL_ANTISTRETCH_RESULT__", esc(ball_antistretch))

    return page("Outils", body)
# === PINCABOS SIMPLE VPX BALL CARD END ===


@app.route("/tools")
def tools_page():
    tables = []
    try:
        tables = pincabos_list_installed_tables_for_export()
    except Exception:
        tables = []

    table_options = ""
    if tables:
        for t in tables:
            folder = esc(t.get("folder", ""))
            # Export: afficher le nom réel du répertoire
            label = folder
            table_options += f'<option value="{folder}">{label}</option>\n'
    else:
        table_options = '<option value="">Aucune table installée détectée</option>'

    body = f"""
<div class="card">
  <h2>Outils PinCabOs</h2>

  <p>
    Centre d’outils pour importer, exporter, gérer et préparer les tables VPX utilisées par VPinFE.
  </p>

  <div style="display:flex; flex-wrap:wrap; gap:12px; margin-top:18px;">
    <a class="button" href="/tools/commander">Ouvrir PinCab Explorer</a>
    <a class="button" href="/console">Ouvrir PinCab Console</a>
    <a class="button" href="/tools/external-disks">Gestion disques externes</a>
    </div>

  <p class="warn" style="margin-top:16px;">
    PinCab Explorer s’ouvre dans une page séparée. Il servira de gestionnaire de fichiers PinCabOs,
    avec navigation dans les tables, ROMs, AltSound, AltColor, PupVideos, UltraDMD, exports, imports,
    /home/pinball et  lorsque celui-ci sera monté.
  </p>
</div>

<div class="card" style="margin-top:20px;">
  <h2>Importer une table complète</h2>

  <p>
    Sélectionne un package <code>.PinCabOs</code> ou un lot de fichiers de table.
    Si un package <code>.PinCabOs</code> est fourni, PinCabOs détecte automatiquement
    le manifest et restaure la table directement, sans passer par l’association VPSdb.
  </p>

  <div class="card" style="background:rgba(95,42,145,0.18); border-color:rgba(95,42,145,0.45); margin:12px 0;">
    <h3>Package PinCabOs</h3>

    <p>
      Un fichier <code>.PinCabOs</code> est une archive complète créée par PinCabOs.
      Elle contient le dossier complet de la table, son <code>pincabos-export-manifest.json</code>,
      les médias, la musique, les ROMs locales, PupVideos, UltraDMD/FlexDMD, AltSound,
      scripts et sous-dossiers exactement comme ils étaient au moment de l’export.
    </p>

    <p>
      Lors de l’import, PinCabOs copie le dossier de table tel quel dans
      <code>/opt/pincabos/vpinball/Tables</code>. La structure n’est pas reclassée
      et aucun chemin legacy global n’est utilisé.
    </p>
  </div>

  <div class="card" style="background:rgba(255,122,0,0.08); border-color:rgba(255,122,0,0.35); margin:12px 0;">
    <h3>Import standard</h3>

    <p>
      Pour importer une nouvelle table à partir de fichiers séparés, fournis au minimum
      une table <code>.vpx</code> ou une archive <code>.zip</code>, <code>.rar</code>
      ou <code>.7z</code> contenant la table.
    </p>

    <p>
      Tu peux ajouter dans le même lot le DirectB2S, les médias, la musique, la ROM,
      les fichiers PinMAME, PupVideos, UltraDMD/FlexDMD, AltSound, scripts et fichiers
      de support. PinCabOs installe le tout dans le dossier portable de la table.
    </p>
  </div>

  <p class="warn">
    Formats supportés :
    <code>.PinCabOs, .zip, .rar, .7z, .vpx, .directb2s, .pov, .ini, .vbs, .scv, .pac, .pal, .vni, .crz, .serum</code>
  </p>

  <form id="tableAnalyzeForm" action="/tools/import-table/analyze" method="post" enctype="multipart/form-data" onsubmit="document.getElementById('analyzeButtonSpinner').style.display='inline-block'; document.getElementById('analyzeSpinner').style.display='block';">
    <label>Fichier(s) de la table ou package .PinCabOs</label><br>
    <input type="file" name="packages" multiple style="width:90%; padding:8px; margin:8px 0;"><br>

    <button class="button" type="submit">Analyser / importer</button>
    <span id="analyzeButtonSpinner" style="display:none; margin-left:10px; vertical-align:middle;"><svg width="20" height="20" viewBox="0 0 50 50" style="vertical-align:middle;"><circle cx="25" cy="25" r="20" fill="none" stroke="rgba(255,255,255,0.25)" stroke-width="6"></circle><path d="M25 5 A20 20 0 0 1 45 25" fill="none" stroke="#ff7a00" stroke-width="6" stroke-linecap="round"><animateTransform attributeName="transform" type="rotate" from="0 25 25" to="360 25 25" dur="0.75s" repeatCount="indefinite"/></path></svg></span>

    <div id="analyzeSpinner" class="card" style="display:none; margin-top:14px;">
      <h3>Traitement en cours...</h3>
      <p>PinCabOs analyse le lot ou restaure directement le package .PinCabOs si un manifest est détecté.</p>
    </div>
  </form>
</div>

<div class="card" style="margin-top:20px;">
  <h2>Exporter / partager une table installée</h2>

  <p>
    Choisis une table déjà installée. PinCabOs va créer un package <code>.PinCabOs</code>
    en compressant le dossier complet de la table sélectionnée, sans filtre et sans option.
  </p>

  <p>
    Le package peut être téléchargé, copié sur une autre machine PinCabOs, puis réimporté
    tel quel. Le manifest est inclus automatiquement et la structure des sous-dossiers
    est conservée intacte.
  </p>

  <form action="/tools/export-table" method="post" onsubmit="document.getElementById('exportButtonSpinner').style.display='inline-block'; document.getElementById('exportSpinner').style.display='block';">
    <label>Table à exporter</label><br>
    <select name="table_folder" style="width:95%; padding:8px; margin:8px 0;">
      {table_options}
    </select><br>

    <label style="display:block; margin:10px 0 14px 0;">
      <input type="checkbox" name="delete_after_export" value="1">
      Supprimer la table locale après export réussi
    </label>

    <button class="button" type="submit">Créer le package .PinCabOs</button>
    <span id="exportButtonSpinner" style="display:none; margin-left:10px; vertical-align:middle;"><svg width="20" height="20" viewBox="0 0 50 50" style="vertical-align:middle;"><circle cx="25" cy="25" r="20" fill="none" stroke="rgba(255,255,255,0.25)" stroke-width="6"></circle><path d="M25 5 A20 20 0 0 1 45 25" fill="none" stroke="#ff7a00" stroke-width="6" stroke-linecap="round"><animateTransform attributeName="transform" type="rotate" from="0 25 25" to="360 25 25" dur="0.75s" repeatCount="indefinite"/></path></svg></span>

    <div id="exportSpinner" class="card" style="display:none; margin-top:14px;">
      <h3>Export en cours...</h3>
      <p>PinCabOs compresse le dossier complet de la table et prépare le package .PinCabOs.</p>
    </div>
  </form>
</div>


{vpx_simple_ball_card()}

"""
    return page("Outils", body)


def pincabos_try_manifest_import_from_saved_batch(batch_dir):
    """
    Import direct d'un package PinCabOs depuis /tools/import-table/analyze.

    Règle:
    - si le batch contient un .PinCabOs/.pincabos/.zip/.7z/.rar avec pincabos-export-manifest.json,
      on bypass complètement VPSdb/analyse;
    - on restaure selon le manifest;
    - si aucun manifest n'est trouvé, on retourne None et l'analyse normale continue.
    """
    batch_dir = Path(batch_dir)

    archive_exts = {".pincabos", ".zip", ".7z", ".rar"}

    archives = []
    try:
        for p in sorted(batch_dir.rglob("*")):
            if p.is_file() and p.suffix.lower() in archive_exts:
                archives.append(p)
    except Exception:
        archives = []

    for archive_path in archives:
        try:
            with tempfile.TemporaryDirectory(prefix="pincabos-json-found-") as td:
                extract_dir = Path(td) / "extract"
                extract_dir.mkdir(parents=True, exist_ok=True)

                r7 = subprocess.run(
                    ["7z", "x", "-y", f"-o{str(extract_dir)}", str(archive_path)],
                    capture_output=True,
                    text=True,
                    timeout=1800,
                    check=False,
                )

                if r7.returncode != 0:
                    continue

                has_manifest = any(
                    n.name == "pincabos-export-manifest.json"
                    for n in extract_dir.rglob("*")
                    if n.is_file()
                )

                if not has_manifest:
                    continue

                table_folder, _manifest_preview = pincabos_manifest_table_folder_from_archive(archive_path)
                if table_folder:
                    table_root = Path("/opt/pincabos/vpinball/Tables") / table_folder
                    if table_root.exists():
                        return pincabos_manifest_import_conflict_page(batch_dir, archive_path, table_folder)

                result = pincabos_import_from_manifest_dir(extract_dir, overwrite_existing=False)
                if result:
                    if result.get("skipped") and "CONFLICT_TABLE_EXISTS" in result.get("skipped", []):
                        return pincabos_manifest_import_conflict_page(batch_dir, archive_path, result.get("table_folder", table_folder or "Imported Table"))

                    result["message"] = "Package PinCabOs détecté — import direct par manifest, analyse VPSdb ignorée."

                    # Nettoyage du batch upload après import manifest.
                    try:
                        uploads_root = Path("/opt/pincabos/imports/uploads").resolve()
                        batch_real = Path(batch_dir).resolve()
                        if batch_real.exists() and uploads_root in batch_real.parents:
                            shutil.rmtree(batch_real)
                    except Exception as e:
                        result.setdefault("skipped", [])
                        result["skipped"].append(f"WARNING cleanup upload batch: {e}")

                    return pincabos_manifest_import_result_page(result)

        except Exception as e:
            return page("Import PinCabOs", f"""
<div class="card">
  <h2>Import PinCabOs impossible</h2>
  <p class="bad">Package PinCabOs détecté, mais erreur pendant l’import manifest.</p>
  <pre>{esc(str(e))}</pre>
  <p><a class="button" href="/tools">Retour aux outils</a></p>
</div>
""")

    return None


@app.route("/tools/import-table/manifest-conflict", methods=["POST"])
def tools_import_table_manifest_conflict():
    batch_dir = Path(request.form.get("batch_dir", "")).resolve()
    archive_path = Path(request.form.get("archive_path", "")).resolve()
    action = request.form.get("conflict_action", "").strip().lower()
    new_table_name = request.form.get("new_table_name", "").strip()

    uploads_root = Path("/opt/pincabos/imports/uploads").resolve()

    if not batch_dir.exists() or uploads_root not in batch_dir.parents:
        return page("Import PinCabOs", """
<div class="card">
  <h2>Import impossible</h2>
  <p class="bad">Batch d’import invalide ou expiré.</p>
  <p><a class="button" href="/tools">Retour aux outils</a></p>
</div>
""")

    if not archive_path.exists() or batch_dir not in archive_path.parents:
        return page("Import PinCabOs", """
<div class="card">
  <h2>Import impossible</h2>
  <p class="bad">Package d’import invalide.</p>
  <p><a class="button" href="/tools">Retour aux outils</a></p>
</div>
""")

    if action not in ["replace", "rename"]:
        return page("Import PinCabOs", """
<div class="card">
  <h2>Import impossible</h2>
  <p class="bad">Action de conflit invalide.</p>
  <p><a class="button" href="/tools">Retour aux outils</a></p>
</div>
""")

    table_folder, _manifest_preview = pincabos_manifest_table_folder_from_archive(archive_path)
    if not table_folder:
        table_folder = "Imported Table"

    if action == "rename":
        if not new_table_name:
            return pincabos_manifest_import_conflict_page(batch_dir, archive_path, table_folder)
        final_table_name = pincabos_standard_table_folder_name(new_table_name) or table_folder
    else:
        final_table_name = table_folder

    try:
        with tempfile.TemporaryDirectory(prefix="pincabos-conflict-import-") as td:
            extract_dir = Path(td) / "extract"
            extract_dir.mkdir(parents=True, exist_ok=True)

            r7 = subprocess.run(
                ["7z", "x", "-y", f"-o{str(extract_dir)}", str(archive_path)],
                capture_output=True,
                text=True,
                timeout=1800,
                check=False,
            )

            if r7.returncode != 0:
                raise RuntimeError((r7.stdout + "\\n" + r7.stderr).strip())

            result = pincabos_import_from_manifest_dir(
                extract_dir,
                table_folder_override=final_table_name,
                overwrite_existing=True,
            )

        if result:
            if action == "replace":
                result["message"] = "Package PinCabOs importé en remplaçant la table existante."
            else:
                result["message"] = f"Package PinCabOs importé sous le nouveau nom: {final_table_name}"

            try:
                if batch_dir.exists() and uploads_root in batch_dir.parents:
                    shutil.rmtree(batch_dir)
            except Exception as e:
                result.setdefault("skipped", [])
                result["skipped"].append(f"WARNING cleanup upload batch: {e}")

            return pincabos_manifest_import_result_page(result)

    except Exception as e:
        return page("Import PinCabOs", f"""
<div class="card">
  <h2>Import impossible</h2>
  <p class="bad">Erreur pendant le traitement du conflit.</p>
  <pre>{esc(str(e))}</pre>
  <p><a class="button" href="/tools">Retour aux outils</a></p>
</div>
""")

    return page("Import PinCabOs", """
<div class="card">
  <h2>Import impossible</h2>
  <p class="bad">Aucun résultat d’import.</p>
  <p><a class="button" href="/tools">Retour aux outils</a></p>
</div>
""")


def pincabos_match_rom_value(m, detected=None):
    """
    Retourne la ROM depuis un match VPSdb/VPinFE si disponible.
    Fallback sur detected["rom"].
    """
    detected = detected or {}

    keys = [
        "rom", "Rom", "ROM",
        "romName", "RomName", "rom_name",
        "romFile", "RomFile", "rom_file",
        "bios", "Bios", "BIOS",
        "pinmame", "PinMAME",
    ]

    for k in keys:
        val = ""
        try:
            val = m.get(k, "")
        except Exception:
            val = ""
        val = str(val or "").strip()
        if val:
            val = Path(val).name
            if val.lower().endswith(".zip"):
                val = val[:-4]
            return val

    val = str(detected.get("rom", "") or "").strip()
    if val.lower().endswith(".zip"):
        val = val[:-4]
    return val


@app.route("/api/import/vpsdb-search")
def api_import_vpsdb_search():
    q = request.args.get("q", "").strip()
    rom = request.args.get("rom", "").strip()
    wanted_vpsid = request.args.get("vpsid", "").strip()

    if not q and not rom and not wanted_vpsid:
        return jsonify({"ok": False, "matches": [], "error": "Recherche vide"})

    # Si un VPSId est fourni, on l'ajoute comme recherche forte.
    search_q = wanted_vpsid if wanted_vpsid else q

    matches = pincabos_vpsdb_matches(search_q, rom)

    # Si recherche par VPSId ne retourne rien, fallback sur le nom.
    if wanted_vpsid and q:
        by_name = pincabos_vpsdb_matches(q, rom)
        seen = set()
        merged = []
        for m in matches + by_name:
            mid = str(m.get("id", "") or "")
            key = mid or str(m)
            if key in seen:
                continue
            seen.add(key)
            merged.append(m)
        matches = merged

    out = []
    for m in matches[:30]:
        title = str(m.get("title", "") or "")
        manufacturer = str(m.get("manufacturer", "") or "")
        year = str(m.get("year", "") or "")
        vpsid = str(m.get("id", "") or "")
        score = str(m.get("score", "") or "")
        assoc_rom = pincabos_match_rom_value(m, {"rom": rom})

        # Si VPSId demandé, boost visuel exact.
        if wanted_vpsid and vpsid.lower() == wanted_vpsid.lower():
            score = "1.0000"

        final_table_name = title
        if manufacturer and year:
            final_table_name = f"{title} ({manufacturer} {year})"

        out.append({
            "title": title,
            "manufacturer": manufacturer,
            "year": year,
            "id": vpsid,
            "score": score,
            "rom": assoc_rom,
            "final_table_name": final_table_name,
        })

    return jsonify({"ok": True, "matches": out})


@app.route("/tools/import-table/analyze", methods=["POST"])
def tools_import_table_analyze():
    uploads = request.files.getlist("packages")
    uploads = [u for u in uploads if u and u.filename]

    if not uploads:
        return page("Outils", """
<div class="card">
  <h2>Analyse impossible</h2>
  <p class="bad">Aucun fichier reçu.</p>
  <p><a class="button" href="/tools">Retour Outils</a></p>
</div>
""")

    job_id = pincabos_import_safe_job_id()
    batch_dir = Path("/opt/pincabos/imports/uploads") / f"batch-{job_id}"
    batch_dir.mkdir(parents=True, exist_ok=True)

    saved = []
    for upload in uploads:
        filename = secure_filename(upload.filename)
        if not filename:
            continue
        dest = batch_dir / filename
        upload.save(dest)
        saved.append(str(dest))

    manifest_response = pincabos_try_manifest_import_from_saved_batch(batch_dir)
    if manifest_response is not None:
        return manifest_response

    detected = pincabos_detect_batch(batch_dir)
    matches = pincabos_vpsdb_matches(detected.get("table_name", ""), detected.get("rom", ""))

    options = ""
    for m in matches[:10]:
        title = str(m.get("title", ""))
        manufacturer = str(m.get("manufacturer", ""))
        year = str(m.get("year", ""))
        vpsid = str(m.get("id", ""))
        score = str(m.get("score", ""))

        final_table_name = title
        if manufacturer and year:
            final_table_name = f"{title} ({manufacturer} {year})"

        assoc_rom = pincabos_match_rom_value(m, detected)

        value = html.escape(json.dumps({
            "mode": "vpsdb",
            "title": title,
            "manufacturer": manufacturer,
            "year": year,
            "vpsid": vpsid,
            "rom": assoc_rom,
            "final_table_name": final_table_name,
        }, ensure_ascii=False))

        label = html.escape(f"{title} — {manufacturer} — {year} — VPSId {vpsid} — score {score}")
        options += f'<option value="{value}">{label}</option>\\n'

    if not options.strip():
        options = '<option value="">Aucune association auto-détectée VPSdb</option>'

    detected_html = html.escape(json.dumps(detected, indent=2, ensure_ascii=False))
    files_html = html.escape("\\n".join(saved))

    default_title = html.escape(detected.get("table_name", ""))
    default_rom = html.escape(detected.get("rom", ""))

    body = f"""
<div class="card">
  <h2>Analyse du lot terminée</h2>

  <h3>Table détectée</h3>
  <p><strong>{html.escape(detected.get("table_name", ""))}</strong></p>

  <h3>ROM détectée</h3>
  <p><strong>{html.escape(detected.get("rom", "")) or "Aucune ROM détectée"}</strong></p>

  <h3>Fichiers détectés</h3>
  <pre>{files_html}</pre>

  <h3>Détails techniques</h3>
  <pre>{detected_html}</pre>
</div>

<div class="card" style="margin-top:20px;">
  <h2>Association VPinFE / VPSdb</h2>

  <form action="/tools/import-table/install" method="post" onsubmit="document.getElementById('installSpinner').style.display='block';">
    <input type="hidden" name="batch_dir" value="{html.escape(str(batch_dir))}">
    <input type="hidden" name="import_mode" id="importMode" value="auto">

    <div class="card" style="margin-top:12px; border-color:rgba(255,122,0,.45);">
      <h3>1. Détection automatique VPSdb</h3>
      <p>PinCabOs propose ici les résultats VPSdb trouvés automatiquement.</p>

      <label>Choix auto-détecté VPSdb</label><br>
      <select name="association" id="autoAssociationSelect" style="width:95%; padding:8px; margin:8px 0;">
        {options}
      </select><br>

      <button class="button" type="submit" onclick="document.getElementById('importMode').value='auto';">
        Importer ce choix auto-détecté
      </button>
    </div>

    <div class="card" style="margin-top:20px; border-color:rgba(95,42,145,.55);">
      <h3>2. Recherche manuelle dans VPSdb</h3>
      <p>Recherche par nom ou par VPSId. Ensuite sélectionne le bon résultat et importe-le.</p>

      <label>Nom recherché</label><br>
      <input id="vpsdbSearchQuery" value="{default_title}" placeholder="Exemple : The Leprechaun King" style="width:90%; padding:8px;"><br><br>

      <label>VPSId optionnel</label><br>
      <input id="vpsdbSearchId" value="" placeholder="Exemple : VAx9weFV" style="width:90%; padding:8px;"><br><br>

      <button class="button secondary" type="button" id="vpsdbSearchButton" onclick="window.pincabosVpsdbSearch && window.pincabosVpsdbSearch();">
        Rechercher VPSdb
      </button>
      <span id="vpsdbSearchSpinner" style="display:none; margin-left:10px;">🔄</span>
      <span id="vpsdbSearchStatus" style="margin-left:10px; opacity:.85;"></span>

      <br><br>
      <label>Résultat de recherche VPSdb</label><br>
      <select name="search_association" id="searchAssociationSelect" style="width:95%; padding:8px; margin:8px 0;">
        <option value="">Aucun résultat de recherche sélectionné</option>
      </select><br>

      <button class="button" type="submit" onclick="document.getElementById('importMode').value='search';">
        Importer le résultat recherché
      </button>
    </div>

    <div class="card" style="margin-top:20px; border-color:rgba(255,122,0,.55); background:rgba(255,122,0,.06);">
      <h3>3. Import manuel complet</h3>
      <p>
        Si rien ne correspond dans VPSdb, remplis ces champs et importe la table avec tes informations.
        Exemple : <code>Demo Table (PinCabOs 2026)</code>.
      </p>

      <label>Nom de table VPinFE</label><br>
      <input name="manual_title" id="manualTitleInput" value="{default_title}" style="width:90%; padding:8px;" placeholder="Exemple : Demo Table (PinCabOs 2026)"><br><br>

      <label>Manufacturier</label><br>
      <input name="manual_manufacturer" id="manualManufacturerInput" value="" placeholder="Exemple : PinCabOs, Williams, Original, Stern" style="width:90%; padding:8px;"><br><br>

      <label>Année</label><br>
      <input name="manual_year" id="manualYearInput" value="" placeholder="Exemple : 2026" style="width:90%; padding:8px;"><br><br>

      <label>ROM</label><br>
      <input name="manual_rom" id="manualRomInput" value="{default_rom}" placeholder="Exemple : hurr_l2 ou laisser vide si aucune ROM" style="width:90%; padding:8px;"><br><br>

      <button class="button" type="submit" onclick="document.getElementById('importMode').value='manual';">
        Importer manuellement
      </button>
    </div>

    <script>
      (function() {{
        window.pincabosVpsdbSearch = async function() {{
          const searchQ = document.getElementById("vpsdbSearchQuery");
          const searchId = document.getElementById("vpsdbSearchId");
          const searchStatus = document.getElementById("vpsdbSearchStatus");
          const spinner = document.getElementById("vpsdbSearchSpinner");
          const searchSelect = document.getElementById("searchAssociationSelect");

          if (!searchSelect) {{
            alert("Erreur: champ résultat VPSdb introuvable.");
            return;
          }}

          const q = encodeURIComponent(searchQ ? searchQ.value.trim() : "");
          const vpsid = encodeURIComponent(searchId ? searchId.value.trim() : "");

          if (!q && !vpsid) {{
            searchSelect.innerHTML = '<option value="">Entre un nom ou un VPSId</option>';
            if (searchStatus) searchStatus.textContent = "Recherche vide";
            return;
          }}

          if (spinner) spinner.style.display = "inline-block";
          if (searchStatus) searchStatus.textContent = "Recherche en cours...";
          searchSelect.innerHTML = '<option value="">Recherche en cours...</option>';

          try {{
            const url = "/api/import/vpsdb-search?q=" + q + "&vpsid=" + vpsid + "&_=" + Date.now();
            const resp = await fetch(url, {{
              method: "GET",
              cache: "no-store",
              headers: {{ "Accept": "application/json" }}
            }});

            const raw = await resp.text();
            const data = JSON.parse(raw);

            searchSelect.innerHTML = "";

            if (!data.ok || !data.matches || data.matches.length === 0) {{
              searchSelect.innerHTML = '<option value="">Aucun résultat VPSdb trouvé</option>';
              if (searchStatus) searchStatus.textContent = "Aucun résultat";
              return;
            }}

            const empty = document.createElement("option");
            empty.value = "";
            empty.textContent = "Choisir un résultat de recherche VPSdb";
            searchSelect.appendChild(empty);

            data.matches.forEach(function(m) {{
              const opt = document.createElement("option");
              opt.value = JSON.stringify({{
                mode: "vpsdb",
                title: m.title || "",
                manufacturer: m.manufacturer || "",
                year: m.year || "",
                vpsid: m.id || "",
                rom: m.rom || "",
                final_table_name: m.final_table_name || ""
              }});

              opt.textContent =
                (m.title || "") + " — " +
                (m.manufacturer || "") + " — " +
                (m.year || "") + " — VPSId " +
                (m.id || "") + " — score " +
                (m.score || "");

              searchSelect.appendChild(opt);
            }});

            if (searchStatus) searchStatus.textContent = data.matches.length + " résultat(s)";
          }} catch(e) {{
            searchSelect.innerHTML = '<option value="">Erreur recherche VPSdb</option>';
            if (searchStatus) searchStatus.textContent = "Erreur recherche";
            console.log("Erreur recherche VPSdb:", e);
          }} finally {{
            if (spinner) spinner.style.display = "none";
          }}
        }};
      }})();
    </script>

    <div id="installSpinner" class="card" style="display:none; margin-top:14px;">
      <h3>Installation en cours...</h3>
      <p>PinCabOs installe les fichiers, crée le .info compatible VPinFE et nettoie les temporaires.</p>
    </div>
  </form>

  <p style="margin-top:14px;"><a class="button secondary" href="/tools">Annuler</a></p>
</div>
"""
    return page("Outils", body)


def pincabos_safe_manifest_relpath(rel):
    rel = str(rel or "").replace("\\", "/").strip()
    if not rel:
        return None
    if rel.startswith("/") or rel.startswith("../") or "/../" in rel or rel == "..":
        return None
    return rel


def pincabos_manifest_dest_path(rel):
    """
    Destination import manifest PinCabOs v2:
    tout reste dans /opt/pincabos/tables/<table>/...
    Cette fonction garde un fallback pour les vieux manifests, mais évite
    les dossiers legacy globaux.
    """
    rel = pincabos_safe_manifest_relpath(rel)
    if not rel:
        return None

    parts = Path(rel).parts
    if not parts:
        return None

    # Manifest v2 exporte directement:
    # table/, media/, music/, roms/, pupvideos/, ...
    standard_dirs = {
        "table", "media", "music", "roms", "pupvideos", "altcolor",
        "altsound", "dmd", "b2s", "scripts", "config", "docs", "extras"
    }

    # La vraie table est déterminée dans pincabos_import_from_manifest_dir()
    # via PINCABOS_MANIFEST_IMPORT_TABLE_DIR.
    table_root = globals().get("PINCABOS_MANIFEST_IMPORT_TABLE_DIR", None)
    if table_root:
        table_root = Path(table_root)

        if parts[0] in standard_dirs:
            return table_root / rel

        # Vieux manifest avec Tables/<table>/...
        if len(parts) >= 3 and parts[0].lower() == "tables":
            return table_root / Path(*parts[2:])

        # Vieux manifest avec PupVideos/xxx, PinMAME/roms/xxx, etc.
        low0 = parts[0].lower()
        if low0 in ["pupvideos"]:
            return table_root / "pupvideos" / Path(*parts[1:])
        if low0 in ["ultradmd", "flexdmd"]:
            return table_root / "dmd" / Path(*parts[1:])
        if low0 == "pinmame" and len(parts) >= 2:
            low1 = parts[1].lower()
            if low1 == "roms":
                return table_root / "roms" / Path(*parts[2:])
            if low1 == "altcolor":
                return table_root / "altcolor" / Path(*parts[2:])
            if low1 == "altsound":
                return table_root / "altsound" / Path(*parts[2:])

        return table_root / "extras" / rel

    # Fallback ultra safe.
    return Path("/opt/pincabos/imported") / rel


def pincabos_find_manifest_root(extract_dir):
    extract_dir = Path(extract_dir)

    direct = extract_dir / "pincabos-export-manifest.json"
    if direct.exists():
        return extract_dir, direct

    matches = list(extract_dir.rglob("pincabos-export-manifest.json"))
    if not matches:
        return None, None

    manifest = matches[0]
    return manifest.parent, manifest


def pincabos_manifest_table_folder_from_archive(archive_path):
    """
    Lit le manifest d'un .PinCabOs/.zip/.7z/.rar et retourne le nom de table demandé.
    Retourne ("", "") si aucun manifest valide n'est trouvé.
    """
    archive_path = Path(archive_path)

    with tempfile.TemporaryDirectory(prefix="pincabos-manifest-preview-") as td:
        extract_dir = Path(td) / "extract"
        extract_dir.mkdir(parents=True, exist_ok=True)

        r7 = subprocess.run(
            ["7z", "x", "-y", f"-o{str(extract_dir)}", str(archive_path)],
            capture_output=True,
            text=True,
            timeout=1800,
            check=False,
        )

        if r7.returncode != 0:
            return "", ""

        root, manifest_path = pincabos_find_manifest_root(extract_dir)
        if not manifest_path:
            return "", ""

        try:
            manifest = json.loads(manifest_path.read_text(errors="replace"))
        except Exception:
            return "", str(manifest_path)

        if manifest.get("format") != "PinCabOs table export":
            return "", str(manifest_path)

        table_folder = str(manifest.get("table_folder") or "").strip()
        if not table_folder:
            table_folder = Path(root).name or "Imported Table"

        table_folder = pincabos_standard_table_folder_name(table_folder)
        return table_folder, str(manifest_path)


def pincabos_manifest_import_conflict_page(batch_dir, archive_path, table_folder):
    table_root = Path("/opt/pincabos/vpinball/Tables") / table_folder

    suggested = table_folder
    i = 2
    while (Path("/opt/pincabos/vpinball/Tables") / suggested).exists():
        suggested = f"{table_folder} ({i})"
        i += 1

    return page("Import PinCabOs", f"""
<div class="card">
  <h2>Table déjà présente</h2>
  <p class="warn">
    Le package <code>.PinCabOs</code> contient la table
    <strong>{esc(table_folder)}</strong>, mais ce dossier existe déjà.
  </p>

  <p><strong>Dossier existant :</strong> <code>{esc(str(table_root))}</code></p>

  <div class="card" style="margin-top:14px; border-color:rgba(255,122,0,.45);">
    <h3>Remplacer la table existante</h3>
    <p>Cette option supprime l’ancien dossier de table, puis restaure le package .PinCabOs.</p>

    <form action="/tools/import-table/manifest-conflict" method="post" onsubmit="document.getElementById('replaceSpinner').style.display='inline-block';">
      <input type="hidden" name="batch_dir" value="{esc(str(batch_dir))}">
      <input type="hidden" name="archive_path" value="{esc(str(archive_path))}">
      <input type="hidden" name="conflict_action" value="replace">
      <button class="button" type="submit">Remplacer la table existante</button>
      <span id="replaceSpinner" style="display:none; margin-left:10px; vertical-align:middle;"><svg width="20" height="20" viewBox="0 0 50 50" style="vertical-align:middle;"><circle cx="25" cy="25" r="20" fill="none" stroke="rgba(255,255,255,0.25)" stroke-width="6"></circle><path d="M25 5 A20 20 0 0 1 45 25" fill="none" stroke="#ff7a00" stroke-width="6" stroke-linecap="round"><animateTransform attributeName="transform" type="rotate" from="0 25 25" to="360 25 25" dur="0.75s" repeatCount="indefinite"/></path></svg></span>
    </form>
  </div>

  <div class="card" style="margin-top:14px; border-color:rgba(95,42,145,.55);">
    <h3>Installer sous un nouveau nom</h3>
    <p>Cette option garde la table existante et installe le package dans un nouveau dossier.</p>

    <form action="/tools/import-table/manifest-conflict" method="post" onsubmit="document.getElementById('renameSpinner').style.display='inline-block';">
      <input type="hidden" name="batch_dir" value="{esc(str(batch_dir))}">
      <input type="hidden" name="archive_path" value="{esc(str(archive_path))}">
      <input type="hidden" name="conflict_action" value="rename">

      <label>Nouveau nom de dossier</label><br>
      <input name="new_table_name" value="{esc(suggested)}" style="width:90%; padding:8px; margin:8px 0;"><br>

      <button class="button" type="submit">Installer avec ce nouveau nom</button>
      <span id="renameSpinner" style="display:none; margin-left:10px; vertical-align:middle;"><svg width="20" height="20" viewBox="0 0 50 50" style="vertical-align:middle;"><circle cx="25" cy="25" r="20" fill="none" stroke="rgba(255,255,255,0.25)" stroke-width="6"></circle><path d="M25 5 A20 20 0 0 1 45 25" fill="none" stroke="#ff7a00" stroke-width="6" stroke-linecap="round"><animateTransform attributeName="transform" type="rotate" from="0 25 25" to="360 25 25" dur="0.75s" repeatCount="indefinite"/></path></svg></span>
    </form>
  </div>

  <p style="margin-top:14px;">
    <a class="button secondary" href="/tools">Annuler</a>
  </p>
</div>
""")


def pincabos_standard_table_folder_name(name):
    return pincabos_force_standard_table_name(name)


def pincabos_update_imported_table_metadata(table_root, table_folder):
    """
    Après import:
    - renomme le .info principal pour suivre le nom du dossier;
    - met à jour pincabos-export-manifest.json;
    - met à jour pincabos-table-manifest.json;
    - garde les autres fichiers intacts.
    """
    table_root = Path(table_root)
    table_folder = pincabos_standard_table_folder_name(table_folder)

    wanted_info = table_root / f"{table_folder}.info"

    try:
        info_files = sorted(table_root.glob("*.info"))
        if info_files:
            # Si le bon .info n'existe pas, renommer le premier .info trouvé.
            if not wanted_info.exists():
                info_files[0].rename(wanted_info)

            # Mettre à jour le Title si c'est du JSON.
            try:
                data = json.loads(wanted_info.read_text(errors="replace"))
                if isinstance(data, dict):
                    if isinstance(data.get("Info"), dict):
                        data["Info"]["Title"] = table_folder
                    elif "title" in data:
                        data["title"] = table_folder
                    wanted_info.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            except Exception:
                pass
    except Exception:
        pass

    for mf_name in ["pincabos-export-manifest.json", "pincabos-table-manifest.json"]:
        mf = table_root / mf_name
        if not mf.exists():
            continue

        try:
            data = json.loads(mf.read_text(errors="replace"))
            if isinstance(data, dict):
                data["table_folder"] = table_folder
                data["table_dir"] = str(table_root)
                data["table_root"] = str(table_root)
                if "title" in data:
                    data["title"] = table_folder
                if "table_name" in data:
                    data["table_name"] = table_folder
                mf.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass


def pincabos_import_from_manifest_dir(extract_dir, table_folder_override=None, overwrite_existing=False):
    root, manifest_path = pincabos_find_manifest_root(extract_dir)

    if not manifest_path:
        return None

    manifest = json.loads(manifest_path.read_text(errors="replace"))

    if manifest.get("format") != "PinCabOs table export":
        return {
            "ok": False,
            "message": "Manifest trouvé, mais format non reconnu.",
            "manifest": str(manifest_path),
            "copied": [],
            "missing": [],
            "skipped": [],
        }

    table_folder = str(table_folder_override or manifest.get("table_folder") or "").strip()
    if not table_folder:
        table_folder = Path(root).name or "Imported Table"

    table_folder = pincabos_force_standard_table_name(table_folder)

    # Destination officielle PinCabOS portable.
    table_root = Path("/opt/pincabos/vpinball/Tables") / table_folder

    copied = []
    missing = []
    skipped = []

    model = str(manifest.get("model") or "").strip().lower()

    # Nouveau modèle export:
    # Le manifest est dans le dossier de table extrait.
    # On copie donc le dossier complet tel quel, sans reclassement.
    if model in ["full-table-folder-as-is", "single-folder-portable-table"] or manifest.get("format_version", 0) >= 7:
        try:
            if table_root.exists():
                if not overwrite_existing:
                    return {
                        "ok": False,
                        "message": "Table déjà présente. Remplacement ou renommage requis.",
                        "manifest": str(manifest_path),
                        "table_folder": table_folder,
                        "rom": manifest.get("rom") or "",
                        "copied": copied,
                        "missing": missing,
                        "skipped": ["CONFLICT_TABLE_EXISTS"],
                    }
                shutil.rmtree(table_root)

            table_root.mkdir(parents=True, exist_ok=True)

            for item in sorted(Path(root).iterdir()):
                dest = table_root / item.name

                if item.is_dir():
                    shutil.copytree(item, dest, dirs_exist_ok=True)
                    for f in dest.rglob("*"):
                        if f.is_file():
                            copied.append(str(f))
                elif item.is_file():
                    shutil.copy2(item, dest)
                    copied.append(str(dest))

            pincabos_update_imported_table_metadata(table_root, table_folder)

            try:
                subprocess.run(
                    ["/bin/chown", "-R", "pinball:pinball", str(table_root)],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=False,
                )
                subprocess.run(
                    ["/bin/chmod", "-R", "u+rwX,g+rwX,o+rX", str(table_root)],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=False,
                )
            except Exception:
                pass

            return {
                "ok": True,
                "message": "Import .PinCabOs full-folder terminé. Dossier de table copié tel quel.",
                "manifest": str(manifest_path),
                "table_folder": table_folder,
                "rom": manifest.get("rom") or "",
                "copied": copied,
                "missing": missing,
                "skipped": skipped,
            }

        except Exception as e:
            return {
                "ok": False,
                "message": f"Erreur pendant l'import full-folder: {e}",
                "manifest": str(manifest_path),
                "table_folder": table_folder,
                "rom": manifest.get("rom") or "",
                "copied": copied,
                "missing": missing,
                "skipped": skipped,
            }

    # Ancien modèle manifest:
    # Supporte files = ["path"] ET files = [{"path":"...", "size":...}]
    if table_root.exists() and not overwrite_existing:
        return {
            "ok": False,
            "message": "Table déjà présente. Remplacement ou renommage requis.",
            "manifest": str(manifest_path),
            "table_folder": table_folder,
            "rom": manifest.get("rom") or "",
            "copied": copied,
            "missing": missing,
            "skipped": ["CONFLICT_TABLE_EXISTS"],
        }

    if table_root.exists() and overwrite_existing:
        shutil.rmtree(table_root)

    table_root.mkdir(parents=True, exist_ok=True)

    standard_dirs = manifest.get("standard_dirs") or [
        "altsound", "cache", "medias", "music",
        "pinmame", "pinmame/roms", "pinmame/nvram", "pinmame/cfg", "pinmame/ini",
        "pupvideos", "scripts", "serum", "user", "vni", "extras"
    ]

    for sub in standard_dirs:
        (table_root / str(sub).strip("/")).mkdir(parents=True, exist_ok=True)

    globals()["PINCABOS_MANIFEST_IMPORT_TABLE_DIR"] = table_root

    for empty_dir in manifest.get("empty_dirs") or []:
        if isinstance(empty_dir, dict):
            empty_dir = empty_dir.get("path", "")
        rel_empty = pincabos_safe_manifest_relpath(empty_dir)
        if rel_empty:
            dest_empty = table_root / rel_empty
            dest_empty.mkdir(parents=True, exist_ok=True)

    files = manifest.get("files") or []

    for entry in files:
        if isinstance(entry, dict):
            rel = entry.get("path", "")
        else:
            rel = entry

        rel = pincabos_safe_manifest_relpath(rel)
        if not rel:
            skipped.append(str(entry))
            continue

        src = root / rel
        if not src.exists() or not src.is_file():
            missing.append(rel)
            continue

        dest = table_root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        copied.append(str(dest))

    pincabos_update_imported_table_metadata(table_root, table_folder)

    try:
        subprocess.run(
            ["/bin/chown", "-R", "pinball:pinball", str(table_root)],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        subprocess.run(
            ["/bin/chmod", "-R", "u+rwX,g+rwX,o+rX", str(table_root)],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except Exception:
        pass

    return {
        "ok": True,
        "message": "Import basé sur manifest terminé.",
        "manifest": str(manifest_path),
        "table_folder": table_folder,
        "rom": manifest.get("rom") or "",
        "copied": copied,
        "missing": missing,
        "skipped": skipped,
    }


def pincabos_try_manifest_import_from_request():
    """
    Si l'utilisateur importe un ZIP PinCabOs contenant pincabos-export-manifest.json,
    on restaure exactement les fichiers listés dans le manifest.
    Si aucun manifest n'est trouvé, retourne None pour laisser l'ancien import continuer.
    """
    if not request:
        return None

    # 1) ZIP envoyé directement dans request.files
    for key in request.files:
        f = request.files.get(key)
        if not f or not f.filename:
            continue

        filename = f.filename.lower()
        if not (filename.endswith(".zip") or filename.endswith(".7z") or filename.endswith(".pincabos")):
            continue

        with tempfile.TemporaryDirectory(prefix="pincabos-import-manifest-") as td:
            zip_path = Path(td) / "upload.zip"
            extract_dir = Path(td) / "extract"
            extract_dir.mkdir(parents=True, exist_ok=True)

            f.save(str(zip_path))

            try:
                r7 = subprocess.run(
                    ["7z", "x", "-y", f"-o{str(extract_dir)}", str(zip_path)],
                    capture_output=True,
                    text=True,
                    timeout=300,
                    check=False,
                )
                if r7.returncode != 0:
                    raise RuntimeError((r7.stdout + "\n" + r7.stderr).strip())
            except Exception as e:
                return page("Import PinCabOs", f"""
<div class="card">
  <h2>Import impossible</h2>
  <p class="bad">Le package ne peut pas être ouvert avec 7z.</p>
  <pre>{esc(str(e))}</pre>
  <p><a class="button" href="/tools">Retour aux outils</a></p>
</div>
""")

            result = pincabos_import_from_manifest_dir(extract_dir)
            if result:
                return pincabos_manifest_import_result_page(result)

    # 2) Chemin temporaire/dossier transmis dans le formulaire
    for value in request.form.values():
        value = str(value or "").strip()
        if not value:
            continue

        candidate = Path(value)
        if not candidate.exists():
            continue

        # Sécurité : seulement chemins temporaires ou PinCabOs
        allowed_prefixes = (
            "/tmp/",
            "/var/tmp/",
            "/opt/pincabos/tmp/",
            "/opt/pincabos/uploads/",
            "/opt/pincabos/imports/",
        )

        if not any(str(candidate).startswith(prefix) for prefix in allowed_prefixes):
            continue

        if candidate.is_dir():
            result = pincabos_import_from_manifest_dir(candidate)
            if result:
                return pincabos_manifest_import_result_page(result)

        if candidate.is_file() and candidate.suffix.lower() in [".zip", ".7z", ".pincabos", ".pincabos".lower()]:
            with tempfile.TemporaryDirectory(prefix="pincabos-import-manifest-") as td:
                extract_dir = Path(td) / "extract"
                extract_dir.mkdir(parents=True, exist_ok=True)

                try:
                    r7 = subprocess.run(
                        ["7z", "x", "-y", f"-o{str(extract_dir)}", str(candidate)],
                        capture_output=True,
                        text=True,
                        timeout=300,
                        check=False,
                    )
                    if r7.returncode != 0:
                        continue
                except Exception:
                    continue

                result = pincabos_import_from_manifest_dir(extract_dir)
                if result:
                    return pincabos_manifest_import_result_page(result)

    return None


def pincabos_manifest_import_result_page(result):
    ok_class = "ok" if result.get("ok") else "bad"
    copied = result.get("copied") or []
    missing = result.get("missing") or []
    skipped = result.get("skipped") or []

    copied_preview = "\n".join(copied[:80])
    if len(copied) > 80:
        copied_preview += f"\n... {len(copied) - 80} autres fichiers copiés"

    missing_preview = "\n".join(missing[:80])
    skipped_preview = "\n".join(skipped[:80])

    return page("Import PinCabOs", f"""
<div class="card">
  <h2>Import PinCabOs basé sur manifest</h2>
  <p class="{ok_class}">{esc(result.get("message", ""))}</p>

  <p><strong>Table :</strong> <code>{esc(result.get("table_folder", ""))}</code></p>
  <p><strong>ROM :</strong> <code>{esc(result.get("rom", ""))}</code></p>
  <p><strong>Manifest :</strong> <code>{esc(result.get("manifest", ""))}</code></p>

  <p><strong>Fichiers copiés :</strong> {len(copied)}</p>
  <pre>{esc(copied_preview)}</pre>

  <p><strong>Fichiers manquants dans le ZIP :</strong> {len(missing)}</p>
  <pre>{esc(missing_preview)}</pre>

  <p><strong>Fichiers ignorés :</strong> {len(skipped)}</p>
  <pre>{esc(skipped_preview)}</pre>

  <p>
    <a class="button" href="/tools">Retour aux outils</a>
    <a class="button secondary" href="/">Dashboard</a>
  </p>
</div>
""")


def pincabos_run_vpinfe_vpx_standardizer():
    """
    Normalise les tables vers le layout portable VPinFE/VPX après import.
    Les dossiers globaux restent en fallback legacy.
    """
    try:
        subprocess.run(
            ["/opt/pincabos/tools/pincabos-vpinfe-vpx-standard.py", "--apply"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=180,
            check=False
        )
    except Exception:
        pass

@app.route("/tools/import-table/install", methods=["POST"])
def tools_import_table_install():
    manifest_response = pincabos_try_manifest_import_from_request()
    if manifest_response is not None:
        return manifest_response

    batch_dir = Path(request.form.get("batch_dir", "")).resolve()
    imports_root = Path("/opt/pincabos/imports/uploads").resolve()

    if not batch_dir.exists() or imports_root not in batch_dir.parents:
        return page("Outils", """
<div class="card">
  <h2>Installation impossible</h2>
  <p class="bad">Dossier batch invalide.</p>
  <p><a class="button" href="/tools">Retour Outils</a></p>
</div>
""")

    import_mode = request.form.get("import_mode", "auto").strip().lower()
    if import_mode not in ["auto", "search", "manual"]:
        import_mode = "auto"

    ipdbid = ""
    table_title = ""
    title = ""
    manufacturer = ""
    year = ""
    rom = ""
    vpsid = ""
    assoc = {}

    if import_mode == "manual":
        title = request.form.get("manual_title", "").strip()
        table_title = title
        manufacturer = request.form.get("manual_manufacturer", "").strip()
        year = request.form.get("manual_year", "").strip()
        rom = request.form.get("manual_rom", "").strip()
        vpsid = ""
        ipdbid = ""

        if not title:
            return page("Outils", """
<div class="card">
  <h2>Installation impossible</h2>
  <p class="bad">Le nom de table manuel est vide.</p>
  <p>Entre un nom de table VPinFE, par exemple <code>Demo Table (PinCabOs 2026)</code>.</p>
  <p><a class="button" href="/tools">Retour Outils</a></p>
</div>
""")

    else:
        if import_mode == "search":
            assoc_raw = request.form.get("search_association", "{}")
        else:
            assoc_raw = request.form.get("association", "{}")

        try:
            assoc = json.loads(assoc_raw) if assoc_raw else {}
        except Exception:
            assoc = {}

        if assoc.get("mode") != "vpsdb":
            return page("Outils", """
<div class="card">
  <h2>Installation impossible</h2>
  <p class="bad">Aucune association VPSdb valide sélectionnée.</p>
  <p>Utilise une sélection auto, un résultat de recherche VPSdb, ou l’import manuel complet.</p>
  <p><a class="button" href="/tools">Retour Outils</a></p>
</div>
""")

        table_title = str(assoc.get("title", "")).strip()
        manufacturer = str(assoc.get("manufacturer", "")).strip()
        year = str(assoc.get("year", "")).strip()
        rom = str(assoc.get("rom", "")).strip()
        vpsid = str(assoc.get("vpsid", "")).strip()
        ipdbid = str(assoc.get("ipdbid", "")).strip()

        title = str(assoc.get("final_table_name", "")).strip()
        if not title:
            title = table_title
            if manufacturer and year:
                title = f"{table_title} ({manufacturer} {year})"

        if not title:
            return page("Outils", """
<div class="card">
  <h2>Installation impossible</h2>
  <p class="bad">Le résultat VPSdb sélectionné ne contient pas de nom de table valide.</p>
  <p><a class="button" href="/tools">Retour Outils</a></p>
</div>
""")

    # Si aucune ROM fournie par VPSdb/manuel, on reprend la ROM détectée pendant l'analyse du batch.
    if not rom:
        try:
            detected_again = pincabos_detect_batch(batch_dir)
            rom = str(detected_again.get("rom", "") or "").strip()
        except Exception:
            rom = ""

    cmd = [
        "/opt/pincabos/tools/pincabos-smart-archive-import.py",
        str(batch_dir),
        "--title", title,
        "--manufacturer", manufacturer,
        "--year", str(year),
        "--vpsid", vpsid,
        "--rom", rom,
        "--ipdbid", ipdbid,
    ]

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        output = (r.stdout + "\n" + r.stderr).strip()
        returncode = r.returncode
    except Exception as e:
        output = f"ERREUR lancement importeur: {e}"
        returncode = 1

    try:
        if batch_dir.exists() and imports_root in batch_dir.parents:
            shutil.rmtree(batch_dir)
    except Exception as e:
        output += f"\n\nWARNING: impossible de supprimer le batch upload: {e}"

    try:
        for work_root in [Path("/opt/pincabos/import/work"), Path("/opt/pincabos/imports/work")]:
            if work_root.exists():
                for item in work_root.iterdir():
                    if item.is_dir():
                        shutil.rmtree(item, ignore_errors=True)
                    else:
                        try:
                            item.unlink()
                        except Exception:
                            pass
    except Exception as e:
        output += f"\n\nWARNING: cleanup work erreur: {e}"

    cls = "ok" if returncode == 0 else "bad"
    title_msg = "Installation terminée" if returncode == 0 else "Installation terminée avec erreur(s)"

    body = f"""
<div class="card">
  <h2>{esc(title_msg)}</h2>
  <p class="{cls}">Mode : <strong>{esc(import_mode)}</strong></p>
  <p class="{cls}">Association : <strong>{esc(title)}</strong> — {esc(manufacturer)} — {esc(str(year))} — VPSId {esc(vpsid)}</p>

  <h3>Rapport</h3>
  <pre>{esc(output)}</pre>

  <p>
    <a class="button" href="/tools">Retour Outils</a>
    <a class="button secondary" href="/tools/commander?root=Tables">Voir les tables</a>
  </p>
</div>
"""
    return page("Outils", body)


def pincabos_commander_roots():
    paths = pincabos_get_vpinfe_paths_for_tools()

    roots = {
        "Tables": Path(paths["tables"]),
        "AltSound": Path(paths["altsound"]),
        "AltColor": Path(paths["altcolor"]),
        "PupVideos": Path(paths["pupvideos"]),
        "UltraDMD": Path(paths["ultradmd"]),
        "Exports": Path("/opt/pincabos/exports"),
        "Imports temporaires": Path("/opt/pincabos/imports"),
        "Home Pinball": Path("/home/pinball"),
        "Partage PinCabOs": Path("/home/pinball/Share"),
        "Clés USB": Path("/mnt/pincab-usb"),
        "Lecteurs SMB": Path("/home/pinball/NetworkDrives"),
    }

    clean = {}
    for name, path in roots.items():
        try:
            path.mkdir(parents=True, exist_ok=True)
            clean[name] = path.resolve()
        except Exception:
            clean[name] = path.resolve()

    return clean


def pincabos_commander_resolve(root_name, rel_path=""):
    roots = pincabos_commander_roots()

    if root_name not in roots:
        raise ValueError("Racine invalide.")

    root = roots[root_name]
    target = (root / rel_path).resolve()

    if target != root and root not in target.parents:
        raise ValueError("Chemin interdit.")

    return root, target


def pincabos_size_human(size):
    try:
        size = float(size)
        for unit in ["o", "Ko", "Mo", "Go", "To"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} Po"
    except Exception:
        return ""


@app.route("/tools/external-disks")
def tools_external_disks():
    from pathlib import Path

    network_root = Path("/home/pinball/NetworkDrives")
    network_root.mkdir(parents=True, exist_ok=True)

    usb_root = Path("/mnt/pincab-usb")
    usb_root.mkdir(parents=True, exist_ok=True)

    usb_list = ""
    try:
        for d in sorted(usb_root.iterdir(), key=lambda x: x.name.lower()):
            if d.is_dir():
                mounted = subprocess.run(
                    ["bash", "-lc", "mountpoint -q " + shlex_quote(str(d))],
                    capture_output=True,
                    text=True
                ).returncode == 0

                if mounted:
                    usb_list += f"""
<li style="margin-bottom:10px;">
  <strong>{esc(d.name)}</strong> —
  <span class="ok">Monté</span> —
  <code>{esc(str(d))}</code>
  <form action="/tools/external-disks/usb/unmount" method="post" style="display:inline; margin-left:10px;">
    <input type="hidden" name="usb_name" value="{esc(d.name)}">
    <button class="button secondary" type="submit">Démonter</button>
  </form>
</li>
"""
                else:
                    # Nettoyage automatique des dossiers USB ghost
                    try:
                        d.rmdir()
                    except Exception:
                        pass
    except Exception:
        pass

    if not usb_list:
        usb_list = "<li>Aucune clé USB montée.</li>"

    smb_list = ""
    try:
        for d in sorted(network_root.iterdir(), key=lambda x: x.name.lower()):
            if d.is_dir():
                mounted = subprocess.run(
                    ["bash", "-lc", "mountpoint -q " + shlex_quote(str(d))],
                    capture_output=True,
                    text=True
                ).returncode == 0

                cls = "ok" if mounted else "warn"
                status = "Monté" if mounted else "Non monté"

                unmount_button = ""
                if mounted:
                    unmount_button = f"""
<form action="/tools/external-disks/smb/unmount" method="post" style="display:inline; margin-left:10px;">
  <input type="hidden" name="drive_name" value="{esc(d.name)}">
  <button class="button secondary" type="submit">Démonter</button>
</form>
"""

                smb_list += f"""
<li style="margin-bottom:10px;">
  <strong>{esc(d.name)}</strong> —
  <span class="{cls}">{status}</span> —
  <code>{esc(str(d))}</code>
  {unmount_button}
</li>
"""
    except Exception:
        pass

    if not smb_list:
        smb_list = "<li>Aucun lecteur SMB monté/configuré.</li>"

    body = f"""
<div class="card">
  <h2>Gestion des disques externes</h2>

  <p>
    Ajoute un partage SMB / NAS / Windows à PinCabOs.
    Après montage, il apparaîtra dans <strong>PinCab Explorer → Lecteurs SMB</strong>.
  </p>

  <p>
    <a class="button secondary" href="/tools">Retour Outils</a>
    <a class="button" href="/tools/commander?root=Lecteurs%20SMB">Ouvrir Lecteurs SMB dans PinCab Explorer</a>
  </p>
</div>

<div class="card" style="margin-top:20px;">
  <h2>Connecter un partage SMB</h2>

  <p>
    Étape 1 : entre les informations du serveur. PinCabOs va se connecter et détecter les partages disponibles.
  </p>

  <form action="/tools/external-disks/smb/detect" method="post">
    <label>Nom du lecteur dans PinCabOs</label><br>
    <input name="drive_name" placeholder="exemple: NAS-Tables" style="width:90%; padding:8px;"><br><br>

    <label>Adresse serveur ou IP</label><br>
    <input name="server" placeholder="exemple: 192.168.254.10 ou NAS-SYNOLOGY" style="width:90%; padding:8px;"><br><br>

    <label>Login</label><br>
    <input name="username" placeholder="utilisateur SMB" style="width:90%; padding:8px;"><br><br>

    <label>Password</label><br>
    <input name="password" type="password" placeholder="mot de passe SMB" style="width:90%; padding:8px;"><br><br>

    <label>Domaine / Workgroup optionnel</label><br>
    <input name="domain" placeholder="WORKGROUP" style="width:90%; padding:8px;"><br><br>

    <button class="button" type="submit">Connecter et détecter les partages</button>
  </form>
</div>

<div class="card" style="margin-top:20px;">
  <h2>Clés USB</h2>

  <p>
    Les clés USB montées automatiquement apparaissent ici et dans
    <strong>PinCab Explorer → Clés USB</strong>.
  </p>

  <ul>
    {usb_list}
  </ul>
</div>

<div class="card" style="margin-top:20px;">
  <h2>Lecteurs SMB</h2>
  <ul>
    {smb_list}
  </ul>
</div>
"""
    return page("Gestion disques externes", body)


@app.route("/tools/external-disks/smb/detect", methods=["POST"])
def tools_external_disks_smb_detect():
    import json
    import re
    import time
    import uuid
    import subprocess
    from pathlib import Path

    drive_name = request.form.get("drive_name", "").strip()
    server = request.form.get("server", "").strip()
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    domain = request.form.get("domain", "").strip() or "WORKGROUP"

    if not server or not username:
        return page("Gestion disques externes", """
<div class="card">
  <h2>Erreur SMB</h2>
  <p class="bad">Serveur/IP et login requis.</p>
  <p><a class="button" href="/tools/external-disks">Retour</a></p>
</div>
""")

    safe_name = re.sub(r"[^A-Za-z0-9._ -]+", "_", drive_name).strip()
    if not safe_name:
        safe_name = server.replace(".", "-").replace("/", "-")

    session_id = uuid.uuid4().hex
    session_dir = Path("/home/pinball/.config/pincabos/smb-sessions")
    session_dir.mkdir(parents=True, exist_ok=True)

    session_file = session_dir / (session_id + ".json")
    session_file.write_text(json.dumps({
        "drive_name": safe_name,
        "server": server,
        "username": username,
        "password": password,
        "domain": domain,
        "created": time.time(),
    }, indent=2, ensure_ascii=False))
    session_file.chmod(0o600)

    cmd = ["smbclient", "-L", "//" + server, "-U", username + "%" + password, "-m", "SMB3", "-g"]

    if domain:
        cmd.extend(["-W", domain])

    shares = []
    error = ""

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=35)
        output = (r.stdout + "\\n" + r.stderr)

        for line in output.splitlines():
            line = line.strip()

            # Format attendu avec -g : Disk|ShareName|Comment
            if line.startswith("Disk|"):
                parts = line.split("|")
                if len(parts) >= 2:
                    share = parts[1].strip()
                    if share and not share.endswith("$"):
                        shares.append(share)

        if r.returncode != 0 and not shares:
            error = output[-4000:]

    except Exception as e:
        error = str(e)

    if not shares:
        body = f"""
<div class="card">
  <h2>Aucun partage détecté</h2>

  <p class="bad">
    PinCabOs n’a pas réussi à détecter les partages disponibles.
    Vérifie l’adresse/IP, le login, le mot de passe et les permissions du compte.
  </p>

  <h3>Détail</h3>
  <pre>{esc(error)}</pre>

  <p>
    <a class="button" href="/tools/external-disks">Retour</a>
  </p>
</div>
"""
        return page("Partages SMB", body)

    options = ""
    for share in shares:
        options += f'<option value="{esc(share)}">{esc(share)}</option>'

    body = f"""
<div class="card">
  <h2>Partages SMB détectés</h2>

  <p>
    Connexion réussie au serveur : <strong>{esc(server)}</strong>
  </p>

  <form action="/tools/external-disks/smb/mount" method="post">
    <input type="hidden" name="session_id" value="{esc(session_id)}">

    <label>Choisir le partage à monter</label><br>
    <select name="share" style="width:90%; padding:8px; margin:8px 0;">
      {options}
    </select><br><br>

    <button class="button" type="submit">Monter le partage sélectionné</button>
    <a class="button secondary" href="/tools/external-disks">Annuler</a>
  </form>
</div>
"""
    return page("Partages SMB", body)


@app.route("/tools/external-disks/smb/mount", methods=["POST"])
def tools_external_disks_smb_mount():
    import json
    import re
    import subprocess
    from pathlib import Path

    session_id = request.form.get("session_id", "").strip()
    share = request.form.get("share", "").strip()

    session_file = Path("/home/pinball/.config/pincabos/smb-sessions") / (session_id + ".json")

    if not session_id or not share or not session_file.exists():
        return page("Gestion disques externes", """
<div class="card">
  <h2>Erreur SMB</h2>
  <p class="bad">Session SMB invalide ou expirée.</p>
  <p><a class="button" href="/tools/external-disks">Retour</a></p>
</div>
""")

    data = json.loads(session_file.read_text())

    drive_name = data["drive_name"]
    server = data["server"]
    username = data["username"]
    password = data["password"]
    domain = data.get("domain") or "WORKGROUP"

    safe_name = re.sub(r"[^A-Za-z0-9._ -]+", "_", drive_name).strip()
    if not safe_name:
        safe_name = share

    mount_root = Path("/home/pinball/NetworkDrives")
    mount_point = mount_root / safe_name

    cred_root = Path("/home/pinball/.config/pincabos/smb")
    cred_root.mkdir(parents=True, exist_ok=True)
    mount_point.mkdir(parents=True, exist_ok=True)

    cred_file = cred_root / (safe_name + ".cred")
    cred_file.write_text(
        "username=" + username + "\n" +
        "password=" + password + "\n" +
        "domain=" + domain + "\n"
    )
    cred_file.chmod(0o600)

    try:
        subprocess.run(["chown", "-R", "pinball:pinball", str(mount_root), str(cred_root)], timeout=30)
    except Exception:
        pass

    source = f"//{server}/{share}"

    cmd = (
        "sudo /opt/pincabos/tools/pincabos-smb-mount-helper.sh "
        + shlex_quote(source) + " "
        + shlex_quote(str(mount_point)) + " "
        + shlex_quote(str(cred_file))
    )

    try:
        r = subprocess.run(["bash", "-lc", cmd], capture_output=True, text=True, timeout=75)
        output = (r.stdout + "\\n" + r.stderr).strip()
    except subprocess.TimeoutExpired as e:
        output = "Le montage SMB a dépassé le délai. Le serveur NAS ne répond pas assez vite ou les options SMB sont incompatibles.\\n"
        output += "Commande: " + cmd
        r = type("Result", (), {"returncode": 124})()

    try:
        session_file.unlink()
    except Exception:
        pass

    if r.returncode != 0:
        body = f"""
<div class="card">
  <h2>Montage SMB échoué</h2>

  <p class="bad">Le partage a été détecté, mais le montage a échoué.</p>

  <h3>Détail</h3>
  <pre>{esc(output)}</pre>

  <p>
    <a class="button" href="/tools/external-disks">Retour</a>
  </p>
</div>
"""
        return page("Gestion disques externes", body)

    body = f"""
<div class="card">
  <h2>Partage SMB monté</h2>

  <p class="ok">
    Le partage <strong>{esc(share)}</strong> est maintenant monté dans :
  </p>

  <pre>{esc(str(mount_point))}</pre>

  <p>
    <a class="button" href="/tools/commander?root=Lecteurs%20SMB">Ouvrir dans PinCab Explorer</a>
    <a class="button secondary" href="/tools/external-disks">Retour Gestion disques externes</a>
  </p>
</div>
"""
    return page("Gestion disques externes", body)


def pcx_roots():
    return {
        "Tables": Path("/opt/pincabos/vpinball/Tables"),
        "Exports": Path("/opt/pincabos/exports"),
        "Imports": Path("/opt/pincabos/imports"),
        "Home Pinball": Path("/home/pinball"),
        "PinCabShare": Path("/home/pinball/Share"),
        "Clés USB": Path("/mnt/pincab-usb"),
        "Lecteurs SMB": Path("/home/pinball/NetworkDrives"),
    }


def pcx_resolve(root_name, rel_path=""):
    roots = pcx_roots()

    if root_name not in roots:
        root_name = "Tables"

    root = roots[root_name].resolve()
    root.mkdir(parents=True, exist_ok=True)

    target = (root / (rel_path or "")).resolve()

    if target != root and root not in target.parents:
        raise ValueError("Chemin interdit.")

    return root_name, root, target


def pcx_back(root_name, rel_path=""):
    return redirect(
        "/tools/commander?root="
        + urllib.parse.quote(root_name or "Tables")
        + "&path="
        + urllib.parse.quote(rel_path or "")
    )


def pcx_size(size):
    try:
        size = float(size)
        for unit in ["o", "Ko", "Mo", "Go", "To"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} Po"
    except Exception:
        return ""


def pcx_selected():
    try:
        data = request.form.get("selected_json", "[]")
        items = json.loads(data)
        if not isinstance(items, list):
            return []
        return [str(x).strip() for x in items if str(x).strip()]
    except Exception:
        return []


def pcx_clean_name(name):
    name = str(name or "").strip().replace("\\", "/").split("/")[-1]
    name = name.replace("\x00", "")
    if name in ["", ".", ".."]:
        raise ValueError("Nom invalide.")
    return name


def pcx_unique(path):
    path = Path(path)
    if not path.exists():
        return path

    parent = path.parent
    stem = path.stem
    suffix = path.suffix

    for i in range(1, 500):
        candidate = parent / f"{stem} - copie {i}{suffix}"
        if not candidate.exists():
            return candidate

    raise ValueError("Impossible de créer un nom unique.")


def pcx_copy_any(src, dst):
    src = Path(src)
    dst = Path(dst)

    if src.is_dir():
        shutil.copytree(src, dst)
    else:
        shutil.copy2(src, dst)


@app.route("/tools/commander")
def tools_commander():
    import time

    root_name = request.args.get("root") or "Tables"
    rel = request.args.get("path") or ""

    try:
        root_name, root, current = pcx_resolve(root_name, rel)
    except Exception:
        root_name, root, current = pcx_resolve("Tables", "")
        rel = ""

    roots = pcx_roots()
    encoded_root = urllib.parse.quote(root_name)
    encoded_rel = urllib.parse.quote(rel)
    current_rel = "/" if current == root else "/" + str(current.relative_to(root))

    sidebar = ""
    for name in roots:
        cls = "pcx-root active" if name == root_name else "pcx-root"
        icon = "📁"
        if name == "Tables":
            icon = "🎮"
        elif "ROM" in name:
            icon = "💾"
        elif "AltSound" in name:
            icon = "🔊"
        elif "AltColor" in name:
            icon = "🎨"
        elif "Pup" in name:
            icon = "🎬"
        elif "Ultra" in name:
            icon = "🖥️"
        elif "Export" in name:
            icon = "📦"
        elif "Import" in name:
            icon = "📥"
        elif "Home" in name:
            icon = "🏠"
        elif name == "PinCabShare":
            icon = "📌"
        elif "USB" in name or "Clés" in name:
            icon = "🔌"
        elif "SMB" in name:
            icon = "🌐"

        sidebar += (
            '<a class="' + cls + '" href="/tools/commander?root=' + urllib.parse.quote(name) + '">' +
            icon + " " + esc(name) + "</a>"
        )

    parent_button = ""
    if current != root:
        parent_rel = str(current.parent.relative_to(root))
        parent_button = '<a class="pcx-btn" href="/tools/commander?root=' + encoded_root + '&path=' + urllib.parse.quote(parent_rel) + '">⬅ Parent</a>'

    rows = ""
    cards = ""

    parent_row = ""
    if current != root:
        parent_rel_for_row = str(current.parent.relative_to(root))
        parent_href_for_row = "/tools/commander?root=" + encoded_root + "&path=" + urllib.parse.quote(parent_rel_for_row)
        parent_row = (
            '<tr class="pcx-parent-row" data-name=".. parent" data-size="-1" data-mtime="-1">' +
            '<td colspan="4"><a class="pcx-name pcx-parent-link" href="' + parent_href_for_row + '">📁 .. Parent</a></td>' +
            '</tr>'
        )
    else:
        parent_row = (
            '<tr class="pcx-parent-row" data-name=".. parent" data-size="-1" data-mtime="-1">' +
            '<td colspan="4"><span class="pcx-parent-disabled">📁 .. Parent — racine actuelle</span></td>' +
            '</tr>'
        )

    try:
        entries = sorted(current.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
    except Exception:
        entries = []

    for item in entries:
        try:
            item_rel = str(item.relative_to(root))
            item_url = urllib.parse.quote(item_rel)
            modified = time.strftime("%Y-%m-%d %H:%M", time.localtime(item.stat().st_mtime))
            is_dir = item.is_dir()
            size = "-" if is_dir else pcx_size(item.stat().st_size)

            icon = "📁" if is_dir else "📄"
            suffix = item.suffix.lower()

            if not is_dir:
                if suffix in [".zip", ".rar", ".7z"]:
                    icon = "📦"
                elif suffix == ".vpx":
                    icon = "🎱"
                elif suffix == ".directb2s":
                    icon = "🖼️"
                elif suffix in [".png", ".jpg", ".jpeg", ".webp", ".gif"]:
                    icon = "🌄"
                elif suffix in [".mp4", ".avi", ".mov"]:
                    icon = "🎬"
                elif suffix in [".ogg", ".wav", ".mp3"]:
                    icon = "🔊"
                elif suffix in [".json", ".txt", ".ini", ".vbs", ".pov"]:
                    icon = "📝"

            if is_dir:
                open_href = "/tools/commander?root=" + encoded_root + "&path=" + item_url
                name_html = '<a class="pcx-name" href="' + open_href + '">' + esc(item.name) + '</a>'
                action = '<a class="pcx-small" href="' + open_href + '">Ouvrir</a>'
            else:
                download_href = "/tools/commander/download?root=" + encoded_root + "&path=" + item_url
                name_html = esc(item.name)
                action = '<a class="pcx-small" href="' + download_href + '">Télécharger</a>'

            item_stat = item.stat()
            rows += (
                '<tr class="pcx-row" data-name="' + esc(item.name.lower()) + '" data-size="' + esc(item_stat.st_size if item.is_file() else 0) + '" data-mtime="' + esc(item_stat.st_mtime) + '" data-rel="' + esc(item_rel) + '">' +
                '<td><input type="checkbox" class="pcx-check" value="' + esc(item_rel) + '"> ' +
                '<span class="pcx-icon">' + icon + '</span> ' + name_html + '</td>' +
                '<td>' + esc(size) + '</td>' +
                '<td>' + esc(modified) + '</td>' +
                '<td>' + action + '</td>' +
                '</tr>'
            )

            cards += (
                '<div class="pcx-card" data-name="' + esc(item.name.lower()) + '">' +
                '<div class="pcx-card-icon">' + icon + '</div>' +
                '<div class="pcx-card-name">' + name_html + '</div>' +
                '<div class="pcx-card-meta">' + esc(size) + '</div>' +
                '</div>'
            )
        except Exception:
            pass

    body = """
<style>
.pcx-page {
  font-size:13px;
}
.pcx-layout {
  display:grid;
  grid-template-columns:250px 1fr;
  gap:18px;
}
.pcx-top, .pcx-side, .pcx-main {
  background:#111418;
  border:1px solid #242a31;
  border-radius:18px;
  padding:16px;
}
.pcx-actions-title {
  color:#ffb000;
  font-weight:900;
  font-size:18px;
  margin-top:14px;
  margin-bottom:8px;
  text-shadow:0 0 12px rgba(255,140,0,.45);
}
.pcx-toolbar {
  display:flex;
  flex-wrap:wrap;
  gap:9px;
  margin-top:8px;
}
.pcx-btn {
  display:inline-block;
  padding:8px 11px;
  border-radius:10px;
  background:#1b2027;
  color:inherit;
  text-decoration:none;
  border:0;
  cursor:pointer;
  font-size:13px;
}
.pcx-btn:hover {
  background:rgba(255,140,0,.25);
}
.pcx-root {
  display:block;
  padding:9px 11px;
  margin-bottom:7px;
  border-radius:10px;
  background:#181c22;
  text-decoration:none;
  color:inherit;
}
.pcx-root:hover {
  background:rgba(255,140,0,.18);
}
.pcx-root.active {
  background:#ff8c00;
  color:#111;
  font-weight:800;
}
.pcx-path {
  margin-top:12px;
  padding:11px 13px;
  border-radius:10px;
  background:#0b0d10;
}
.pcx-path-label {
  color:#ffb000;
  font-weight:800;
  margin-bottom:6px;
}
.pcx-real-path,
.pcx-main-path {
  margin:6px 0 0 0;
  color:#ffb000;
  font-size:18px;
  line-height:1.25;
  word-break:break-all;
  text-shadow:0 0 12px rgba(255,140,0,.35);
}
.pcx-main-path {
  font-size:16px;
  color:#ffffff;
  opacity:.95;
}
.pcx-select-all {
  display:inline-flex;
  align-items:center;
  gap:6px;
  cursor:pointer;
}
.pcx-head {
  display:flex;
  justify-content:space-between;
  gap:12px;
  align-items:center;
  flex-wrap:wrap;
  margin-bottom:14px;
}
.pcx-search {
  padding:9px;
  border-radius:10px;
  border:1px solid #333a44;
  background:#0b0d10;
  color:inherit;
  min-width:260px;
}
.pcx-table {
  width:100%;
  border-collapse:collapse;
}
.pcx-table th {
  text-align:left;
  padding:8px 10px;
  border-bottom:1px solid #333a44;
  font-size:12px;
}
.pcx-sortable {
  cursor:pointer;
  user-select:none;
}
.pcx-sortable:hover {
  color:#ffb000;
  text-decoration:underline;
}
.pcx-parent-row td {
  background:rgba(255,140,0,.08);
  border-bottom:1px solid rgba(255,140,0,.25);
}
.pcx-parent-link {
  display:inline-block;
  padding:6px 0;
  font-weight:900;
}
.pcx-parent-disabled {
  display:inline-block;
  padding:6px 0;
  opacity:.55;
  font-weight:800;
}
.pcx-table td {
  padding:7px 10px;
  border-bottom:1px solid #232831;
}
.pcx-row:hover {
  background:rgba(255,140,0,.12);
}
.pcx-row.selected {
  background:rgba(255,140,0,.24);
}
.pcx-icon {
  font-size:18px;
  margin-right:8px;
}
.pcx-name {
  font-weight:800;
  text-decoration:none;
}
.pcx-small {
  display:inline-block;
  padding:5px 8px;
  border-radius:8px;
  background:#1b2027;
  color:inherit;
  text-decoration:none;
  font-size:12px;
}
.pcx-grid {
  display:none;
  grid-template-columns:repeat(auto-fill,minmax(150px,1fr));
  gap:12px;
}
.pcx-card {
  background:#161a20;
  border:1px solid #242a31;
  border-radius:16px;
  padding:12px;
  min-height:110px;
}
.pcx-card-icon {
  font-size:34px;
}
.pcx-card-name {
  margin-top:6px;
  font-weight:700;
  word-break:break-word;
}
.pcx-card-meta {
  margin-top:5px;
  opacity:.75;
  font-size:12px;
}
@media(max-width:900px) {
  .pcx-layout {
    grid-template-columns:1fr;
  }
}
</style>

<div class="pcx-page">
  <div class="pcx-top">
    <h2>PinCab Explorer</h2>
    <div class="pcx-actions-title">Actions</div>

<script>
document.addEventListener("DOMContentLoaded", function () {
  const page = document.querySelector(".pcx-page");
  if (!page) return;

  if (page.querySelector(".pcx-refresh-btn")) return;

  const buttons = Array.from(page.querySelectorAll("button, a.pcx-btn, input[type='submit'], input[type='button']"));

  const gridBtn = buttons.find(function (el) {
    const txt = (el.innerText || el.value || "").trim();
    return txt.includes("Vue grille");
  });

  if (!gridBtn) return;

  const refresh = document.createElement("a");
  refresh.href = window.location.pathname + window.location.search;
  refresh.className = "pcx-btn pcx-refresh-btn";
  refresh.innerHTML = '<span class="pcx-btn-icon">🔄</span>Rafraîchir';

  if (gridBtn.nextSibling) {
    gridBtn.parentNode.insertBefore(refresh, gridBtn.nextSibling);
  } else {
    gridBtn.parentNode.appendChild(refresh);
  }
});
</script>


<style>
/* PinCab Explorer : bouton Supprimer rouge foncé */
.pcx-page .pcx-delete-danger,
.pcx-page button.pcx-delete-danger,
.pcx-page a.pcx-delete-danger,
.pcx-page input.pcx-delete-danger {
  background: #7a0000 !important;
  color: #ffffff !important;
  border: 1px solid #ff4444 !important;
  box-shadow: 0 0 12px rgba(255,0,0,0.35) !important;
}

.pcx-page .pcx-delete-danger:hover,
.pcx-page button.pcx-delete-danger:hover,
.pcx-page a.pcx-delete-danger:hover,
.pcx-page input.pcx-delete-danger:hover {
  background: #a00000 !important;
  color: #ffffff !important;
}

.pcx-page .pcx-btn-icon {
  display: inline-block !important;
  margin-right: 6px !important;
  font-size: 1.05em !important;
  line-height: 1 !important;
}
</style>

<script>
document.addEventListener("DOMContentLoaded", function () {
  const page = document.querySelector(".pcx-page");
  if (!page) return;

  const icons = [
    { label: "Vue liste", icon: "📋" },
    { label: "Vue grille", icon: "▦" },
    { label: "Créer dossier", icon: "📁" },
    { label: "Upload", icon: "⬆️" },
    { label: "Renommer", icon: "✏️" },
    { label: "Copier", icon: "📄" },
    { label: "Couper", icon: "✂️" },
    { label: "Coller", icon: "📋" },
    { label: "Dupliquer", icon: "📑" },
    { label: "Extraire ZIP", icon: "📦" },
    { label: "Archiver sélection", icon: "🗜️" },
    { label: "Infos", icon: "ℹ️" },
    { label: "Supprimer", icon: "🗑️", danger: true }
  ];

  const candidates = page.querySelectorAll("button, a.pcx-btn, input[type='submit'], input[type='button']");

  candidates.forEach(function (el) {
    const raw = (el.innerText || el.value || "").trim();
    if (!raw) return;

    icons.forEach(function (item) {
      if (!raw.includes(item.label)) return;

      if (item.danger) {
        el.classList.add("pcx-delete-danger");
      }

      if (el.dataset.pcxIconDone === "1") return;

      if (el.tagName.toLowerCase() === "input") {
        el.value = item.icon + " " + raw;
      } else {
        el.innerHTML = '<span class="pcx-btn-icon">' + item.icon + '</span>' + raw;
      }

      el.dataset.pcxIconDone = "1";
    });
  });
});
</script>


<style>
/* PinCab Explorer : bouton Retour Outils orange seulement */
.pcx-page a.pcx-btn[href="/tools"],
.pcx-page a.pcx-btn[href="/tools"]:visited {
  background: #ff7a00 !important;
  color: #160020 !important;
  border: 1px solid #ffb000 !important;
  box-shadow: 0 0 14px rgba(255,122,0,0.45) !important;
}

.pcx-page a.pcx-btn[href="/tools"]:hover {
  background: #ffb000 !important;
  color: #160020 !important;
}
</style>


<style>
/* PinCab Explorer : liens fichiers/dossiers en blanc */
.pcx-page a:not(.button):not(.pcx-btn),
.pcx-page a:not(.button):not(.pcx-btn):visited,
.pcx-page table a:not(.button):not(.pcx-btn),
.pcx-page table a:not(.button):not(.pcx-btn):visited,
.pcx-page td a:not(.button):not(.pcx-btn),
.pcx-page td a:not(.button):not(.pcx-btn):visited {
  color: #ffffff !important;
  text-decoration: none !important;
}

.pcx-page a:not(.button):not(.pcx-btn):hover,
.pcx-page table a:not(.button):not(.pcx-btn):hover,
.pcx-page td a:not(.button):not(.pcx-btn):hover {
  color: #ffb000 !important;
  text-decoration: underline !important;
}
</style>


    <div class="pcx-toolbar">
      <a class="pcx-btn" href="/tools">Retour Outils</a>
      __PARENT_BUTTON__
      <button class="pcx-btn" onclick="pcxView('list')">Vue liste</button>
      <button class="pcx-btn" onclick="pcxView('grid')">Vue grille</button>
      <button class="pcx-btn" onclick="pcxCreateFolder()">Créer dossier</button>
      <button class="pcx-btn" onclick="document.getElementById('pcxUploadInput').click()">Upload</button>
      <button class="pcx-btn" onclick="pcxRename()">Renommer</button>
      <button class="pcx-btn" onclick="pcxCopy()">Copier</button>
      <button class="pcx-btn" onclick="pcxCut()">Couper</button>
      <button class="pcx-btn" onclick="pcxPaste()">Coller</button>
        <button class="pcx-btn" onclick="pcxDuplicate()">Dupliquer</button>
        <button class="pcx-btn" onclick="pcxExtractZip()">Extraire ZIP</button>
        <button class="pcx-btn" onclick="pcxArchiveSelection()">Archiver sélection</button>
        <button class="pcx-btn" onclick="pcxInfo()">Infos</button>
        <button class="pcx-btn" onclick="pcxDelete()">Supprimer</button>
    </div>

    <form id="pcxUploadForm" action="/tools/commander/upload" method="post" enctype="multipart/form-data" style="display:none;">
      <input type="hidden" name="root" value="__ROOT_NAME__">
      <input type="hidden" name="path" value="__REL_RAW__">
      <input id="pcxUploadInput" type="file" name="files" multiple onchange="document.getElementById('pcxUploadForm').submit()">
    </form>

  </div>

  <div class="pcx-layout" style="margin-top:18px;">
    <div class="pcx-side">
      <h3>Emplacements</h3>
      __SIDEBAR__
    </div>

    <div class="pcx-main">
      <div class="pcx-head">
        <div>
          <h3 class="pcx-main-root-title" style="margin:0;">__ROOT_NAME__</h3>
          <small>__CURRENT_REL__</small>
          <h2 class="pcx-main-path">__CURRENT_ABS_PATH__</h2>
        </div>
        <input id="pcxSearch" class="pcx-search" placeholder="Rechercher..." oninput="pcxFilter()">
      </div>

      <div id="pcxList">
        <table class="pcx-table">
          <thead>
            <tr>
              <th class="pcx-sortable" onclick="pcxSortTable('name')"><label class="pcx-select-all" onclick="event.stopPropagation();"><input id="pcxSelectAll" type="checkbox" onchange="pcxToggleAll(this)"> Nom</label> <span id="pcxSortName"></span></th>
              <th class="pcx-sortable" onclick="pcxSortTable('size')">Taille <span id="pcxSortSize"></span></th>
              <th class="pcx-sortable" onclick="pcxSortTable('mtime')">Modifié <span id="pcxSortMtime"></span></th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            __PARENT_ROW__
            __ROWS__
          </tbody>
        </table>
      </div>

      <div id="pcxGrid" class="pcx-grid">
        __CARDS__
      </div>
    </div>
  </div>
</div>

<script>
function pcxSelected() {
  return Array.from(document.querySelectorAll('.pcx-check:checked')).map(cb => cb.value);
}

function pcxPost(action, extra = {}) {
  const form = document.createElement('form');
  form.method = 'POST';
  form.action = action;

  const fields = {
    root: "__ROOT_NAME_JS__",
    path: "__REL_RAW_JS__",
    selected_json: JSON.stringify(pcxSelected()),
    ...extra
  };

  Object.entries(fields).forEach(([key, value]) => {
    const input = document.createElement('input');
    input.type = 'hidden';
    input.name = key;
    input.value = value;
    form.appendChild(input);
  });

  document.body.appendChild(form);
  form.submit();
}

function pcxCreateFolder() {
  const name = prompt('Nom du nouveau dossier :');
  if (!name) return;
  pcxPost('/tools/commander/create-folder', {folder_name: name});
}

function pcxRename() {
  const selected = pcxSelected();
  if (selected.length !== 1) {
    alert('Sélectionne un seul élément à renommer.');
    return;
  }

  const currentName = selected[0].split('/').pop();
  const name = prompt('Nouveau nom :', currentName);
  if (!name || name === currentName) return;

  pcxPost('/tools/commander/rename', {new_name: name});
}

function pcxDelete() {
  const selected = pcxSelected();
  if (!selected.length) {
    alert('Sélectionne au moins un élément à supprimer.');
    return;
  }

  if (!confirm('Supprimer définitivement ' + selected.length + ' élément(s) ?')) return;
  pcxPost('/tools/commander/delete');
}

function pcxCopy() {
  const selected = pcxSelected();
  if (!selected.length) {
    alert('Sélectionne au moins un élément à copier.');
    return;
  }
  pcxPost('/tools/commander/clipboard', {mode: 'copy'});
}

function pcxCut() {
  const selected = pcxSelected();
  if (!selected.length) {
    alert('Sélectionne au moins un élément à couper.');
    return;
  }
  pcxPost('/tools/commander/clipboard', {mode: 'cut'});
}

function pcxPaste() {
  pcxPost('/tools/commander/paste');
}

function pcxDuplicate() {
  const selected = pcxSelected();
  if (!selected.length) {
    alert('Sélectionne au moins un fichier ou dossier à dupliquer.');
    return;
  }

  pcxPost('/tools/commander/duplicate');
}

function pcxExtractZip() {
  const selected = pcxSelected();
  if (!selected.length) {
    alert('Sélectionne au moins une archive ZIP à extraire.');
    return;
  }

  const bad = selected.filter(x => !x.toLowerCase().endsWith('.zip'));
  if (bad.length) {
    alert('Extraction ZIP seulement. Élément non ZIP: ' + bad[0]);
    return;
  }

  pcxPost('/tools/commander/extract-zip');
}


function pcxArchiveSelection() {
  const selected = pcxSelected();

  if (!selected.length) {
    alert('Sélectionne au moins un fichier ou dossier à archiver.');
    return;
  }

  const suggested = selected.length === 1
    ? selected[0].replace(/\/+$/g, '').split('/').pop().replace(/\.zip$/i, '')
    : 'selection-pincabos';

  const archiveName = prompt("Nom de l'archive ZIP :", suggested);

  if (archiveName === null) {
    return;
  }

  const cleaned = archiveName.trim();

  if (!cleaned) {
    alert("Nom d'archive vide. Opération annulée.");
    return;
  }

  pcxPost('/tools/commander/archive-selection', { archive_name: cleaned });
}

function pcxInfo() {
  const selected = pcxSelected();
  if (selected.length > 1) {
    alert('Sélectionne un seul élément pour voir les infos.');
    return;
  }

  pcxPost('/tools/commander/info');
}

function pcxView(mode) {
  const list = document.getElementById('pcxList');
  const grid = document.getElementById('pcxGrid');

  if (mode === 'grid') {
    list.style.display = 'none';
    grid.style.display = 'grid';
    localStorage.setItem('pincabosPcxView', 'grid');
  } else {
    list.style.display = 'block';
    grid.style.display = 'none';
    localStorage.setItem('pincabosPcxView', 'list');
  }
}

function pcxFilter() {
  const q = document.getElementById('pcxSearch').value.toLowerCase();

  document.querySelectorAll('.pcx-row').forEach(row => {
    row.style.display = (row.dataset.name || '').includes(q) ? '' : 'none';
  });

  document.querySelectorAll('.pcx-card').forEach(card => {
    card.style.display = (card.dataset.name || '').includes(q) ? '' : 'none';
  });
}

let pcxSortState = { key: "", dir: "asc" };

function pcxSortTable(type) {
  const tbody = document.querySelector(".pcx-table tbody");
  if (!tbody) return;

  const parentRow = tbody.querySelector(".pcx-parent-row");
  const rows = Array.from(tbody.querySelectorAll("tr.pcx-row"));

  const dir = pcxSortState.key === type && pcxSortState.dir === "asc" ? "desc" : "asc";
  pcxSortState = { key: type, dir: dir };

  rows.sort((a, b) => {
    let av;
    let bv;

    if (type === "name") {
      av = (a.dataset.name || "").toLowerCase();
      bv = (b.dataset.name || "").toLowerCase();
    } else if (type === "size") {
      av = parseFloat(a.dataset.size || "0") || 0;
      bv = parseFloat(b.dataset.size || "0") || 0;
    } else if (type === "mtime") {
      av = parseFloat(a.dataset.mtime || "0") || 0;
      bv = parseFloat(b.dataset.mtime || "0") || 0;
    } else {
      return 0;
    }

    if (av < bv) return dir === "asc" ? -1 : 1;
    if (av > bv) return dir === "asc" ? 1 : -1;
    return 0;
  });

  tbody.innerHTML = "";
  if (parentRow) tbody.appendChild(parentRow);
  rows.forEach(row => tbody.appendChild(row));

  ["pcxSortName", "pcxSortSize", "pcxSortMtime"].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.textContent = "";
  });

  const arrow = dir === "asc" ? "▲" : "▼";

  if (type === "name") {
    const el = document.getElementById("pcxSortName");
    if (el) el.textContent = arrow;
  }

  if (type === "size") {
    const el = document.getElementById("pcxSortSize");
    if (el) el.textContent = arrow;
  }

  if (type === "mtime") {
    const el = document.getElementById("pcxSortMtime");
    if (el) el.textContent = arrow;
  }
}


function pcxUpdateSelectAllState() {
  const master = document.getElementById('pcxSelectAll');
  if (!master) return;

  const checks = Array.from(document.querySelectorAll('.pcx-check'));
  const visibleChecks = checks.filter(cb => {
    const row = cb.closest('.pcx-row');
    return row && row.style.display !== 'none';
  });

  if (!visibleChecks.length) {
    master.checked = false;
    master.indeterminate = false;
    return;
  }

  const selectedCount = visibleChecks.filter(cb => cb.checked).length;
  master.checked = selectedCount === visibleChecks.length;
  master.indeterminate = selectedCount > 0 && selectedCount < visibleChecks.length;
}

function pcxToggleAll(master) {
  const checks = Array.from(document.querySelectorAll('.pcx-check'));

  checks.forEach(cb => {
    const row = cb.closest('.pcx-row');
    if (!row || row.style.display === 'none') return;

    cb.checked = master.checked;
    if (cb.checked) row.classList.add('selected');
    else row.classList.remove('selected');
  });

  pcxUpdateSelectAllState();
}

document.querySelectorAll('.pcx-check').forEach(cb => {
  cb.addEventListener('change', () => {
    const row = cb.closest('.pcx-row');
    if (cb.checked) row.classList.add('selected');
    else row.classList.remove('selected');
    pcxUpdateSelectAllState();
  });
});

pcxUpdateSelectAllState();

pcxView(localStorage.getItem('pincabosPcxView') || 'list');
</script>
"""

    body = body.replace("__PARENT_BUTTON__", parent_button)
    body = body.replace("__ROOT_NAME__", esc(root_name))
    body = body.replace("__ROOT_NAME_JS__", esc(root_name))
    body = body.replace("__REL_RAW__", esc(rel))
    body = body.replace("__REL_RAW_JS__", esc(rel))
    current_rel_display = "" if str(current_rel).strip("/") == "" else current_rel
    body = body.replace("__CURRENT_REL__", esc(current_rel_display))
    body = body.replace("__CURRENT_ABS_PATH__", esc(str(current)))
    body = body.replace("__SIDEBAR__", sidebar)
    body = body.replace("__PARENT_ROW__", parent_row)
    body = body.replace("__ROWS__", rows)
    body = body.replace("__CARDS__", cards)

    return page("PinCab Explorer", body)


@app.route("/tools/commander/download")
def tools_commander_download():
    root_name = request.args.get("root") or "Tables"
    rel = request.args.get("path") or ""

    try:
        root_name, root, target = pcx_resolve(root_name, rel)
    except Exception:
        return "Chemin invalide", 400

    if not target.exists() or not target.is_file():
        return "Fichier introuvable", 404

    return send_file(target, as_attachment=True, download_name=target.name)


@app.route("/tools/commander/duplicate", methods=["POST"])
def tools_commander_duplicate():
    root_name = request.form.get("root") or "Tables"
    rel = request.form.get("path") or ""

    try:
        root_name, root, current = pcx_resolve(root_name, rel)
        selected = pcx_selected()

        for item_rel in selected:
            name = pcx_clean_name(item_rel)
            src = (current / name).resolve()

            if not src.exists():
                continue
            if src != root and root not in src.parents:
                continue

            dst = pcx_unique(current / (src.stem + " - copie" + src.suffix))
            pcx_copy_any(src, dst)

            try:
                shutil.chown(dst, user="pinball", group="pinball")
                if dst.is_dir():
                    for p in dst.rglob("*"):
                        try:
                            shutil.chown(p, user="pinball", group="pinball")
                        except Exception:
                            pass
            except Exception:
                pass

    except Exception as e:
        print("PCX duplicate error:", e)

    return pcx_back(root_name, rel)


@app.route("/tools/commander/extract-zip", methods=["POST"])
def tools_commander_extract_zip():
    root_name = request.form.get("root") or "Tables"
    rel = request.form.get("path") or ""

    try:
        root_name, root, current = pcx_resolve(root_name, rel)
        selected = pcx_selected()

        for item_rel in selected:
            name = pcx_clean_name(item_rel)
            src = (current / name).resolve()

            if not src.exists() or not src.is_file():
                continue
            if src.suffix.lower() != ".zip":
                continue
            if src != root and root not in src.parents:
                continue

            dest = pcx_unique(current / src.stem)
            dest.mkdir(parents=True, exist_ok=True)

            with zipfile.ZipFile(src, "r") as z:
                for member in z.infolist():
                    member_name = str(member.filename or "").replace("\\", "/")
                    member_path = Path(member_name)

                    if not member_name or member_name.startswith("/") or ".." in member_path.parts:
                        continue

                    z.extract(member, dest)

            try:
                shutil.chown(dest, user="pinball", group="pinball")
                for p in dest.rglob("*"):
                    try:
                        shutil.chown(p, user="pinball", group="pinball")
                    except Exception:
                        pass
            except Exception:
                pass

    except Exception as e:
        print("PCX extract zip error:", e)

    return pcx_back(root_name, rel)


@app.route("/tools/commander/archive-selection", methods=["POST"])
def tools_commander_archive_selection():
    import zipfile
    from pathlib import Path
    from datetime import datetime

    root_name = request.form.get("root") or "Tables"
    rel = request.form.get("path") or ""

    try:
        root_name, root, current = pcx_resolve(root_name, rel)
        selected = pcx_selected()

        if not selected:
            return pcx_back(root_name, rel)

        archive_name = (request.form.get("archive_name") or "").strip()
        if archive_name.lower().endswith(".zip"):
            archive_name = archive_name[:-4].strip()

        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")

        if archive_name:
            safe_archive_name = "".join(
                c if c.isalnum() or c in ("-", "_", ".", " ") else "-"
                for c in archive_name
            )
            safe_archive_name = "-".join(safe_archive_name.split()).strip(".-_") or "pincabos-selection"
        else:
            safe_root_name = "".join(
                c if c.isalnum() or c in ("-", "_") else "-"
                for c in root_name
            ).strip("-") or "PinCabOS"
            safe_archive_name = f"pincabos-selection-{safe_root_name}"

        zip_name = f"{safe_archive_name}-{stamp}.zip"
        zip_path = pcx_unique(current / zip_name)

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            added = 0

            for item_rel in selected:
                name = pcx_clean_name(item_rel)
                src = (current / name).resolve()

                if not src.exists():
                    continue

                if src != root and root not in src.parents:
                    continue

                if src == zip_path:
                    continue

                if src.is_file():
                    z.write(src, src.name)
                    added += 1
                    continue

                if src.is_dir():
                    folder_name = src.name
                    z.writestr(folder_name.rstrip("/") + "/", "")

                    for p in sorted(src.rglob("*")):
                        try:
                            if not p.exists():
                                continue

                            if p.resolve() == zip_path:
                                continue

                            arc = Path(folder_name) / p.relative_to(src)
                            arc_name = str(arc).replace("\\", "/")

                            if p.is_dir():
                                z.writestr(arc_name.rstrip("/") + "/", "")
                            elif p.is_file():
                                z.write(p, arc_name)
                                added += 1
                        except Exception as e:
                            print("PCX archive skip:", p, e)

            if added == 0:
                z.writestr("README.txt", "Aucun fichier valide dans la sélection PinCabOS.\n")

        try:
            import shutil
            shutil.chown(zip_path, user="pinball", group="pinball")
        except Exception:
            pass

        print("PCX archive created:", zip_path)

    except Exception as e:
        print("PCX archive selection error:", e)

    return pcx_back(root_name, rel)


@app.route("/tools/commander/info", methods=["POST"])
def tools_commander_info():
    import stat

    root_name = request.form.get("root") or "Tables"
    rel = request.form.get("path") or ""

    try:
        root_name, root, current = pcx_resolve(root_name, rel)
        selected = pcx_selected()

        if selected:
            name = pcx_clean_name(selected[0])
            target = (current / name).resolve()
        else:
            target = current.resolve()

        if not target.exists():
            raise ValueError("Élément introuvable.")

        if target != root and root not in target.parents:
            raise ValueError("Chemin interdit.")

        st = target.stat()
        kind = "Dossier" if target.is_dir() else "Fichier"

        total_size = st.st_size
        files = 0
        folders = 0

        if target.is_dir():
            total_size = 0
            for p in target.rglob("*"):
                try:
                    if p.is_file():
                        files += 1
                        total_size += p.stat().st_size
                    elif p.is_dir():
                        folders += 1
                except Exception:
                    pass

        modified = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        permissions = stat.filemode(st.st_mode)

        body = f"""
<div class="card">
  <h2>Infos PinCab Explorer</h2>

  <p><strong>Type :</strong> {esc(kind)}</p>
  <p><strong>Nom :</strong> <code>{esc(target.name)}</code></p>
  <p><strong>Racine :</strong> <code>{esc(root_name)}</code></p>
  <p><strong>Chemin :</strong> <code>{esc(str(target))}</code></p>
  <p><strong>Taille :</strong> <code>{esc(pcx_size(total_size))}</code></p>
  <p><strong>Contenu :</strong> <code>{files} fichiers / {folders} dossiers</code></p>
  <p><strong>Permissions :</strong> <code>{esc(permissions)}</code></p>
  <p><strong>UID/GID :</strong> <code>{st.st_uid}:{st.st_gid}</code></p>
  <p><strong>Modifié :</strong> <code>{esc(modified)}</code></p>

  <p>
    <a class="button" href="/tools/commander?root={urllib.parse.quote(root_name)}&path={urllib.parse.quote(rel)}">Retour PinCab Explorer</a>
  </p>
</div>
"""
        return page("Infos PinCab Explorer", body)

    except Exception as e:
        body = f"""
<div class="card">
  <h2>Erreur infos PinCab Explorer</h2>
  <p class="bad">{esc(e)}</p>
  <p>
    <a class="button" href="/tools/commander?root={urllib.parse.quote(root_name)}&path={urllib.parse.quote(rel)}">Retour PinCab Explorer</a>
  </p>
</div>
"""
        return page("Infos PinCab Explorer", body)


@app.route("/tools/commander/create-folder", methods=["POST"])
def tools_commander_create_folder():
    root_name = request.form.get("root") or "Tables"
    rel = request.form.get("path") or ""
    folder_name = request.form.get("folder_name") or ""

    try:
        root_name, root, current = pcx_resolve(root_name, rel)
        folder_name = pcx_clean_name(folder_name)
        target = (current / folder_name).resolve()

        if target != root and root not in target.parents:
            raise ValueError("Chemin interdit.")

        target.mkdir(parents=False, exist_ok=False)
    except Exception as e:
        print("PCX create-folder error:", e)

    return pcx_back(root_name, rel)


@app.route("/tools/commander/upload", methods=["POST"])
def tools_commander_upload():
    root_name = request.form.get("root") or "Tables"
    rel = request.form.get("path") or ""

    try:
        root_name, root, current = pcx_resolve(root_name, rel)

        files = request.files.getlist("files")
        for upload in files:
            if not upload or not upload.filename:
                continue

            filename = secure_filename(upload.filename)
            if not filename:
                continue

            target = (current / filename).resolve()

            if target != root and root not in target.parents:
                raise ValueError("Chemin interdit.")

            if target.exists():
                target = pcx_unique(target)

            upload.save(target)
    except Exception as e:
        print("PCX upload error:", e)

    return pcx_back(root_name, rel)


@app.route("/tools/commander/delete", methods=["POST"])
def tools_commander_delete():
    root_name = request.form.get("root") or "Tables"
    rel = request.form.get("path") or ""
    selected = pcx_selected()

    try:
        root_name, root, current = pcx_resolve(root_name, rel)

        for item_rel in selected:
            target = (root / item_rel).resolve()

            if target == root or root not in target.parents:
                continue

            if target.is_dir():
                shutil.rmtree(target)
            elif target.exists():
                target.unlink()
    except Exception as e:
        print("PCX delete error:", e)

    return pcx_back(root_name, rel)


@app.route("/tools/commander/rename", methods=["POST"])
def tools_commander_rename():
    root_name = request.form.get("root") or "Tables"
    rel = request.form.get("path") or ""
    selected = pcx_selected()
    new_name = request.form.get("new_name") or ""

    try:
        if len(selected) != 1:
            raise ValueError("Sélectionne un seul élément.")

        root_name, root, current = pcx_resolve(root_name, rel)

        src = (root / selected[0]).resolve()
        if src == root or root not in src.parents or not src.exists():
            raise ValueError("Source invalide.")

        new_name = pcx_clean_name(new_name)
        dst = (src.parent / new_name).resolve()

        if dst == root or root not in dst.parents:
            raise ValueError("Destination invalide.")

        if dst.exists():
            raise ValueError("Existe déjà.")

        src.rename(dst)
    except Exception as e:
        print("PCX rename error:", e)

    return pcx_back(root_name, rel)


@app.route("/tools/commander/clipboard", methods=["POST"])
def tools_commander_clipboard():
    root_name = request.form.get("root") or "Tables"
    rel = request.form.get("path") or ""
    mode = request.form.get("mode") or "copy"
    selected = pcx_selected()

    try:
        if mode not in ["copy", "cut"]:
            mode = "copy"

        root_name, root, current = pcx_resolve(root_name, rel)

        valid = []
        for item_rel in selected:
            target = (root / item_rel).resolve()
            if target != root and root in target.parents and target.exists():
                valid.append(item_rel)

        clip = {
            "mode": mode,
            "root": root_name,
            "items": valid,
        }

        clip_path = Path("/opt/pincabos/imports/commander-clipboard.json")
        clip_path.parent.mkdir(parents=True, exist_ok=True)
        pincabos_write_json_with_meta(clip_path, clip, "Commander Clipboard")
    except Exception as e:
        print("PCX clipboard error:", e)

    return pcx_back(root_name, rel)


@app.route("/tools/commander/paste", methods=["POST"])
def tools_commander_paste():
    root_name = request.form.get("root") or "Tables"
    rel = request.form.get("path") or ""

    try:
        dst_root_name, dst_root, dst_current = pcx_resolve(root_name, rel)

        clip_path = Path("/opt/pincabos/imports/commander-clipboard.json")
        if not clip_path.exists():
            raise ValueError("Clipboard vide.")

        clip = json.loads(clip_path.read_text())
        src_root_name = clip.get("root")
        mode = clip.get("mode", "copy")
        items = clip.get("items", [])

        src_root_name, src_root, _ = pcx_resolve(src_root_name, "")

        for item_rel in items:
            src = (src_root / item_rel).resolve()

            if src == src_root or src_root not in src.parents or not src.exists():
                continue

            dst = (dst_current / src.name).resolve()

            if dst == dst_root or dst_root not in dst.parents:
                continue

            if dst.exists():
                dst = pcx_unique(dst)

            if mode == "cut":
                shutil.move(str(src), str(dst))
            else:
                pcx_copy_any(src, dst)

        if mode == "cut":
            clip_path.unlink(missing_ok=True)
    except Exception as e:
        print("PCX paste error:", e)

    return pcx_back(root_name, rel)


def pincabos_find_value_deep(obj, wanted_keys):
    """
    Cherche récursivement une clé dans un dict/list JSON.
    """
    wanted = {str(k).lower() for k in wanted_keys}

    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).lower() in wanted and v not in ("", None):
                return str(v).strip()
        for v in obj.values():
            found = pincabos_find_value_deep(v, wanted)
            if found:
                return found

    elif isinstance(obj, list):
        for item in obj:
            found = pincabos_find_value_deep(item, wanted)
            if found:
                return found

    return ""


def pincabos_export_safe_filename(name):
    name = str(name or "").strip()
    name = name.replace("\\", " ").replace("/", " ")
    name = re.sub(r'[:"*?<>|]+', " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name or "PinCabOs-Table"


def pincabos_table_export_dirs():
    """
    Modèle export PinCabOS:
    - aucune option;
    - aucun chemin legacy global;
    - on exporte le dossier complet de la table sélectionnée tel quel;
    - on ajoute/actualise seulement le manifest d'export;
    - on compresse au maximum;
    - extension finale .PinCabOs.
    """
    return {
        "tables_root": Path("/opt/pincabos/vpinball/Tables"),
        "exports_root": Path("/opt/pincabos/exports"),
    }


def pincabos_write_full_folder_export_manifest(table_dir):
    table_dir = Path(table_dir)
    manifest_path = table_dir / "pincabos-export-manifest.json"

    files = []
    empty_dirs = []

    for p in sorted(table_dir.rglob("*")):
        rel = p.relative_to(table_dir).as_posix()

        if p.is_dir():
            try:
                if not any(p.iterdir()):
                    empty_dirs.append(rel)
            except Exception:
                pass
            continue

        if p.is_file():
            try:
                files.append({
                    "path": rel,
                    "size": p.stat().st_size,
                })
            except Exception:
                files.append({
                    "path": rel,
                    "size": 0,
                })

    manifest = {
        "format": "PinCabOs table export",
        "format_version": 7,
        "model": "full-table-folder-as-is",
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "table_folder": table_dir.name,
        "table_root": str(table_dir),
        "export_rule": "Complete selected table directory, no legacy global paths, no optional filters.",
        "files": files,
        "empty_dirs": empty_dirs,
    }

    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    try:
        subprocess.run(["/bin/chown", "pinball:pinball", str(manifest_path)], timeout=10, check=False)
        subprocess.run(["/bin/chmod", "664", str(manifest_path)], timeout=10, check=False)
    except Exception:
        pass

    return manifest_path


def pincabos_zip_full_table_folder(table_dir, output_path):
    table_dir = Path(table_dir)
    output_path = Path(output_path)

    import zipfile

    with zipfile.ZipFile(
        output_path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
        allowZip64=True,
    ) as z:
        for p in sorted(table_dir.rglob("*")):
            rel = p.relative_to(table_dir.parent).as_posix()

            if p.is_dir():
                try:
                    if not any(p.iterdir()):
                        z.writestr(rel.rstrip("/") + "/", "")
                except Exception:
                    pass
                continue

            if p.is_file():
                z.write(p, rel)

    return output_path


def pincabos_detect_vpsid_for_export(table_dir):
    """
    Détecte le VPSId pour nommer l'export.
    Sources:
    - *.info JSON
    - pincabos-table-manifest.json
    - pincabos-export-manifest.json
    """
    table_dir = Path(table_dir)

    keys = {
        "vpsid", "vps_id", "vpsdb", "vpsdbid", "vpsdb_id",
        "idvpsdb", "id_vpsdb", "id"
    }

    def find_deep(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                lk = str(k).strip().lower()
                if lk in keys and v not in ("", None):
                    val = str(v).strip()
                    # évite de prendre un id générique trop long ou un chemin
                    if val and "/" not in val and "\\" not in val and len(val) <= 64:
                        return val
            for v in obj.values():
                found = find_deep(v)
                if found:
                    return found

        if isinstance(obj, list):
            for item in obj:
                found = find_deep(item)
                if found:
                    return found

        return ""

    candidates = []
    candidates.extend(sorted(table_dir.glob("*.info")))
    candidates.append(table_dir / "pincabos-table-manifest.json")
    candidates.append(table_dir / "pincabos-export-manifest.json")

    for f in candidates:
        try:
            if not f.exists() or not f.is_file():
                continue
            data = json.loads(f.read_text(errors="replace"))
            found = find_deep(data)
            if found:
                return pincabos_export_safe_filename(found)
        except Exception:
            pass

    return ""


@app.route("/tools/export-table", methods=["POST"])
def tools_export_table():
    paths = pincabos_table_export_dirs()
    tables_root = paths["tables_root"].resolve()
    exports_root = paths["exports_root"]

    table_name = request.form.get("table_folder", "").strip()
    if not table_name:
        table_name = request.form.get("table", "").strip()
    if not table_name:
        table_name = request.form.get("table_name", "").strip()

    if not table_name:
        return page("Export PinCabOS", """
<div class="card">
  <h2>Export impossible</h2>
  <p class="bad">Aucune table sélectionnée.</p>
  <p><a class="button" href="/tools">Retour Outils</a></p>
</div>
""")

    table_dir = (tables_root / table_name).resolve()

    if not table_dir.exists() or not table_dir.is_dir() or tables_root not in table_dir.parents:
        return page("Export PinCabOS", f"""
<div class="card">
  <h2>Export impossible</h2>
  <p class="bad">Dossier de table invalide.</p>
  <p><code>{esc(str(table_dir))}</code></p>
  <p><a class="button" href="/tools">Retour Outils</a></p>
</div>
""")

    exports_root.mkdir(parents=True, exist_ok=True)

    manifest_path = pincabos_write_full_folder_export_manifest(table_dir)

    safe_table = pincabos_export_safe_filename(table_dir.name)
    vpsid = pincabos_detect_vpsid_for_export(table_dir)

    if vpsid:
        export_base = f"{safe_table} - VPSId {vpsid}"
    else:
        export_base = safe_table

    tmp_zip = exports_root / f"{export_base}.zip"
    final_pkg = exports_root / f"{export_base}.PinCabOs"

    if tmp_zip.exists():
        tmp_zip.unlink()
    if final_pkg.exists():
        final_pkg.unlink()

    pincabos_zip_full_table_folder(table_dir, tmp_zip)

    tmp_zip.rename(final_pkg)

    try:
        subprocess.run(["/bin/chown", "pinball:pinball", str(final_pkg)], timeout=10, check=False)
        subprocess.run(["/bin/chmod", "664", str(final_pkg)], timeout=10, check=False)
    except Exception:
        pass

    size_mb = final_pkg.stat().st_size / 1024 / 1024

    delete_after_export = request.form.get("delete_after_export") == "1"
    deleted_table = False
    delete_message = ""

    export_ok = False
    try:
        import zipfile
        export_ok = final_pkg.exists() and final_pkg.is_file() and final_pkg.stat().st_size > 0
        if export_ok:
            with zipfile.ZipFile(final_pkg, "r") as z:
                export_ok = z.testzip() is None
    except Exception as e:
        export_ok = False
        delete_message = f"Validation export échouée: {e}"

    if delete_after_export:
        if export_ok:
            try:
                if table_dir.exists() and table_dir.is_dir() and tables_root in table_dir.parents:
                    shutil.rmtree(table_dir)
                    deleted_table = True
                    delete_message = "Table locale supprimée après export validé."
            except Exception as e:
                delete_message = f"Export OK, mais suppression impossible: {e}"
        else:
            if not delete_message:
                delete_message = "Suppression annulée: le package exporté n’a pas passé la validation."

    delete_html = ""
    if delete_after_export:
        cls = "ok" if deleted_table else "warn"
        delete_html = f'<p class="{cls}"><strong>Suppression après export :</strong> {esc(delete_message)}</p>'

    return page("Export PinCabOS", f"""
<div class="card">
  <h2>Export terminé</h2>
  <p class="ok">Package créé avec le dossier complet de la table, sans filtre ni option legacy.</p>
  {delete_html}

  <p><strong>Table :</strong> <code>{esc(table_dir.name)}</code></p>
  <p><strong>VPSId :</strong> <code>{esc(vpsid or "non détecté")}</code></p>
  <p><strong>Manifest :</strong> <code>{esc(str(manifest_path))}</code></p>
  <p><strong>Package :</strong> <code>{esc(str(final_pkg))}</code></p>
  <p><strong>Taille :</strong> {size_mb:.2f} MiB</p>

  <p>
    <a class="button" href="/download-export?file={esc(final_pkg.name)}">Télécharger .PinCabOs</a>
    <a class="button secondary" href="/tools">Retour Outils</a>
  </p>
</div>
""")


@app.route("/download-export")
def download_export():
    paths = pincabos_table_export_dirs()
    exports_root = paths["exports_root"].resolve()

    filename = request.args.get("file", "").strip()
    if not filename:
        return "Fichier manquant", 400

    filename = Path(filename).name
    if not filename.lower().endswith(".pincabos"):
        return "Extension invalide", 400

    target = (exports_root / filename).resolve()

    if not target.exists() or not target.is_file() or exports_root not in target.parents:
        return "Fichier introuvable", 404

    return send_file(
        str(target),
        as_attachment=True,
        download_name=target.name,
        mimetype="application/octet-stream",
    )


@app.route("/api/import/analyze-zip", methods=["POST"])
def api_import_analyze_zip():
    try:
        from pathlib import Path
        import sys

        tools_dir = "/opt/pincabos/tools"
        if tools_dir not in sys.path:
            sys.path.insert(0, tools_dir)

        from pincabos_import_classifier import analyze_zip

        data = request.get_json(silent=True) or {}
        zip_path = data.get("zip_path") or data.get("path") or ""

        if not zip_path:
            return jsonify({"ok": False, "error": "zip_path manquant"}), 400

        zp = Path(zip_path).resolve()

        allowed_roots = [
            Path("/opt/pincabos/imports").resolve(),
            Path("/opt/pincabos/uploads").resolve(),
            Path("/opt/pincabos/tmp").resolve(),
            Path("/opt/pincabos/tables").resolve(),
        ]

        if not any(str(zp).startswith(str(root)) for root in allowed_roots):
            return jsonify({"ok": False, "error": "chemin zip non autorisé"}), 403

        return jsonify(analyze_zip(zp))

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/import/apply-zip-choice", methods=["POST"])
def api_import_apply_zip_choice():
    try:
        from pathlib import Path
        import sys

        tools_dir = "/opt/pincabos/tools"
        if tools_dir not in sys.path:
            sys.path.insert(0, tools_dir)

        from pincabos_import_classifier import import_zip_by_choice, normalize_table_layout

        data = request.get_json(silent=True) or {}
        zip_path = data.get("zip_path") or data.get("path") or ""
        table_dir = data.get("table_dir") or ""
        choice = data.get("choice") or ""

        if not zip_path:
            return jsonify({"ok": False, "error": "zip_path manquant"}), 400
        if not table_dir:
            return jsonify({"ok": False, "error": "table_dir manquant"}), 400
        if choice not in ("rom", "medias", "music", "ignore"):
            return jsonify({"ok": False, "error": "choice invalide"}), 400

        zp = Path(zip_path).resolve()
        td = Path(table_dir).resolve()

        allowed_zip_roots = [
            Path("/opt/pincabos/imports").resolve(),
            Path("/opt/pincabos/uploads").resolve(),
            Path("/opt/pincabos/tmp").resolve(),
            Path("/opt/pincabos/tables").resolve(),
        ]

        tables_root = Path("/opt/pincabos/tables").resolve()

        if not any(str(zp).startswith(str(root)) for root in allowed_zip_roots):
            return jsonify({"ok": False, "error": "chemin zip non autorisé"}), 403

        if not str(td).startswith(str(tables_root)):
            return jsonify({"ok": False, "error": "table_dir non autorisé"}), 403

        standard_dirs = [
            "table", "media", "music", "roms", "pupvideos", "altcolor",
            "altsound", "dmd", "b2s", "scripts", "config", "docs", "extras"
        ]

        for sub in standard_dirs:
            (td / sub).mkdir(parents=True, exist_ok=True)

        result = import_zip_by_choice(zp, td, choice)

        if result.get("ok"):
            result["normalize"] = normalize_table_layout(td)

            try:
                subprocess.run(
                    ["/opt/pincabos/tools/pincabos-import-portable-normalize.py", "--table", td.name],
                    capture_output=True,
                    text=True,
                    timeout=120,
                    check=False,
                )
            except Exception:
                pass

        return jsonify(result)

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
# === /PinCabOs Import ZIP Analyzer API ===


# === INPUTS COMMANDER V1 - PINCABOS START ===
PINCABOS_INPUTS_INI = "/home/pinball/.local/share/VPinballX/10.8/VPinballX.ini"
PINCABOS_INPUTS_CFG = "/opt/pincabos/config/inputs-commander.json"

PINCABOS_INPUT_KEYMAP = [
    ("LeftFlipperKey", "Flipper gauche", "42"),
    ("RightFlipperKey", "Flipper droit", "54"),
    ("StagedLeftFlipperKey", "Flipper gauche staged / upper", ""),
    ("StagedRightFlipperKey", "Flipper droit staged / upper", ""),
    ("LeftMagnaSave", "Magna Save gauche", "29"),
    ("RightMagnaSave", "Magna Save droit", "97"),
    ("LeftMagnaSave2", "Magna Save gauche 2", ""),
    ("RightMagnaSave2", "Magna Save droit 2", ""),
    ("StartGameKey", "Start", "2"),
    ("StartGameKey2", "Start 2", ""),
    ("AddCreditKey", "Coin / crédit", "6"),
    ("AddCreditKey2", "Coin / crédit 2", ""),
    ("PlungerKey", "Plunger / Launch Ball", "28"),
    ("LockbarKey", "Lockbar Fire", ""),
    ("ExitGameKey", "Exit", "1"),
    ("PauseKey", "Pause", ""),
    ("LeftTiltKey", "Nudge gauche digital", "44"),
    ("RightTiltKey", "Nudge droite digital", "53"),
    ("CenterTiltKey", "Nudge centre digital", "57"),
    ("MechanicalTilt", "Tilt mécanique", "20"),
    ("VolumeUpKey", "Volume +", ""),
    ("VolumeDownKey", "Volume -", ""),
    ("CoinDoorKey", "Coin Door", ""),
    ("ServiceCancelKey", "Service Cancel", ""),
    ("ServiceDownKey", "Service Down", ""),
    ("ServiceUpKey", "Service Up", ""),
    ("ServiceEnterKey", "Service Enter", ""),
    ("BuyInKey", "Buy In / Extra Ball", ""),
    ("FrameCountKey", "Frame Counter / FPS", ""),
    ("DebuggerKey", "Debugger", ""),
    ("Enable3DKey", "Activer 3D", ""),
    ("JoyCustom1Key", "Custom 1", "22"),
    ("JoyCustom2Key", "Custom 2", "23"),
    ("JoyCustom3Key", "Custom 3", "24"),
    ("JoyCustom4Key", "Custom 4", "25"),
]

PINCABOS_INPUT_PLAYERMAP = [
    ("PBWEnabled", "Nudge analogique VPX activé", "0"),
    ("NudgeStrength", "Force visuelle du nudge", "0.01"),
    ("PlungerAxis", "Axe plunger VPX", ""),
]

PINCABOS_INPUTS_DEFAULT_CFG = {
    "input_mode": "auto",
    "capture_backend": "evdev",
    "preferred_device": "",
    "dudes_profile": "off",
    "dudes_shift_enabled": False,
    "dudes_shift_input": "",
    "dudes_nightmode_input": "",
    "stabilization_delay_ms": 20,
    "nudge_axis_x": "",
    "nudge_axis_y": "",
    "nudge_axis_z": "",
    "nudge_deadzone": "0.08",
    "nudge_gain_x": "1.0",
    "nudge_gain_y": "1.0",
    "nudge_invert_x": False,
    "nudge_invert_y": False,
    "virtual_tilt_enabled": False,
    "virtual_tilt_threshold": "0.85",
    "plunger_min": "0",
    "plunger_max": "65535",
    "plunger_invert": False,
    "launch_ball_emulation": "off",
}

def inputs_esc(value):
    import html
    return html.escape(str(value if value is not None else ""), quote=True)

def inputs_cmd(cmd, timeout=5):
    import subprocess
    try:
        r = subprocess.run(cmd, shell=True, text=True, capture_output=True, timeout=timeout)
        return ((r.stdout or "") + (r.stderr or "")).strip()
    except Exception as e:
        return str(e)

def inputs_load_cfg():
    from pathlib import Path
    import json
    cfg = dict(PINCABOS_INPUTS_DEFAULT_CFG)
    p = Path(PINCABOS_INPUTS_CFG)
    if p.exists():
        try:
            data = json.loads(p.read_text(errors="replace"))
            if isinstance(data, dict):
                cfg.update(data)
        except Exception:
            pass
    return cfg

def inputs_save_cfg(cfg):
    from pathlib import Path
    import json
    import subprocess
    p = Path(PINCABOS_INPUTS_CFG)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + chr(10))
    try:
        subprocess.run(["chown", "pinball:pinball", str(p)], timeout=10)
    except Exception:
        pass

def inputs_read_ini():
    from pathlib import Path
    p = Path(PINCABOS_INPUTS_INI)
    lines = p.read_text(errors="replace").splitlines() if p.exists() else []
    found = {}
    section = ""
    for line in lines:
        s = line.strip()
        if s.startswith("[") and s.endswith("]"):
            section = s.strip("[]")
            continue
        if "=" in line and not s.startswith((";", "#")):
            k, v = line.split("=", 1)
            found[k.strip()] = {"value": v.strip(), "section": section}
    return lines, found

def inputs_find_section(lines, wanted):
    for i, line in enumerate(lines):
        if line.strip().lower() == "[" + wanted.lower() + "]":
            end = len(lines)
            for j in range(i + 1, len(lines)):
                s = lines[j].strip()
                if s.startswith("[") and s.endswith("]"):
                    end = j
                    break
            return i, end
    return None, None

def inputs_rewrite_ini(key_values, player_values):
    from pathlib import Path
    from datetime import datetime
    import shutil
    import subprocess

    ini = Path(PINCABOS_INPUTS_INI)
    if not ini.exists():
        raise FileNotFoundError(str(ini))

    backup_dir = Path("/opt/pincabos/backups/inputs-commander")
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = backup_dir / f"VPinballX.ini.backup-inputs-commander-{stamp}"
    shutil.copy2(ini, backup)

    lines, found = inputs_read_ini()

    keyboard_section = "Keyboard"
    for probe in ["AddCreditKey", "LeftFlipperKey", "RightFlipperKey", "StartGameKey"]:
        if probe in found and found[probe].get("section"):
            keyboard_section = found[probe]["section"]
            break

    def rewrite_section(section_name, values, managed_keys, label):
        nonlocal lines
        start, end = inputs_find_section(lines, section_name)
        if start is None:
            if lines and lines[-1].strip():
                lines.append("")
            lines.append("[" + section_name + "]")
            start = len(lines) - 1
            end = len(lines)

        before = lines[:start + 1]
        section = lines[start + 1:end]
        after = lines[end:]

        cleaned = []
        for line in section:
            stripped = line.strip()
            if "PinCabOS fonction(Inputs Commander" in line:
                continue
            if "=" in line and not stripped.startswith((";", "#")):
                key = line.split("=", 1)[0].strip()
                if key in managed_keys:
                    continue
            cleaned.append(line)

        while cleaned and not cleaned[-1].strip():
            cleaned.pop()
        if cleaned:
            cleaned.append("")

        comment = "; Modifié " + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + " par PinCabOS fonction(" + label + ")"
        new_part = [comment]
        for key in managed_keys:
            new_part.append(key + " = " + str(values.get(key, "")))

        lines = before + cleaned + new_part + after

    keyboard_keys = [k for k, label, default in PINCABOS_INPUT_KEYMAP]
    player_keys = [k for k, label, default in PINCABOS_INPUT_PLAYERMAP]

    rewrite_section(keyboard_section, key_values, keyboard_keys, "Inputs Commander Keyboard")
    rewrite_section("Player", player_values, player_keys, "Inputs Commander Nudge")

    ini.write_text(chr(10).join(lines) + chr(10))
    try:
        subprocess.run(["chown", "pinball:pinball", str(ini)], timeout=10)
    except Exception:
        pass

    return str(backup), keyboard_section

def inputs_select(name, current, choices):
    out = ['<select name="' + inputs_esc(name) + '">']
    for value, label in choices:
        sel = " selected" if str(current) == str(value) else ""
        out.append('<option value="' + inputs_esc(value) + '"' + sel + ">" + inputs_esc(label) + "</option>")
    out.append("</select>")
    return "".join(out)

def inputs_checked(cfg, key):
    return "checked" if cfg.get(key) else ""

def inputs_devices_html():
    raw_proc = inputs_cmd("cat /proc/bus/input/devices 2>/dev/null || true", 5)
    raw_byid = inputs_cmd("ls -lah /dev/input/by-id 2>/dev/null || true", 5)
    raw_dev = inputs_cmd("ls -lah /dev/input/event* /dev/input/js* 2>/dev/null || true", 5)
    raw_usb = inputs_cmd("lsusb 2>/dev/null || true", 5)

    rows = []
    block = []
    for line in raw_proc.splitlines() + [""]:
        if line.strip():
            block.append(line)
            continue
        if not block:
            continue
        name = ""
        handlers = ""
        phys = ""
        for b in block:
            if b.startswith("N: Name="):
                name = b.split("=", 1)[1].strip().strip('"')
            elif b.startswith("H: Handlers="):
                handlers = b.split("=", 1)[1].strip()
            elif b.startswith("P: Phys="):
                phys = b.split("=", 1)[1].strip()
        if name or handlers:
            rows.append("<tr><td>" + inputs_esc(name) + "</td><td><code>" + inputs_esc(handlers) + "</code></td><td><code>" + inputs_esc(phys) + "</code></td></tr>")
        block = []

    table = "<p class='warn'>Aucun périphérique input détecté.</p>"
    if rows:
        table = "<table><tr><th>Périphérique</th><th>Handlers</th><th>Phys</th></tr>" + "".join(rows) + "</table>"

    return """
<div class="card">
  <h2>Périphériques HID / evdev détectés</h2>
  """ + table + """
  <details><summary>Voir /dev/input/by-id</summary><pre>""" + inputs_esc(raw_byid) + """</pre></details>
  <details><summary>Voir /dev/input/event* et js*</summary><pre>""" + inputs_esc(raw_dev) + """</pre></details>
  <details><summary>Voir lsusb</summary><pre>""" + inputs_esc(raw_usb) + """</pre></details>
  <details><summary>Voir /proc/bus/input/devices complet</summary><pre>""" + inputs_esc(raw_proc) + """</pre></details>
</div>
"""


@app.route("/inputs")
def inputs_page():
    body = """
<div class="card">
  <h1>Inputs</h1>
  <p>
    Gestion des entrées du pincab : boutons, plunger, nudge, tilt, magna save,
    coin, start, exit, HID, raw input, gamepad/XInput et Dude’s Cab.
  </p>

  <p>
    <a class="button" href="/inputs/map-commander">🎛️ Ouvrir Map Commander</a>
  </p>
</div>

<div class="card">
  <h2>Entrées PinCabOS</h2>
  <table>
    <tr><td>Boutons cabinet</td><td>Flippers, Start, Coin, Exit, Launch Ball, Magna Save, Tilt</td></tr>
    <tr><td>Nudge analogique</td><td>Axes X/Y/Z, deadzone, gain, inversion, virtual tilt</td></tr>
    <tr><td>Plunger</td><td>Axe VPX, calibration min/max, inversion, launch ball</td></tr>
  </table>
</div>
"""
    return page("Inputs", body)


@app.route("/inputs/map-commander")
def inputs_map_commander_page():
    cfg = inputs_load_cfg()
    lines, found = inputs_read_ini()

    key_rows = []
    for idx, (key, label, default) in enumerate(PINCABOS_INPUT_KEYMAP):
        current = found.get(key, {}).get("value", default)
        section = found.get(key, {}).get("section", "auto")
        status = "Détecté" if key in found else "Défaut"
        status_class = "good" if key in found else "warn"
        row = """
<tr>
  <td class="map-func"><strong>""" + inputs_esc(label) + """</strong></td>
  <td class="map-key"><code>""" + inputs_esc(key) + """</code></td>
  <td class="map-raw"><input id="raw_""" + inputs_esc(key) + """" class="map-raw-input" value="" readonly></td>
  <td class="map-value"><input id="key_""" + inputs_esc(key) + """" name="key_""" + inputs_esc(key) + """" value=\"""" + inputs_esc(current) + """" class="map-code-input"></td>
  <td class="map-section"><code>""" + inputs_esc(section) + """</code></td>
  <td class="map-state"><span class=\"""" + status_class + """\">""" + inputs_esc(status) + """</span></td>
  <td class="map-actions"><button class="button secondary map-mini-btn" type="button" onclick="detectInput('key_""" + inputs_esc(key) + """')">Détecter</button><button class="button secondary map-mini-btn" type="button" onclick="clearInput('key_""" + inputs_esc(key) + """')">Clear</button></td>
</tr>
"""
        key_rows.append(row)

    player_rows = []
    for key, label, default in PINCABOS_INPUT_PLAYERMAP:
        current = found.get(key, {}).get("value", default)
        section = found.get(key, {}).get("section", "Player")
        status = "Détecté" if key in found else "Défaut"
        status_class = "good" if key in found else "warn"
        player_rows.append("""
<tr>
  <td class="map-func"><strong>""" + inputs_esc(label) + """</strong></td>
  <td class="map-key"><code>""" + inputs_esc(key) + """</code></td>
  <td class="map-value"><input name="player_""" + inputs_esc(key) + """" value=\"""" + inputs_esc(current) + """" class="map-code-input"></td>
  <td class="map-section"><code>""" + inputs_esc(section) + """</code></td>
  <td class="map-state"><span class=\"""" + status_class + """\">""" + inputs_esc(status) + """</span></td>
</tr>
""")

    body = """
<style>
.map-grid {
  display: grid;
  grid-template-columns: minmax(260px, 1fr) minmax(260px, 1fr);
  gap: 14px;
}
.map-key-columns {
  display: grid;
  grid-template-columns: minmax(480px, 1fr) minmax(480px, 1fr);
  gap: 14px;
  align-items: start;
}
.map-key-column {
  border: 1px solid rgba(255,176,0,.22);
  border-radius: 14px;
  padding: 10px;
  background: rgba(0,0,0,.14);
}
.map-key-column h3 {
  margin-top: 0;
  color: #ffb000;
}
.map-box {
  border: 1px solid rgba(255,176,0,.25);
  border-radius: 14px;
  padding: 14px;
  background: rgba(0,0,0,.18);
}
.map-table-wrap { overflow-x: auto; }
.map-table {
  width: 100%;
  border-collapse: collapse;
}
.map-table th, .map-table td {
  vertical-align: middle;
  padding: 10px;
}
.map-table th { text-align:left; color:#ffb000; }
.map-func { min-width: 210px; }
.map-key { min-width: 190px; }
.map-value { width: 120px; text-align:center; }
.map-section { width: 100px; text-align:center; }
.map-state { width: 100px; text-align:center; }
.map-actions { width: 190px; white-space:nowrap; text-align:right; }
.map-code-input {
  width: 90px;
  text-align: center;
  font-family: monospace;
}
.map-mini-btn {
  min-width: 76px !important;
  font-size: 12px !important;
  padding: 4px 7px !important;
  margin-left: 5px !important;
}
#map-detect-status {
  margin-top: 10px;
  padding: 8px 10px;
  border-radius: 10px;
  background: rgba(255,176,0,.08);
  border: 1px solid rgba(255,176,0,.25);
}
@media (max-width: 850px) {
  .map-grid { grid-template-columns: 1fr; }
  .map-key-columns { grid-template-columns: 1fr; }
}

.map-raw { width: 170px; text-align:center; }
.map-raw-input { width:155px; text-align:center; font-family:monospace; opacity:.9; }
.map-detect-modal { position:fixed; inset:0; background:rgba(0,0,0,.72); z-index:99999; display:none; align-items:center; justify-content:center; }
.map-detect-box { width:min(520px,92vw); border:1px solid rgba(255,176,0,.55); border-radius:18px; padding:22px; background:rgba(20,0,30,.96); box-shadow:0 0 35px rgba(255,122,0,.28); text-align:center; }
.map-detect-count { font-size:54px; font-weight:900; color:#ffb000; margin:12px 0; }
.map-detect-raw { margin-top:12px; padding:10px; border-radius:10px; background:rgba(0,0,0,.35); font-family:monospace; }

</style>

<div class="card">
  <h1>Map Commander</h1>
  <p>
    Mapping des boutons, du nudge analogique et du plunger vers VPX Standalone.
  </p>
  <p>
    Fichier VPX : <code>""" + inputs_esc(PINCABOS_INPUTS_INI) + """</code><br>
    Config PinCabOS : <code>""" + inputs_esc(PINCABOS_INPUTS_CFG) + """</code>
  </p>

  <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:14px 0;">
    <div style="border:1px solid rgba(255,176,0,.45);border-radius:14px;padding:12px;background:rgba(255,176,0,.08);box-shadow:0 0 18px rgba(255,122,0,.12);">
      <strong>⚠️ Configuration recommandée sur le cab</strong><br>
      PinCabOS suggère de faire la configuration Map Commander directement sur le cab,
      en utilisant les boutons <strong>Afficher sur le cab</strong> pour valider les entrées réelles.
    </div>

    <div style="border:1px solid rgba(255,176,0,.45);border-radius:14px;padding:12px;background:rgba(255,176,0,.08);box-shadow:0 0 18px rgba(255,122,0,.12);">
      <strong>⚡ Conseil performance / latence</strong><br>
      PinCabOS suggère, si possible, d’utiliser un mapping <strong>clavier</strong>
      plutôt qu’un mapping joystick, surtout pour réduire la latence des boutons critiques.
    </div>
  </div>

  <p><a class="button secondary" href="/inputs">← Retour Inputs</a></p>
</div>

<form method="post" action="/inputs/save">

<div class="card">
  <h2>Mapping boutons VPX</h2>
  <p>Ces valeurs écrivent les codes dans <code>VPinballX.ini</code>.</p>
  <div class="map-table-wrap">
    <table class="map-table">
      <tr><th>Fonction</th><th>Clé VPX</th><th>Détecté brut</th><th>Valeur VPX</th><th>Section</th><th>État</th><th>Actions</th></tr>
      """ + "".join(key_rows) + """
    </table>
  </div>

<div class="map-detect-modal" id="mapDetectModal">
  <div class="map-detect-box">
    <h2>Détection en cours</h2>
    <p>Appuie sur une touche clavier dans cette page ou sur un bouton joystick.</p>
    <div class="map-detect-count" id="mapDetectCountdown">30</div>
    <div class="map-detect-raw" id="mapDetectRaw">En attente...</div>
    <p><button class="button secondary" type="button" onclick="closeDetectPopup()">Annuler</button></p>
  </div>
</div>

<script>
let mapDetectTimer = null;
let mapDetectKeyHandler = null;
let mapDetectActive = false;

function clearInput(id) {
  const el = document.getElementById(id);
  const rawEl = document.getElementById(id.replace("key_", "raw_"));
  if (el) {
    el.value = "";
    el.dispatchEvent(new Event("input", {bubbles:true}));
    el.focus();
  }
  if (rawEl) rawEl.value = "";
}

function closeDetectPopup() {
  mapDetectActive = false;

  const modal = document.getElementById("mapDetectModal");
  if (modal) modal.style.display = "none";

  if (mapDetectTimer) {
    clearInterval(mapDetectTimer);
    mapDetectTimer = null;
  }

  if (mapDetectKeyHandler) {
    window.removeEventListener("keydown", mapDetectKeyHandler, true);
    mapDetectKeyHandler = null;
  }
}

async function detectInput(id) {
  const el = document.getElementById(id);
  const rawEl = document.getElementById(id.replace("key_", "raw_"));
  const modal = document.getElementById("mapDetectModal");
  const countdown = document.getElementById("mapDetectCountdown");
  const rawBox = document.getElementById("mapDetectRaw");

  if (!el) return;

  const keyMap = {
    Escape:1,
    Digit1:2, Digit2:3, Digit3:4, Digit4:5, Digit5:6, Digit6:7, Digit7:8, Digit8:9, Digit9:10, Digit0:11,
    KeyQ:16, KeyW:17, KeyE:18, KeyR:19, KeyT:20, KeyY:21, KeyU:22, KeyI:23, KeyO:24, KeyP:25,
    KeyA:30, KeyS:31, KeyD:32, KeyF:33, KeyG:34, KeyH:35, KeyJ:36, KeyK:37, KeyL:38,
    KeyZ:44, KeyX:45, KeyC:46, KeyV:47, KeyB:48, KeyN:49, KeyM:50,
    Enter:28, Space:57,
    ShiftLeft:42, ShiftRight:54,
    ControlLeft:29, ControlRight:97,
    AltLeft:56, AltRight:100,
    ArrowLeft:105, ArrowRight:106, ArrowUp:103, ArrowDown:108,
    Insert:110, Delete:111, Home:102, End:107, PageUp:104, PageDown:109,
    F1:59, F2:60, F3:61, F4:62, F5:63, F6:64, F7:65, F8:66, F9:67, F10:68, F11:87, F12:88
  };

  mapDetectActive = true;
  let seconds = 30;

  if (modal) modal.style.display = "flex";
  if (countdown) countdown.textContent = seconds;
  if (rawBox) rawBox.textContent = "En attente...";
  el.focus();

  if (mapDetectTimer) clearInterval(mapDetectTimer);
  mapDetectTimer = setInterval(() => {
    seconds--;
    if (countdown) countdown.textContent = seconds;
    if (seconds <= 0) {
      if (rawBox) rawBox.textContent = "Timeout : aucune entrée détectée.";
      setTimeout(closeDetectPopup, 800);
    }
  }, 1000);

  function finish(code, raw) {
    if (!mapDetectActive) return;

    el.value = String(code);
    if (rawEl) rawEl.value = raw;
    if (rawBox) rawBox.textContent = raw + " -> VPX code " + code;

    setTimeout(closeDetectPopup, 700);
  }

  mapDetectKeyHandler = function(e) {
    if (!mapDetectActive) return;

    e.preventDefault();
    e.stopPropagation();

    const code = keyMap[e.code];
    const raw = "keyboard:web code=" + e.code + " key=" + e.key;

    if (code !== undefined) {
      finish(code, raw);
    } else if (rawBox) {
      rawBox.textContent = "Touche non mappée : " + raw;
    }
  };

  window.addEventListener("keydown", mapDetectKeyHandler, true);

  try {
    const r = await fetch("/inputs/detect-once", {method:"POST"});
    const data = await r.json();

    if (mapDetectActive && data.ok) {
      const raw = "evdev device=" + data.name + " code=" + data.code;
      finish(data.code, raw);
    }
  } catch(e) {
    if (rawBox) rawBox.textContent = "evdev non disponible, clavier web actif.";
  }
}
</script>

</div>

<div class="card">
  <h2>Nudge analogique / Plunger</h2>
  <p>Réglages analogiques VPX / PinCabOS.</p>

  <div class="np-grid-safe">
    <div class="np-panel-safe">
      <h3>🎯 Nudge X / Y</h3>
      <div class="nudge-scope-safe"><div class="nudge-dot-safe"></div></div>

      <div class="np-fields-safe">
        <label>Axe X <input name="nudge_axis_x" value=\"""" + inputs_esc(cfg.get("nudge_axis_x", "")) + """\"></label>
        <label class="checkline"><input type="checkbox" name="nudge_invert_x" value="1" """ + inputs_checked(cfg, "nudge_invert_x") + """> Inverser X</label>

        <label>Axe Y <input name="nudge_axis_y" value=\"""" + inputs_esc(cfg.get("nudge_axis_y", "")) + """\"></label>
        <label class="checkline"><input type="checkbox" name="nudge_invert_y" value="1" """ + inputs_checked(cfg, "nudge_invert_y") + """> Inverser Y</label>

        <label>Deadzone <input name="nudge_deadzone" value=\"""" + inputs_esc(cfg.get("nudge_deadzone", "0.08")) + """\"></label>
        <label>Max field <input name="nudge_maxfield" value=\"""" + inputs_esc(cfg.get("nudge_maxfield", "1.00")) + """\"></label>

        <label>Gain X <input name="nudge_gain_x" value=\"""" + inputs_esc(cfg.get("nudge_gain_x", "1.0")) + """\"></label>
        <label>Gain Y <input name="nudge_gain_y" value=\"""" + inputs_esc(cfg.get("nudge_gain_y", "1.0")) + """\"></label>

        <label class="checkline"><input type="checkbox" name="virtual_tilt_enabled" value="1" """ + inputs_checked(cfg, "virtual_tilt_enabled") + """> Virtual tilt</label>
        <label>Seuil tilt <input name="virtual_tilt_threshold" value=\"""" + inputs_esc(cfg.get("virtual_tilt_threshold", "0.85")) + """\"></label>
      </div>

      <p><button class="button" type="submit">Appliquer Nudge</button></p>
    </div>

    <div class="np-panel-safe">
      <h3>🕹️ Plunger Z</h3>
      <div class="plunger-track-safe"><div class="plunger-pointer-safe"></div></div>

      <div class="np-fields-safe">
        <label>Axe Z / Plunger <input name="nudge_axis_z" value=\"""" + inputs_esc(cfg.get("nudge_axis_z", "")) + """\"></label>
        <label>Deadzone plunger <input name="plunger_deadzone" value=\"""" + inputs_esc(cfg.get("plunger_deadzone", "0.03")) + """\"></label>

        <label>Min calibration <input name="plunger_min" value=\"""" + inputs_esc(cfg.get("plunger_min", "0")) + """\"></label>
        <label>Max calibration <input name="plunger_max" value=\"""" + inputs_esc(cfg.get("plunger_max", "65535")) + """\"></label>

        <label>Max field plunger <input name="plunger_maxfield" value=\"""" + inputs_esc(cfg.get("plunger_maxfield", "1.00")) + """\"></label>
        <label class="checkline"><input type="checkbox" name="plunger_invert" value="1" """ + inputs_checked(cfg, "plunger_invert") + """> Inverser plunger</label>

        <label>Émulation Launch Ball """ + inputs_select("launch_ball_emulation", cfg.get("launch_ball_emulation", "off"), [
          ("off", "Désactivée"),
          ("push", "Pousser à fond = Launch Ball"),
          ("pull", "Tirer à fond = Launch Ball"),
          ("both", "Pousser ou tirer = Launch Ball"),
      ]) + """</label>
      </div>

      <p><button class="button" type="submit">Appliquer Plunger</button></p>
    </div>
  </div>

  <details style="margin-top:16px;">
    <summary>Paramètres VPX dans [Player]</summary>
    <div class="map-table-wrap">
      <table class="map-table">
        <tr><th>Paramètre</th><th>Clé VPX</th><th>Valeur</th><th>Section</th><th>État</th></tr>
        """ + "".join(player_rows) + """
      </table>
    </div>
  </details>
</div>

<div class="card">
  <button class="button" type="submit">Sauvegarder Map Commander</button>
  
</div>

</form>
"""
    return page("Map Commander", body)


@app.route("/inputs/save", methods=["POST"])
def inputs_save():
    cfg = inputs_load_cfg()

    for key in [
        "input_mode",
        "capture_backend",
        "preferred_device",
        "dudes_profile",
        "dudes_shift_input",
        "dudes_nightmode_input",
        "nudge_axis_x",
        "nudge_axis_y",
        "nudge_axis_z",
        "nudge_deadzone",
        "nudge_gain_x",
        "nudge_gain_y",
        "virtual_tilt_threshold",
        "plunger_min",
        "plunger_max",
        "launch_ball_emulation",
        "stabilization_delay_ms",
    ]:
        cfg[key] = request.form.get(key, "").strip()

    for key in [
        "dudes_shift_enabled",
        "nudge_invert_x",
        "nudge_invert_y",
        "virtual_tilt_enabled",
        "plunger_invert",
    ]:
        cfg[key] = request.form.get(key) == "1"

    key_values = {}
    for key, label, default in PINCABOS_INPUT_KEYMAP:
        key_values[key] = request.form.get("key_" + key, "").strip()

    player_values = {}
    for key, label, default in PINCABOS_INPUT_PLAYERMAP:
        player_values[key] = request.form.get("player_" + key, "").strip()

    try:
        backup, keyboard_section = inputs_rewrite_ini(key_values, player_values)
        inputs_save_cfg(cfg)
        body = """
<div class="card">
  <h1>Inputs Commander sauvegardé</h1>
  <p class="good">Mapping écrit dans <code>""" + inputs_esc(PINCABOS_INPUTS_INI) + """</code>.</p>
  <p>Section clavier utilisée : <code>""" + inputs_esc(keyboard_section) + """</code></p>
  <p>Backup : <code>""" + inputs_esc(backup) + """</code></p>
  <a class="button" href="/inputs/map-commander">Retour Map Commander</a>
</div>
"""
        return page("Inputs", body)
    except Exception as e:
        body = """
<div class="card">
  <h1>Erreur Inputs Commander</h1>
  <p class="bad"><code>""" + inputs_esc(e) + """</code></p>
  <a class="button" href="/inputs">Retour</a>
</div>
"""
        return page("Inputs", body)


@app.route("/inputs/detect-once", methods=["POST"])
def inputs_detect_once():
    import os, glob, time, select, struct, json
    EVENT_FMT = "llHHI"
    EVENT_SIZE = struct.calcsize(EVENT_FMT)

    devices = []
    for dev in sorted(glob.glob("/dev/input/event*")):
        try:
            fd = os.open(dev, os.O_RDONLY | os.O_NONBLOCK)
            devices.append((dev, fd))
        except Exception:
            pass

    if not devices:
        return jsonify({"ok": False, "error": "Aucun /dev/input/event* lisible. Vérifie les permissions du service PinCabOS."})

    try:
        deadline = time.time() + 8
        while time.time() < deadline:
            r, _, _ = select.select([fd for _, fd in devices], [], [], 0.25)
            for fd in r:
                try:
                    data = os.read(fd, EVENT_SIZE)
                    if len(data) != EVENT_SIZE:
                        continue
                    sec, usec, etype, code, value = struct.unpack(EVENT_FMT, data)
                    if etype == 1 and value == 1:
                        devname = next((d for d, f in devices if f == fd), "event")
                        return jsonify({"ok": True, "code": str(code), "name": devname})
                except Exception:
                    continue
        return jsonify({"ok": False, "error": "timeout"})
    finally:
        for _, fd in devices:
            try:
                os.close(fd)
            except Exception:
                pass


@app.route("/inputs/defaults", methods=["POST"])
def inputs_defaults():
    cfg = dict(PINCABOS_INPUTS_DEFAULT_CFG)
    inputs_save_cfg(cfg)

    key_values = {key: default for key, label, default in PINCABOS_INPUT_KEYMAP}
    player_values = {key: default for key, label, default in PINCABOS_INPUT_PLAYERMAP}

    try:
        backup, keyboard_section = inputs_rewrite_ini(key_values, player_values)
        body = """
<div class="card">
  <h1>Défauts Inputs appliqués</h1>
  <p class="good">Défauts PinCabOS appliqués.</p>
  <p>Section clavier utilisée : <code>""" + inputs_esc(keyboard_section) + """</code></p>
  <p>Backup : <code>""" + inputs_esc(backup) + """</code></p>
  <a class="button" href="/inputs/map-commander">Retour Map Commander</a>
</div>
"""
        return page("Inputs", body)
    except Exception as e:
        body = """
<div class="card">
  <h1>Erreur preset Inputs</h1>
  <p class="bad"><code>""" + inputs_esc(e) + """</code></p>
  <a class="button" href="/inputs">Retour</a>
</div>
"""
        return page("Inputs", body)
# === INPUTS COMMANDER V1 - PINCABOS END ===


@app.route("/pcos-update-api/status")
def pincabos_update_status():
    import json, pathlib, subprocess
    cfg_path = pathlib.Path("/opt/pincabos/config/pincabos-update.json")
    version_path = pathlib.Path("/opt/pincabos/config/version.json")
    last_path = pathlib.Path("/opt/pincabos/config/last-update.json")

    cfg = {}
    version = {}
    last = {}

    try:
        if cfg_path.exists():
            cfg = json.loads(cfg_path.read_text())
    except Exception as e:
        cfg = {"error": str(e)}

    try:
        if version_path.exists():
            version = json.loads(version_path.read_text())
    except Exception as e:
        version = {"error": str(e)}

    try:
        if last_path.exists():
            last = json.loads(last_path.read_text())
    except Exception as e:
        last = {"error": str(e)}

    return jsonify({
        "ok": True,
        "config": cfg,
        "local_version": version,
        "last_update": last
    })


@app.route("/pincabos-update/run", methods=["POST"])
def pincabos_update_run():
    import subprocess
    try:
        subprocess.Popen(
            ["/usr/bin/sudo", "/opt/pincabos/tools/pincabos-apply-update.sh"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return jsonify({"ok": True, "message": "Mise à jour PinCabOS lancée"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


def pincabos_start_update_job(force=False):
    import os
    import subprocess
    import time

    script = "/opt/pincabos/tools/pincabos-apply-update.sh"
    unit = "pincabos-apply-update-" + str(int(time.time()))

    cmd = [
        "/usr/bin/systemd-run",
        "--unit", unit,
        "--collect",
        "--same-dir",
        "--property=Type=simple",
        "--property=KillMode=process",
        "--property=TimeoutStartSec=0",
        script
    ]

    if force:
        cmd.append("--force")

    if os.geteuid() != 0:
        cmd = ["/usr/bin/sudo", "-n"] + cmd

    subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    return {
        "unit": unit,
        "cmd": cmd,
        "force": force
    }


@app.route("/pincabos-update")
def pincabos_update_page():
    body = """
<div class="card">
  <h1>⬆️ Mise à jour PinCabOS</h1>
  <p>Cette mise à jour télécharge le dernier paquet PinCabOS depuis le serveur configuré, fait un backup local, applique les fichiers système PinCabOS, puis redémarre si requis.</p>
  <p><strong>Préservé :</strong> tables, médias, configuration VPinFE utilisateur, VPX, VPinFE upstream, fichiers cab.</p>
  <p><strong>Mis à jour :</strong> WebApp PinCabOS, outils PinCabOS, services PinCabOS, configurations système PinCabOS.</p>

  <div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:14px;margin-bottom:14px;">
    <button class="button" type="button" onclick="pcosCheckUpdate()">🔍 Vérifier</button>
    <button class="button" type="button" onclick="pcosRunUpdate(false)">⬆️ Update normal</button>
    <button class="button secondary" type="button" onclick="pcosRunUpdate(true)" style="border-color:#ff3b30;color:#fff;background:rgba(255,59,48,.25);">🔥 Forcer la MAJ System</button>
  </div>

  
  <div style="margin-top:16px;">
    <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:6px;">
      <strong id="pcosStep">Prêt</strong>
      <span id="pcosPct">0%</span>
    </div>
    <div style="height:24px;background:rgba(0,0,0,.45);border:1px solid rgba(255,176,0,.35);border-radius:999px;overflow:hidden;">
      <div id="pcosBar" style="height:100%;width:0%;background:linear-gradient(90deg,#ff7a00,#ffb000);box-shadow:0 0 14px rgba(255,176,0,.55);transition:width .35s;"></div>
    </div>
    <p id="pcosMsg" style="color:#ffb000;margin-top:10px;">Aucune mise à jour en cours.</p>
  </div>

  <h2>Opérations</h2>
  <pre id="pcosEvents" style="min-height:140px;max-height:260px;overflow:auto;background:rgba(0,0,0,.45);border:1px solid rgba(255,176,0,.25);border-radius:12px;padding:12px;white-space:pre-wrap;">Prêt.</pre>

  <h2>Log technique</h2>
  <pre id="pcosUpdateLog" style="min-height:260px;max-height:520px;overflow:auto;background:rgba(0,0,0,.45);border:1px solid rgba(255,176,0,.25);border-radius:12px;padding:12px;white-space:pre-wrap;">Prêt.</pre>

</div>


<div id="pcosRebootModal" style="display:none;position:fixed;inset:0;z-index:999999;background:rgba(0,0,0,.88);align-items:center;justify-content:center;text-align:center;padding:30px;">
  <div style="max-width:760px;width:92%;border:2px solid rgba(255,176,0,.75);border-radius:24px;background:rgba(20,0,35,.94);box-shadow:0 0 45px rgba(255,122,0,.35);padding:34px;">
    <div style="font-size:58px;line-height:1;margin-bottom:14px;">🔄</div>
    <h1 style="display:block;color:#ffb000;font-size:34px;margin:0 0 12px 0;">Redémarrage requis</h1>
    <p id="pcosRebootMsg" style="font-size:23px;color:white;margin:12px 0;">Update terminé. Redémarrage dans 10 secondes...</p>
    <button id="pcosRebootNow" class="button" type="button" style="font-size:20px;">Redémarrer maintenant</button>
  </div>
</div>


<script>

let pcosPollTimer = null;


let pcosRebootTimer = null;
let pcosRebootLeft = 10;
let pcosRebootRequested = false;

function pcosShowRebootModal() {
  if (pcosRebootRequested) return;
  const modal = document.getElementById("pcosRebootModal");
  const msg = document.getElementById("pcosRebootMsg");
  if (!modal || !msg) return;

  modal.style.display = "flex";

  if (pcosRebootTimer) return;

  pcosRebootLeft = 10;
  msg.textContent = "Update terminé. Redémarrage dans " + pcosRebootLeft + " secondes...";

  pcosRebootTimer = setInterval(function() {
    pcosRebootLeft -= 1;
    msg.textContent = "Update terminé. Redémarrage dans " + pcosRebootLeft + " secondes...";

    if (pcosRebootLeft <= 0) {
      clearInterval(pcosRebootTimer);
      pcosRebootTimer = null;
      pcosRebootNow();
    }
  }, 1000);
}

async function pcosRebootNow() {
  if (pcosRebootRequested) return;
  pcosRebootRequested = true;

  if (pcosRebootTimer) {
    clearInterval(pcosRebootTimer);
    pcosRebootTimer = null;
  }

  const modal = document.getElementById("pcosRebootModal");
  const msg = document.getElementById("pcosRebootMsg");
  const btn = document.getElementById("pcosRebootNow");

  if (msg) msg.textContent = "Redémarrage demandé...";
  if (btn) {
    btn.disabled = true;
    btn.textContent = "Redémarrage en cours...";
  }

  try {
    await pcosFetchJson("/pcos-update-api/reboot", {method:"POST", cache:"no-store"});
  } catch(e) {
    if (msg) msg.textContent = "Redémarrage demandé. La WebApp peut devenir indisponible.";
  }

  setTimeout(function() {
    if (modal) modal.style.display = "none";
  }, 1000);
}

async function pcosFetchJson(url, options) {
  const r = await fetch(url, options || {});
  const text = await r.text();
  try {
    return JSON.parse(text);
  } catch(e) {
    throw new Error("Réponse non-JSON: " + text.substring(0, 120));
  }
}

function pcosSetProgress(data) {
  const pct = Math.max(0, Math.min(100, Number(data.percent || 0)));

  const bar = document.getElementById("pcosBar");
  const pctEl = document.getElementById("pcosPct");
  const step = document.getElementById("pcosStep");
  const msg = document.getElementById("pcosMsg");
  const events = document.getElementById("pcosEvents");
  const log = document.getElementById("pcosUpdateLog");

  if (bar) bar.style.width = pct + "%";
  if (pctEl) pctEl.textContent = pct + "%";
  if (step) step.textContent = data.step || "Prêt";
  if (msg) msg.textContent = data.message || "";

  if (events) {
    events.textContent = (data.events || []).join("\\n") || "Prêt.";
    events.scrollTop = events.scrollHeight;
  }

  if (log) {
    log.textContent = data.log_tail || log.textContent || "";
    log.scrollTop = log.scrollHeight;
  }

  if (false && data.state === "awaiting_reboot") {
    pcosShowRebootModal();
  }
}

async function pcosPollProgress() {
  try {
    const data = await pcosFetchJson("/pcos-update-api/progress?ts=" + Date.now());
    pcosSetProgress(data);

    if (!data.running && ["done", "failed", "idle"].includes(data.state)) {
      if (pcosPollTimer) {
        clearInterval(pcosPollTimer);
        pcosPollTimer = null;
      }
    }
  } catch(e) {
    const msg = document.getElementById("pcosMsg") || document.getElementById("pcosUpdateLog");
    if (msg) msg.textContent = "Erreur lecture progression: " + e.message;
  }
}

async function pcosCheckUpdate() {
  const log = document.getElementById("pcosUpdateLog");
  log.textContent = "Vérification...";
  try {
    const data = await pcosFetchJson("/pcos-update-api/status?ts=" + Date.now());
    log.textContent = JSON.stringify(data, null, 2);
    await pcosPollProgress();
  } catch(e) {
    log.textContent = "Erreur: " + e.message;
  }
}

async function pcosRunUpdate(force) {
  const confirmMsg = force
    ? "FORCER la mise à jour système PinCabOS ?"
    : "Installer l’update normale PinCabOS ?";
  if (!confirm(confirmMsg)) return;

  const log = document.getElementById("pcosUpdateLog");
  log.textContent = force ? "Force system update lancé..." : "Update normal lancé...";

  try {
    const url = force ? "/pcos-update-api/run?force=1" : "/pcos-update-api/run";
    const data = await pcosFetchJson(url, {method:"POST"});
    log.textContent = JSON.stringify(data, null, 2);

    await pcosPollProgress();
    if (!pcosPollTimer) {
      pcosPollTimer = setInterval(pcosPollProgress, 1000);
    }
  } catch(e) {
    log.textContent = "Erreur: " + e.message;
  }
}

document.addEventListener("DOMContentLoaded", function() {
  const rebootBtn = document.getElementById("pcosRebootNow");
  if (rebootBtn) rebootBtn.addEventListener("click", pcosRebootNow);
  pcosPollProgress();
});

</script>
"""
    return page("Mise à jour PinCabOS", body)


@app.route("/api/pcos-update-api/status")
def api_pincabos_update_status():
    import json
    import pathlib
    import urllib.request
    from flask import jsonify

    cfg_path = pathlib.Path("/opt/pincabos/config/pincabos-update.json")
    version_path = pathlib.Path("/opt/pincabos/config/version.json")
    last_path = pathlib.Path("/opt/pincabos/config/last-update.json")

    cfg = {}
    local_version = {}
    last_update = {}
    latest = {}
    latest_error = None

    try:
        if cfg_path.exists():
            cfg = json.loads(cfg_path.read_text(errors="replace"))
    except Exception as e:
        cfg = {"error": str(e)}

    try:
        if version_path.exists():
            local_version = json.loads(version_path.read_text(errors="replace"))
    except Exception as e:
        local_version = {"error": str(e)}

    try:
        if last_path.exists():
            last_update = json.loads(last_path.read_text(errors="replace"))
    except Exception as e:
        last_update = {"error": str(e)}

    latest_url = cfg.get("latest_json_url", "https://update.pincabos.cc/updates/latest.json")

    try:
        with urllib.request.urlopen(latest_url, timeout=8) as r:
            latest = json.loads(r.read().decode("utf-8", "replace"))
    except Exception as e:
        latest_error = str(e)

    return jsonify({
        "ok": True,
        "config": cfg,
        "local_version": local_version,
        "last_update": last_update,
        "latest_url": latest_url,
        "latest": latest,
        "latest_error": latest_error
    })


@app.route("/api/pcos-update-api/progress")
def api_pincabos_update_progress():
    import json
    import pathlib
    from flask import jsonify

    status_path = pathlib.Path("/opt/pincabos/logs/updates/pincabos-update-status.json")

    data = {
        "ok": True,
        "running": False,
        "state": "idle",
        "percent": 0,
        "step": "Prêt",
        "message": "Aucune mise à jour en cours.",
        "events": [],
        "log": "",
        "log_tail": ""
    }

    try:
        if status_path.exists():
            loaded = json.loads(status_path.read_text(errors="replace"))
            if isinstance(loaded, dict):
                data.update(loaded)
    except Exception as e:
        data["ok"] = False
        data["error"] = str(e)

    log_path = data.get("log")
    try:
        if log_path and pathlib.Path(log_path).exists():
            raw_log = pathlib.Path(log_path).read_text(errors="replace")

            # PinCabOS Log technique:
            # Certains logs contiennent des retours échappés comme \\n / \\r,
            # ou des retours terminal \r. On les convertit côté serveur
            # avant de les envoyer à la page /pincabos-update.
            raw_log = raw_log.replace("\\r\\n", "\n")
            raw_log = raw_log.replace("\\n", "\n")
            raw_log = raw_log.replace("\\r", "\n")
            raw_log = raw_log.replace("\r\n", "\n")
            raw_log = raw_log.replace("\r", "\n")

            lines = raw_log.splitlines()
            data["log_tail"] = "\n".join(lines[-220:])
    except Exception as e:
        data["log_tail"] = "Erreur lecture log: " + str(e)

    return jsonify(data)


@app.route("/api/pincabos-update/run", methods=["POST"])
def api_pincabos_update_run():
    import os
    import subprocess
    from flask import request, jsonify

    force = request.args.get("force", "0") in ("1", "true", "yes", "on")
    script = "/opt/pincabos/tools/pincabos-apply-update.sh"

    if os.geteuid() == 0:
        cmd = [script]
    else:
        cmd = ["/usr/bin/sudo", "-n", script]

    if force:
        cmd.append("--force")

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return jsonify({
            "ok": True,
            "pid": proc.pid,
            "force": force,
            "cmd": cmd,
            "message": "Force system update lancé" if force else "Update normal lancé"
        })
    except Exception as e:
        return jsonify({
            "ok": False,
            "force": force,
            "error": str(e)
        }), 500


@app.route("/pcos-update-api/status")
def pcos_update_api_status():
    import json
    import pathlib
    import urllib.request
    from flask import jsonify

    cfg_path = pathlib.Path("/opt/pincabos/config/pincabos-update.json")
    version_path = pathlib.Path("/opt/pincabos/config/version.json")
    last_path = pathlib.Path("/opt/pincabos/config/last-update.json")

    def read_json(path):
        try:
            if path.exists():
                return json.loads(path.read_text(errors="replace"))
        except Exception as e:
            return {"error": str(e)}
        return {}

    cfg = read_json(cfg_path)
    local_version = read_json(version_path)
    last_update = read_json(last_path)

    latest_url = cfg.get("latest_json_url", "https://update.pincabos.cc/updates/latest.json")
    latest = {}
    latest_error = None

    try:
        with urllib.request.urlopen(latest_url, timeout=8) as r:
            latest = json.loads(r.read().decode("utf-8", "replace"))
    except Exception as e:
        latest_error = str(e)

    return jsonify({
        "ok": True,
        "config": cfg,
        "local_version": local_version,
        "last_update": last_update,
        "latest_url": latest_url,
        "latest": latest,
        "latest_error": latest_error
    })


@app.route("/pcos-update-api/progress")
def pcos_update_api_progress():
    import json
    import pathlib
    from flask import jsonify

    status_path = pathlib.Path("/opt/pincabos/logs/updates/pincabos-update-status.json")

    data = {
        "ok": True,
        "running": False,
        "state": "idle",
        "percent": 0,
        "step": "Prêt",
        "message": "Aucune mise à jour en cours.",
        "events": [],
        "log": "",
        "log_tail": ""
    }

    try:
        if status_path.exists():
            loaded = json.loads(status_path.read_text(errors="replace"))
            if isinstance(loaded, dict):
                data.update(loaded)
    except Exception as e:
        data["ok"] = False
        data["error"] = str(e)

    log_path = data.get("log")
    try:
        if log_path and pathlib.Path(log_path).exists():
            raw_log = pathlib.Path(log_path).read_text(errors="replace")

            # PinCabOS Log technique /pincabos-update:
            # convertir les retours échappés \\n / \\r en vrais retours ligne
            # avant de les envoyer au <pre id="pcosUpdateLog">.
            raw_log = raw_log.replace("\\r\\n", "\n")
            raw_log = raw_log.replace("\\n", "\n")
            raw_log = raw_log.replace("\\r", "\n")
            raw_log = raw_log.replace("\r\n", "\n")
            raw_log = raw_log.replace("\r", "\n")

            lines = raw_log.splitlines()
            data["log_tail"] = "\n".join(lines[-220:])
    except Exception as e:
        data["log_tail"] = "Erreur lecture log: " + str(e)

    return jsonify(data)


@app.route("/pcos-update-api/run", methods=["POST"])
def pcos_update_api_run():
    from flask import request, jsonify

    force = request.args.get("force", "0") in ("1", "true", "yes", "on")

    try:
        job = pincabos_start_update_job(force=force)
        return jsonify({
            "ok": True,
            "force": force,
            "unit": job.get("unit"),
            "cmd": job.get("cmd"),
            "message": "Forcer la MAJ System lancé via systemd-run" if force else "Update normal lancé via systemd-run"
        })
    except Exception as e:
        return jsonify({
            "ok": False,
            "force": force,
            "error": str(e)
        }), 500


@app.route("/pincabos-update/check", methods=["GET"])
def pincabos_update_check_form():
    import json
    import pathlib
    import urllib.request
    from flask import Response

    cfg_path = pathlib.Path("/opt/pincabos/config/pincabos-update.json")
    latest_url = "https://update.pincabos.cc/updates/latest.json"

    try:
        if cfg_path.exists():
            cfg = json.loads(cfg_path.read_text(errors="replace"))
            latest_url = cfg.get("latest_json_url", latest_url)
    except Exception:
        pass

    try:
        req = urllib.request.Request(latest_url, headers={"User-Agent": "PinCabOS-Updater/1.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            latest = json.loads(r.read().decode("utf-8", "replace"))

        data = {
            "online": True,
            "latest_url": latest_url,
            "latest": latest
        }
    except Exception as e:
        data = {
            "online": False,
            "latest_url": latest_url,
            "error": str(e)
        }

    html = "<!doctype html><html><body style='background:#080012;color:white;font-family:Arial;padding:30px;'>"
    html += "<h1>Vérification update PinCabOS</h1>"
    html += "<pre style='white-space:pre-wrap;background:#000;padding:15px;border:1px solid #ffb000;border-radius:12px;'>"
    html += json.dumps(data, indent=2, ensure_ascii=False)
    html += "</pre>"
    html += "<p><a style='color:#ffb000;font-size:20px;' href='/pincabos-update'>⬅ Retour mise à jour PinCabOS</a></p>"
    html += "</body></html>"

    return Response(html, mimetype="text/html")


@app.route("/pincabos-update/start-normal", methods=["POST"])
def pincabos_update_start_normal_form():
    from flask import redirect
    pincabos_start_update_job(force=False)
    return redirect("/pincabos-update")


@app.route("/pincabos-update/start-force", methods=["POST"])
def pincabos_update_start_force_form():
    from flask import redirect
    pincabos_start_update_job(force=True)
    return redirect("/pincabos-update")


@app.route("/pcos-update-api/reboot", methods=["POST"])
def pcos_update_clean_reboot():
    import os
    import subprocess
    import time
    from flask import jsonify

    unit = "pincabos-reboot-" + str(int(time.time()))

    cmd = [
        "/usr/bin/systemd-run",
        "--unit", unit,
        "--collect",
        "/bin/bash",
        "-lc",
        "sleep 1; /usr/bin/systemctl reboot"
    ]

    if os.geteuid() != 0:
        cmd = ["/usr/bin/sudo", "-n"] + cmd

    try:
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return jsonify({"ok": True, "unit": unit, "message": "Redémarrage demandé"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/pcos-update-api/reboot", methods=["POST"])
def pcos_update_api_reboot():
    import os
    import subprocess
    import time
    import json
    import pathlib
    import datetime
    from flask import jsonify

    status_path = pathlib.Path("/opt/pincabos/logs/updates/pincabos-update-status.json")

    try:
        data = {}
        if status_path.exists():
            data = json.loads(status_path.read_text(errors="replace"))

        events = data.get("events", [])
        events.append(f"[{datetime.datetime.now().isoformat(timespec='seconds')}] Redémarrage - reboot demandé depuis WebApp")

        data.update({
            "ok": True,
            "running": True,
            "state": "rebooting",
            "percent": 100,
            "step": "Redémarrage",
            "message": "Redémarrage demandé depuis la WebApp...",
            "updated_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "events": events[-100:]
        })

        status_path.parent.mkdir(parents=True, exist_ok=True)
        status_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    except Exception:
        pass

    unit = "pincabos-reboot-" + str(int(time.time()))
    cmd = [
        "/usr/bin/systemd-run",
        "--unit", unit,
        "--collect",
        "/bin/bash",
        "-lc",
        "sleep 2; /usr/bin/systemctl reboot"
    ]

    if os.geteuid() != 0:
        cmd = ["/usr/bin/sudo", "-n"] + cmd

    try:
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return jsonify({"ok": True, "unit": unit, "message": "Redémarrage demandé"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=False)
