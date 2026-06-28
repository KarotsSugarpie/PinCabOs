# PinCabOs-File created by Karots Sugarpie
import urllib.error
import urllib.request
import sqlite3
import tempfile
import zipfile
import mimetypes
import urllib.parse
from flask import send_file, request, redirect, session
from screen import screen_bp
import shutil
import uuid
import shlex
from werkzeug.utils import secure_filename
from dashboard_plus import render_dashboard
from flask import Flask, redirect, url_for, jsonify, request
from pathlib import Path
from tools import register_tools_routes

# === PINCABOS MODULAR ROUTES START ===
import pincabos_webapp_audio as pco_audio_routes
import pincabos_webapp_inputs as pco_inputs_routes
import pincabos_webapp_firstrun as pco_firstrun_routes
import pincabos_webapp_updates as pco_updates_routes
import pincabos_webapp_dev_admin as pco_dev_admin_routes
import pincabos_webapp_exports as pco_exports_routes
# === PINCABOS MODULAR ROUTES END ===

# === PINCABOS WEBAPP CORE CLEAN IMPORT START ===
from pincabos_webapp_core import (
    PCO_PATHS,
    PCO_SERVICES,
    pco_path,
    pco_script,
    pco_sudo_script_cmd,
    pco_systemctl_cmd,
    pco_service,
    pco_service_status,
    pco_vpinfe_service_name,
    pco_frontend_compat_service_name,
    pco_build_update_commands,
    pco_build_full_update_command as pco_core_build_full_update_command,
    pco_path_text,
    pco_script_text,
    pco_vpx_kill_pattern,
    pco_vpx_version_command,
    pco_vpinfe_version_command,
    pco_launch_webapp_screen_command,
    pco_smb_mount_helper_command,
    pincabos_vpx_executable_path,
    pincabos_vpx_tables_dir,
    pincabos_vpx_ini_path,
    pincabos_vpinfe_ini_path,
    pincabos_vpinfe_config_ini_path,
    PINCABOS_VPX_EXECUTABLE,
    PINCABOS_VPX_TABLES_DIR,
    PINCABOS_VPX_INI,
    PINCABOS_VPINFE_ROOT,
    PINCABOS_VPINFE_CURRENT,
    PINCABOS_VPINFE_INI,
    PINCABOS_VPINFE_CONFIG_INI,
    PINCABOS_VPINFE_TEMPLATE_INI,
    PINCABOS_VPINFE_BIN,
)
# === PINCABOS WEBAPP CORE CLEAN IMPORT END ===
# === PINCABOS WEBAPP ADMIN MODULE IMPORT START ===
from pincabos_webapp_admin import (
    pco_admin_cmd_for_script,
    pco_admin_cmd_for_systemctl,
    pco_admin_shell_join,
    pco_admin_run_capture,
    pco_admin_now_stamp,
    pco_admin_tail_text,
    pco_admin_existing_scripts,
    pco_admin_iframe_body,
)
# === PINCABOS WEBAPP ADMIN MODULE IMPORT END ===

# === PINCABOS OFFICIAL VPX PATHS START ===
# Stage2 clean:
# Les chemins VPX/VPinball sont centralises dans pincabos_webapp_core.py.
# VPX officiel: pco_path('vpx_dir')
# Wrapper officiel: pco_path('vpx_wrapper')
# Tables officielles: /home/pinball/Tables
PINNED_VPX_EXECUTABLE = PINCABOS_VPX_EXECUTABLE
PINNED_VPX_TABLES_DIR = PINCABOS_VPX_TABLES_DIR
PINNED_VPX_INI = PINCABOS_VPX_INI
# === PINCABOS OFFICIAL VPX PATHS END ===

# === PINCABOS OFFICIAL VPINFE PATHS START ===
# Stage2 clean:
# Les chemins VPinFE sont centralises dans pincabos_webapp_core.py.
# VPinFE current: pco_path('vpinfe_current')
# Runtime ini: chemin runtime officiel résolu depuis version.json / manifest PinCabOS
# Config ini: /home/pinball/.config/vpinfe/vpinfe.ini
# Template ini: /opt/pincabos/essentials/VPinFEfiles/vpinfe.ini
# === PINCABOS OFFICIAL VPINFE PATHS END ===


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

def pincabos_webapp_secret_key():
    """Load a persistent session secret without falling back to a public value."""
    configured = os.environ.get("PINCABOS_SECRET_KEY", "").strip()
    if configured:
        if len(configured) < 32:
            raise RuntimeError("PINCABOS_SECRET_KEY doit contenir au moins 32 caractères.")
        return configured

    secret_path = Path("/opt/pincabos/config/webapp-secret.key")
    try:
        if secret_path.is_file():
            saved = secret_path.read_text(encoding="utf-8").strip()
            if len(saved) >= 32:
                return saved
            raise RuntimeError(f"Secret WebApp invalide: {secret_path}")

        import secrets
        secret_path.parent.mkdir(parents=True, exist_ok=True)
        generated = secrets.token_urlsafe(48)
        try:
            fd = os.open(str(secret_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            saved = secret_path.read_text(encoding="utf-8").strip()
            if len(saved) >= 32:
                return saved
            raise RuntimeError(f"Secret WebApp invalide: {secret_path}")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(generated + "\n")
        try:
            os.chmod(secret_path, 0o600)
        except OSError:
            pass
        return generated
    except OSError as exc:
        raise RuntimeError("Impossible de charger ou créer le secret de session PinCabOS.") from exc


app = Flask(__name__)
app.register_blueprint(screen_bp)
app.secret_key = pincabos_webapp_secret_key()
app.config['MAX_CONTENT_LENGTH'] = 8 * 1024 * 1024 * 1024

BASE = Path("/opt/pincabos")
LOG_DIR = BASE / "logs" / "updates"
JOB_DIR = LOG_DIR / "jobs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
JOB_DIR.mkdir(parents=True, exist_ok=True)

# === PINCABOS CLEAN UPDATE COMMANDS START ===
UPDATE_COMMANDS = pco_build_update_commands()

def pincabos_build_full_update_command():
    return pco_core_build_full_update_command()

UPDATE_COMMANDS["all"] = pincabos_build_full_update_command()
# === PINCABOS CLEAN UPDATE COMMANDS END ===


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
    return pco_service_status(name)

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

    payload = {
        "has_job": True,
        "status": status,
        "target": job.get("target", ""),
        "progress": progress,
        "message": message,
        "log": log_text,
        "log_name": log_file.name if log_file.exists() else "log en attente"
    }
    return pincabos_update_fix_stale_progress_payload(payload)


def pincabos_version():
    version_file = Path("/opt/pincabos/config/version.json")
    default = {
        "name": "PinCabOs",
        "version": "Development",
        "build": "dev",
        "author": "Karots Sugarpie",
        "update_channel": "SugarPiesNetwork",
        "update_base_url": "https://pincabos.cc/updates",
        "latest_json_url": ""
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
      border-radius: var(--pco-appearance-card-radius, 18px);
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
      color: var(--pco-appearance-accent, #ffb000);
      font-size: 20px;
      font-weight: bold;
      text-shadow: 0 0 15px rgba(255,122,0,0.75);
      white-space: normal;
      line-height: 1.25;
    }}
    .brand-subtitle {{
      color: var(--pco-appearance-muted-text, #d8b8ff);
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
      background: var(--pco-appearance-button-bg, #ff7a00);
      color: var(--pco-appearance-button-text, #160020);
      padding: 10px 15px;
      border-radius: var(--pco-appearance-button-radius, 10px);
      text-decoration: none;
      font-weight: bold;
      margin: 5px;
      border: none;
      cursor: pointer;
    }}
    .secondary {{
      background: var(--pco-appearance-secondary-bg, #5f2a91) !important;
      color: var(--pco-appearance-secondary-text, white) !important;
      border: 1px solid var(--pco-appearance-accent2, #ff7a00) !important;
    }}
    .nav a.active {{
      background: var(--pco-appearance-nav-active-bg, #ff7a00) !important;
      color: var(--pco-appearance-nav-active-text, #160020) !important;
      border: 1px solid var(--pco-appearance-accent, #ffb000) !important;
      box-shadow: 0 0 18px rgba(255,122,0,0.8);
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
      gap: 20px;
    }}
    .card {{
      background: var(--pco-appearance-card-bg, rgba(29, 11, 46, 0.76));
      border: 1px solid var(--pco-appearance-card-border, #ff7a00);
      border-radius: var(--pco-appearance-card-radius, 18px);
      padding: 22px;
      box-shadow: var(--pco-appearance-card-shadow, 0 0 25px rgba(255, 122, 0, 0.25));
    }}
    .card h2 {{
      margin-top: 0;
      color: var(--pco-appearance-accent, #ffb000);
    }}
    .ok {{ color: #00ff99; font-weight: bold; }}
    .bad {{ color: #ff5555; font-weight: bold; }}
    .warn {{ color: var(--pco-appearance-accent, #ffb000); font-weight: bold; }}
    code {{
      background: #000;
      color: var(--pco-appearance-accent, #ffb000);
      padding: 4px 8px;
      border-radius: 6px;
      display: inline-block;
      margin: 2px 0;
    }}
    pre {{
      white-space: pre-wrap;
      background: var(--pco-appearance-input-bg, #050007);
      color: var(--pco-appearance-input-text, #eee);
      padding: 15px;
      border-radius: 12px;
      border: 1px solid var(--pco-appearance-purple, #5f2a91);
      height: 520px;
      overflow-y: scroll;
      font-size: 13px;
    }}
    .progress-wrap {{
      background: var(--pco-appearance-input-bg, #050007);
      border: 1px solid var(--pco-appearance-card-border, #ff7a00);
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
      color: var(--pco-appearance-accent, #ffb000);
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
      padding: 6px;
      border-radius: 8px;
      border: 1px solid var(--pco-appearance-card-border, #ff7a00);
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
      border-radius: var(--pco-appearance-card-radius, 18px);
      background: rgba(12, 0, 22, 0.58);
      border: 1px solid rgba(255, 122, 0, 0.25);
      box-shadow: 0 0 22px rgba(95, 42, 145, 0.22);
    }}

    .nav-tools-clean {{
      padding: 10px;
      border-radius: var(--pco-appearance-card-radius, 18px);
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
      color: var(--pco-appearance-accent, #ffb000);
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
      color: var(--pco-appearance-accent, #ffb000);
      font-weight: 800;
      font-size: 13px;
      white-space: nowrap;
      text-shadow: 0 0 10px rgba(255,122,0,0.45);
    }}

    .top-language-widget select {{
      padding: 7px 10px;
      border-radius: var(--pco-appearance-button-radius, 10px);
      border: 1px solid var(--pco-appearance-card-border, #ff7a00);
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
      color: var(--pco-appearance-accent, #ffb000);
      font-weight: 800;
      margin-bottom: 8px;
    }}

    .import-progress-track {{
      height: 18px;
      background: #160020;
      border: 1px solid var(--pco-appearance-purple, #5f2a91);
      border-radius: 999px;
      overflow: hidden;
    }}

    .import-progress-bar {{
      height: 100%;
      width: 0%;
      background: var(--pco-appearance-button-bg, #ff7a00);
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
<link rel="stylesheet" href="/static/pincabos-appearance-vars.css?v=appearance">
<link rel="icon" type="image/png" href="/static/branding/favicon.png?v=branding">
</head>
<body>

<div class="top-language-widget">
  <div id="google_translate_element"></div>
  <span>Langue :</span>
  <select id="pincabos_language_select" onchange="setPinCabOsLanguage(this.value)">
              <option value="fr">Français</option>
              <option value="en">English</option>
              <option value="es">Español</option>
              <option value="it">Italiano</option>
              <option value="de">Deutsch</option>
              <option value="nl">Nederlands</option>
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
    <span class="pco-menu-tools">
      <button type="button" id="pco-menu-pin-btn" class="pco-menu-tool-btn pco-menu-pin-btn" title="Épingler le menu" aria-label="Épingler le menu" onclick="return window.pcoMenuTogglePin(event);">📌</button>
      <button type="button" id="pco-menu-close-btn" class="pco-menu-tool-btn pco-menu-close-btn" title="Fermer la page" aria-label="Fermer la page" onclick="return window.pcoMenuClosePage(event);">X</button>
    </span>
    <link rel="stylesheet" href="/static/pincabos-menu-tools.css?v=20260615131347">
    <script src="/static/pincabos-menu-tools.js?v=20260615131347"></script>
 </div>

  <div class="nav-row nav-tools-clean">
    <span class="nav-vpinfe-vps-group" style="display:inline-flex;align-items:center;gap:8px;flex:0 0 auto;">
      <a href="http://{ip}:8001" target="_blank" class="secondary nav-action">Ouvrir VPinFE</a>
      <a href="https://virtualpinballspreadsheet.github.io/" target="_blank" rel="noopener noreferrer" class="secondary nav-action">Ouvrir VPS</a>
      <!-- PinCabOS topbar tools copy buttons -->
      <a class="button pco-topbar-tool-copy" href="/tools/commander">PinCab Explorer</a>
      <a class="button pco-topbar-tool-copy" href="/console">PinCab Console</a>
      <!-- /PinCabOS topbar tools copy buttons -->
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
      <p>Checklist : accès WebApp réseau, GPU/pilotes, puis détection et assignation des écrans.</p>
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
# Moved to modular route file by PinCabOS refactor (original lines 1123-1123).
# Tools hub routes are registered after the main page() layout helper is available.
register_tools_routes(app, page)

# Moved to modular route file by PinCabOS refactor (original lines 1127-1133).

# Moved to modular route file by PinCabOS refactor (original lines 1135-1136).

# Moved to modular route file by PinCabOS refactor (original lines 1138-1145).

# Moved to modular route file by PinCabOS refactor (original lines 1147-1178).

# Moved to modular route file by PinCabOS refactor (original lines 1180-1188).

# Moved to modular route file by PinCabOS refactor (original lines 1190-1207).

# Moved to modular route file by PinCabOS refactor (original lines 1209-1225).

# Moved to modular route file by PinCabOS refactor (original lines 1227-1256).

# Moved to modular route file by PinCabOS refactor (original lines 1258-1288).


# ---------------------------------------------------------------------------
# PinCabOS update stale progress guard
# Created by Karots Sugarpie
#
# Dependencies/requisites:
# - /usr/bin/pgrep
# - /opt/pincabos/logs/updates
#
# Purpose:
# - If the WebApp was restarted during update, old progress JSON can stay
#   at running/90%. This guard makes the UI recover to 100% when no update
#   runner is active anymore.
# ---------------------------------------------------------------------------
def pincabos_update_fix_stale_progress_payload(payload):
    try:
        if not isinstance(payload, dict):
            return payload

        percent = int(payload.get("percent", payload.get("progress", 0)) or 0)
        running = bool(payload.get("running") or payload.get("active") or payload.get("state") == "running")

        if running and percent >= 90:
            import subprocess
            active = subprocess.run(
                ["/usr/bin/pgrep", "-f", "pincabos-update-engine-runner.sh"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=2,
            ).returncode == 0

            if not active:
                payload.update({
                    "ok": True,
                    "state": "done",
                    "running": False,
                    "active": False,
                    "done": True,
                    "finished": True,
                    "success": True,
                    "percent": 100,
                    "progress": 100,
                    "step": "GO",
                    "stage": "GO",
                    "title": "Terminé",
                    "message": "Mise à jour WebApp terminée",
                    "events": ["GO", "Mise à jour WebApp terminée"],
                })
    except Exception:
        pass

    return payload


# Moved to modular route file by PinCabOS refactor (original lines 1344-1753).


# Moved to modular route file by PinCabOS refactor (original lines 1756-1770).


# Moved to modular route file by PinCabOS refactor (original lines 1773-1832).


# Moved to modular route file by PinCabOS refactor (original lines 1835-1854).


# Moved to modular route file by PinCabOS refactor (original lines 1857-1878).
# === FIRST RUN WIZARD - PINCABOS END ===

# === PINCABOS FIRST RUN AUTO REDIRECT START ===
def pincabos_firstrun_is_complete():
    try:
        cfg = firstrun_load_cfg()
        keys = firstrun_required_keys()

        if cfg.get("gpu") and not firstrun_gpu_update_state().get("ready"):
            return False

        if cfg.get("screens") and not cfg.get("gpu"):
            return False

        return all(bool(cfg.get(k)) for k in keys)
    except Exception:
        return False


@app.before_request
def pincabos_first_run_auto_redirect():
    try:
        path = request.path or "/"

        allowed_prefixes = (
            "/first-run",
            "/static",
            "/api",
            "/admin",
            "/dev",
            "/service-control",
            "/pcos-update-api",
            "/pincabos-update",
        )

        if path != "/":
            return None

        if any(path.startswith(p) for p in allowed_prefixes):
            return None

        if not pincabos_firstrun_is_complete():
            return redirect("/first-run")

        return None
    except Exception:
        return None
# === PINCABOS FIRST RUN AUTO REDIRECT END ===






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
<pre>{esc(pco_path_text('vpx_dir'))}/
├── current/
├── backups/
└── downloads/

~/.vpinball/
└── VPinballX.ini</pre>

<h3>VPinFE</h3>
<pre>{esc(pco_path_text('vpinfe_root'))}/
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





# Moved to modular route file by PinCabOS refactor (original lines 2196-2270).


# Moved to modular route file by PinCabOS refactor (original lines 2273-2279).



# Moved to modular route file by PinCabOS refactor (original lines 2283-2368).


# Moved to modular route file by PinCabOS refactor (original lines 2371-2377).



# Moved to modular route file by PinCabOS refactor (original lines 2381-2448).


# Moved to modular route file by PinCabOS refactor (original lines 2451-2458).


# Moved to modular route file by PinCabOS refactor (original lines 2461-2605).


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
  padding:8px 11px;
  background:rgba(255,176,0,.06);
  border-radius:8px;
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
    <li>VPX migré vers <strong>VPinballX-BGFX</strong>.</li>
    <li>Compatibilité GL supprimée : PinCabOS utilise le launcher BGFX seulement.</li>
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
    <li>VPX Linux installé dans <code>{esc(pco_path_text("vpx_dir"))}</code>.</li>
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
    <li>Mise à jour PinCabOS WebApp pour WebApp, outils, services et configurations.</li>
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
    <tr><td>VPX</td><td><code>{esc(pco_path_text("vpx_dir"))}</code></td></tr>
    <tr><td>VPX Executable Path</td><td><code>{esc(pco_path_text('vpx_wrapper'))}</code></td></tr>
    <tr><td>VPinFE</td><td><code>{esc(pco_path_text("vpinfe_current"))}</code></td></tr>
    <tr><td>Tables Directory</td><td><code>/home/pinball/Tables</code></td></tr>
    <tr><td>VPX Ini Path</td><td><code>/home/pinball/.vpinball/VPinballX.ini</code></td></tr>
    <tr><td>PupVideos</td><td><code>/home/pinball/.vpinball/pupvideos</code></td></tr>
    <tr><td>Imports</td><td><code>/home/pinball/Downloads</code></td></tr>
    <tr><td>Exports</td><td><code>/home/pinball/Exports</code></td></tr>
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
      padding:8px 11px;
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


@app.route("/")
def dashboard():
    return render_dashboard(page, esc, get_ip, service_status, pincabos_version)


def gpu_info_text():
    return run_cmd(["/usr/bin/sudo", str(pco_script("detect_gpu"))], timeout=15)


def screens_layout_text():
    try:
        f = Path("/opt/pincabos/config/screens/screens.json")
        if f.exists():
            return f.read_text(errors="replace")
    except Exception as e:
        return f"Erreur lecture screens.json: {e}"
    return "Aucune auto-détection écran sauvegardée pour le moment."


def dof_file_status():
    cfg = Path("/home/pinball/.vpinball/directoutputconfig")

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
            "journalctl -u pincabos-vpinfe.service -n 260 --no-pager | "
            "grep -iE 'dof|directoutput|global config|cabinet|ini|framework|device|pinscape|pacled|pacdrive|dudes|ftdi|pinone' || true"
        ],
        timeout=8
    )
    return log[-20000:] if log else "Aucun log DOF trouvé."



# PinCabOS GPU per-screen wallpapers
# Created by Karots Sugarpie
# Dependencies:
# - python3: /usr/bin/python3
# - optional wallpaper tools: feh, xwallpaper, nitrogen, gsettings
# Paths:
# - /opt/pincabos/media/wallpapers
# - /opt/pincabos/config/screens/wallpapers.json

PINCABOS_WALLPAPER_DIR = Path("/opt/pincabos/media/wallpapers")
PINCABOS_WALLPAPER_CFG = Path("/opt/pincabos/config/screens/wallpapers.json")

def pco_wallpaper_role_label(role):
    return {
        "playfield": "Playfield",
        "backglass": "Backglass",
        "fulldmd": "FullDMD",
    }.get(str(role or ""), str(role or ""))

def pco_wallpaper_role_icon(role):
    return {
        "playfield": "🎮",
        "backglass": "🖼️",
        "fulldmd": "📺",
    }.get(str(role or ""), "🖼️")

def pco_wallpaper_load_cfg():
    try:
        if PINCABOS_WALLPAPER_CFG.exists():
            data = json.loads(PINCABOS_WALLPAPER_CFG.read_text(errors="replace") or "{}")
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {"roles": {}}

def pco_wallpaper_save_cfg(data):
    PINCABOS_WALLPAPER_CFG.parent.mkdir(parents=True, exist_ok=True)
    data["updated_by"] = "PinCabOS WebApp GPU wallpapers"
    data["updated_at"] = datetime.now().isoformat(timespec="seconds")
    PINCABOS_WALLPAPER_CFG.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")

def pco_wallpaper_safe_ext(filename):
    ext = Path(str(filename or "")).suffix.lower()
    if ext not in [".png", ".jpg", ".jpeg", ".webp", ".bmp"]:
        return ""
    return ext

def pco_wallpaper_public_url(path):
    try:
        path = Path(path).resolve()
        base = PINCABOS_WALLPAPER_DIR.resolve()
        if path == base or base not in path.parents:
            return ""
        return "/gpu/wallpaper/file/" + urllib.parse.quote(path.name)
    except Exception:
        return ""

@app.route("/gpu/wallpaper/file/<path:filename>")
def gpu_wallpaper_file(filename):
    from flask import send_from_directory
    safe = Path(filename).name
    return send_from_directory(str(PINCABOS_WALLPAPER_DIR), safe)

def pco_wallpaper_apply_image(path):
    import shutil
    import subprocess
    import os

    img = str(Path(path).resolve())
    if not Path(img).exists():
        return False, "NOGO: image absente: " + img

    env = os.environ.copy()
    env.setdefault("DISPLAY", ":0")
    env.setdefault("XAUTHORITY", "/home/pinball/.Xauthority")
    env.setdefault("XDG_RUNTIME_DIR", "/run/user/1000")

    attempts = []

    feh = shutil.which("feh")
    if feh:
        attempts.append([feh, "--bg-fill", img])

    xwallpaper = shutil.which("xwallpaper")
    if xwallpaper:
        attempts.append([xwallpaper, "--zoom", img])

    nitrogen = shutil.which("nitrogen")
    if nitrogen:
        attempts.append([nitrogen, "--set-zoom-fill", img])

    gsettings = shutil.which("gsettings")
    if gsettings:
        attempts.append([gsettings, "set", "org.gnome.desktop.background", "picture-uri", "file://" + img])

    if not attempts:
        return False, "WARN: image sauvegardée, mais aucun outil wallpaper trouvé (feh/xwallpaper/nitrogen/gsettings absent)."

    last = ""
    for cmd in attempts:
        try:
            r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=8, env=env)
            out = (r.stdout or "").strip()
            last = "+ " + " ".join(cmd) + "\n" + out
            if r.returncode == 0:
                return True, "GO: wallpaper appliqué avec " + Path(cmd[0]).name + "\n" + last
        except Exception as e:
            last = "+ " + " ".join(cmd) + "\nErreur: " + str(e)

    return False, "WARN: image sauvegardée, mais application wallpaper non confirmée.\n" + last

def pco_gpu_wallpaper_section_html():
    cfg = pco_wallpaper_load_cfg()
    roles_cfg = cfg.get("roles", {}) if isinstance(cfg.get("roles", {}), dict) else {}

    try:
        screen_roles = pincabos_load_screen_roles()
    except Exception:
        screen_roles = {}

    cards = ""
    for role in ["playfield", "backglass", "fulldmd"]:
        label = pco_wallpaper_role_label(role)
        icon = pco_wallpaper_role_icon(role)
        data = roles_cfg.get(role, {}) if isinstance(roles_cfg.get(role, {}), dict) else {}
        img_path = data.get("path", "")
        img_url = pco_wallpaper_public_url(img_path) if img_path else ""
        status = data.get("last_status", "Aucun wallpaper choisi.")
        output = ""
        try:
            output = str((screen_roles.get(role) or {}).get("output") or "")
        except Exception:
            output = ""

        preview = (
            '<img class="pco-wallpaper-preview-img" src="' + esc(img_url) + '?v=' + esc(str(time.time())) + '" alt="' + esc(label) + '">'
            if img_url else
            '<div class="pco-wallpaper-empty">Aucun aperçu</div>'
        )

        cards += f"""
        <div class="card pco-wallpaper-card">
          <h3>{icon} Wallpaper {esc(label)}</h3>
          <p><small>Écran assigné : <code>{esc(output or "non assigné")}</code></small></p>
          <div class="pco-wallpaper-preview">{preview}</div>

          <form action="/gpu/wallpaper/select" method="post" enctype="multipart/form-data" class="pco-wallpaper-form">
            <input type="hidden" name="role" value="{esc(role)}">
            <label>Image</label>
            <input type="file" name="wallpaper" accept=".png,.jpg,.jpeg,.webp,.bmp,image/*" required>
            <div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:10px;">
              <button type="submit">Parcourir / Sauvegarder</button>
            </div>
          </form>

          <form action="/gpu/wallpaper/apply" method="post" class="pco-wallpaper-form">
            <input type="hidden" name="role" value="{esc(role)}">
            <button type="submit" class="secondary">Appliquer {esc(label)}</button>
          </form>

          <p><small>{esc(status)}</small></p>
          <p><small>Fichier : <code>{esc(img_path or "-")}</code></small></p>
        </div>
        """

    return f"""
    <style>
      .pco-wallpaper-grid {{
        display:grid;
        grid-template-columns:repeat(auto-fit,minmax(260px,1fr));
        gap:16px;
      }}
      .pco-wallpaper-card input[type=file] {{
        width:100%;
        box-sizing:border-box;
        margin-top:6px;
      }}
      .pco-wallpaper-preview {{
        min-height:150px;
        border:1px solid rgba(255,176,0,.35);
        border-radius:14px;
        background:rgba(0,0,0,.35);
        display:flex;
        align-items:center;
        justify-content:center;
        overflow:hidden;
        margin:12px 0;
      }}
      .pco-wallpaper-preview-img {{
        width:100%;
        height:180px;
        object-fit:cover;
        display:block;
      }}
      .pco-wallpaper-empty {{
        opacity:.75;
        color:#ffb000;
        font-weight:800;
      }}
      .pco-wallpaper-form {{
        margin:10px 0;
      }}
    </style>

    <div class="card">
      <h2>Wallpapers par écran</h2>
      <p>Choisis une image pour chaque écran. Chaque carte garde son aperçu et son bouton Appliquer.</p>
      <div class="pco-wallpaper-grid">
        {cards}
      </div>
    </div>
    """

@app.route("/gpu/wallpaper/select", methods=["POST"])
def gpu_wallpaper_select():
    role = request.form.get("role", "").strip().lower()
    if role not in ("playfield", "backglass", "fulldmd"):
        return "Rôle wallpaper invalide.", 400

    f = request.files.get("wallpaper")
    if not f or not f.filename:
        return redirect(url_for("gpu_page", gpu_action="wallpaper", gpu_cls="bad", gpu_title="Aucune image sélectionnée."), code=303)

    ext = pco_wallpaper_safe_ext(f.filename)
    if not ext:
        return redirect(url_for("gpu_page", gpu_action="wallpaper", gpu_cls="bad", gpu_title="Format image non supporté."), code=303)

    PINCABOS_WALLPAPER_DIR.mkdir(parents=True, exist_ok=True)
    dst = PINCABOS_WALLPAPER_DIR / (role + ext)

    # Nettoyer anciennes extensions du même rôle.
    for old in PINCABOS_WALLPAPER_DIR.glob(role + ".*"):
        try:
            old.unlink()
        except Exception:
            pass

    f.save(str(dst))
    try:
        dst.chmod(0o664)
    except Exception:
        pass

    cfg = pco_wallpaper_load_cfg()
    roles = cfg.get("roles", {}) if isinstance(cfg.get("roles", {}), dict) else {}
    roles[role] = {
        "path": str(dst),
        "original_name": f.filename,
        "last_status": "Image sauvegardée. Clique Appliquer pour l’envoyer au bureau.",
        "selected_at": datetime.now().isoformat(timespec="seconds"),
    }
    cfg["roles"] = roles
    pco_wallpaper_save_cfg(cfg)

    return redirect(url_for("gpu_page", gpu_action="wallpaper", gpu_cls="ok", gpu_title="Wallpaper " + pco_wallpaper_role_label(role) + " sauvegardé."), code=303)

@app.route("/gpu/wallpaper/apply", methods=["POST"])
def gpu_wallpaper_apply():
    role = request.form.get("role", "").strip().lower()
    if role not in ("playfield", "backglass", "fulldmd"):
        return "Rôle wallpaper invalide.", 400

    cfg = pco_wallpaper_load_cfg()
    roles = cfg.get("roles", {}) if isinstance(cfg.get("roles", {}), dict) else {}
    item = roles.get(role, {}) if isinstance(roles.get(role, {}), dict) else {}
    path = item.get("path", "")

    ok, msg = pco_wallpaper_apply_image(path)

    item["last_status"] = msg
    item["applied_at"] = datetime.now().isoformat(timespec="seconds")
    roles[role] = item
    cfg["roles"] = roles
    pco_wallpaper_save_cfg(cfg)

    cls = "ok" if ok else "warn"
    return redirect(url_for("gpu_page", gpu_action="wallpaper", gpu_cls=cls, gpu_title=msg.splitlines()[0]), code=303)


@app.route("/gpu")
def gpu_page():
    from pathlib import Path

    gpu_text = gpu_info_text()
    screens, raw = pincabos_parse_xrandr_screens()
    roles = pincabos_load_screen_roles()

    gpu_opts = {
        "cabinet_mode": True,
        "playfield_orientation": "landscape",
        "playfield_rotation": "0",
    }

    try:
        import json
        cfg_opts = Path("/opt/pincabos/config/screens/screens.json")
        if cfg_opts.exists():
            data_opts = json.loads(cfg_opts.read_text(errors="replace"))
            gpu_opts["cabinet_mode"] = bool(data_opts.get("cabinet_mode", True))
            gpu_opts["playfield_orientation"] = str(data_opts.get("playfield_orientation", "landscape")).lower()
            gpu_opts["playfield_rotation"] = str(data_opts.get("playfield_rotation", "0"))
    except Exception:
        pass

    if gpu_opts["playfield_orientation"] not in ("landscape", "portrait"):
        gpu_opts["playfield_orientation"] = "landscape"
    if gpu_opts["playfield_rotation"] not in ("0", "90", "180", "270"):
        gpu_opts["playfield_rotation"] = "0"

    cabmode_checked = "checked" if gpu_opts.get("cabinet_mode", True) else ""
    orientation_landscape_selected = "selected" if gpu_opts.get("playfield_orientation") == "landscape" else ""
    orientation_portrait_selected = "selected" if gpu_opts.get("playfield_orientation") == "portrait" else ""
    rotation_0_selected = "selected" if gpu_opts.get("playfield_rotation") == "0" else ""
    rotation_90_selected = "selected" if gpu_opts.get("playfield_rotation") == "90" else ""
    rotation_180_selected = "selected" if gpu_opts.get("playfield_rotation") == "180" else ""
    rotation_270_selected = "selected" if gpu_opts.get("playfield_rotation") == "270" else ""

    def pco_gpu_saved_mode(role_name):
        try:
            cfg_modes = Path("/opt/pincabos/config/screens/screens.json")
            if cfg_modes.exists():
                data_modes = json.loads(cfg_modes.read_text(errors="replace") or "{}")
                role_data = (data_modes.get("roles") or {}).get(role_name) or {}
                return str(role_data.get("mode") or ""), str(role_data.get("rate") or "")
        except Exception:
            pass
        return "", ""

    def pco_gpu_screen_name_from_selected(selected):
        selected = str(selected or "")
        for item in screens:
            if str(item.get("id")) == selected:
                return str(item.get("name") or item.get("output") or "")
            if str(item.get("name") or item.get("output") or "") == selected:
                return str(item.get("name") or item.get("output") or "")
        return ""

    def pco_gpu_modes_from_raw(selected):
        wanted = pco_gpu_screen_name_from_selected(selected)
        if not wanted:
            return []

        modes = []
        active = False

        try:
            for line in str(raw or "").splitlines():
                m = re.match(r"^([A-Za-z0-9_.:-]+)\s+connected\b.*$", line)
                if m:
                    active = (m.group(1) == wanted)
                    continue

                if not active:
                    continue

                mm = re.match(r"^\s+(\d+x\d+)\s+(.+)$", line)
                if not mm:
                    continue

                mode = mm.group(1)
                tail = mm.group(2)

                rates = []
                for r in re.findall(r"(\d+(?:\.\d+)?)\*?\+?", tail):
                    if r not in rates:
                        rates.append(r)

                if not rates:
                    rates = [""]

                modes.append({"mode": mode, "rates": rates})
        except Exception:
            return []

        return modes

    def pco_gpu_mode_select(role_name, selected):
        selected_mode, selected_rate = pco_gpu_saved_mode(role_name)
        modes = pco_gpu_modes_from_raw(selected)

        opts = ['<option value="">-- Auto / inchangé --</option>']

        for item in modes:
            mode = str(item.get("mode") or "")
            rates = item.get("rates") or [""]

            if not mode:
                continue

            for rate in rates:
                rate = str(rate or "").replace("*", "").replace("+", "")
                value = mode + (("@" + rate) if rate else "")
                label = mode + ((" " + rate + "Hz") if rate else "")
                sel = "selected" if mode == selected_mode and (not selected_rate or selected_rate == rate) else ""
                opts.append('<option value="' + esc(value) + '" ' + sel + '>' + esc(label) + '</option>')

        return (
            '<select name="' + esc(role_name) + '_mode" style="width:100%; padding:8px; margin:6px 0;">'
            + "\\n".join(opts) +
            '</select>'
        )


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
        cfg = Path("/opt/pincabos/config/screens/screens.json")
        if cfg.exists():
            screens_json = cfg.read_text(errors="replace")
    except Exception as e:
        screens_json = f"Erreur lecture screens.json: {e}"

    gpu_status_rows = ""
    gpu_status_rows += (
        '<tr><td><strong>xrandr / X11</strong></td><td>'
        + ('<span class="ok">OK — ' + esc(str(len(screens))) + ' écran(s) détecté(s)</span>' if screens else '<span class="bad">Aucun écran détecté</span>')
        + '</td></tr>'
    )
    gpu_status_rows += (
        '<tr><td><strong>screens.json</strong></td><td>'
        + ('<span class="ok">présent / lisible</span>' if screens_json and screens_json.strip() not in ("{}", "") and not screens_json.startswith("Erreur") else '<span class="warn">vide ou absent</span>')
        + '</td></tr>'
    )
    role_count = len([v for v in roles.values() if str(v).strip()])
    gpu_status_rows += (
        '<tr><td><strong>Rôles assignés</strong></td><td>'
        + ('<span class="ok">' + esc(str(role_count)) + ' rôle(s) sauvegardé(s)</span>' if role_count else '<span class="warn">aucun rôle sauvegardé</span>')
        + '</td></tr>'
    )

    gpu_quick_tools = """
      <div style="display:flex; gap:10px; flex-wrap:wrap; margin-top:12px;">
        <form action="/auto-screens" method="post" style="display:inline;" onsubmit="return confirm('Lancer auto-détection écrans et mettre à jour screens.json ?');">
          <button class="button" type="submit">Auto-détecter écrans</button>
        </form>
        <a class="button secondary" href="/gpu">Rafraîchir Écrans / GPU</a>
      </div>
    """

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

    wallpaper_html = pco_gpu_wallpaper_section_html()

    body = f"""
<div class="card" style="margin-top:0;">
  <h2>Écrans détectés</h2>

  <style>
    .pincabos-screen-table-wrap {{{{
      width: 100%;
      overflow-x: auto;
      margin-top: 10px;
    }}}}

    .pincabos-screen-table {{{{
      width: 100%;
      border-collapse: collapse;
      table-layout: fixed;
      font-size: 0.95rem;
    }}}}

    .pincabos-screen-table th,
    .pincabos-screen-table td {{{{
      padding: 10px 12px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.12);
      vertical-align: middle;
      white-space: nowrap;
    }}}}

    .pincabos-screen-table th {{{{
      color: var(--pco-appearance-accent, #ffb000);
      text-align: left;
      font-weight: 700;
    }}}}

    .pincabos-screen-table th:nth-child(1),
    .pincabos-screen-table td:nth-child(1) {{{{
      width: 70px;
      text-align: center;
    }}}}

    .pincabos-screen-table th:nth-child(2),
    .pincabos-screen-table td:nth-child(2) {{{{
      width: 34%;
      text-align: left;
    }}}}

    .pincabos-screen-table th:nth-child(3),
    .pincabos-screen-table td:nth-child(3),
    .pincabos-screen-table th:nth-child(4),
    .pincabos-screen-table td:nth-child(4),
    .pincabos-screen-table th:nth-child(5),
    .pincabos-screen-table td:nth-child(5) {{{{
      text-align: center;
    }}}}

    .pincabos-screen-table code {{{{
      display: inline-block;
      min-width: 28px;
      text-align: center;
    }}}}
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

  <div class="card" style="margin-top:20px;">
    <h2>Statut rapide Écrans / GPU</h2>
    <div class="pincabos-screen-table-wrap">
      <table class="pincabos-screen-table">
        {gpu_status_rows}
      </table>
    </div>
    {gpu_quick_tools}
  </div>

<div class="grid">
  <div class="card pco-gpu-driver-card">
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
    <style>
      .pco-gpu-driver-card {{
        display: flex;
        flex-direction: column;
        min-height: 980px;
      }}
      .pco-gpu-driver-log {{
        flex: 1 1 auto;
        min-height: 760px;
        max-height: none;
        overflow: auto;
        resize: vertical;
        white-space: pre;
      }}
    </style>
<pre class="pco-gpu-driver-log" style="height:75vh !important; min-height:760px !important; max-height:none !important; overflow:auto !important; resize:vertical !important; white-space:pre !important;">{esc(gpu_text)}</pre>
  </div>

  <div class="card">
    <style>
      .pco-gpu-assign-grid {{
        display: grid;
        grid-template-columns: minmax(260px, 1.4fr) minmax(220px, 1fr);
        gap: 10px 16px;
        align-items: end;
        margin: 12px 0 14px 0;
      }}
      .pco-gpu-assign-grid label {{
        display: block;
        font-weight: 800;
        margin: 0 0 6px 0;
      }}
      .pco-gpu-assign-grid select {{
        width: 100%;
      }}
      @media (max-width: 760px) {{
        .pco-gpu-assign-grid {{
          grid-template-columns: 1fr;
        }}
      }}
    </style>
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
      <div class="pco-gpu-assign-grid">
        <div>
          <label>Playfield / Primary</label>
          {role_select("playfield", roles.get("playfield", ""))}
        </div>
        <div>
          <label>Résolution</label>
          {pco_gpu_mode_select("playfield", roles.get("playfield", ""))}
        </div>
      </div>

      <div class="pco-gpu-assign-grid">
        <div>
          <label>Backglass / Secondary</label>
          {role_select("backglass", roles.get("backglass", ""))}
        </div>
        <div>
          <label>Résolution</label>
          {pco_gpu_mode_select("backglass", roles.get("backglass", ""))}
        </div>
      </div>

      <div class="pco-gpu-assign-grid">
        <div>
          <label>FullDMD / Tertiary</label>
          {role_select("fulldmd", roles.get("fulldmd", ""))}
        </div>
        <div>
          <label>Résolution</label>
          {pco_gpu_mode_select("fulldmd", roles.get("fulldmd", ""))}
        </div>
      </div>

      <div style="margin-top:14px; padding:12px; border:1px solid rgba(255,255,255,.12); border-radius:12px;">
        <h3 style="margin-top:0;">Options PinCab</h3>

        <label style="display:flex; align-items:center; gap:8px; margin:8px 0;">
          <input type="checkbox" name="cabinet_mode" value="1" {cabmode_checked}>
          <strong>Cabinet Mode</strong>
        </label>

        <label>Playfield Orientation</label><br>
        <select name="playfield_orientation" style="width:95%; padding:8px; margin:6px 0;">
          <option value="landscape" {orientation_landscape_selected}>Landscape</option>
          <option value="portrait" {orientation_portrait_selected}>Portrait</option>
        </select><br>

        <label>Playfield Rotation</label><br>
        <select name="playfield_rotation" style="width:95%; padding:8px; margin:6px 0;">
          <option value="0" {rotation_0_selected}>0</option>
          <option value="90" {rotation_90_selected}>90</option>
          <option value="180" {rotation_180_selected}>180</option>
          <option value="270" {rotation_270_selected}>270</option>
        </select>
      </div>

      <button class="button" type="submit" style="margin-top:12px;">Appliquer assignation écrans</button>
    </form>

    <div style="margin-top:12px; display:flex; gap:10px; flex-wrap:wrap;">
      {vpinfe_buttons}
    </div>

    <div class="pco-wallpaper-inside-assignation">
      {wallpaper_html}
    </div>

  </div>
</div>



<div class="grid" style="margin-top:20px;">
  <div class="card">
    <h2>Configuration écran PinCabOS actuelle</h2>
    <p>Source : <code>/opt/pincabos/config/screens/screens.json</code></p>
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
    Lit /opt/pincabos/config/screens/screens.json et retourne les ids déjà assignés.
    """
    import json
    from pathlib import Path

    cfg = Path("/opt/pincabos/config/screens/screens.json")
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


def pincabos_write_manual_screen_roles(playfield_id, backglass_id, fulldmd_id, cabinet_mode=True, playfield_orientation="landscape", playfield_rotation="0"):
    """
    Sauvegarde les rôles écran dans screens.json et met à jour VPinFE [Displays].
    """
    import json
    import subprocess
    from pathlib import Path

    screens, raw = pincabos_parse_xrandr_screens()

    cabinet_mode = bool(cabinet_mode)

    playfield_orientation = str(playfield_orientation or "landscape").strip().lower()
    if playfield_orientation not in ("landscape", "portrait"):
        playfield_orientation = "landscape"

    playfield_rotation = str(playfield_rotation or "0").strip()
    if playfield_rotation not in ("0", "90", "180", "270"):
        playfield_rotation = "0"

    by_id = {str(s["id"]): s for s in screens}

    if playfield_id not in by_id:
        raise ValueError("Playfield invalide ou non sélectionné.")

    playfield = by_id.get(playfield_id)
    backglass = by_id.get(backglass_id) if backglass_id in by_id else None
    fulldmd = by_id.get(fulldmd_id) if fulldmd_id in by_id else None

    layout = {
        "mode": "manual",
        "cabinet_mode": cabinet_mode,
        "playfield_orientation": playfield_orientation,
        "playfield_rotation": playfield_rotation,
        "playfield": playfield,
        "backglass": backglass,
        "fulldmd": fulldmd,
        "all_screens": screens,
        "xrandr_raw": raw,
    }

    cfg = Path("/opt/pincabos/config/screens/screens.json")
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(json.dumps(layout, indent=2, ensure_ascii=False), encoding="utf-8")

    # Mettre à jour VPinFE [Displays] sans toucher au reste.
    ini = pincabos_vpx_ini_path()
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

    lines = set_ini_key(lines, "Displays", "cabmode", "true" if cabinet_mode else "false")
    lines = set_ini_key(lines, "Displays", "tableorientation", playfield_orientation)
    lines = set_ini_key(lines, "Displays", "tablerotation", playfield_rotation)

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



def pco_gpu_save_resolution_modes_to_screens_json():
    try:
        cfg = Path("/opt/pincabos/config/screens/screens.json")
        data = {}
        if cfg.exists():
            data = json.loads(cfg.read_text(errors="replace") or "{}")
        if not isinstance(data, dict):
            data = {}

        roles_data = data.get("roles")
        if not isinstance(roles_data, dict):
            roles_data = {}
            data["roles"] = roles_data

        for role in ("playfield", "backglass", "fulldmd"):
            value = (request.form.get(role + "_mode") or "").strip()
            if role not in roles_data or not isinstance(roles_data.get(role), dict):
                roles_data[role] = {}

            if value:
                if "@" in value:
                    mode, rate = value.split("@", 1)
                else:
                    mode, rate = value, ""
                roles_data[role]["mode"] = mode
                roles_data[role]["rate"] = rate
            else:
                roles_data[role].pop("mode", None)
                roles_data[role].pop("rate", None)

        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        return "GO: résolutions sauvegardées dans screens.json"
    except Exception as e:
        return "WARN: impossible de sauvegarder les résolutions: " + str(e)



def pco_gpu_apply_system_resolution_modes():
    helper = Path("/opt/pincabos/tools/pincabos-screen-xrandr.sh")
    if not helper.exists():
        return "WARN: helper système absent: " + str(helper)
    try:
        return run_cmd(["/usr/bin/sudo", "-n", str(helper), "apply"], timeout=30)
    except Exception as e:
        return "WARN: application système échouée: " + str(e)


@app.route("/gpu/apply-screens", methods=["POST"])
def gpu_screens_apply():
    res_modes_out = pco_gpu_save_resolution_modes_to_screens_json()
    system_modes_out = pco_gpu_apply_system_resolution_modes()
    playfield = request.form.get("playfield", "").strip()
    backglass = request.form.get("backglass", "").strip()
    fulldmd = request.form.get("fulldmd", "").strip()
    cabinet_mode = request.form.get("cabinet_mode", "") == "1"
    playfield_orientation = request.form.get("playfield_orientation", "landscape").strip().lower()
    playfield_rotation = request.form.get("playfield_rotation", "0").strip()

    try:
        layout = pincabos_write_manual_screen_roles(playfield, backglass, fulldmd, cabinet_mode, playfield_orientation, playfield_rotation)
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

    cfg = Path("/opt/pincabos/config/screens/screens.json")
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

    cabinet_mode = bool(data.get("cabinet_mode", True))

    playfield_orientation = str(data.get("playfield_orientation", "landscape")).strip().lower()
    if playfield_orientation not in ("landscape", "portrait"):
        playfield_orientation = "landscape"

    playfield_rotation = str(data.get("playfield_rotation", "0")).strip()
    if playfield_rotation not in ("0", "90", "180", "270"):
        playfield_rotation = "0"

    ini = pincabos_vpinfe_ini_path()
    ini.parent.mkdir(parents=True, exist_ok=True)

    backup = ""
    if ini.exists():
        backup = str(ini) + ".backup-screens-" + datetime.now().strftime("%Y%m%d-%H%M%S")
        shutil.copy2(ini, backup)

    lines = ini.read_text(errors="replace").splitlines() if ini.exists() else []

    lines = pincabos_gpu_ini_set_key_local(lines, "Displays", "cabmode", "true" if cabinet_mode else "false")
    lines = pincabos_gpu_ini_set_key_local(lines, "Displays", "tablescreenid", str(playfield.get("id", "")))
    lines = pincabos_gpu_ini_set_key_local(lines, "Displays", "tableorientation", playfield_orientation)
    lines = pincabos_gpu_ini_set_key_local(lines, "Displays", "tablerotation", playfield_rotation)

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
    lines = pincabos_gpu_ini_set_key_local(lines, "PinCabOs.Screens", "cabinet_mode", "true" if cabinet_mode else "false")
    lines = pincabos_gpu_ini_set_key_local(lines, "PinCabOs.Screens", "playfield_orientation", playfield_orientation)
    lines = pincabos_gpu_ini_set_key_local(lines, "PinCabOs.Screens", "playfield_rotation", playfield_rotation)
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
cabmode = {"true" if cabinet_mode else "false"}
tablescreenid = {playfield.get("id", "")}
bgscreenid = {backglass.get("id", "") if backglass else ""}
dmdscreenid = {fulldmd.get("id", "") if fulldmd else ""}
tableorientation = {playfield_orientation}
tablerotation = {playfield_rotation}
"""


def pincabos_gpu_apply_config_to_vpx():
    from pathlib import Path
    from datetime import datetime
    import shutil
    import subprocess

    data, playfield, backglass, fulldmd = pincabos_gpu_read_screens_config_for_apply()

    cabinet_mode = bool(data.get("cabinet_mode", True))

    playfield_orientation = str(data.get("playfield_orientation", "landscape")).strip().lower()
    if playfield_orientation not in ("landscape", "portrait"):
        playfield_orientation = "landscape"

    playfield_rotation = str(data.get("playfield_rotation", "0")).strip()
    if playfield_rotation not in ("0", "90", "180", "270"):
        playfield_rotation = "0"

    ini = pincabos_vpx_ini_path()
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
        ["/usr/bin/sudo", "/bin/systemctl", "restart", "pincabos-vpinfe.service"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return redirect(url_for("gpu_page"))

@app.route("/auto-screens", methods=["POST"])
def auto_screens():
    subprocess.Popen(
        ["/usr/bin/sudo", str(pco_script("auto_detect_screens"))],
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
    script = str(pco_script("install_dof_component"))

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

    # Après installation, PinCabOS prépare aussi pco_path('dof_tools')/<famille>.
    # Si la famille est prête côté dossier + udev, on considère le support prêt.
    if kind in ["serial", "dudes-esp", "ftdi", "arduino", "serial-usb"]:
        return udev and serial_ok

    return udev and libusb_ok


def dof_configurator_status(kind):
    base = Path(str(pco_path("dof_tools"))) / kind
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
      Dossier outils : <code>{esc(pco_path_text('dof_tools'))}</code><br>
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
    Dossier outils : <code>{esc(pco_path_text('dof_tools'))}</code><br>
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
    Path("/home/pinball/.vpinball/directoutputconfig"),
    Path("/opt/pincabos/config/dof"),
    Path("/home/pinball/.vpinball/directoutputconfig"),
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
        helper = Path("/usr/local/sbin/pincabos-dof-online-api-import")
        if not helper.exists():
            body = """
<div class="card">
  <h2>Import DOF via API indisponible</h2>
  <p class="warn">
    Le helper API PinCabOS est absent :<br>
    <code>/usr/local/sbin/pincabos-dof-online-api-import</code>
  </p>
  <p>
    Pour importer le <strong>cabinet JSON</strong>, utilise plutôt DOF Commander :
  </p>
  <p>
    <a class="button" href="/dof/commander">Importer cabinet JSON dans DOF Commander</a>
    <a class="button secondary" href="/dof">Retour DOF</a>
  </p>
  <p>
    Pour importer les fichiers DOF Config Tool, utilise l’import ZIP manuel.
  </p>
</div>
"""
            return page("DOF", body)

        cmd = [str(helper), api_key, force]
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

    target_dir = Path("/home/pinball/.vpinball/directoutputconfig")
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
      Dossier cible : <code>/home/pinball/.vpinball/directoutputconfig</code>
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

    script = str(pco_script("dof_commander_test_output"))
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
    Outil diagnostic : <code>{esc(pco_script_text('dof_driver_status'))}</code>
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
    <p>Service VPinFE : <code>{esc(service_status("pincabos-vpinfe.service"))}</code></p>
    <p>Dossier config DOF :</p>
    <p><code>{esc(cfg_path)}</code></p>
    <p>Détection : {summary}</p>
    <p>

    <!-- PINCABOS_DOF_STATIC_ASSETS_START -->
    <link rel="stylesheet" href="/static/pincabos-dof-pro.css?v=20260528">
    <script defer src="/static/pincabos-dof-pro.js?v=20260528"></script>
    <!-- PINCABOS_DOF_STATIC_ASSETS_END -->

      <a class="button secondary" href="/dof/commander">Ouvrir DOF Commander</a>
      <a class="button" href="/dof/commander">Importer cabinet JSON</a>
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
        Destination : <code>/home/pinball/.vpinball/directoutputconfig</code>
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
        "pincabos-vpinfe.service",
        "pincabos-webapp.service",
        "pincabos-console.service",
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
    """
    service_map = {
        # VPinFE / frontend
        "frontend": "pincabos-vpinfe.service",
        "vpinfe": "pincabos-vpinfe.service",
        "front": "pincabos-vpinfe.service",

        # Web manager
        "web": "pincabos-webapp.service",
        "web-manager": "pincabos-webapp.service",
        "manager": "pincabos-webapp.service",

        # Console Commander
        "console": "pincabos-console.service",
        "webconsole": "pincabos-console.service",
        "web-console": "pincabos-console.service",

        # Console web

        # Auto timezone
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



# === PINCABOS DASHBOARD VPX PROCESS CONTROL START ===
@app.route("/process-control/vpx/<action>", methods=["POST"])
def process_control_vpx(action):
    """
    Contrôle prudent du processus VPX lancé par VPinFE.
    VPX n'est pas un service systemd direct, donc:
      - stop / kill : termine VPinballX seulement
      - restart     : termine VPinballX puis redémarre VPinFE
      - start       : redémarre VPinFE, car VPX part normalement via VPinFE/table
    """
    action = str(action or "").strip().lower()

    allowed = {"start", "stop", "restart", "kill", "play"}
    if action not in allowed:
        return f"Action VPX non autorisée: {esc(action)}", 400

    try:
        if action in {"stop", "kill"}:
            subprocess.Popen(
                ["/usr/bin/pkill", "-TERM", "-f", pco_vpx_kill_pattern()],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        elif action in {"restart", "start", "play"}:
            subprocess.Popen(
                ["/usr/bin/pkill", "-TERM", "-f", pco_vpx_kill_pattern()],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            subprocess.Popen(
                ["/usr/bin/sudo", "/bin/systemctl", "restart", "pincabos-vpinfe.service"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    except Exception as e:
        return f"Erreur contrôle VPX: {esc(str(e))}", 500

    return redirect(request.referrer or "/")
# === PINCABOS DASHBOARD VPX PROCESS CONTROL END ===





# === PINCABOS VPINFE VERSION HELPERS START ===
def pincabos_vpinfe_local_version():
    """
    Détection locale VPinFE robuste.
    Source officielle PinCabOS:
      /opt/pincabos/apps/frontend/vpinfe/current
    Ne pas utiliser ~/.config/vpinfe comme source de vérité.
    """
    import re
    import subprocess
    from pathlib import Path

    candidates = [
        Path("/opt/pincabos/apps/frontend/vpinfe/current/vpinfe"),
        Path("/opt/pincabos/apps/frontend/vpinfe/current/VPinFE"),
    ]

    for exe in candidates:
        if exe.exists():
            if exe.is_file() and exe.stat().st_mode & 0o111:
                for arg in ("--version", "-version", "version"):
                    try:
                        r = subprocess.run(
                            [str(exe), arg],
                            text=True,
                            capture_output=True,
                            timeout=8,
                            cwd=str(exe.parent),
                            env={
                                "HOME": "/home/pinball",
                                "XDG_CONFIG_HOME": "/home/pinball/.config",
                                "XDG_DATA_HOME": "/home/pinball/.local/share",
                            },
                        )
                        out = ((r.stdout or "") + "\n" + (r.stderr or "")).strip()
                        m = re.search(r"Version:\s*(v?\d+(?:\.\d+)+)", out, re.I)
                        if m:
                            return m.group(1)
                        m = re.search(r"\bv?\d+(?:\.\d+)+\b", out)
                        if m:
                            return m.group(0)
                    except Exception:
                        pass
                return "installée"

    current = Path("/opt/pincabos/apps/frontend/vpinfe/current")
    if current.is_dir():
        for vf in ("VERSION", "version.txt", "package.json"):
            f = current / vf
            if f.is_file():
                try:
                    txt = f.read_text(errors="replace")
                    m = re.search(r"v?\d+(?:\.\d+)+", txt)
                    if m:
                        return m.group(0)
                except Exception:
                    pass
        return "installée"

    return "non détectée"


def pincabos_vpinfe_available_version():
    try:
        import urllib.request
        import json as _json

        with urllib.request.urlopen("https://api.github.com/repos/superhac/vpinfe/releases/latest", timeout=6) as r:
            data = _json.loads(r.read().decode("utf-8", errors="replace"))
            tag = (data.get("tag_name") or "").strip()
            if tag:
                return tag
    except Exception:
        pass

    try:
        r = subprocess.run(
            ["/usr/bin/git", "-C", str(pco_path("vpinfe_root")), "ls-remote", "--tags", "origin"],
            text=True,
            capture_output=True,
            timeout=8
        )
        tags = []
        for line in r.stdout.splitlines():
            if "refs/tags/" in line and "^{}" not in line:
                tags.append(line.rsplit("/", 1)[-1].strip())
        if tags:
            def version_key(v):
                out = []
                for part in v.lstrip("v").split("."):
                    out.append(int(part) if part.isdigit() else part)
                return out
            return sorted(tags, key=version_key)[-1]
    except Exception:
        pass

    return "non détectée"
# === PINCABOS VPINFE VERSION HELPERS END ===


def pincabos_vpinball_local_version():
    """
    Détection locale VPX/VPinball.
    On évite les faux positifs comme 0.115 provenant de libs/aide.
    Chemins officiels PinCabOS:
      /opt/pincabos/bin/vpx.sh
      /opt/pincabos/bin/vpx.sh
    """
    import re
    import subprocess
    from pathlib import Path

    candidates = [
        Path("/opt/pincabos/bin/vpx.sh"),
        Path("/opt/pincabos/apps/vpinball/current/VPinballX-BGFX"),
        Path("/opt/pincabos/bin/vpx.sh"),
    ]

    ignored_versions = {"0.115", "0.14", "0.14.0", "0.1.0", "0.4.1", "0.8.0", "0.9.0"}

    for exe in candidates:
        if exe.exists() and exe.is_file() and exe.stat().st_mode & 0o111:
            for arg in ("-version", "--version"):
                try:
                    r = subprocess.run(
                        [str(exe), arg],
                        text=True,
                        capture_output=True,
                        timeout=8,
                        cwd=str(exe.parent),
                        env={
                            "HOME": "/home/pinball",
                            "XDG_CONFIG_HOME": "/home/pinball/.config",
                            "XDG_DATA_HOME": "/home/pinball/.local/share",
                        },
                    )
                    out = ((r.stdout or "") + "\n" + (r.stderr or "")).strip()

                    # On accepte surtout les versions VPX connues 10.x.
                    m = re.search(r"\bv?10\.\d+(?:\.\d+){0,2}\b", out)
                    if m:
                        return m.group(0)

                    # Fallback général, mais ignore les versions de libs.
                    for m in re.finditer(r"\bv?\d+(?:\.\d+){1,3}\b", out):
                        val = m.group(0)
                        if val not in ignored_versions and not val.startswith("0."):
                            return val
                except Exception:
                    pass

            # Binaire présent, mais version exacte non fiable.
            if "BGFX" in exe.name.upper():
                return "VPX BGFX installé"
            return "VPX installé"

    if Path("/opt/pincabos/apps/vpinball").is_dir():
        return "VPX installé"

    return "non détectée"


def pincabos_vpinball_available_version():
    """
    Version disponible VPX/VPinball.
    Pour l'instant on tente GitHub officiel, sinon fallback local.
    """
    import json as _json
    import urllib.request
    import re
    import subprocess

    urls = [
        "https://api.github.com/repos/vpinball/vpinball/releases/latest",
        "https://api.github.com/repos/vpinball/vpinball/actions/artifacts",
    ]

    for url in urls:
        try:
            with urllib.request.urlopen(url, timeout=6) as r:
                data = _json.loads(r.read().decode("utf-8", errors="replace"))

            tag = (data.get("tag_name") or data.get("name") or "").strip()
            m = re.search(r"\bv?\d+(?:\.\d+){1,3}\b", tag)
            if m:
                return m.group(0)

            artifacts = data.get("artifacts") or []
            for a in artifacts:
                name = str(a.get("name") or "")
                if "linux" in name.lower() or "bgfx" in name.lower() or "vpinball" in name.lower():
                    m = re.search(r"\bv?\d+(?:\.\d+){1,3}\b", name)
                    if m:
                        return m.group(0)
        except Exception:
            pass

    # Fallback: ne pas afficher non détectée si VPX local est présent.
    local = pincabos_vpinball_local_version()
    if local != "non détectée":
        return local

    return "non détectée"




def pincabos_gpu_local_version():
    """
    État GPU/pilote local.
    Ne lance aucune installation.
    """
    import subprocess
    import re

    try:
        r = subprocess.run(
            ["/usr/bin/nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
            text=True,
            capture_output=True,
            timeout=4,
        )
        out = (r.stdout or "").strip().splitlines()
        if out and out[0].strip():
            return "NVIDIA " + out[0].strip()
    except Exception:
        pass

    try:
        r = subprocess.run(
            ["/sbin/modinfo", "nvidia"],
            text=True,
            capture_output=True,
            timeout=4,
        )
        out = (r.stdout or "") + "\\n" + (r.stderr or "")
        m = re.search(r"^version:\\s*(.+)$", out, re.M)
        if m:
            return "NVIDIA " + m.group(1).strip()
    except Exception:
        pass

    try:
        r = subprocess.run(
            ["/usr/bin/lspci"],
            text=True,
            capture_output=True,
            timeout=4,
        )
        out = r.stdout or ""
        lines = [
            x for x in out.splitlines()
            if "VGA" in x or "3D controller" in x or "Display controller" in x
        ]
        if lines:
            line = lines[0]
            up = line.upper()
            if "NVIDIA" in up:
                return "NVIDIA détectée"
            if "AMD" in up or "ATI" in up:
                return "AMD/Mesa détecté"
            if "INTEL" in up:
                return "Intel/Mesa détecté"
            if "RED HAT" in up or "VIRTIO" in up:
                return "Virtio/QEMU détecté"
            return "GPU détecté"
    except Exception:
        pass

    return "non détecté"


def pincabos_gpu_available_version():
    """
    Pilote GPU recommandé disponible.
    Ne lance aucune installation.
    """
    import subprocess
    import re

    try:
        r = subprocess.run(
            ["/usr/bin/ubuntu-drivers", "devices"],
            text=True,
            capture_output=True,
            timeout=8,
        )
        out = (r.stdout or "") + "\\n" + (r.stderr or "")
        m = re.search(r"(nvidia-driver-\\d+[^ \\n]*)\\s+.*recommended", out, re.I)
        if m:
            return m.group(1).strip()
        m = re.search(r"(nvidia-driver-\\d+[^ \\n]*)", out, re.I)
        if m:
            return m.group(1).strip()
    except Exception:
        pass

    local = pincabos_gpu_local_version()
    if local != "non détecté":
        return "à jour / auto"

    return "non détecté"


def pincabos_ubuntu_local_version():
    """
    Version Ubuntu locale.
    """
    from pathlib import Path

    osr = Path("/etc/os-release")
    if osr.is_file():
        data = {}
        for line in osr.read_text(errors="replace").splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                data[k] = v.strip().strip('"')
        return data.get("PRETTY_NAME") or data.get("VERSION") or data.get("VERSION_ID") or "Ubuntu détecté"

    return "non détectée"


def pincabos_ubuntu_available_version():
    """
    Résumé des paquets Ubuntu disponibles.
    Ne fait pas apt update; lit seulement l'état apt actuel.
    """
    import subprocess

    try:
        r = subprocess.run(
            ["/usr/bin/apt", "list", "--upgradable"],
            text=True,
            capture_output=True,
            timeout=8,
        )
        lines = []
        for line in (r.stdout or "").splitlines():
            line = line.strip()
            if not line or line.startswith("Listing"):
                continue
            if "/" in line and "[" in line:
                lines.append(line)

        if len(lines) == 0:
            return "à jour"
        if len(lines) == 1:
            return "1 paquet"
        return str(len(lines)) + " paquets"
    except Exception:
        pass

    return "vérifier"

# Moved to modular route file by PinCabOS refactor (original lines 7246-7515).


# Moved to modular route file by PinCabOS refactor (original lines 7518-7520).

# Moved to modular route file by PinCabOS refactor (original lines 7522-7627).


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


def pincabos_set_ini_key_plain(lines, section, key, value):
    """
    Modifie/ajoute une clé INI sans ajouter de commentaire PinCabOS.
    Utilisé pour les INI officiels VPinFE/VPX afin de ne pas les polluer.
    """
    section_header = f"[{section}]"
    key_l = str(key).lower()
    value = str(value)

    out = []
    in_section = False
    found_section = False
    written = False

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("[") and stripped.endswith("]"):
            if in_section and not written:
                out.append(f"{key} = {value}")
                written = True
            in_section = (stripped.lower() == section_header.lower())
            if in_section:
                found_section = True
            out.append(line)
            continue

        if in_section:
            # Supprimer les anciens commentaires auto PinCabOS juste avant/près des clés gérées.
            if stripped.startswith(";") and "par PinCabOS fonction(" in stripped:
                continue

            if "=" in line:
                k = line.split("=", 1)[0].strip().lower()
                if k == key_l:
                    out.append(f"{key} = {value}")
                    written = True
                    continue

        out.append(line)

    if found_section and in_section and not written:
        out.append(f"{key} = {value}")
        written = True

    if not found_section:
        if out and out[-1].strip():
            out.append("")
        out.append(section_header)
        out.append(f"{key} = {value}")

    return out


def save_fulldmd_to_configs(data):
    function_name = "FullDMD Save"

    screen_id = str(data.get("screen_id", "0"))
    x = int(data.get("x", 0))
    y = int(data.get("y", 0))
    w = int(data.get("width", 0))
    h = int(data.get("height", 0))

    # Format attendu par les clés legacy VPinFE/VPinball.
    geometry = f"{x},{y},{w},{h}"
    geometry_x11 = f"{w}x{h}+{x}+{y}"

    Path("/opt/pincabos/config").mkdir(parents=True, exist_ok=True)

    # JSON PinCabOS seulement. Les détails avancés restent ici, pas dans les INI officiels.
    fulldmd_json = Path("/opt/pincabos/config/fulldmd-calibration.json")
    pincabos_backup_config_file(fulldmd_json, function_name)
    pincabos_write_json_with_meta(fulldmd_json, {
        "screen_id": screen_id,
        "x": x,
        "y": y,
        "width": w,
        "height": h,
        "geometry": geometry,
        "geometry_x11": geometry_x11,
        "note": "PinCabOs FullDMD visible area calibration"
    }, function_name)

    # VPinFE officiel: modifier uniquement [Displays].
    vpinfe_ini = PINCABOS_VPINFE_CONFIG_INI
    pincabos_backup_config_file(vpinfe_ini, function_name)

    vpinfe_lines = pincabos_read_ini_lines(vpinfe_ini)
    vpinfe_lines = pincabos_set_ini_key_plain(vpinfe_lines, "Displays", "dmdscreenid", screen_id)
    vpinfe_lines = pincabos_set_ini_key_plain(vpinfe_lines, "Displays", "dmdwindowoverride", geometry)
    vpinfe_lines = pincabos_set_ini_key_plain(vpinfe_lines, "Displays", "fulldmdscreenid", screen_id)
    vpinfe_lines = pincabos_set_ini_key_plain(vpinfe_lines, "Displays", "fulldmdx", str(x))
    vpinfe_lines = pincabos_set_ini_key_plain(vpinfe_lines, "Displays", "fulldmdy", str(y))
    vpinfe_lines = pincabos_set_ini_key_plain(vpinfe_lines, "Displays", "fulldmdwidth", str(w))
    vpinfe_lines = pincabos_set_ini_key_plain(vpinfe_lines, "Displays", "fulldmdheight", str(h))
    pincabos_write_ini_lines(vpinfe_ini, vpinfe_lines)

    # VPinballX.ini: modifier uniquement [Displays].
    vpx_ini = pincabos_vpx_ini_path()
    pincabos_backup_config_file(vpx_ini, function_name)

    vpx_lines = pincabos_read_ini_lines(vpx_ini)
    vpx_lines = pincabos_set_ini_key_plain(vpx_lines, "Displays", "dmdscreenid", screen_id)
    vpx_lines = pincabos_set_ini_key_plain(vpx_lines, "Displays", "dmdwindowoverride", geometry)
    vpx_lines = pincabos_set_ini_key_plain(vpx_lines, "Displays", "fulldmdscreenid", screen_id)
    vpx_lines = pincabos_set_ini_key_plain(vpx_lines, "Displays", "fulldmdx", str(x))
    vpx_lines = pincabos_set_ini_key_plain(vpx_lines, "Displays", "fulldmdy", str(y))
    vpx_lines = pincabos_set_ini_key_plain(vpx_lines, "Displays", "fulldmdwidth", str(w))
    vpx_lines = pincabos_set_ini_key_plain(vpx_lines, "Displays", "fulldmdheight", str(h))
    pincabos_write_ini_lines(vpx_ini, vpx_lines)

    subprocess.run(["/bin/chown", "-R", "pinball:pinball", "/opt/pincabos/config"], timeout=5)
    subprocess.run(["/bin/chown", "pinball:pinball", str(vpinfe_ini)], timeout=5)
    subprocess.run(["/bin/chown", "pinball:pinball", str(vpx_ini)], timeout=5)




# === PINCABOS FULLDMD/DMD PAGE HELPERS START ===
def load_dmd_calibration():
    cfg = Path("/opt/pincabos/config/dmd-calibration.json")
    default = {"screen_id": 2, "x": 80, "y": 40, "width": 512, "height": 128, "geometry": "512x128+80+40"}
    try:
        if cfg.exists():
            data = json.loads(cfg.read_text(errors="replace"))
            for k, v in default.items():
                data.setdefault(k, v)
            return data
    except Exception:
        pass
    return default

def pincabos_ini_section_summary(path_str):
    path = Path(path_str)
    wanted = {"PinCabOs.FullDMD", "PinCabOs.DMD", "PinCabOs.Screens", "Displays"}
    if not path.exists():
        return f"ABSENT: {path}"
    lines = path.read_text(errors="replace").splitlines()
    out = []
    keep = False
    for line in lines:
        s = line.strip()
        if s.startswith("[") and s.endswith("]"):
            sec = s[1:-1]
            keep = sec in wanted
            if keep:
                if out:
                    out.append("")
                out.append(line)
            continue
        if keep:
            low = s.lower()
            if "dmd" in low or "screen" in low or "width" in low or "height" in low or "geometry" in low or low.startswith(("x", "y", "enabled")):
                out.append(line)
    return "\n".join(out).strip() or "Aucune valeur DMD/FullDMD trouvée."
# === PINCABOS FULLDMD/DMD PAGE HELPERS END ===

@app.route("/fulldmd")
def fulldmd_page():
    cal = load_fulldmd_calibration()
    vpx_ini_summary = pincabos_ini_section_summary("/home/pinball/.vpinball/VPinballX.ini")
    vpinfe_ini_summary = pincabos_ini_section_summary("/home/pinball/.config/vpinfe/vpinfe.ini")
    dmd_cal = load_dmd_calibration()
    vpx_ini_summary = pincabos_ini_section_summary("/home/pinball/.vpinball/VPinballX.ini")
    vpinfe_ini_summary = pincabos_ini_section_summary("/home/pinball/.config/vpinfe/vpinfe.ini")

    screens_json = "{}"
    try:
        f = Path("/opt/pincabos/config/screens/screens.json")
        if f.exists():
            screens_json = f.read_text(errors="replace")
    except Exception:
        pass

    body = """
<div class="grid fulldmd-calibration-grid" style="display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:20px;align-items:start;">
  <div class="card">
    <h2>Calibration FullDMD</h2>
    <p>Déplace et étire le rectangle pour représenter la zone visible du FullDMD.</p>
    <p>Config sauvegardée dans :</p>
    <p><code>/opt/pincabos/config/fulldmd-calibration.json</code></p>
    <p><code>Chemin VPX officiel</code></p>
    <p><code>/home/pinball/.vpinball/VPinballX.ini</code></p>

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
    <h2>Calibration DMD global</h2>
    <p>Déplace et étire le rectangle pour représenter la position globale des DMD.</p>
    <p>Config sauvegardée dans :</p>
    <p><code>/opt/pincabos/config/dmd-calibration.json</code></p>
    <p><code>/home/pinball/.config/vpinfe/vpinfe.ini</code></p>
    <p><code>/home/pinball/.vpinball/VPinballX.ini</code></p>

    <label class="fulldmd-section-label">Écran DMD / Screen ID</label>

    <div class="fulldmd-config-layout">
      <div class="fulldmd-fields-row">
        <div class="fulldmd-field">
          <label for="dmd_screen_id">Écran / Screen ID</label>
          <input id="dmd_screen_id" type="text" value="__DMD_SCREEN_ID__">
        </div>

        <div class="fulldmd-field">
          <label for="dmd_x">X</label>
          <input id="dmd_x" type="number" value="__DMD_X__">
        </div>

        <div class="fulldmd-field">
          <label for="dmd_y">Y</label>
          <input id="dmd_y" type="number" value="__DMD_Y__">
        </div>

        <div class="fulldmd-field">
          <label for="dmd_w">Largeur</label>
          <input id="dmd_w" type="number" value="__DMD_W__">
        </div>

        <div class="fulldmd-field">
          <label for="dmd_h">Hauteur</label>
          <input id="dmd_h" type="number" value="__DMD_H__">
        </div>
      </div>

      <div class="fulldmd-actions-column">
        __DMD_TOGGLE_BUTTON__
<form action="/dmd/apply" method="post">
          <button class="button secondary fulldmd-action-btn" type="submit">Appliquer DMD</button>
        </form>

        <a class="button secondary fulldmd-action-btn" href="/fulldmd">Rafraîchir</a>

        <button class="button fulldmd-action-btn" onclick="saveDmdCal()">Sauvegarder DMD</button>
      </div>
    </div>

    <p id="dmd-save-status" class="warn"></p>
  </div>

  <div class="card fulldmd-info-card" style="height:720px;display:flex;flex-direction:column;min-width:0;padding:18px;box-sizing:border-box;overflow:hidden;">
    <h2 style="margin:0 0 12px 0;flex:0 0 auto;">Écrans détectés</h2>
    <pre style="flex:1 1 auto;height:100%;min-height:0;max-height:none !important;width:100%;box-sizing:border-box;margin:0;overflow:auto;white-space:pre-wrap;word-break:break-word;">__SCREENS_JSON__</pre>
  </div>


  <div class="card fulldmd-info-card" style="height:720px;display:flex;flex-direction:column;min-width:0;padding:18px;box-sizing:border-box;overflow:hidden;">
    <h2 style="margin:0 0 12px 0;flex:0 0 auto;">Valeurs actuelles VPX / VPinFE</h2>

    <h3>VPX officiel</h3>
    <p><code>/home/pinball/.vpinball/VPinballX.ini</code></p>
    <pre style="height:250px;min-height:0;max-height:none !important;width:100%;box-sizing:border-box;margin:0 0 12px 0;overflow:auto;white-space:pre-wrap;word-break:break-word;">__VPX_INI_SUMMARY__</pre>

    <h3>VPinFE officiel</h3>
    <p><code>/home/pinball/.config/vpinfe/vpinfe.ini</code></p>
    <pre style="height:250px;min-height:0;max-height:none !important;width:100%;box-sizing:border-box;margin:0;overflow:auto;white-space:pre-wrap;word-break:break-word;">__VPINFE_INI_SUMMARY__</pre>
  </div>

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

async function saveDmdCal() {
  const payload = {
    screen_id: document.getElementById('dmd_screen_id').value,
    x: parseInt(document.getElementById('dmd_x').value || '0', 10),
    y: parseInt(document.getElementById('dmd_y').value || '0', 10),
    width: parseInt(document.getElementById('dmd_w').value || '0', 10),
    height: parseInt(document.getElementById('dmd_h').value || '0', 10)
  };

  const r = await fetch('/api/dmd/save', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload)
  });

  const data = await r.json();
  document.getElementById('dmd-save-status').textContent =
    data.ok ? 'Calibration DMD sauvegardée et synchronisée.' : ('Erreur DMD: ' + (data.error || 'unknown'));
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
    body = body.replace("__DMD_TOGGLE_BUTTON__", pincabos_dmd_toggle_button())
    body = body.replace("__DMD_SCREEN_ID__", esc(dmd_cal.get("screen_id", "")))
    body = body.replace("__DMD_X__", esc(dmd_cal.get("x", 0)))
    body = body.replace("__DMD_Y__", esc(dmd_cal.get("y", 0)))
    body = body.replace("__DMD_W__", esc(dmd_cal.get("width", 512)))
    body = body.replace("__DMD_H__", esc(dmd_cal.get("height", 128)))
    body = body.replace("__VPX_INI_SUMMARY__", esc(vpx_ini_summary))
    body = body.replace("__VPINFE_INI_SUMMARY__", esc(vpinfe_ini_summary))

    return page("FullDMD", body)


@app.route("/api/fulldmd/status")
def api_fulldmd_status():
    return jsonify({
        "ok": True,
        "log": "Log temps réel FullDMD désactivé.",
        "message": "Log temps réel désactivé."
    })


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
    Important: le fichier /run peut devenir stale.
    Source de vérité: process Chrome avec profil/URL FullDMD.
    """
    import subprocess
    import time

    try:
        out = subprocess.check_output(
            ["/usr/bin/pgrep", "-af", "pincabos_fulldmd_calibrator_screen|pincabos-fulldmd-calibrator|/fulldmd-screen"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        lines = []
        for line in out.splitlines():
            low = line.lower()
            if "grep" in low:
                continue
            if "pincabos_fulldmd_calibrator_screen" in low or "pincabos-fulldmd-calibrator" in low or "/fulldmd-screen" in low:
                lines.append(line)
        if lines:
            try:
                FULLDMD_ACTIVE_STATE.write_text(str(time.time()) + "\n", encoding="utf-8")
                FULLDMD_ACTIVE_STATE.chmod(0o666)
            except Exception:
                pass
            return True
    except Exception:
        pass

    # Si aucun process réel, l'état /run est fantôme.
    try:
        FULLDMD_ACTIVE_STATE.unlink(missing_ok=True)
    except Exception:
        pass

    return False


def pincabos_fulldmd_toggle_button():
    if pincabos_fulldmd_calibrator_running():
        return """
        <form action="/close-fulldmd-calibrator" method="post">
          <button class="button fulldmd-action-btn fulldmd-toggle-active" type="submit"
                  style="background:#ff7a00 !important;color:#160020 !important;border:1px solid #ffb000 !important;box-shadow:0 0 18px rgba(255,122,0,.9),0 0 28px rgba(255,176,0,.45) !important;">
            Fermer Calibration FullDMD
          </button>
        </form>
        """
    return """
        <form action="/launch-fulldmd-calibrator" method="post">
          <button class="button secondary fulldmd-action-btn fulldmd-toggle-inactive" type="submit">
            Ouvrir Calibration FullDMD
          </button>
        </form>
        """




# === PINCABOS DMD CALIBRATOR TOGGLE START ===
def pincabos_dmd_calibrator_running():
    state_file = Path("/run/pincabos-dmd-calibrator.active")

    try:
        result = subprocess.run(
            ["/usr/bin/pgrep", "-af", "pincabos-dmd-calibrator|pincabos_dmd_calibrator|dmd-screen"],
            text=True,
            capture_output=True,
            timeout=3
        )
        process_running = result.returncode == 0 and bool(result.stdout.strip())
    except Exception:
        process_running = False

    return state_file.exists() or process_running

def pincabos_dmd_toggle_button():
    if pincabos_dmd_calibrator_running():
        return """
        <form action="/close-dmd-calibrator" method="post">
          <button class="button fulldmd-action-btn fulldmd-toggle-active" type="submit"
                  style="background:#ff7a00 !important;color:#160020 !important;border:1px solid #ffb000 !important;box-shadow:0 0 18px rgba(255,122,0,.9),0 0 28px rgba(255,176,0,.45) !important;">
            Fermer Calibration DMD
          </button>
        </form>
        """
    return """
        <form action="/launch-dmd-calibrator" method="post">
          <button class="button secondary fulldmd-action-btn fulldmd-toggle-inactive" type="submit">
            Ouvrir Calibration DMD
          </button>
        </form>
        """
# === PINCABOS DMD CALIBRATOR TOGGLE END ===

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
        ["/usr/bin/sudo", str(pco_script("launch_fulldmd_calibrator"))],
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
      border: 1px solid var(--pco-appearance-card-border, #ff7a00);
      border-radius: 14px;
      padding: 12px;
      box-shadow: 0 0 25px rgba(255,122,0,0.55);
      text-align: center;
      z-index: 230;
      cursor: default;
    }

    #title {
      font-weight: bold;
      color: var(--pco-appearance-accent, #ffb000);
      margin-bottom: 6px;
      text-shadow: 0 0 12px rgba(255,122,0,0.7);
    }

    #hint {
      font-size: 12px;
      color: var(--pco-appearance-muted-text, #d8b8ff);
      margin-bottom: 8px;
    }

    input {
      width: 70px;
      padding: 5px;
      margin: 3px;
      background: #111;
      color: #fff;
      border: 1px solid var(--pco-appearance-card-border, #ff7a00);
      border-radius: 6px;
      text-align: center;
    }

    button {
      background: var(--pco-appearance-button-bg, #ff7a00);
      color: var(--pco-appearance-button-text, #160020);
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
      border: 1px solid var(--pco-appearance-card-border, #ff7a00);
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

<div class="card">
  <h2>Calibration DMD global</h2>
  <p>Cette section calibre la position globale des DMD. Elle écrit les valeurs dans :</p>
  <p><code>/opt/pincabos/config/dmd-calibration.json</code></p>
  <p><code>/home/pinball/.config/vpinfe/vpinfe.ini</code></p>
  <p><code>/home/pinball/.vpinball/VPinballX.ini</code></p>
  <p>Fenêtre plus petite que FullDMD, par défaut sur écran ID <strong>2</strong>.</p>
  <form action="/launch-dmd-calibrator" method="post" style="display:inline-block">
    <button class="button" type="submit">Ouvrir calibration DMD</button>
  </form>
  <form action="/close-dmd-calibrator" method="post" style="display:inline-block;margin-left:8px">
    <button class="button secondary" type="submit">Fermer DMD</button>
  </form>
</div>


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


# === PINCABOS DMD CALIBRATION ROUTES START ===

@app.route("/dmd/apply", methods=["POST"])
def pincabos_apply_dmd_calibration():
    try:
        subprocess.run(["/usr/bin/sudo", str(pco_script("sync_dmd_calibrations"))], timeout=8, check=False)
    except Exception:
        pass
    return redirect("/fulldmd")

@app.route("/dmd-screen")
def pincabos_dmd_screen():
    body = """
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>PinCabOS DMD Calibration</title>
<style>
html,body{margin:0;width:100%;height:100%;overflow:hidden;background:#050505;color:#ffb000;font-family:Arial,sans-serif;cursor:default;}
#stage{position:relative;width:100vw;height:100vh;background:
  linear-gradient(90deg,rgba(255,176,0,.10) 1px,transparent 1px),
  linear-gradient(rgba(255,176,0,.10) 1px,transparent 1px);
  background-size:40px 40px;
}
#rect{position:absolute;border:3px solid #ffb000;background:rgba(255,176,0,.18);box-shadow:0 0 18px rgba(255,176,0,.7);box-sizing:border-box;}
#rect:before{content:"DMD";position:absolute;left:8px;top:6px;color:#fff;font-weight:bold;text-shadow:0 0 8px #000;}
#handle{position:absolute;right:-8px;bottom:-8px;width:18px;height:18px;background:#ffb000;border:2px solid #fff;box-sizing:border-box;cursor:nwse-resize;}
#panel{position:absolute;left:12px;top:12px;background:rgba(0,0,0,.72);border:1px solid rgba(255,176,0,.45);padding:10px;border-radius:10px;font-size:13px;z-index:10;}
button{background:#ff7a00;color:#fff;border:1px solid #ffb000;border-radius:8px;padding:7px 10px;margin:3px;cursor:pointer;}
button.secondary{background:#222;}
code{color:#fff;}
</style>
</head>
<body>
<div id="stage">
  <div id="panel">
    <strong>PinCabOS DMD Calibration</strong><br>
    Fenêtre fixe fullscreen sur la surface FullDMD.<br>
    Déplace seulement le carré DMD.<br>
    <code id="info"></code><br>
    <button onclick="save()">Sauvegarder DMD</button>
    <button class="secondary" onclick="centerRect()">Centrer</button>
    <button class="secondary" onclick="fitTop()">Top DMD</button>
    <button class="secondary" onclick="window.close()">Fermer</button>
  </div>
  <div id="rect"><div id="handle"></div></div>
</div>

<script>
const qs = new URLSearchParams(location.search);

function parseNums(name, fallback) {
  const raw = qs.get(name) || "";
  const parts = raw.split(",").map(v => parseInt(v || "0", 10));
  if (parts.length >= fallback.length && parts.every(v => !Number.isNaN(v))) return parts;
  return fallback;
}

const override = parseNums("override", [80,40,512,128]);
const win = parseNums("window", [0,0,window.innerWidth,window.innerHeight]);
const screenId = qs.get("screen_id") || "0";

let x = override[0], y = override[1], w = override[2], h = override[3];

const rect = document.getElementById("rect");
const info = document.getElementById("info");

function clamp() {
  if (w < 64) w = 64;
  if (h < 32) h = 32;
  if (x < 0) x = 0;
  if (y < 0) y = 0;
  if (x + w > window.innerWidth) x = Math.max(0, window.innerWidth - w);
  if (y + h > window.innerHeight) y = Math.max(0, window.innerHeight - h);
}

function draw() {
  clamp();
  rect.style.left = x + "px";
  rect.style.top = y + "px";
  rect.style.width = w + "px";
  rect.style.height = h + "px";
  info.textContent =
    "local=" + x + "," + y + "," + w + "," + h +
    " | réel=" + (win[0]+x) + "," + (win[1]+y) + "," + w + "," + h +
    " | screen=" + screenId;
}

let mode = null, sx = 0, sy = 0, ox = 0, oy = 0, ow = 0, oh = 0;

rect.addEventListener("pointerdown", e => {
  if (e.target.id === "handle") return;
  mode = "move";
  sx = e.clientX; sy = e.clientY; ox = x; oy = y;
  rect.setPointerCapture(e.pointerId);
});

document.getElementById("handle").addEventListener("pointerdown", e => {
  mode = "resize";
  sx = e.clientX; sy = e.clientY; ow = w; oh = h;
  rect.setPointerCapture(e.pointerId);
  e.stopPropagation();
});

window.addEventListener("pointermove", e => {
  if (!mode) return;
  if (mode === "move") {
    x = ox + (e.clientX - sx);
    y = oy + (e.clientY - sy);
  } else if (mode === "resize") {
    w = ow + (e.clientX - sx);
    h = oh + (e.clientY - sy);
  }
  draw();
});

window.addEventListener("pointerup", () => { mode = null; });

window.addEventListener("keydown", e => {
  const step = e.shiftKey ? 10 : 1;
  if (e.key === "ArrowLeft") x -= step;
  if (e.key === "ArrowRight") x += step;
  if (e.key === "ArrowUp") y -= step;
  if (e.key === "ArrowDown") y += step;
  if (e.key === "+") { w += step; h += step; }
  if (e.key === "-") { w -= step; h -= step; }
  draw();
});

function centerRect() {
  x = Math.round((window.innerWidth - w) / 2);
  y = Math.round((window.innerHeight - h) / 2);
  draw();
}

function fitTop() {
  x = 0;
  y = 0;
  w = window.innerWidth;
  h = Math.max(80, Math.round(window.innerHeight * 0.18));
  draw();
}

async function save() {
  draw();
  const payload = {
    screen_id: screenId,
    x: x,
    y: y,
    width: w,
    height: h,
    window_x: win[0],
    window_y: win[1],
    window_width: win[2],
    window_height: win[3]
  };

  const r = await fetch("/api/dmd/save", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(payload)
  });

  const j = await r.json();
  alert(j.ok ? ("DMD sauvegardé. Réel: " + j.real_geometry) : ("Erreur: " + (j.error || "unknown")));
}

draw();
</script>
</body>
</html>
"""
    return body

@app.route("/api/dmd/save", methods=["POST"])
def pincabos_api_dmd_save():
    try:
        import json
        import subprocess
        from pathlib import Path
        from datetime import datetime

        data = request.get_json(force=True, silent=True) or {}

        def as_int(name, default=0):
            try:
                return int(data.get(name, default))
            except Exception:
                return int(default)

        screen_id = str(data.get("screen_id", ""))
        local_x = as_int("x", 0)
        local_y = as_int("y", 0)
        width = as_int("width", 512)
        height = as_int("height", 128)

        window_x = as_int("window_x", 0)
        window_y = as_int("window_y", 0)
        window_width = as_int("window_width", 0)
        window_height = as_int("window_height", 0)

        real_x = window_x + local_x
        real_y = window_y + local_y

        clean = {
            "screen_id": screen_id,
            "x": real_x,
            "y": real_y,
            "width": width,
            "height": height,
            "geometry": f"{width}x{height}+{real_x}+{real_y}",
            "real": {
                "x": real_x,
                "y": real_y,
                "width": width,
                "height": height,
                "geometry": f"{width}x{height}+{real_x}+{real_y}",
            },
            "local": {
                "x": local_x,
                "y": local_y,
                "width": width,
                "height": height,
                "geometry": f"{width}x{height}+{local_x}+{local_y}",
            },
            "window": {
                "x": window_x,
                "y": window_y,
                "width": window_width,
                "height": window_height,
                "geometry": f"{window_width}x{window_height}+{window_x}+{window_y}",
            },
            "note": "PinCabOS global DMD position calibration. x/y top-level are real desktop coordinates.",
            "_pincabos_meta": {
                "modified_by": "PinCabOS",
                "function": "DMD Calibration",
                "updated_at": datetime.now().isoformat(timespec="seconds"),
                "formula": "real_x = window_x + local_x; real_y = window_y + local_y",
            },
        }

        cfg = Path("/opt/pincabos/config/dmd-calibration.json")
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text(json.dumps(clean, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

        log = Path("/opt/pincabos/logs/dmd-calibration.log")
        with log.open("a", encoding="utf-8") as f:
            f.write(
                datetime.now().strftime("%F %T")
                + f" - DMD save local={local_x},{local_y},{width},{height} "
                + f"window={window_x},{window_y},{window_width},{window_height} "
                + f"real={real_x},{real_y},{width},{height}\n"
            )

        subprocess.run(
            ["/usr/bin/sudo", str(pco_script("sync_dmd_calibrations"))],
            timeout=8,
            check=False,
        )

        return jsonify({
            "ok": True,
            "message": "DMD sauvegardé et synchronisé.",
            "local_geometry": f"{width}x{height}+{local_x}+{local_y}",
            "window_geometry": f"{window_width}x{window_height}+{window_x}+{window_y}",
            "real_geometry": f"{width}x{height}+{real_x}+{real_y}",
        })

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/launch-dmd-calibrator", methods=["POST"])
def pincabos_launch_dmd_calibrator():
    try:
        Path("/run/pincabos-dmd-calibrator.active").write_text(
            datetime.now().isoformat(timespec="seconds") + "\n"
        )
    except Exception:
        pass

    subprocess.Popen(["/usr/bin/sudo", str(pco_script("launch_dmd_calibrator"))])
    return redirect("/fulldmd?dmd_calibration=open&ts=" + datetime.now().strftime("%Y%m%d%H%M%S"))


@app.route("/close-dmd-calibrator", methods=["POST"])
def pincabos_close_dmd_calibrator():
    try:
        Path("/run/pincabos-dmd-calibrator.active").unlink(missing_ok=True)
    except Exception:
        pass

    try:
        subprocess.run(
            ["/usr/bin/sudo", str(pco_script("close_dmd_calibrator"))],
            timeout=5,
            check=False
        )
    except Exception:
        pass

    try:
        Path("/run/pincabos-dmd-calibrator.active").unlink(missing_ok=True)
    except Exception:
        pass

    return redirect("/fulldmd?dmd_calibration=closed&ts=" + datetime.now().strftime("%Y%m%d%H%M%S"))


@app.route("/fulldmd-log-page-disabled")
def fulldmd_log_page():
    parts = []

    parts.append("===== Log temps réel désactivé FullDMD =====")
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
        ini = pincabos_vpinfe_ini_path()
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
        ini = pincabos_vpx_ini_path()
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
      background: var(--pco-appearance-input-bg, #050007);
      color: var(--pco-appearance-input-text, #eee);
      font-family: monospace;
      font-size: 13px;
    }}
    pre {{
      white-space: pre-wrap;
      margin: 0;
      padding: 15px;
    }}
    .top {{
      color: var(--pco-appearance-accent, #ffb000);
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
@app.route("/console/")
def console_page():
    ip = get_ip()
    console_url = f"http://{ip}:8090"

    body = f"""
<style>
  body {{
    background:
      radial-gradient(circle at top, rgba(16,0,28,.16), transparent 34%),
      linear-gradient(180deg, #000000 0%, #010003 55%, #000000 100%) !important;
  }}

  .pco-console-card {{
      background: rgba(29, 11, 46, 0.76) !important;
      border: 1px solid var(--pco-appearance-accent2, #ff7a00) !important;
      border-radius: var(--pco-appearance-card-radius, 18px);
      box-shadow: var(--pco-appearance-card-shadow, 0 0 25px rgba(255, 122, 0, 0.25));
    }}

    .pco-console-frame-wrap {{
    background: #000;
    border: 1px solid rgba(42, 14, 70, .42);
    border-radius: 14px;
    padding: 8px;
    box-shadow:
      inset 0 0 36px rgba(0, 0, 0, 1),
      0 0 42px rgba(0, 0, 0, .95);
  }}

  #pincabos-console-frame {{
    background: #000 !important;
    filter: brightness(.66) contrast(1.18) saturate(.82);
  }}
</style>

<div class="card pco-console-card">
  <div class="pco-console-info" style="
  margin: 0 0 14px 0;
  padding: 14px 16px;
  border-radius: var(--pco-appearance-card-radius, 18px);
  background: var(--pco-appearance-card-bg, rgba(29, 11, 46, 0.76));
  border: 1px solid var(--pco-appearance-card-border, #ff7a00);
  box-shadow: 0 0 25px rgba(255, 122, 0, 0.18);
  color: #fff;
  line-height: 1.45;
">
  <h2 style="margin:0 0 5px 0;color:#ffb000;">PinCab Console</h2>
  <p style="margin:0 0 8px 0;">Terminal Web PinCabOs.</p>

  <p style="margin:0 0 8px 0;">La console est protégée par un identifiant séparé.</p>

  <p style="margin:0 0 5px 0;"><strong>URL directe :</strong></p>
  <p style="margin:0 0 8px 0;">
    <a href="{console_url}" target="_blank" rel="noopener" style="color:#ffb000;">
      {console_url}
    </a>
  </p>

  <p style="margin:0 0 10px 0;">
    <a class="button" href="{console_url}" target="_blank" rel="noopener">
      Ouvrir la console dans un nouvel onglet
    </a>
  </p>

  <div style="
    display:inline-flex;
    align-items:center;
    gap:7px;
    margin:0;
    padding:4px 7px;
    border-radius:999px;
    border:1px solid rgba(255,176,0,.35);
    background:rgba(255,176,0,.08);
    color:#fff;
    font-size:12px;
    line-height:1.1;
  ">
    <span style="color:#ffb000;font-weight:700;">Root :</span>
    <code style="
      display:inline-block;
      margin:0;
      padding:2px 6px;
      border-radius:6px;
      background:#050007;
      color:#00ff99;
      font-size:12px;
      line-height:1.1;
      font-weight:700;
      border:1px solid #5f2a91;
    ">sudo -i</code>
  </div>
</div>

<iframe
      id="pincabos-console-frame"
      src="{console_url}"
      allowfullscreen
      style="width:100%; height:78vh; min-height:720px; border:0; border-radius:10px; background:#000;">
    </iframe>
  </div>
</div>

<script>
function openPinCabConsoleFullscreen() {{
  const url = "{console_url}";
  const w = screen.availWidth || window.innerWidth || 1280;
  const h = screen.availHeight || window.innerHeight || 720;

  window.open(
    url,
    "PinCabOSConsoleCommander",
    "popup=yes,width=" + w + ",height=" + h + ",left=0,top=0,menubar=no,toolbar=no,location=no,status=no,scrollbars=no,resizable=yes"
  );
}}
</script>
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
            ["/usr/bin/sudo", str(pco_script("change_root_password"))],
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
    return run_cmd(["/usr/bin/sudo", str(pco_script("network_info"))], timeout=15)


def network_current_mode():
    out = run_cmd(["/usr/bin/sudo", str(pco_script("network_current_mode"))], timeout=8)
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
    out = run_cmd(["/usr/bin/sudo", str(pco_script("wifi_scan"))], timeout=15)
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
          "Nouvelle URL WebApp probable : http://" + ip + "/\\n\\n" +
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
      <input name="password" type="password" value="" placeholder="Mot de passe console" style="width:90%; padding:8px; margin:6px 0;"><br>

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
            ["/usr/bin/sudo", str(pco_script("network_set_dhcp")), iface],
            timeout=30
        )
        return network_action_result("Configuration réseau — DHCP", out)

    if mode == "static":
        ipcidr = request.form.get("ipcidr", "").strip()
        gateway = request.form.get("gateway", "").strip()
        dns = request.form.get("dns", "").strip() or "1.1.1.1,8.8.8.8"

        out = run_cmd(
            ["/usr/bin/sudo", str(pco_script("network_set_static")), iface, ipcidr, gateway, dns],
            timeout=30
        )
        return network_action_result("Configuration réseau — IP fixe", out)

    return network_action_result("Configuration réseau", "Mode invalide.")


@app.route("/network/wifi-join", methods=["POST"])
def network_wifi_join():
    ssid = request.form.get("ssid", "").strip()
    password = request.form.get("password", "")

    out = run_cmd(
        ["/usr/bin/sudo", str(pco_script("wifi_join")), ssid, password],
        timeout=40
    )
    return network_action_result("Connexion WiFi", out)


@app.route("/network/wifi-hotspot", methods=["POST"])
def network_wifi_hotspot():
    ssid = request.form.get("ssid", "PinCabOs_WiFi").strip() or "PinCabOs_WiFi"
    password = (request.form.get("password", "") or "").strip()

    out = run_cmd(
        ["/usr/bin/sudo", str(pco_script("wifi_hotspot")), ssid, password],
        timeout=40
    )
    return network_action_result("Hotspot WiFi — activation", out)


@app.route("/network/wifi-hotspot-stop", methods=["POST"])
def network_wifi_hotspot_stop():
    out = run_cmd(
        ["/usr/bin/sudo", str(pco_script("wifi_hotspot_stop"))],
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
            ["/usr/bin/sudo", str(pco_script("close_webapp_screen"))],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

        if state["playfield"] == "1":
            subprocess.Popen(
                ["/usr/bin/sudo", str(pco_script("launch_webapp_screen")), "0", "http://127.0.0.1/"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )

        if state["backglass"] == "1":
            subprocess.Popen(
                ["/usr/bin/sudo", str(pco_script("launch_webapp_screen")), "1", "http://127.0.0.1/"],
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
        ["/usr/bin/sudo", str(pco_script("launch_webapp_screen")), screen, "http://127.0.0.1/"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    return redirect(request.referrer or url_for("dashboard"))


@app.route("/close-webapp-screen", methods=["POST"])
def close_webapp_screen():
    subprocess.Popen(
        ["/usr/bin/sudo", str(pco_script("close_webapp_screen"))],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    return redirect(request.referrer or url_for("dashboard"))


# Moved to modular route file by PinCabOS refactor (original lines 9709-9709).

# Moved to modular route file by PinCabOS refactor (original lines 9711-9723).


# Moved to modular route file by PinCabOS refactor (original lines 9726-9737).


# Moved to modular route file by PinCabOS refactor (original lines 9740-9753).


# Moved to modular route file by PinCabOS refactor (original lines 9756-9758).



# Moved to modular route file by PinCabOS refactor (original lines 9762-9809).



# Moved to modular route file by PinCabOS refactor (original lines 9813-9823).


# Moved to modular route file by PinCabOS refactor (original lines 9826-9827).


# Moved to modular route file by PinCabOS refactor (original lines 9830-9831).


# Moved to modular route file by PinCabOS refactor (original lines 9834-9855).


# Moved to modular route file by PinCabOS refactor (original lines 9858-9869).


AUDIO_VPX_INI = pincabos_vpx_ini_path()
AUDIO_VPINFE_INI = pincabos_vpinfe_ini_path()
AUDIO_BACKUP_DIR = Path("/opt/pincabos/backups/audio-ssf")


# Moved to modular route file by PinCabOS refactor (original lines 9877-9885).


# Moved to modular route file by PinCabOS refactor (original lines 9888-9890).


# Moved to modular route file by PinCabOS refactor (original lines 9893-9896).


# Moved to modular route file by PinCabOS refactor (original lines 9899-9901).


# Moved to modular route file by PinCabOS refactor (original lines 9904-9923).


# Moved to modular route file by PinCabOS refactor (original lines 9926-9972).


# Moved to modular route file by PinCabOS refactor (original lines 9975-9994).


# Moved to modular route file by PinCabOS refactor (original lines 9997-10007).


# Moved to modular route file by PinCabOS refactor (original lines 10010-10094).


# === PINCABOS AUDIO OPTIONAL ALSA CARD HELPER START ===
# Moved to modular route file by PinCabOS refactor (original lines 10098-10107).


# Moved to modular route file by PinCabOS refactor (original lines 10110-10189).


# Moved to modular route file by PinCabOS refactor (original lines 10192-10318).





# === PINCABOS AUDIO INI READ HELPERS RESTORE START ===
# Moved to modular route file by PinCabOS refactor (original lines 10325-10356).


# Moved to modular route file by PinCabOS refactor (original lines 10359-10364).
# === PINCABOS AUDIO INI READ HELPERS RESTORE END ===


# Moved to modular route file by PinCabOS refactor (original lines 10368-10442).
# === PINCABOS AUDIO INI VALUES CARD END ===


# === PINCABOS AUDIO SYSTEM VOLUME BALANCE START ===

# Moved to modular route file by PinCabOS refactor (original lines 10448-10459).


# Moved to modular route file by PinCabOS refactor (original lines 10462-10471).


# Moved to modular route file by PinCabOS refactor (original lines 10474-10508).


# Moved to modular route file by PinCabOS refactor (original lines 10511-10554).


# Moved to modular route file by PinCabOS refactor (original lines 10557-10646).


# Moved to modular route file by PinCabOS refactor (original lines 10649-10650).


# Moved to modular route file by PinCabOS refactor (original lines 10653-10826).


# === PINCABOS AUDIO SSF PAGE ROUTE FIX START ===
# Moved to modular route file by PinCabOS refactor (original lines 10830-11028).
# === PINCABOS AUDIO SSF PAGE ROUTE FIX END ===


# Moved to modular route file by PinCabOS refactor (original lines 11032-11082).


# Moved to modular route file by PinCabOS refactor (original lines 11085-11088).


# Moved to modular route file by PinCabOS refactor (original lines 11091-11096).


# === PINCABOS AUDIO VU HTML ROUTE START ===
# Moved to modular route file by PinCabOS refactor (original lines 11100-11102).


# Moved to modular route file by PinCabOS refactor (original lines 11105-11106).


# Moved to modular route file by PinCabOS refactor (original lines 11109-11131).


# === SSF COMMANDER V1 - PINCABOS START ===
# Moved to modular route file by PinCabOS refactor (original lines 11135-11135).

# Moved to modular route file by PinCabOS refactor (original lines 11137-11147).

# Moved to modular route file by PinCabOS refactor (original lines 11149-11154).

# Moved to modular route file by PinCabOS refactor (original lines 11156-11158).

# Moved to modular route file by PinCabOS refactor (original lines 11160-11190).

# Moved to modular route file by PinCabOS refactor (original lines 11192-11288).


# Moved to modular route file by PinCabOS refactor (original lines 11291-11303).

# === PINCABOS AUDIO WAV ROUTES REAL START ===
# Moved to modular route file by PinCabOS refactor (original lines 11306-11407).


# Moved to modular route file by PinCabOS refactor (original lines 11410-11450).


# Moved to modular route file by PinCabOS refactor (original lines 11453-11457).


# Moved to modular route file by PinCabOS refactor (original lines 11460-11554).


# Moved to modular route file by PinCabOS refactor (original lines 11557-11595).


# Moved to modular route file by PinCabOS refactor (original lines 11598-11627).





# === PINCABOS DEV REAL LOGIN START ===
DEV_LOGIN_USER = "PinCabOsDev"
DEV_LOGIN_PASS = "Dev43po3$"

# Moved to modular route file by PinCabOS refactor (original lines 11637-11641).

# Moved to modular route file by PinCabOS refactor (original lines 11643-11661).

# === PINCABOS ADMIN HIDDEN PAGE START ===
ADMIN_LOGIN_USER = "PinCabOsDev"
ADMIN_LOGIN_PASS = "Dev43po3$"

# Moved to modular route file by PinCabOS refactor (original lines 11667-11671).

# Moved to modular route file by PinCabOS refactor (original lines 11673-11701).

# === PINCABOS ADMIN SIMPLE STATUS HELPERS START ===












# Moved to modular route file by PinCabOS refactor (original lines 11716-11767).

# Moved to modular route file by PinCabOS refactor (original lines 11769-11803).


# Moved to modular route file by PinCabOS refactor (original lines 11806-11868).


# Moved to modular route file by PinCabOS refactor (original lines 11871-11950).

# Moved to modular route file by PinCabOS refactor (original lines 11952-11987).

# Moved to modular route file by PinCabOS refactor (original lines 11989-12004).




# === PinCabOS managed block: admin-log-options-html BEGIN ===
# Moved to modular route file by PinCabOS refactor (original lines 12010-12033).
# === PinCabOS managed block: admin-log-options-html END ===


# Moved to modular route file by PinCabOS refactor (original lines 12037-12358).


# Moved to modular route file by PinCabOS refactor (original lines 12361-12362).


# Moved to modular route file by PinCabOS refactor (original lines 12365-12376).

# Moved to modular route file by PinCabOS refactor (original lines 12378-12383).

# === PINCABOS ADMIN RESTORE STABLE START ===
ADMIN_LOGIN_USER = "PinCabOsDev"
ADMIN_LOGIN_PASS = "Dev43po3$"

# Moved to modular route file by PinCabOS refactor (original lines 12389-12393).


# Moved to modular route file by PinCabOS refactor (original lines 12396-12402).

# Moved to modular route file by PinCabOS refactor (original lines 12404-12410).

# Moved to modular route file by PinCabOS refactor (original lines 12412-12418).

# Moved to modular route file by PinCabOS refactor (original lines 12420-12423).

# Moved to modular route file by PinCabOS refactor (original lines 12425-12441).

# Moved to modular route file by PinCabOS refactor (original lines 12443-12455).

# Moved to modular route file by PinCabOS refactor (original lines 12457-12460).
# === PINCABOS ADMIN RESTORE STABLE END ===


# Compatibility proxy: the following legacy Admin enhancements are applied before
# modular route registration. It delegates to the moved original admin page.
def pincabos_admin_page(*args, **kwargs):
    return pco_dev_admin_routes.pco_admin_page_base(*args, **kwargs)

# === PINCABOS ABOUT SUPPORTERS ADMIN START ===
ABOUT_SUPPORTERS_CONFIG = Path("/opt/pincabos/config/about-supporters.json")

def pincabos_about_supporters_default():
    return {
        "title": "Testeurs / Soutiens fondateurs",
        "intro": "Merci aux personnes qui aident à tester PinCabOs, rapporter les problèmes, proposer des idées et soutenir le développement du projet.",
        "supporters": [
            "Strung Flo",
            "Nicolas Prou",
            "Olivier Chéron",
        ],
        "founders_title": "Nom Fondateurs",
        "founders": [],
    }

def pincabos_about_supporters_normalize_list(value):
    if isinstance(value, str):
        return [x.strip() for x in value.splitlines() if x.strip()]
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    return []

def pincabos_about_supporters_load():
    import json

    default = pincabos_about_supporters_default()

    try:
        if ABOUT_SUPPORTERS_CONFIG.exists():
            data = json.loads(ABOUT_SUPPORTERS_CONFIG.read_text(errors="replace"))
            if not isinstance(data, dict):
                data = {}
        else:
            data = {}
    except Exception:
        data = {}

    supporters = pincabos_about_supporters_normalize_list(data.get("supporters", default["supporters"]))
    founders = pincabos_about_supporters_normalize_list(data.get("founders", default["founders"]))

    if not supporters:
        supporters = default["supporters"]

    return {
        "title": str(data.get("title") or default["title"]).strip(),
        "intro": str(data.get("intro") or default["intro"]).strip(),
        "supporters": supporters,
        "founders_title": str(data.get("founders_title") or default["founders_title"]).strip(),
        "founders": founders,
    }

def pincabos_about_supporters_save(data):
    import json
    import datetime

    ABOUT_SUPPORTERS_CONFIG.parent.mkdir(parents=True, exist_ok=True)

    backup_dir = Path("/opt/pincabos/backups/about-supporters")
    backup_dir.mkdir(parents=True, exist_ok=True)

    try:
        backup_dir.chmod(0o775)
    except Exception:
        pass

    if ABOUT_SUPPORTERS_CONFIG.exists():
        ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = backup_dir / ("about-supporters.json.backup-admin-" + ts)
        backup.write_text(ABOUT_SUPPORTERS_CONFIG.read_text(errors="replace"), encoding="utf-8")

    ABOUT_SUPPORTERS_CONFIG.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8"
    )

    try:
        ABOUT_SUPPORTERS_CONFIG.chmod(0o664)
    except Exception:
        pass

def pincabos_about_supporters_public_card():
    data = pincabos_about_supporters_load()

    rows = []

    # Fusion visuelle des deux listes, puis tri alphabétique par nom.
    # role = "supporter" => une étoile
    # role = "founder"   => deux étoiles
    people = []

    for name in data.get("supporters", []):
        people.append({
            "name": str(name).strip(),
            "role": "supporter",
        })

    for name in data.get("founders", []):
        people.append({
            "name": str(name).strip(),
            "role": "founder",
        })

    people = [p for p in people if p.get("name")]

    # Déduplique en gardant le rôle fondateur prioritaire si le même nom est dans les deux listes.
    merged = {}
    for p in people:
        key = p["name"].casefold()
        if key not in merged:
            merged[key] = p
        elif p.get("role") == "founder":
            merged[key] = p

    people = sorted(
        merged.values(),
        key=lambda p: p.get("name", "").casefold()
    )

    for person in people:
        name = person.get("name", "")
        role = person.get("role", "supporter")

        if role == "founder":
            rows.append(
                '<div style="display:inline-flex;align-items:center;gap:8px;margin:6px 10px 6px 0;'
                'padding:10px 14px;border:1px solid rgba(255,176,0,.55);border-radius:999px;'
                'background:rgba(255,176,0,.08);box-shadow:0 0 16px rgba(255,176,0,.18);">'
                '<span style="color:#ffb000;">★★</span>'
                '<strong>' + esc(name) + '</strong>'
                '<span style="color:#ffb000;">★★</span>'
                '</div>'
            )
        else:
            rows.append(
                '<div style="display:inline-flex;align-items:center;gap:8px;margin:6px 10px 6px 0;'
                'padding:9px 12px;border:1px solid rgba(255,176,0,.35);border-radius:999px;'
                'background:rgba(0,0,0,.25);">'
                '<span style="color:#ffb000;">★</span>'
                '<strong>' + esc(name) + '</strong>'
                '<span style="color:#ffb000;">★</span>'
                '</div>'
            )

    if not rows:
        rows.append('<p class="warn">Aucun testeur/supporter configuré.</p>')

    return """
<!-- PINCABOS_ABOUT_SUPPORTERS_CARD -->
<div class="card" id="testeurs-soutiens-fondateurs">
  <h2>__TITLE__</h2>
  <p>__INTRO__</p>
  <div style="margin-top:10px;">__ROWS__</div>
</div>
""".replace("__TITLE__", esc(data.get("title", ""))) \
   .replace("__INTRO__", esc(data.get("intro", ""))) \
   .replace("__ROWS__", "\n".join(rows))

def pincabos_about_supporters_admin_card():
    data = pincabos_about_supporters_load()
    supporters_text = "\n".join(data.get("supporters", []))
    founders_text = "\n".join(data.get("founders", []))

    return """
<!-- PINCABOS_ADMIN_ABOUT_SUPPORTERS_CARD -->
<div class="card" id="about-supporters" style="margin-top:20px;">
  <h2>About - Testeurs / Soutiens fondateurs</h2>
  <p>Modifie la section affichée dans <code>/about</code>.</p>

  <form method="post" action="/admin/about-supporters/save">
    <label>Titre<br>
      <input name="title" value="__TITLE__" style="width:95%;padding:10px;">
    </label>

    <p>
      <label>Texte<br>
        <textarea name="intro" rows="3" style="width:95%;padding:10px;">__INTRO__</textarea>
      </label>
    </p>

    <p>
      <label>Noms Testeurs / Soutiens, un par ligne<br>
        <textarea name="supporters" rows="8" style="width:95%;padding:10px;">__SUPPORTERS__</textarea>
      </label>
    </p>

    <p>
      <label>Nom Fondateurs<br>
        <input name="founders_title" value="__FOUNDERS_TITLE__" style="width:95%;padding:10px;">
      </label>
    </p>

    <p>
      <label>Noms Fondateurs, un par ligne<br>
        <textarea name="founders" rows="6" style="width:95%;padding:10px;">__FOUNDERS__</textarea>
      </label>
      <small style="opacity:.75;">Dans About, ces noms restent dans la même section et apparaissent avec deux étoiles de chaque côté.</small>
    </p>

    <p>
      <button class="button" type="submit">💾 Sauvegarder Testeurs / Soutiens</button>
      <a class="button secondary" href="/about#testeurs-soutiens-fondateurs">👁️ Voir dans About</a>
    </p>
  </form>
</div>
""".replace("__TITLE__", esc(data.get("title", ""))) \
   .replace("__INTRO__", esc(data.get("intro", ""))) \
   .replace("__SUPPORTERS__", esc(supporters_text)) \
   .replace("__FOUNDERS_TITLE__", esc(data.get("founders_title", "Nom Fondateurs"))) \
   .replace("__FOUNDERS__", esc(founders_text))

def pincabos_about_supporters_insert_public(html):
    card = pincabos_about_supporters_public_card()
    body = str(html)

    if "PINCABOS_ABOUT_SUPPORTERS_CARD" in body:
        return body

    import re
    pattern = re.compile(
        r'<div class="card"[^>]*>\s*<h2>\s*Testeurs\s*/\s*Soutiens fondateurs\s*</h2>[\s\S]*?</div>',
        re.IGNORECASE
    )
    body, count = pattern.subn(card, body, count=1)
    if count:
        return body

    if "</main>" in body:
        return body.replace("</main>", card + "\n</main>", 1)
    if "</body>" in body:
        return body.replace("</body>", card + "\n</body>", 1)
    return body + "\n" + card

try:
    _pincabos_about_original_endpoint = None
    _pincabos_about_original_view = None

    for _rule in app.url_map.iter_rules():
        if getattr(_rule, "rule", "") == "/about":
            _pincabos_about_original_endpoint = _rule.endpoint
            _pincabos_about_original_view = app.view_functions.get(_rule.endpoint)
            break

    if _pincabos_about_original_endpoint and _pincabos_about_original_view:
        def _pincabos_about_supporters_wrapped_view(*args, **kwargs):
            result = _pincabos_about_original_view(*args, **kwargs)

            if isinstance(result, tuple):
                body = pincabos_about_supporters_insert_public(result[0])
                return (body,) + result[1:]

            return pincabos_about_supporters_insert_public(result)

        app.view_functions[_pincabos_about_original_endpoint] = _pincabos_about_supporters_wrapped_view
except Exception:
    pass

try:
    _pincabos_admin_page_original_for_about_supporters = pincabos_admin_page

    def pincabos_admin_page():
        html = _pincabos_admin_page_original_for_about_supporters()
        card = pincabos_about_supporters_admin_card()

        if "PINCABOS_ADMIN_ABOUT_SUPPORTERS_CARD" in str(html):
            return html

        def _pco_insert_before_footer(body, card):
            # Position voulue:
            # APRÈS la carte complète qui contient "Publish / Cleanup PinCabOS",
            # pas dans la carte, pas juste après les boutons, pas dans le footer.

            import re

            def _pco_find_matching_div_end(src, div_start):
                # Trouve le </div> correspondant au <div ...> de div_start.
                tag_re = re.compile(r'<(/?)div\b[^>]*>', re.IGNORECASE)
                depth = 0

                for m in tag_re.finditer(src, div_start):
                    closing = m.group(1) == "/"

                    if not closing:
                        depth += 1
                    else:
                        depth -= 1
                        if depth == 0:
                            return m.end()

                return -1

            title_idx = body.find("Publish / Cleanup PinCabOS")
            if title_idx != -1:
                # Trouver le début de la carte contenant ce titre.
                card_start = body.rfind('<div class="card"', 0, title_idx)
                if card_start == -1:
                    card_start = body.rfind("<div", 0, title_idx)

                if card_start != -1:
                    card_end = _pco_find_matching_div_end(body, card_start)
                    if card_end != -1:
                        return body[:card_end] + "\n" + card + body[card_end:]

            # Fallback: avant Version PinCabOS, pour rester dans la zone admin.
            version_idx = body.find("PINCABOS_ADMIN_VERSION_JSON_CARD")
            if version_idx != -1:
                version_card_start = body.rfind('<div class="card"', 0, version_idx)
                if version_card_start != -1:
                    return body[:version_card_start] + card + "\n" + body[version_card_start:]

            # Fallback: avant le footer parent complet.
            lower = body.lower()
            footer_parent = lower.find('id="pincabos-support-footer-static"')
            if footer_parent != -1:
                div_idx = lower.rfind("<div", 0, footer_parent)
                insert_idx = div_idx if div_idx != -1 else footer_parent
                return body[:insert_idx] + card + "\n" + body[insert_idx:]

            return body + "\n" + card


        if isinstance(html, tuple):
            body = str(html[0])
            rest = html[1:]
            body = _pco_insert_before_footer(body, card)
            return (body,) + rest

        body = str(html)
        body = _pco_insert_before_footer(body, card)
        return body

    @app.route("/admin/about-supporters/save", methods=["POST"])
    def pincabos_admin_about_supporters_save():
        guard = pincabos_admin_require_login()
        if guard:
            return guard

        default = pincabos_about_supporters_default()

        title = (request.form.get("title", "") or "").strip() or default["title"]
        intro = (request.form.get("intro", "") or "").strip() or default["intro"]
        supporters = pincabos_about_supporters_normalize_list(request.form.get("supporters", "") or "")
        founders_title = (request.form.get("founders_title", "") or "").strip() or default["founders_title"]
        founders = pincabos_about_supporters_normalize_list(request.form.get("founders", "") or "")

        data = {
            "title": title,
            "intro": intro,
            "supporters": supporters,
            "founders_title": founders_title,
            "founders": founders,
        }

        pincabos_about_supporters_save(data)
        return redirect("/admin#about-supporters")

except Exception:
    pass
# === PINCABOS ABOUT SUPPORTERS ADMIN END ===

# === PINCABOS FOOTER ABOUT SUPPORTERS START ===
def pincabos_footer_supporters_card():
    data = pincabos_about_supporters_load()

    people = []

    for name in data.get("supporters", []):
        people.append({
            "name": str(name).strip(),
            "role": "supporter",
        })

    for name in data.get("founders", []):
        people.append({
            "name": str(name).strip(),
            "role": "founder",
        })

    people = [p for p in people if p.get("name")]

    merged = {}
    for p in people:
        key = p["name"].casefold()
        if key not in merged:
            merged[key] = p
        elif p.get("role") == "founder":
            merged[key] = p

    people = sorted(
        merged.values(),
        key=lambda p: p.get("name", "").casefold()
    )

    rows = []
    for person in people:
        name = person.get("name", "")
        role = person.get("role", "supporter")

        if role == "founder":
            rows.append(
                '<div style="display:inline-flex;align-items:center;justify-content:center;gap:5px;'
                'margin:4px 5px;padding:5px 8px;border:1px solid rgba(255,176,0,.55);'
                'border-radius:999px;background:rgba(255,176,0,.08);'
                'box-shadow:0 0 10px rgba(255,176,0,.12);font-size:70%;line-height:1.15;text-align:center;">'
                '<span style="color:#ffb000;">★★</span>'
                '<strong>' + esc(name) + '</strong>'
                '<span style="color:#ffb000;">★★</span>'
                '</div>'
            )
        else:
            rows.append(
                '<div style="display:inline-flex;align-items:center;justify-content:center;gap:5px;'
                'margin:4px 5px;padding:5px 8px;border:1px solid rgba(255,176,0,.35);'
                'border-radius:999px;background:rgba(0,0,0,.22);'
                'font-size:70%;line-height:1.15;text-align:center;">'
                '<span style="color:#ffb000;">★</span>'
                '<strong>' + esc(name) + '</strong>'
                '<span style="color:#ffb000;">★</span>'
                '</div>'
            )

    if not rows:
        return ""

    return """
<!-- PINCABOS_FOOTER_ABOUT_SUPPORTERS_CARD -->
<div class="pincabos-footer-about-supporters-safe" style="display:block;width:100%;max-width:none;margin:0;padding:14px 24px 13px 24px;border-top:1px solid rgba(255,176,0,.28);border-bottom:1px solid rgba(255,176,0,.18);box-sizing:border-box;clear:both;background:rgba(0,0,0,.10);text-align:center;">
  <div style="width:100%;max-width:100%;margin:0 auto;padding:0;box-sizing:border-box;text-align:center;">
    <h2 style="margin:0 0 6px 0;font-size:70%;line-height:1.15;text-align:center;">__TITLE__</h2>
    <p style="margin:0 0 9px 0;opacity:.88;font-size:70%;line-height:1.25;text-align:center;">__INTRO__</p>
    <div style="display:flex;flex-wrap:wrap;align-items:center;justify-content:center;gap:4px 6px;width:100%;max-width:100%;box-sizing:border-box;text-align:center;">__ROWS__</div>
  </div>
</div>
""".replace("__TITLE__", esc(data.get("title", "Testeurs / Soutiens fondateurs"))) \
   .replace("__INTRO__", esc(data.get("intro", ""))) \
   .replace("__ROWS__", "\n".join(rows))

def pincabos_footer_supporters_insert(html):
    body = str(html)

    if "PINCABOS_FOOTER_ABOUT_SUPPORTERS_CARD" in body:
        return body

    footer_id = 'id="pincabos-support-footer-static"'
    lower = body.lower()
    idx = lower.find(footer_id)

    if idx == -1:
        return body

    footer_start = lower.rfind("<div", 0, idx)
    if footer_start == -1:
        return body

    import re
    tag_re = re.compile(r'<(/?)div\b[^>]*>', re.IGNORECASE)
    depth = 0
    footer_close_end = -1

    for m in tag_re.finditer(body, footer_start):
        closing = m.group(1) == "/"
        if not closing:
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                # Important: insérer APRÈS la fermeture complète du footer parent,
                # pas dedans. Ça évite les colonnes du footer.
                footer_close_end = m.end()
                break

    if footer_close_end == -1:
        return body

    card = pincabos_footer_supporters_card()
    if not card:
        return body

    return body[:footer_close_end] + "\n" + card + "\n" + body[footer_close_end:]

try:
    _pincabos_page_original_for_footer_supporters = page

    def page(*args, **kwargs):
        result = _pincabos_page_original_for_footer_supporters(*args, **kwargs)

        if isinstance(result, tuple):
            body = pincabos_footer_supporters_insert(result[0])
            return (body,) + result[1:]

        return pincabos_footer_supporters_insert(result)

except Exception:
    pass
# === PINCABOS FOOTER ABOUT SUPPORTERS END ===




# === PINCABOS ADMIN VERSION JSON CARD WRAPPER START ===
try:
    _pincabos_admin_page_original_for_version_json_card = pincabos_admin_page

    def pincabos_admin_version_json_card_html():
        return f"""
<!-- PINCABOS_ADMIN_VERSION_JSON_CARD -->
<div class="card" id="version-json" style="margin-top:20px;">
  <h2>Version PinCabOS</h2>
  <p>Cette section met à jour le fichier maître <code>/opt/pincabos/config/version.json</code>.</p>

  <form method="post" action="/admin/version/save">
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
"""

    def pincabos_admin_page():
        html = _pincabos_admin_page_original_for_version_json_card()
        card = pincabos_admin_version_json_card_html()

        if "PINCABOS_ADMIN_VERSION_JSON_CARD" in str(html):
            return html

        if isinstance(html, tuple):
            body = str(html[0])
            rest = html[1:]
            if "<h1>Admin PinCabOS</h1>" in body:
                body = body.replace("<h1>Admin PinCabOS</h1>", "<h1>Admin PinCabOS</h1>\n" + card, 1)
            elif "</main>" in body:
                body = body.replace("</main>", card + "\n</main>", 1)
            else:
                body = card + "\n" + body
            return (body,) + rest

        body = str(html)
        if "<h1>Admin PinCabOS</h1>" in body:
            body = body.replace("<h1>Admin PinCabOS</h1>", "<h1>Admin PinCabOS</h1>\n" + card, 1)
        elif "</main>" in body:
            body = body.replace("</main>", card + "\n</main>", 1)
        else:
            body = card + "\n" + body
        return body

    @app.route("/admin/version/save", methods=["POST"])
    def pincabos_admin_version_save():
        guard = pincabos_admin_require_login()
        if guard:
            return guard

        import json
        import datetime
        from pathlib import Path

        version_path = Path("/opt/pincabos/config/version.json")
        backup_dir = Path("/opt/pincabos/backups/version-json")
        backup_dir.mkdir(parents=True, exist_ok=True)
        version_path.parent.mkdir(parents=True, exist_ok=True)

        if version_path.exists():
            ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            backup = backup_dir / ("version.json.backup-admin-light-" + ts)
            backup.write_text(version_path.read_text(errors="replace"), encoding="utf-8")

        keys = [
            "name",
            "version",
            "build",
            "channel",
            "codename",
            "author",
            "update_channel",
            "update_base_url",
            "latest_json_url",
        ]

        clean = {}
        for key in keys:
            clean[key] = (request.form.get(key, "") or "").strip()

        clean["managed_by"] = "PinCabOS"
        clean["updated_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        version_path.write_text(
            json.dumps(clean, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8"
        )

        return redirect("/admin#version-json")

except Exception as _pco_admin_version_json_card_error:
    pass
# === PINCABOS ADMIN VERSION JSON CARD WRAPPER END ===







# === PinCabOS managed block: admin-publy-webpass-secret BEGIN ===
# Moved to modular route file by PinCabOS refactor (original lines 13078-13079).


# Moved to modular route file by PinCabOS refactor (original lines 13082-13089).


# Moved to modular route file by PinCabOS refactor (original lines 13092-13099).
# === PinCabOS managed block: admin-publy-webpass-secret END ===

# === PINCABOS ADMIN PUBLISH IFRAME GET ROUTES START ===

# Moved to modular route file by PinCabOS refactor (original lines 13104-13118).



# === PinCabOS managed block: admin-publy-helper BEGIN ===
# Moved to modular route file by PinCabOS refactor (original lines 13123-13140).
# === PinCabOS managed block: admin-publy-helper END ===


# Moved to modular route file by PinCabOS refactor (original lines 13144-13150).


# Moved to modular route file by PinCabOS refactor (original lines 13153-13159).




# Moved to modular route file by PinCabOS refactor (original lines 13164-13177).

# Moved to modular route file by PinCabOS refactor (original lines 13179-13184).

# Moved to modular route file by PinCabOS refactor (original lines 13186-13191).



# === PinCabOS managed block: admin-log-helpers BEGIN ===
# Moved to modular route file by PinCabOS refactor (original lines 13196-13199).


# Moved to modular route file by PinCabOS refactor (original lines 13202-13219).


# Moved to modular route file by PinCabOS refactor (original lines 13222-13258).


# Moved to modular route file by PinCabOS refactor (original lines 13261-13283).
# === PinCabOS managed block: admin-log-helpers END ===


# Moved to modular route file by PinCabOS refactor (original lines 13287-13301).

# Moved to modular route file by PinCabOS refactor (original lines 13303-13348).

# Moved to modular route file by PinCabOS refactor (original lines 13350-13360).

# Moved to modular route file by PinCabOS refactor (original lines 13362-13375).

# Moved to modular route file by PinCabOS refactor (original lines 13377-13396).
# === PINCABOS ADMIN LOGS MANAGER END ===


# Stage5B.4B: legacy route disabled, real iframe route is pincabos_admin_frame_cleanup_dry_run.
# Moved to modular route file by PinCabOS refactor (original lines 13401-13406).

# Stage5B.4B: legacy route disabled, real iframe route is pincabos_admin_frame_cleanup_apply.
# Moved to modular route file by PinCabOS refactor (original lines 13409-13414).


# Moved to modular route file by PinCabOS refactor (original lines 13417-13420).

# Moved to modular route file by PinCabOS refactor (original lines 13422-13517).

# Moved to modular route file by PinCabOS refactor (original lines 13519-13559).

# Moved to modular route file by PinCabOS refactor (original lines 13561-13567).

# Moved to modular route file by PinCabOS refactor (original lines 13569-13575).

# Stage5B.4B: legacy route disabled, real iframe route is pincabos_admin_frame_cleanup_dry_run.
# Moved to modular route file by PinCabOS refactor (original lines 13578-13583).

# Stage5B.4B: legacy route disabled, real iframe route is pincabos_admin_frame_cleanup_apply.
# Moved to modular route file by PinCabOS refactor (original lines 13586-13591).

# Moved to modular route file by PinCabOS refactor (original lines 13593-13605).

# Moved to modular route file by PinCabOS refactor (original lines 13607-13615).
# === PINCABOS ADMIN HIDDEN PAGE END ===


# Moved to modular route file by PinCabOS refactor (original lines 13619-13631).


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
        helper = str(pco_script("vpinfe_vpsdb_match"))
        r = subprocess.run(
            [helper, table_name, rom or ""],
            capture_output=True,
            text=True,
            timeout=30
        )

        if r.returncode != 0:
            print(f"PCO VPSdb helper failed rc={r.returncode}: {helper} stderr={r.stderr[-1200:]}")
            return []

        raw = (r.stdout or "").strip()
        if not raw:
            print(f"PCO VPSdb helper returned empty output: {helper}")
            return []

        data = json.loads(raw)
        if not data.get("ok"):
            print(f"PCO VPSdb helper returned error: {data.get('error', 'unknown error')}")
            return []

        return data.get("matches", [])
    except Exception as exc:
        print(f"PCO VPSdb matcher exception: {exc}")
        return []


def pincabos_get_vpinfe_paths_for_tools():
    """
    Chemins utilisés par VPinFE / PinCabOs.
    On lit tablerootdir si disponible, sinon on utilise le chemin PinCabOs standard.
    """
    from pathlib import Path

    cfg_path = pincabos_vpx_ini_path()

    result = {
        "config": str(cfg_path),
        "tables": "/home/pinball/Tables",
        "roms": "/home/pinball/.vpinball/pinmame/roms",
        "altcolor": "/home/pinball/.vpinball/pinmame/altcolor",
        "altsound": "/home/pinball/.vpinball/pinmame/altsound",
        "pupvideos": "/home/pinball/.vpinball/pupvideos",
        "ultradmd": "/home/pinball/.vpinball/ultradmd",
        "exports": "/home/pinball/Exports",
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
    root = tables.parent if tables.exists() else Path("/home/pinball")

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
VPX_BALLCAB_PRIMARY_INI = pincabos_vpx_ini_path()
VPX_BALLCAB_SECONDARY_INI = pincabos_vpx_ini_path()
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


# === PINCABOS VPX BALLCAB IMAGE PREVIEW PHASE 1 FIX START ===
# PinCabOs-File block created by Karots Sugarpie
# Dependencies / requisites:
# - /home/pinball/.vpinball/UserBalls
# - /home/pinball/.vpinball
# - /home/pinball/Tables
# - /opt/pincabos/media
# - /opt/pincabos/apps/vpinball
# - Flask send_file/request already imported
# Created by Karots Sugarpie

VPX_BALLCAB_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
VPX_BALLCAB_IMAGE_KEYS = {"BallImage", "DecalImage", "Image", "SphereMap"}
VPX_BALLCAB_IMAGE_ROOTS = [
    Path("/home/pinball/.vpinball/UserBalls"),
    Path("/home/pinball/.vpinball"),
    Path("/home/pinball/Tables"),
    Path("/opt/pincabos/media"),
    Path("/opt/pincabos/apps/vpinball"),
]
VPX_BALLCAB_IMAGE_SKIP_PARTS = {
    ".git", ".venv", "__pycache__", "backups", "backup", "logs", "log", "cache", "tmp", "temp"
}


def vpx_ballcab_safe_image_roots():
    roots = []
    for root in VPX_BALLCAB_IMAGE_ROOTS:
        try:
            if root.exists() and root.is_dir():
                roots.append(root.resolve())
        except Exception:
            pass
    return roots


def vpx_ballcab_image_allowed(path):
    try:
        real = Path(path).resolve()
    except Exception:
        return False

    if real.suffix.lower() not in VPX_BALLCAB_IMAGE_EXTS:
        return False

    for root in vpx_ballcab_safe_image_roots():
        try:
            if real == root or root in real.parents:
                return True
        except Exception:
            pass

    return False


def vpx_ballcab_image_url(path):
    try:
        real = Path(path).resolve()
    except Exception:
        return ""

    if not vpx_ballcab_image_allowed(real):
        return ""

    return "/tools/vpx-ball-cabinet/image?path=" + urllib.parse.quote(str(real), safe="")







VPX_BALLCAB_BROWSE_DIR = Path("/opt/pincabos/media/images/balls")
VPX_BALLCAB_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}


def vpx_ballcab_list_images():
    """
    Browse scope intentionally restricted to:
    /opt/pincabos/media/images/balls

    Created by Karots Sugarpie
    """
    from urllib.parse import quote

    root = VPX_BALLCAB_BROWSE_DIR
    images = []

    if not root.exists() or not root.is_dir():
        return images

    for p in sorted(root.rglob("*"), key=lambda x: str(x).lower()):
        try:
            if not p.is_file():
                continue

            if p.suffix.lower() not in VPX_BALLCAB_IMAGE_EXTS:
                continue

            resolved = p.resolve()
            root_resolved = root.resolve()

            # Hard safety: never expose anything outside the requested directory.
            if root_resolved not in resolved.parents and resolved != root_resolved:
                continue

            rel = resolved.relative_to(root_resolved).as_posix()

            images.append({
                "name": resolved.name,
                "rel": rel,
                "path": str(resolved),
                "url": "/tools/vpx-ball-cabinet/image?path=" + quote(str(resolved), safe="")
            })
        except Exception:
            continue

    return images


def vpx_ballcab_find_image(value, images=None):
    if images is None:
        images = vpx_ballcab_list_images()

    needle = (value or "").replace("\\\\", "/").strip().lower()
    needle_name = needle.split("/")[-1] if needle else ""

    if not needle:
        return None

    for item in images:
        name = (item.get("name") or "").replace("\\\\", "/").strip().lower()
        rel = (item.get("rel") or "").replace("\\\\", "/").strip().lower()
        path = (item.get("path") or "").replace("\\\\", "/").strip().lower()

        if needle in [name, rel, path]:
            return item

        if needle_name and needle_name == name:
            return item

        if rel.endswith("/" + needle) or path.endswith("/" + needle):
            return item

    return None


@app.route("/tools/vpx-ball-cabinet/image")
def tools_vpx_ball_cabinet_image():
    value = request.args.get("path", "")
    item = vpx_ballcab_find_image(value, vpx_ballcab_list_images())

    if not item:
        return "Image not found in /opt/pincabos/media/images/balls", 404

    return send_file(item["path"])


def vpx_ballcab_current_preview(lines):
    """
    Build the read-only technical preview shown under VPX Ball / Cabinet.

    Created by Karots Sugarpie
    """
    out = []

    for section, keys in VPX_BALLCAB_KEYS.items():
        out.append("[" + section + "]")

        for key, label in keys:
            val = vpx_ballcab_get_value(lines, section, key)
            out.append(key + "=" + (val if val else ""))

        out.append("")

    return "\n".join(out).strip()


@app.route("/tools/vpx-ball-cabinet/images.json")
def tools_vpx_ball_cabinet_images_json():
    try:
        return jsonify({"ok": True, "images": vpx_ballcab_list_images()})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "images": []}), 500


def vpx_ballcab_rows(lines):
    """
    Rebuild original hidden table rows used by the clean-grid JavaScript editor.
    The visible UI moves these real form inputs into the grid, so form submit remains intact.

    Created by Karots Sugarpie
    """
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
    body = body.replace("</form>", "</form><script src=\"/static/pincabos-vpxball-cabinet.js?v=cleangridv4\"></script>", 1)
    body = body.replace("__INI__", esc(str(ini)))
    body = body.replace("__OTHER__", esc(str(other)))
    body = body.replace("__OTHER_INFO__", esc(other_info))
    body = body.replace("__ROWS__", vpx_ballcab_rows(lines))
    body = body.replace("__PREVIEW__", esc(vpx_ballcab_current_preview(lines)))

    return page("Outils", body)


def vpx_ballcab_normalize_image_value(value):
    """
    Normalize VPX Ball/Cabinet image values to absolute paths inside:
    /opt/pincabos/media/images/balls

    VPX tested OK with absolute paths; filename-only values can fail to open.

    Created by Karots Sugarpie
    """
    value = (value or "").strip()
    if not value:
        return ""

    image_keys_root = Path("/opt/pincabos/media/images/balls").resolve()

    try:
        p = Path(value)

        if p.is_absolute():
            rp = p.resolve()
            if image_keys_root in rp.parents:
                return str(rp)
            if rp == image_keys_root:
                return str(rp)

        candidate = (image_keys_root / p.name).resolve()
        if candidate.exists() and image_keys_root in candidate.parents:
            return str(candidate)
    except Exception:
        pass

    return value



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
VPX_SIMPLE_BALL_INI = pincabos_vpx_ini_path()
VPX_SIMPLE_BALL_USERBALLS_DIR = Path("/home/pinball/.vpinball/UserBalls")
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


# === PINCABOS AUDIO WAV STOP ROUTE FIX START ===
# Moved to modular route file by PinCabOS refactor (original lines 14990-15004).
# === PINCABOS AUDIO WAV STOP ROUTE FIX END ===



# /tools route is registered from tools.py
# Moved to modular route file by PinCabOS refactor (original lines 15010-15044).


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
                    table_root = pincabos_vpx_tables_dir() / table_folder
                    if table_root.exists():
                        return pincabos_manifest_import_conflict_page(batch_dir, archive_path, table_folder)

                result = pincabos_import_from_manifest_dir(extract_dir, overwrite_existing=False)
                if result:
                    if result.get("skipped") and "CONFLICT_TABLE_EXISTS" in result.get("skipped", []):
                        return pincabos_manifest_import_conflict_page(batch_dir, archive_path, result.get("table_folder", table_folder or "Imported Table"))

                    result["message"] = "Package PinCabOs détecté — import direct par manifest, analyse VPSdb ignorée."

                    # Nettoyage du batch upload après import manifest.
                    try:
                        uploads_root = Path("/home/pinball/Downloads").resolve()
                        batch_real = Path(batch_dir).resolve()
                        if batch_real.exists() and uploads_root in batch_real.parents:
                            shutil.rmtree(batch_real)
                    except Exception as e:
                        result.setdefault("skipped", [])
                        result["skipped"].append(f"WARNING cleanup upload batch: {e}")

                    return pincabos_manifest_import_result_page(result)

        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            try:
                log_dir = Path("/opt/pincabos/logs")
                log_dir.mkdir(parents=True, exist_ok=True)
                log_file = log_dir / "import-manifest-error.log"
                with log_file.open("a", encoding="utf-8") as lf:
                    lf.write("\n=== IMPORT_MANIFEST_TRACEBACK ===\n")
                    lf.write(f"archive_path={archive_path}\n")
                    lf.write(f"batch_dir={batch_dir}\n")
                    lf.write(tb)
                    lf.write("\n")
            except Exception:
                pass

            return page("Import PinCabOs", f"""
<div class="card">
  <h2>Import PinCabOs impossible</h2>
  <p class="bad">Package PinCabOs détecté, mais erreur pendant l’import manifest.</p>
  <pre>{esc(str(e))}</pre>
  <p class="warn">Traceback complet écrit dans <code>/opt/pincabos/logs/import-manifest-error.log</code></p>
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

    uploads_root = Path("/home/pinball/Downloads").resolve()

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
    batch_dir = Path("/home/pinball/Downloads") / f"batch-{job_id}"
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
    table_root = pincabos_vpx_tables_dir() / table_folder

    suggested = table_folder
    i = 2
    while (pincabos_vpx_tables_dir() / suggested).exists():
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


# Moved to modular route file by PinCabOS refactor (original lines 15782-15833).


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
    table_root = pincabos_vpx_tables_dir() / table_folder

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
            "/home/pinball/Downloads/",
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
            [str(pco_script("vpinfe_vpx_standard")), "--apply"],
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
    imports_root = Path("/home/pinball/Downloads").resolve()

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
        str(pco_script("smart_archive_import")),
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
        for work_root in [Path("/home/pinball/Downloads/work"), Path("/home/pinball/Downloads/work")]:
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
        "Exports": Path("/home/pinball/Exports"),
        "Imports temporaires": Path("/home/pinball/Downloads"),
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
        pco_smb_mount_helper_command(source, mount_point, cred_file)
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
        "Tables": pincabos_vpx_tables_dir(),
        "Exports": Path("/home/pinball/Exports"),
        "Imports": Path("/home/pinball/Downloads"),
        "Home Pinball": Path("/home/pinball"),
        "Logs": Path("/opt/pincabos/logs"),
        "Backups": Path("/opt/pincabos/backups"),
        "Medias": Path("/opt/pincabos/media"),
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
        elif name == "Logs":
            icon = "📋"
        elif name == "Backups":
            icon = "🗄️"
        elif name == "Medias":
            icon = "🎞️"
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
  border-radius:8px;
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
  border-radius:8px;
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
  border-radius:8px;
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
  border-radius:8px;
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
  background: var(--pco-appearance-nav-active-bg, #ff7a00) !important;
  color: var(--pco-appearance-nav-active-text, #160020) !important;
  border: 1px solid var(--pco-appearance-accent, #ffb000) !important;
  box-shadow: 0 0 14px rgba(255,122,0,0.45) !important;
}

.pcx-page a.pcx-btn[href="/tools"]:hover {
  background: #ffb000 !important;
  color: var(--pco-appearance-nav-active-text, #160020) !important;
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
    ? selected[0].replace(/\\/+$/g, '').split('/').pop().replace(/\\.zip$/i, '')
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

        clip_path = Path("/home/pinball/Downloads/commander-clipboard.json")
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

        clip_path = Path("/home/pinball/Downloads/commander-clipboard.json")
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
        "tables_root": pincabos_vpx_tables_dir(),
        "exports_root": Path("/home/pinball/Exports"),
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
            Path("/home/pinball/Downloads").resolve(),
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
            Path("/home/pinball/Downloads").resolve(),
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
                    [str(pco_script("import_portable_normalize")), "--table", td.name],
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
# Moved to modular route file by PinCabOS refactor (original lines 18659-18660).

# Moved to modular route file by PinCabOS refactor (original lines 18662-18698).

# Moved to modular route file by PinCabOS refactor (original lines 18700-18704).

# Moved to modular route file by PinCabOS refactor (original lines 18706-18729).

# Moved to modular route file by PinCabOS refactor (original lines 18731-18733).

# Moved to modular route file by PinCabOS refactor (original lines 18735-18741).

# Moved to modular route file by PinCabOS refactor (original lines 18743-18755).

# Moved to modular route file by PinCabOS refactor (original lines 18757-18767).

# Moved to modular route file by PinCabOS refactor (original lines 18769-18783).

# Moved to modular route file by PinCabOS refactor (original lines 18785-18795).

# Moved to modular route file by PinCabOS refactor (original lines 18797-18870).

# Moved to modular route file by PinCabOS refactor (original lines 18872-18878).

# Moved to modular route file by PinCabOS refactor (original lines 18880-18881).

# Moved to modular route file by PinCabOS refactor (original lines 18883-18924).


# Moved to modular route file by PinCabOS refactor (original lines 18927-18951).


# Moved to modular route file by PinCabOS refactor (original lines 18954-19312).


# Moved to modular route file by PinCabOS refactor (original lines 19315-19378).


# Moved to modular route file by PinCabOS refactor (original lines 19381-19419).


# Moved to modular route file by PinCabOS refactor (original lines 19422-19450).
# === INPUTS COMMANDER V1 - PINCABOS END ===


# Stage5A.3: route legacy retirée pour éviter doublon avec pcos_update_api_status.
# Moved to modular route file by PinCabOS refactor (original lines 19455-19488).


# Moved to modular route file by PinCabOS refactor (original lines 19491-19502).


# Moved to modular route file by PinCabOS refactor (original lines 19505-19541).


# Moved to modular route file by PinCabOS refactor (original lines 19544-19547).

# Moved to modular route file by PinCabOS refactor (original lines 19549-19784).


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

    # PCO_STATUS_SYNC_INSTALL_SH
    # Quand le bouton Vérifier appelle /pcos-update-api/status,
    # on resynchronise les scripts install locaux depuis https://ins.pincabos.cc/install.
    install_sync_ok = False
    install_sync_log = ""
    try:
        import subprocess as _pco_subprocess
        _pco_sync_script = "/opt/pincabos/scripts/pincabos-update-channel-check.sh"
        _pco_sync = _pco_subprocess.run(
            [_pco_sync_script],
            stdout=_pco_subprocess.PIPE,
            stderr=_pco_subprocess.STDOUT,
            text=True,
            timeout=300,
        )
        install_sync_ok = (_pco_sync.returncode == 0)
        install_sync_log = _pco_sync.stdout or ""
    except Exception as e:
        install_sync_ok = False
        install_sync_log = "Erreur sync install: " + repr(e)

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

    latest_url = cfg.get("latest_json_url", "https://ins.pincabos.cc/install/pkg/latest.json")

    try:
        req = urllib.request.Request(
            latest_url,
            headers={
                "User-Agent": "PinCabOS-Updater/1.0",
                "Accept": "application/json,*/*",
                "Cache-Control": "no-cache",
            },
        )
        with urllib.request.urlopen(req, timeout=12) as r:
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
        "latest_error": latest_error,
        "install_sync_ok": install_sync_ok,
        "install_sync_log_tail": install_sync_log[-12000:]
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
            raw_status = status_path.read_text(errors="replace").strip()
            if raw_status.endswith("\\n"):
                raw_status = raw_status[:-2].rstrip()
            loaded = json.loads(raw_status)
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
    script = str(pco_script("apply_update"))

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
            "message": "Force system update lancé" if force else "Mise à jour PinCabOS WebApp lancé"
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

    latest_url = cfg.get("latest_json_url", "https://ins.pincabos.cc/install/pkg/latest.json")
    latest = {}
    latest_error = None

    # PCO_INSTALL_SYNC_IN_STATUS_REAL
    install_sync_ok = False
    install_sync_log_tail = ""
    try:
        import subprocess as _pco_subprocess
        _sync_script = "/opt/pincabos/scripts/pincabos-update-channel-check.sh"
        _sync_proc = _pco_subprocess.run(
            [_sync_script],
            stdout=_pco_subprocess.PIPE,
            stderr=_pco_subprocess.STDOUT,
            text=True,
            timeout=300,
        )
        install_sync_ok = (_sync_proc.returncode == 0)
        install_sync_log_tail = (_sync_proc.stdout or "")[-12000:]
    except Exception as e:
        install_sync_ok = False
        install_sync_log_tail = "Erreur sync install: " + repr(e)

    try:
        req = urllib.request.Request(
            latest_url,
            headers={
                "User-Agent": "PinCabOS-Updater/1.0",
                "Accept": "application/json,*/*",
                "Cache-Control": "no-cache",
            },
        )
        with urllib.request.urlopen(req, timeout=12) as r:
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
        "latest_error": latest_error,
        "install_sync_ok": install_sync_ok,
        "install_sync_log_tail": install_sync_log_tail
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
            raw_status = status_path.read_text(errors="replace").strip()
            if raw_status.endswith("\\n"):
                raw_status = raw_status[:-2].rstrip()
            loaded = json.loads(raw_status)
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
    import os
    import json
    import pathlib
    import subprocess
    import time
    import datetime
    from flask import request, jsonify

    mode = request.args.get("mode", "webapp").strip().lower()
    if mode not in ("webapp", "system"):
        return jsonify({"ok": False, "error": "Mode invalide", "mode": mode}), 400

    runner = "/opt/pincabos/bin/pincabos-update-engine-runner.sh"
    if not os.path.exists(runner):
        return jsonify({"ok": False, "error": "Runner absent", "runner": runner}), 500

    log_dir = pathlib.Path("/opt/pincabos/logs/updates")
    log_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = log_dir / f"pincabos-update-{mode}-{ts}.log"
    status_path = log_dir / "pincabos-update-status.json"

    title = "MAJ System complète" if mode == "system" else "Mise à jour PinCabOS WebApp"
    now = datetime.datetime.now().isoformat(timespec="seconds")

    log_path.write_text(
        "────────────────────────────────────────────────────────────────\\n"
        f" PinCabOS - {title}\\n"
        f" Préparation lancement runner sudo direct\\n"
        f" Mode: {mode}\\n"
        f" Runner: {runner}\\n"
        "────────────────────────────────────────────────────────────────\\n\\n",
        encoding="utf-8"
    )

    status = {
        "ok": True,
        "running": True,
        "state": "starting",
        "percent": 1,
        "step": title,
        "message": "Préparation du lancement runner...",
        "target": mode,
        "mode": mode,
        "log": str(log_path),
        "reboot_required": mode == "system",
        "awaiting_reboot": False,
        "updated_at": now,
        "events": [f"[{now}] {title} - préparation lancement"],
    }
    status_path.write_text(json.dumps(status, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    unit = "pincabos-update-" + mode + "-" + str(int(time.time()))
    cmd = [runner, mode]

    if os.geteuid() != 0:
        cmd = ["/usr/bin/sudo", "-n"] + cmd

    try:
        with log_path.open("a", encoding="utf-8") as f:
            f.write("Commande runner:\\n")
            f.write(" ".join(cmd) + "\\n\\n")

        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            env={**os.environ, "PINCABOS_UPDATE_LOG": str(log_path)},
        )

        now = datetime.datetime.now().isoformat(timespec="seconds")
        status.update({
            "ok": True,
            "running": True,
            "state": "running",
            "percent": 3,
            "step": title,
            "message": "Runner lancé. Lecture du log live...",
            "updated_at": now,
        })
        status["events"].append(f"[{now}] Runner lancé: {unit}")
        status_path.write_text(json.dumps(status, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

        return jsonify({
            "ok": True,
            "started": True,
            "mode": mode,
            "target": mode,
            "unit": unit,
            "cmd": cmd,
            "message": "MAJ System complète lancée via 02-install-engine.sh" if mode == "system" else "Mise à jour WebApp lancée via 02-install-engine.sh --webapp",
            "reboot_after_success": mode == "system",
            "log": str(log_path),
        })

    except Exception as e:
        now = datetime.datetime.now().isoformat(timespec="seconds")
        status.update({
            "ok": False,
            "running": False,
            "state": "failed",
            "percent": 100,
            "step": "Erreur lancement update",
            "message": str(e),
            "updated_at": now,
        })
        status["events"].append(f"[{now}] Exception lancement: {e}")
        status_path.write_text(json.dumps(status, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

        with log_path.open("a", encoding="utf-8") as f:
            f.write("\\nNOGOOD: exception lancement update\\n")
            f.write(str(e) + "\\n")

        return jsonify({
            "ok": False,
            "mode": mode,
            "error": str(e),
            "log": str(log_path),
        }), 500


# Moved to modular route file by PinCabOS refactor (original lines 20218-20279).


# Moved to modular route file by PinCabOS refactor (original lines 20282-20286).


# Moved to modular route file by PinCabOS refactor (original lines 20289-20293).


# Stage5A.3: route legacy retirée pour éviter doublon avec pcos_update_api_reboot.
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




# --- PinCabOS update channel check patch ---
# Moved to modular route file by PinCabOS refactor (original lines 20393-20476).


# Moved to modular route file by PinCabOS refactor (original lines 20479-20529).
# --- /PinCabOS update channel check patch ---



# Removed obsolete duplicate route block: # === PINCABOS VMTEST ROUTE ALIASES START ===


# Removed obsolete duplicate route block: # === PINCABOS VMTEST CONSOLE PAGE START ===




# === PinCabOS cab-current route aliases ===
# Compatibilité routes/menu après nettoyage Alpha 1.1.
# Ces routes ne remplacent pas les fonctions existantes; elles évitent les 404 de boutons/menu.

@app.route("/wifi")
def pincabos_alias_wifi():
    return redirect("/network", code=302)

@app.route("/screens")
def pincabos_alias_screens():
    # La vraie gestion écrans est maintenant dans GPU / Screens.
    try:
        return redirect("/gpu/screens", code=302)
    except Exception:
        return redirect("/gpu", code=302)

@app.route("/outputs")
def pincabos_alias_outputs():
    # Outputs = ancien DOF côté menu.
    return redirect("/dof", code=302)

# Moved to modular route file by PinCabOS refactor (original lines 20663-20674).

@app.route("/network/hostname", methods=["POST"])
def pincabos_network_hostname_alias():
    # Empêche le formulaire hostname de tomber en 404 si l'action existe dans l'ancien HTML.
    # On ne change pas le hostname ici pour éviter un patch réseau agressif.
    return redirect("/network", code=303)

@app.route("/tools/external-disks/usb/unmount", methods=["POST"])
def pincabos_tools_usb_unmount_alias():
    # Route placeholder sûre: ne démonte rien à l’aveugle.
    return redirect("/tools", code=303)

@app.route("/tools/external-disks/smb/unmount", methods=["POST"])
def pincabos_tools_smb_unmount_alias():
    # Route placeholder sûre: ne démonte rien à l’aveugle.
    return redirect("/tools", code=303)

@app.route("/api/dof/manager/")
def pincabos_api_dof_manager_slash_alias():
    # Compatibilité avec fetch('/api/dof/manager/').
    return jsonify({"ok": True, "status": "available", "message": "DOF manager route alias active"})

# === PINCABOS LEGACY ROUTE ALIASES - BGFX MIGRATION ===
# Created by Karots Sugarpie
# Purpose:
#   Keep Alpha15/old menu URLs working after Alpha16 tools route migration.
# Safety:
#   Redirect-only aliases. No filesystem or config mutation.

@app.route("/external-disks")
@app.route("/external-disks/")
def pincabos_legacy_external_disks_alias():
    return redirect("/tools/external-disks", code=302)

@app.route("/import")
@app.route("/import/")
def pincabos_legacy_import_alias():
    return redirect("/tools", code=302)

@app.route("/tables")
@app.route("/tables/")
def pincabos_legacy_tables_alias():
    return redirect("/tools", code=302)

# === PINCABOS LEGACY ROUTE ALIASES - END ===


# === PINCABOS MENU CLOSE ACTIVE CHROME TAB START ===
@app.route("/api/menu/close-tab", methods=["POST"])
def pincabos_menu_close_tab_api():
    import os
    import subprocess
    from flask import jsonify

    helper = "/opt/pincabos/bin/pincabos-close-active-chrome-tab.sh"

    if not os.path.exists(helper):
        return jsonify({"ok": False, "error": "helper_missing", "helper": helper}), 500

    env = os.environ.copy()
    env.setdefault("DISPLAY", ":0")

    # Best effort Xauthority discovery for the pinball desktop session.
    for xa in (
        "/home/pinball/.Xauthority",
        "/var/run/lightdm/root/:0",
        "/run/user/1000/gdm/Xauthority",
        "/run/user/1000/Xauthority",
    ):
        if os.path.exists(xa):
            env.setdefault("XAUTHORITY", xa)
            break

    try:
        proc = subprocess.run(
            [helper],
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=3,
        )
        return jsonify({
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "output": proc.stdout[-2000:],
        }), (200 if proc.returncode == 0 else 500)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500
# === PINCABOS MENU CLOSE ACTIVE CHROME TAB END ===



# PinCabOS dashboard-plus final display correction
# Corrects stale dashboard-plus display values without rewriting the whole dashboard.
def _pco_dashboard_plus_final_detect_vpx():
    import os
    import subprocess
    import re

    candidates = [
        "/opt/pincabos/bin/vpx.sh",
        "/opt/pincabos/apps/vpinball/VPinballX-BGFX",
        "/opt/pincabos/apps/vpinball/VPinballX",
        "/opt/pincabos/apps/vpinball/VPinballX_GL",
        "/opt/pincabos/apps/vpinball/VPinballX-BGFX",
    ]

    existing = [x for x in candidates if os.path.exists(x)]
    if not existing:
        return "non détecté"

    for exe in existing:
        for arg in ("--version", "-version", "-h", "--help"):
            try:
                r = subprocess.run(
                    [exe, arg],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    timeout=3,
                    env=dict(os.environ, DISPLAY=os.environ.get("DISPLAY", ":0")),
                )
                out = (r.stdout or "").strip()
                if not out:
                    continue

                lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
                for ln in lines[:12]:
                    if re.search(r"(VPinball|Visual Pinball|VPX|VPinballX|version|standalone)", ln, re.I):
                        ln = re.sub(r"\s+", " ", ln)
                        if len(ln) > 96:
                            ln = ln[:93] + "..."
                        return ln

                # If command responded but no clear version line.
                return "installé / version non lisible"
            except Exception:
                continue

    if "/opt/pincabos/bin/vpx.sh" in existing:
        return "installé / wrapper vpx.sh"
    return "installé / version non lisible"


def _pco_dashboard_plus_final_audio_message():
    import os
    import subprocess

    cards = ""
    try:
        if os.path.exists("/proc/asound/cards"):
            cards = open("/proc/asound/cards", "r", errors="replace").read().strip()
    except Exception:
        cards = ""

    if cards and "no soundcards" not in cards.lower():
        try:
            r = subprocess.run(["aplay", "-l"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=3)
            out = (r.stdout or "").strip()
            if out and "no soundcards" not in out.lower():
                return None
        except Exception:
            return None

    return "Aucune carte audio ALSA détectée par Linux dans cette VM/session. Ce n’est pas une erreur PinCabOS si la VM n’a pas de périphérique audio attaché. Sur un cabinet réel, vérifier avec aplay -l, pactl list short sinks et wpctl status."


def _pco_dashboard_plus_final_html_fix(html):
    if not isinstance(html, str):
        return html

    vpx_label = _pco_dashboard_plus_final_detect_vpx()
    audio_msg = _pco_dashboard_plus_final_audio_message()

    # Correct stale service name.
    html = html.replace("pincabos-webapp.service", "pincabos-webapp.service")

    # Correct old VPX runtime path.
    html = html.replace("/opt/pincabos/apps/vpinball", "/opt/pincabos/apps/vpinball")

    # Correct rendered VPX version text.
    html = html.replace("VPX : non détecté", "VPX : " + vpx_label)
    html = html.replace("VPX&nbsp;: non détecté", "VPX&nbsp;: " + vpx_label)

    # Correct common HTML separated VPX value patterns.
    html = re.sub(
        r"(VPX\s*</[^>]+>\s*<[^>]+>)(non détecté|non detecte|not detected)(</[^>]+>)",
        r"\1" + vpx_label + r"\3",
        html,
        flags=re.I,
    )

    # Clarify audio if Linux has no audio device.
    if audio_msg:
        html = html.replace(
            "Aucune sortie audio ALSA détectée par le dashboard.",
            audio_msg,
        )
        html = html.replace(
            "Aucune configuration audio sauvegardée.",
            "Aucune configuration audio sauvegardée. Le dashboard ne peut pas mapper SSF V2 tant qu’aucune carte audio Linux n’est visible.",
        )

    # Make essential path labels current.
    html = html.replace("VPX runtime", "VPX runtime")
    html = html.replace("VPinFE runtime", "VPinFE runtime")

    return html


def _pco_dashboard_plus_final_install_wrapper():
    try:
        dashboard_rules = []
        for rule in list(app.url_map.iter_rules()):
            r = str(rule.rule).lower()
            if "dashboard" in r or "dashbord" in r or r == "/":
                dashboard_rules.append(rule)

        for rule in dashboard_rules:
            endpoint = rule.endpoint
            old_view = app.view_functions.get(endpoint)
            if not old_view or getattr(old_view, "_pco_dashboard_plus_final_wrapped", False):
                continue

            def _make_wrapper(fn):
                def _wrapped(*args, **kwargs):
                    resp = fn(*args, **kwargs)

                    try:
                        flask_resp = app.make_response(resp)
                        ctype = flask_resp.headers.get("Content-Type", "")
                        if "text/html" in ctype or ctype.startswith("text/") or ctype == "":
                            data = flask_resp.get_data(as_text=True)
                            fixed = _pco_dashboard_plus_final_html_fix(data)
                            if fixed != data:
                                flask_resp.set_data(fixed)
                                flask_resp.headers["Content-Length"] = str(len(flask_resp.get_data()))
                        return flask_resp
                    except Exception:
                        return resp

                _wrapped._pco_dashboard_plus_final_wrapped = True
                _wrapped.__name__ = getattr(fn, "__name__", "dashboard_plus_final_wrapped")
                return _wrapped

            app.view_functions[endpoint] = _make_wrapper(old_view)

        print("GO: dashboard-plus final correction wrapper installed")
    except Exception as exc:
        print("NOGO: dashboard-plus final correction wrapper failed:", exc)


_pco_dashboard_plus_final_install_wrapper()


# === PINCABOS MODULAR ROUTES REGISTRATION START ===
# Registration occurs after the core helpers are defined so modules can reuse the one canonical layout and services.
for _pco_module in (
    pco_audio_routes,
    pco_inputs_routes,
    pco_firstrun_routes,
    pco_updates_routes,
    pco_dev_admin_routes,
    pco_exports_routes,
):
    _pco_module.register(app, globals())
del _pco_module
# === PINCABOS MODULAR ROUTES REGISTRATION END ===

if __name__ == "__main__":
    app.run(host=os.environ.get("PINCABOS_WEB_HOST", os.environ.get("PCO_WEB_HOST", "127.0.0.1")), port=int(os.environ.get("PINCABOS_WEB_PORT", os.environ.get("PCO_WEB_PORT", "5055"))), debug=False)

