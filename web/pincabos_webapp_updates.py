# PinCabOS WebApp module: Update UI and update job routes.
# Generated from the monolithic app.py refactor.
# The host app injects legacy shared helpers during register().
from __future__ import annotations

import glob
import html
import json
import os
import re
import shlex
import shutil
import socket
import struct
import subprocess
import tempfile
import time
import zipfile
from datetime import datetime
from pathlib import Path

from flask import jsonify, redirect, request, send_file, session, url_for

ROUTES: list[tuple[str, dict, object]] = []
BEFORE_REQUESTS: list[object] = []
AFTER_REQUESTS: list[object] = []

def route(rule: str, **options):
    """Record a Flask route locally; register() attaches it to the host app."""
    def decorator(func):
        ROUTES.append((rule, options, func))
        return func
    return decorator

def before_request(func):
    BEFORE_REQUESTS.append(func)
    return func

def after_request(func):
    AFTER_REQUESTS.append(func)
    return func

def register(host_app, runtime_globals: dict):
    """Bind shared helpers once, then register module-owned routes unchanged."""
    protected = {'ROUTES', 'route', 'register', '__name__', '__file__', '__package__'}
    for key, value in runtime_globals.items():
        if key not in protected:
            globals()[key] = value
    # Publish moved helpers back to the host namespace for legacy core pages that
    # still call them (for example page() -> firstrun_load_cfg()).
    prefixes = ("audio_", "ssf_", "inputs_", "firstrun_", "pincabos_", "PINCABOS_", "AUDIO_")
    for key, value in list(globals().items()):
        if key.startswith(prefixes):
            runtime_globals[key] = value
    for before_func in BEFORE_REQUESTS:
        host_app.before_request(before_func)
    for after_func in AFTER_REQUESTS:
        host_app.after_request(after_func)
    for rule, options, view_func in ROUTES:
        host_app.add_url_rule(rule, endpoint=view_func.__name__, view_func=view_func, **options)



@route("/updates")
def updates():
    vpinfe_local_version = pincabos_vpinfe_local_version()
    vpinfe_available_version = pincabos_vpinfe_available_version()

    vpinball_local_version = pincabos_vpinball_local_version()
    vpinball_available_version = pincabos_vpinball_available_version()

    gpu_local_version = pincabos_gpu_local_version()
    gpu_available_version = pincabos_gpu_available_version()

    ubuntu_local_version = pincabos_ubuntu_local_version()
    ubuntu_available_version = pincabos_ubuntu_available_version()

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
  <style>
    .pco-update-actions {
      display: flex;
      flex-direction: column;
      gap: 10px;
      margin-top: 14px;
    }

    .pco-update-row {
      display: grid !important;
      grid-template-columns: 260px minmax(150px, auto) minmax(150px, auto);
      align-items: center;
      gap: 12px;
      margin: 0;
    }

    .pco-update-row .button {
      width: 260px;
      min-width: 260px;
      max-width: 260px;
      text-align: center;
      justify-content: center;
      box-sizing: border-box;
    }

    .pco-update-row-full {
      display: grid !important;
      grid-template-columns: 260px 1fr;
      align-items: center;
      gap: 12px;
      margin-top: 14px;
    }

    .pco-update-row-full .button {
      width: 260px;
      min-width: 260px;
      max-width: 260px;
      text-align: center;
      justify-content: center;
      box-sizing: border-box;
    }

    @media (max-width: 760px) {
      .pco-update-row,
      .pco-update-row-full {
        grid-template-columns: 1fr;
      }

      .pco-update-row .button,
      .pco-update-row-full .button {
        width: 100%;
        min-width: 0;
        max-width: none;
      }
    }
  </style>

  <div class="card">
    <h2>Mises à jour</h2>
    <p>Utilise ces boutons pour mettre à jour les composants PinCabOS.</p>

    <div class="card" style="border:1px solid rgba(255,176,0,.45);background:rgba(255,176,0,.07);margin-bottom:14px;">
      <h2>⬆️ Mise à jour PinCabOS</h2>
      <p>Met à jour la WebApp, les outils et services PinCabOS sans écraser les tables, VPX, VPinFE ou la configuration utilisateur.</p>
      <p><a class="button" href="/pincabos-update">Ouvrir la mise à jour PinCabOS</a></p>
    </div>

    <form action="/run-update/vpinfe" method="post" class="pco-update-row">
      <button class="button" type="submit">Mettre à jour VPinFE</button>
      <span class="pill">Local : <code>__VPINFE_LOCAL_VERSION__</code></span>
      <span class="pill">Disponible : <code>__VPINFE_AVAILABLE_VERSION__</code></span>
    </form>

    <form action="/run-update/vpx" method="post" class="pco-update-row">
    <button class="button" type="submit">Mettre à jour VPX / VPinball</button>
    <span class="pill">Local : <code>__VPINBALL_LOCAL_VERSION__</code></span>
    <span class="pill">Disponible : <code>__VPINBALL_AVAILABLE_VERSION__</code></span>
  </form>

    <form action="/run-update/gpu" method="post" class="pco-update-row">
    <button class="button secondary" type="submit">Mises à jour pilotes GPU</button>
    <span class="pill">Local : <code>__GPU_LOCAL_VERSION__</code></span>
    <span class="pill">Disponible : <code>__GPU_AVAILABLE_VERSION__</code></span>
  </form>

    <form action="/run-update/system" method="post" class="pco-update-row">
    <button class="button secondary" type="submit">Mettre à jour Ubuntu</button>
    <span class="pill">Local : <code>__UBUNTU_LOCAL_VERSION__</code></span>
    <span class="pill">Disponible : <code>__UBUNTU_AVAILABLE_VERSION__</code></span>
  </form>

    <hr style="border:0;border-top:1px solid rgba(255,176,0,.25);margin:18px 0;">

    <form action="/run-update/all" method="post" class="pco-update-row-full" onsubmit="return confirm('Lancer la mise à jour complète ? Cela lance PinCabOS FORCE, VPinFE, VPX Linux, GPU et Ubuntu.');">
      <button class="button secondary" type="submit" style="border-color:#ffb000;color:#fff;background:rgba(255,122,0,.25);">Mise à jour complète</button>
      <span class="pill">Lance PinCabOS, VPinFE, VPX, GPU et Ubuntu</span>
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
    body = body.replace("__VPINFE_LOCAL_VERSION__", esc(vpinfe_local_version))
    body = body.replace("__VPINFE_AVAILABLE_VERSION__", esc(vpinfe_available_version))
    body = body.replace("__VPINBALL_LOCAL_VERSION__", esc(vpinball_local_version))
    body = body.replace("__VPINBALL_AVAILABLE_VERSION__", esc(vpinball_available_version))
    body = body.replace("__GPU_LOCAL_VERSION__", esc(gpu_local_version))
    body = body.replace("__GPU_AVAILABLE_VERSION__", esc(gpu_available_version))
    body = body.replace("__UBUNTU_LOCAL_VERSION__", esc(ubuntu_local_version))
    body = body.replace("__UBUNTU_AVAILABLE_VERSION__", esc(ubuntu_available_version))

    return page("Mises à jour", body)


@route("/api/update-status")
def api_update_status():
    return jsonify(get_job_status())


@route("/run-update/<target>", methods=["POST"])
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


# === PINCABOS OFFICIAL FULLDMD TARGET START ===
PINCABOS_FULLDMD_SCREEN_ID = 2

def pincabos_fulldmd_screen_id():
    return PINCABOS_FULLDMD_SCREEN_ID
# === PINCABOS OFFICIAL FULLDMD TARGET END ===

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


@route("/pincabos-update/run", methods=["POST"])
def pincabos_update_run():
    import subprocess
    try:
        subprocess.Popen(
            ["/usr/bin/sudo", str(pco_script("apply_update"))],
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

    script = str(pco_script("apply_update"))
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


@route("/update")
@route("/pcos-update")
def pincabos_update_alias_page():
    return redirect("/pincabos-update")


@route("/pincabos-update")
def pincabos_update_page():
    body = """
<div class="card">
  <h1>⬆️ Mise à jour PinCabOS</h1>
  <p>Cette mise à jour télécharge le dernier paquet PinCabOS depuis le serveur configuré, fait un backup local, applique les fichiers système PinCabOS, puis redémarre si requis.</p>
  <p><strong>Préservé :</strong> tables, médias, configuration VPinFE utilisateur, VPX, VPinFE upstream, fichiers cab.</p>
  <p><strong>Mis à jour :</strong> WebApp PinCabOS, outils PinCabOS, services PinCabOS, configurations système PinCabOS.</p>

  <div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:14px;margin-bottom:14px;">
    <button class="button" type="button" onclick="pcosCheckUpdate()">🔍 Vérifier</button>
    <button class="button" type="button" onclick="pcosRunUpdate(\'webapp\')">⬆️ Mise à jour PinCabOS WebApp</button>
    <button class="button secondary" type="button" onclick="pcosRunUpdate(\'system\')" style="border-color:#ff3b30;color:#fff;background:rgba(255,59,48,.25);">🔥 Mise à jour PinCabOS System</button>
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

    const ok = !data.latest_error;
    const ops = [
      "Vérification latest.json: " + (ok ? "OK" : "NOGOOD"),
      "latest_url: " + (data.latest_url || ""),
      "Config channel: " + ((data.config && data.config.channel) ? data.config.channel : ""),
      "Version locale: " + ((data.local_version && data.local_version.version) ? data.local_version.version : ""),
      ok ? "Canal de mises à jour OK, tu peux maintenant faire la mise à jour." : "NOGOOD: " + data.latest_error,
      ok ? "Updates Channel is Good, you can now update." : "Updates Channel is NOT ready."
    ];

    const bar = document.getElementById("pcosBar");
    const pctEl = document.getElementById("pcosPct");
    const step = document.getElementById("pcosStep");
    const msg = document.getElementById("pcosMsg");
    const events = document.getElementById("pcosEvents");

    if (bar) bar.style.width = "100%";
    if (pctEl) pctEl.textContent = "100%";
    if (step) step.textContent = ok ? "Vérification OK" : "Vérification NOGOOD";
    if (msg) msg.textContent = ok ? "Updates Channel is Good, you can now update." : "Updates Channel is NOT ready.";
    if (events) {
      events.textContent = ops.join("\\n");
      events.scrollTop = events.scrollHeight;
    }
  } catch(e) {
    log.textContent = "Erreur: " + e.message;
  }
}

async function pcosRunUpdate(mode) {
  const isSystem = mode === "system";
  const confirmMsg = isSystem
    ? "Lancer la MAJ System complète PinCabOS ? Le système va redémarrer après succès."
    : "Lancer la mise à jour PinCabOS WebApp seulement ?";
  if (!confirm(confirmMsg)) return;

  const log = document.getElementById("pcosUpdateLog");
  log.textContent = isSystem ? "MAJ System complète lancée..." : "Mise à jour PinCabOS WebApp lancée...";

  try {
    const url = "/pcos-update-api/run?mode=" + encodeURIComponent(isSystem ? "system" : "webapp");
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


@route("/pincabos-update/check", methods=["GET"])
def pincabos_update_check_form():
    # PCO_PATCH_UPDATE_CHECK_DOWNLOAD_INSTALL_SH
    # Avant toute vérification update, on restaure/télécharge les scripts install locaux.
    # Source officielle: https://ins.pincabos.cc/install
    try:
        import subprocess as _pco_subprocess
        _pco_script = "/opt/pincabos/scripts/pincabos-update-channel-check.sh"
        _pco_channel = _pco_subprocess.run(
            [_pco_script],
            stdout=_pco_subprocess.PIPE,
            stderr=_pco_subprocess.STDOUT,
            text=True,
            timeout=300,
        )
        _pco_channel_ok = (_pco_channel.returncode == 0)
        _pco_channel_log = (_pco_channel.stdout or "")[-12000:]
    except Exception as _pco_e:
        _pco_channel_ok = False
        _pco_channel_log = "Erreur channel install: " + repr(_pco_e)

    import json
    import pathlib
    import urllib.request
    from flask import Response

    cfg_path = pathlib.Path("/opt/pincabos/config/pincabos-update.json")
    latest_url = "https://ins.pincabos.cc/install/pkg/latest.json"

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


@route("/pincabos-update/start-normal", methods=["POST"])
def pincabos_update_start_normal_form():
    from flask import redirect
    pincabos_start_update_job(force=False)
    return redirect("/pincabos-update")


@route("/pincabos-update/start-force", methods=["POST"])
def pincabos_update_start_force_form():
    from flask import redirect
    pincabos_start_update_job(force=True)
    return redirect("/pincabos-update")


@route("/pincabos-update/check-channel", methods=["GET", "POST"])
def pincabos_update_check_channel():
    import html
    import subprocess

    script = "/opt/pincabos/scripts/pincabos-update-channel-check.sh"
    proc = subprocess.run(
        [script],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=300,
    )

    ok = proc.returncode == 0
    output = html.escape(proc.stdout or "")

    if ok:
        status_html = """
        <h1 style="color:#00c853;">Canal de mises à jour OK</h1>
        <h2 style="color:#00c853;">Updates Channel is Good, you can now update.</h2>
        <p>Les fichiers disponibles dans <strong>https://ins.pincabos.cc/install</strong> ont été téléchargés localement dans <strong>/opt/pincabos/install/</strong>.</p>
        <p>The available install files were downloaded locally into <strong>/opt/pincabos/install/</strong>.</p>
        """
    else:
        status_html = """
        <h1 style="color:#ff3b30;">Canal de mises à jour NOGOOD</h1>
        <h2 style="color:#ff3b30;">Updates Channel is NOT ready.</h2>
        <p>Un problème est arrivé pendant la vérification ou le téléchargement.</p>
        <p>A problem happened during the check or download.</p>
        """

    return f"""
    <!doctype html>
    <html>
    <head>
      <meta charset="utf-8">
      <title>PinCabOS Update Channel Check</title>
      <style>
        body {{
          background:#05070a;
          color:#f5f5f5;
          font-family:Arial, sans-serif;
          padding:28px;
        }}
        .box {{
          max-width:1100px;
          margin:auto;
          border:1px solid rgba(255,255,255,.15);
          border-radius:18px;
          padding:24px;
          background:rgba(255,255,255,.04);
        }}
        pre {{
          white-space:pre-wrap;
          background:#000;
          color:#d7ffd7;
          padding:18px;
          border-radius:12px;
          overflow:auto;
          border:1px solid rgba(255,255,255,.12);
        }}
        a.button {{
          display:inline-block;
          margin-top:14px;
          padding:12px 18px;
          border-radius:999px;
          text-decoration:none;
          color:white;
          background:#ff7a00;
          font-weight:bold;
        }}
      </style>
    </head>
    <body>
      <div class="box">
        {status_html}
        <a class="button" href="/pincabos-update">Retour / Back</a>
        <h3>Log</h3>
        <pre>{output}</pre>
      </div>
    </body>
    </html>
    """, (200 if ok else 500)


@after_request
def pincabos_update_verify_button_rewrite(response):
    try:
        from flask import request

        if request.path != "/pincabos-update":
            return response

        ctype = response.headers.get("Content-Type", "")
        if "text/html" not in ctype.lower():
            return response

        body = response.get_data(as_text=True)
        if "pco-update-channel-check-rewrite" in body:
            return response

        inject = """
<script id="pco-update-channel-check-rewrite">
document.addEventListener("DOMContentLoaded", function() {
  const target = "/pincabos-update/check-channel";
  const words = ["vérifier", "verifier", "verify", "check"];
  document.querySelectorAll("a, button, input[type=button], input[type=submit]").forEach(function(el) {
    const txt = ((el.innerText || el.value || el.textContent || "") + "").trim().toLowerCase();
    if (!words.some(w => txt.includes(w))) return;

    if (el.tagName.toLowerCase() === "a") {
      el.href = target;
      el.target = "_self";
    } else {
      el.onclick = function(ev) {
        ev.preventDefault();
        window.location.href = target;
        return false;
      };
    }
  });
});
</script>
"""

        if "</body>" in body:
            body = body.replace("</body>", inject + "\n</body>", 1)
        else:
            body += inject

        response.set_data(body)
        response.headers["Content-Length"] = str(len(response.get_data()))
    except Exception:
        return response

    return response
