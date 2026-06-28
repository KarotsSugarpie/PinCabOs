# PinCabOs-File created by Karots Sugarpie
from pathlib import Path
import subprocess
import re


def read_first(cmd, fallback=""):
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=6)
        data = (out.stdout + out.stderr).strip()
        return data if data else fallback
    except Exception:
        return fallback


def pct_bar(esc, value, label=""):
    try:
        v = float(value)
    except Exception:
        v = 0.0

    cls = "ok" if v < 50 else ("warn" if v < 80 else "bad")

    return f"""
<div style="margin:8px 0;">
  <div style="display:flex; justify-content:space-between; font-size:13px;">
    <span>{esc(label)}</span>
    <span>{v:.1f}%</span>
  </div>
  <div style="height:14px; background:#160020; border:1px solid #5f2a91; border-radius:999px; overflow:hidden;">
    <div class="{cls}" style="height:100%; width:{max(0, min(v, 100)):.1f}%; background:#ff7a00; box-shadow:0 0 12px rgba(255,122,0,0.75);"></div>
  </div>
</div>
"""


def get_cpu_usage():
    out = read_first(["bash", "--noprofile", "--norc", "-c", "top -bn2 -d 0.2 | grep 'Cpu(s)' | tail -n1"], "")
    try:
        m = re.search(r'(\d+[.,]?\d*)\s*id', out)
        if m:
            idle = float(m.group(1).replace(",", "."))
            return max(0, min(100, 100 - idle))
    except Exception:
        pass
    return 0.0


def get_cpu_info():
    model = read_first(["bash", "--noprofile", "--norc", "-c", "lscpu | awk -F: '/Model name/ {gsub(/^ +/,\"\",$2); print $2; exit}'"], "inconnu")
    cpus = read_first(["bash", "--noprofile", "--norc", "-c", "nproc"], "0")
    details = read_first(["bash", "--noprofile", "--norc", "-c", "lscpu | grep -E 'Model name|Socket\\(s\\)|Core\\(s\\) per socket|Thread\\(s\\) per core|CPU\\(s\\)'"], "")
    return model, cpus, details


def get_memory_info():
    total = read_first(["bash", "--noprofile", "--norc", "-c", "free -h | awk '/Mem:/ {print $2}'"], "inconnu")
    used = read_first(["bash", "--noprofile", "--norc", "-c", "free -h | awk '/Mem:/ {print $3}'"], "inconnu")
    pct = read_first(["bash", "--noprofile", "--norc", "-c", "free | awk '/Mem:/ {printf \"%.1f\", $3/$2*100}'"], "0")
    mem_type = read_first(["bash", "--noprofile", "--norc", "-c", "dmidecode -t memory 2>/dev/null | awk -F: '/Type:/ && $2 !~ /Unknown|Other/ {gsub(/^ +/,\"\",$2); print $2; exit}'"], "non détecté / VM")
    mem_speed = read_first(["bash", "--noprofile", "--norc", "-c", "dmidecode -t memory 2>/dev/null | awk -F: '/Speed:/ && $2 !~ /Unknown/ {gsub(/^ +/,\"\",$2); print $2; exit}'"], "non détecté")
    return total, used, pct, mem_type, mem_speed


def get_disk_info():
    root_pct = read_first(["bash", "--noprofile", "--norc", "-c", "df -P / | awk 'NR==2 {gsub(\"%\",\"\",$5); print $5}'"], "0")
    root_used = read_first(["bash", "--noprofile", "--norc", "-c", "df -h / | awk 'NR==2 {print $3\" / \"$2}'"], "inconnu")
    opt_pct = read_first(["bash", "--noprofile", "--norc", "-c", "df -P /opt 2>/dev/null | awk 'NR==2 {gsub(\"%\",\"\",$5); print $5}'"], root_pct)
    opt_used = read_first(["bash", "--noprofile", "--norc", "-c", "df -h /opt 2>/dev/null | awk 'NR==2 {print $3\" / \"$2}'"], root_used)
    disks = read_first(["bash", "--noprofile", "--norc", "-c", "lsblk -d -o NAME,MODEL,SIZE,ROTA,TYPE,TRAN | sed 's/  */ /g'"], "")
    disk_type = read_first(["bash", "--noprofile", "--norc", "-c", "lsblk -d -o ROTA,TYPE | awk '$2==\"disk\" {if ($1==0) print \"SSD/NVMe\"; else print \"HDD\"; exit}'"], "inconnu")
    return root_pct, root_used, opt_pct, opt_used, disk_type, disks


def get_gpu_info():
    pci = read_first([
        "bash", "--noprofile", "--norc", "-c",
        "lspci -nnk | grep -A4 -Ei 'vga|3d|display'"
    ], "Aucun GPU détecté")

    model = read_first([
        "bash", "--noprofile", "--norc", "-c",
        "lspci | grep -Ei 'vga|3d|display' | sed 's/^.*: //' | head -n1"
    ], "inconnu")

    driver = read_first([
        "bash", "--noprofile", "--norc", "-c",
        "lspci -nnk | awk '/VGA|3D|Display/{f=1} f&&/Kernel driver in use/{print $NF; exit}'"
    ], "non détecté")

    nvidia_ver = read_first([
        "bash", "--noprofile", "--norc", "-c",
        "nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null | head -n1"
    ], "")

    nvidia_util = read_first([
        "bash", "--noprofile", "--norc", "-c",
        "nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits 2>/dev/null | head -n1"
    ], "")

    mesa = read_first([
        "bash", "--noprofile", "--norc", "-c",
        "runuser -u pinball -- bash -lc 'DISPLAY=:0 XDG_RUNTIME_DIR=/run/user/1000 glxinfo -B 2>/dev/null | grep -E \"OpenGL vendor|OpenGL renderer|OpenGL core profile version|OpenGL version\"' 2>/dev/null"
    ], "")

    version = "NVIDIA " + nvidia_ver if nvidia_ver else "non détectée"

    if not mesa:
        mesa = (
            "OpenGL résumé glxinfo non retourné dans la session WebApp.\\n"
            "GPU détecté: " + str(model) + "\\n"
            "Driver actif: " + str(driver) + "\\n"
            "Version driver/OpenGL: " + str(version)
        )

    vulkan_raw = read_first([
        "bash", "--noprofile", "--norc", "-c",
        "vulkaninfo --summary 2>/dev/null | grep -E 'deviceName|driverName|driverInfo' | head -n40"
    ], "")

    # Filtre llvmpipe pour éviter de mélanger le GPU NVIDIA avec le rendu logiciel Mesa.
    vulkan_lines = []
    skip_block = False
    for line in vulkan_raw.splitlines():
        clean = line.strip()
        low = clean.lower()

        if "devicename" in low:
            skip_block = "llvmpipe" in low

        if skip_block:
            continue

        if clean:
            vulkan_lines.append(clean)

    vulkan = "\n".join(vulkan_lines[:20])

    if not vulkan:
        vulkan = vulkan_raw

    gpu_pct = nvidia_util if nvidia_util else "0"
    return model, driver, version, gpu_pct, pci, mesa, vulkan


def path_status(path):
    return '<span class="ok">OK</span>' if Path(path).exists() else '<span class="bad">absent</span>'


def dashboard_path_rows(esc):
    """
    Chemins essentiels synchronisés avec /opt/pincabos/config/version.json
    section pincabos_manifest.

    Utilise principalement:
      - pincabos_manifest.pincabos_critical_directories
      - pincabos_manifest.pincabos_critical_files
      - pincabos_manifest.official_vpx_paths
      - pincabos_manifest.official_vpinfe_paths
      - pincabos_manifest.full_dmd_calibration
      - pincabos_manifest.dmd_calibration

    Évite d'afficher toute la racine système (/usr, /lib, /etc/passwd, etc.)
    dans le dashboard pour garder la carte utile et lisible.
    """
    import json

    version_json = Path("/opt/pincabos/config/version.json")

    fallback_paths = [
        ("Base PinCabOS", "/opt/pincabos", "fallback"),
        ("WebApp", "/opt/pincabos/web", "fallback"),
        ("Applications", "/opt/pincabos/apps", "fallback"),
        ("VPX runtime", "/opt/pincabos/apps/vpinball", "fallback"),
        ("VPinFE runtime", "/opt/pincabos/apps/frontend/vpinfe", "fallback"),
        ("Config PinCabOS", "/opt/pincabos/config", "fallback"),
        ("Version PinCabOS", "/opt/pincabos/config/version.json", "fallback"),
        ("Tables VPX", "/home/pinball/Tables", "fallback"),
        ("Share", "/home/pinball/Share", "fallback"),
    ]

    items = []
    seen = set()

    def add(label, path, source):
        label = str(label or "").strip()
        path = str(path or "").strip()
        source = str(source or "").strip()

        if not label or not path:
            return

        if not path.startswith("/"):
            return

        key = path
        if key in seen:
            return

        seen.add(key)
        items.append((label, path, source))

    try:
        data = json.loads(version_json.read_text(errors="replace"))
        manifest = data.get("pincabos_manifest", {}) if isinstance(data, dict) else {}

        if isinstance(manifest, dict):
            # Dossiers PinCabOS utiles au dashboard.
            for entry in manifest.get("pincabos_critical_directories", []):
                if not isinstance(entry, dict):
                    continue
                path = entry.get("path", "")
                typ = entry.get("type", "")
                desc = entry.get("description", "")
                label = typ or desc or path
                add(label, path, "pincabos_manifest / directories")

            # Fichiers PinCabOS utiles au dashboard.
            for entry in manifest.get("pincabos_critical_files", []):
                if not isinstance(entry, dict):
                    continue
                path = entry.get("path", "")
                typ = entry.get("type", "")
                desc = entry.get("description", "")
                label = typ or desc or path
                add(label, path, "pincabos_manifest / files")

            # Chemins officiels VPX.
            official_vpx = manifest.get("official_vpx_paths", {})
            if isinstance(official_vpx, dict):
                add("VPX executable officiel", official_vpx.get("vpx_executable_path", ""), "official_vpx_paths")
                add("Tables directory officiel", official_vpx.get("tables_directory", ""), "official_vpx_paths")
                add("VPX INI officiel", official_vpx.get("vpx_ini_path", ""), "official_vpx_paths")

            # Chemins officiels VPinFE.
            official_vpinfe = manifest.get("official_vpinfe_paths", {})
            if isinstance(official_vpinfe, dict):
                add("VPinFE root officiel", official_vpinfe.get("root", ""), "official_vpinfe_paths")
                add("VPinFE current officiel", official_vpinfe.get("current", ""), "official_vpinfe_paths")
                add("VPinFE INI officiel", official_vpinfe.get("ini", ""), "official_vpinfe_paths")

            # FullDMD / DMD.
            full_dmd = manifest.get("full_dmd_calibration", {})
            if isinstance(full_dmd, dict):
                add("FullDMD calibration", full_dmd.get("source_json", ""), "full_dmd_calibration")
                add("FullDMD sync script", full_dmd.get("sync_script", ""), "full_dmd_calibration")
                add("FullDMD VPinFE INI", full_dmd.get("vpinfe_ini", ""), "full_dmd_calibration")
                add("FullDMD VPX INI", full_dmd.get("vpx_ini", ""), "full_dmd_calibration")

            dmd = manifest.get("dmd_calibration", {})
            if isinstance(dmd, dict):
                add("DMD calibration", dmd.get("source_json", ""), "dmd_calibration")
                add("DMD sync script", dmd.get("sync_script", ""), "dmd_calibration")

    except Exception as e:
        add("Erreur lecture version.json", "/opt/pincabos/config/version.json", "erreur: " + str(e))

    if not items:
        for label, path, source in fallback_paths:
            add(label, path, source)

    # Garde les chemins critiques de base même si manifest incomplet.
    for label, path, source in fallback_paths:
        add(label, path, "fallback critique")

    rows = []
    for label, path, source in items:
        rows.append(
            "<tr>"
            f"<td>{esc(label)}<br><small>{esc(source)}</small></td>"
            f"<td><code>{esc(path)}</code></td>"
            f"<td>{path_status(path)}</td>"
            "</tr>"
        )

    return "\n".join(rows)


def service_display_status(service_status, svc):
    active = service_status(svc)
    enabled = read_first(["bash", "--noprofile", "--norc", "-c", f"systemctl is-enabled {svc} 2>/dev/null"], "")

    if active == "active":
        return "active"

    if enabled == "enabled":
        return "inactive"

    return active

def systemctl_show_value(service, prop):
    return read_first(
        ["bash", "--noprofile", "--norc", "-c", f"systemctl show {service} -p {prop} --value 2>/dev/null"],
        ""
    ).strip()


def human_bytes(value):
    try:
        n = int(str(value).strip())
    except Exception:
        return "-"
    if n <= 0:
        return "-"
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    size = float(n)
    unit = 0
    while size >= 1024 and unit < len(units) - 1:
        size /= 1024
        unit += 1
    if unit == 0:
        return f"{int(size)} {units[unit]}"
    return f"{size:.1f} {units[unit]}"



def service_buttons(key, include_stop=True, include_kill=True):
    buttons = []

    buttons.append(
        '<form action="/service-control/{}/start" method="post" class="svc-form">'
        '<button class="button secondary svc-btn" type="submit" title="Activer" aria-label="Activer">▶</button>'
        '</form>'.format(key)
    )

    if include_stop:
        buttons.append(
            '<form action="/service-control/{}/stop" method="post" class="svc-form">'
            '<button class="button secondary svc-btn" type="submit" title="Désactiver" aria-label="Désactiver">■</button>'
            '</form>'.format(key)
        )

    buttons.append(
        '<form action="/service-control/{}/restart" method="post" class="svc-form">'
        '<button class="button svc-btn" type="submit" title="Relancer" aria-label="Relancer">↻</button>'
        '</form>'.format(key)
    )

    if include_kill:
        buttons.append(
            '<form action="/service-control/{}/kill" method="post" class="svc-form" '
            'onsubmit="return confirm(\'Terminer le processus du service ?\');">'
            '<button class="button secondary svc-btn svc-kill" type="submit" title="Terminer" aria-label="Terminer">✖</button>'
            '</form>'.format(key)
        )

    return '<div class="svc-actions">' + "\n".join(buttons) + '</div>'




def dashboard_services_rows(esc, service_status):
    services = [
        ("VPinFE", "pincabos-vpinfe.service", "vpinfe", True, True),
        ("Web Manager", "pincabos-webapp.service", "web", False, False),
        ("Console Web", "pincabos-console.service", "console", True, True),
    ]

    rows = []

    for label, svc, key, include_stop, include_kill in services:
        st = service_display_status(service_status, svc)

        main_pid = systemctl_show_value(svc, "MainPID")
        if not main_pid or main_pid == "0":
            main_pid = "-"

        mem_current = human_bytes(systemctl_show_value(svc, "MemoryCurrent"))

        tasks_current = systemctl_show_value(svc, "TasksCurrent")
        if not tasks_current or tasks_current == "[not set]":
            tasks_current = "-"

        rows.append(
            '<tr>'
            '<td><strong>{}</strong><br><small><code>{}</code></small></td>'
            '<td><span class="ok">{}</span></td>'
            '<td><code>{}</code></td>'
            '<td>{}<br><small>Tasks : {}</small></td>'
            '<td class="svc-control-cell">{}</td>'
            '</tr>'.format(
                esc(label),
                esc(svc),
                esc(st),
                esc(main_pid),
                esc(mem_current),
                esc(tasks_current),
                service_buttons(key, include_stop, include_kill),
            )
        )

    rows.append('<tr><td><strong>VPX</strong></td><td><span class="ok">installé</span></td><td>-</td><td>-</td><td>-</td></tr>')
    rows.append('<tr><td><strong>Table demo</strong></td><td><span class="ok">absente</span></td><td>-</td><td>-</td><td>-</td></tr>')
    rows.append('<tr><td><strong>DOF / libdof</strong></td><td><span class="ok">non confirmé</span></td><td>-</td><td>-</td><td>-</td></tr>')

    return "\n".join(rows)






def firstrun_dashboard_state():
    try:
        import json
        from pathlib import Path
        cfg_path = Path("/opt/pincabos/config/firstrun.json")
        required = ["network", "gpu", "screens"]
        data = {}
        if cfg_path.exists():
            data = json.loads(cfg_path.read_text(errors="replace"))
        done_count = sum(1 for k in required if data.get(k))
        complete = done_count == len(required)
        pct = int((done_count / len(required)) * 100)
        return complete, done_count, len(required), pct
    except Exception:
        return False, 0, 5, 0

def audio_router_dashboard_card(esc, service_status):
    svc = "pincabos-webapp.service"
    try:
        pid = systemctl_show_value(svc, "MainPID")
    except Exception:
        pid = "-"
    if not pid or pid == "0":
        pid = "-"

    st = service_display_status(service_status, svc)

    return f"""
  
<div class="card" style="border:1px solid rgba(255,176,0,.35);background:rgba(255,176,0,.07);">
  <h2>🚀 Premier démarrage PinCabOS</h2>
  <p>Checklist recommandée après installation : mises à jour, réseau, GPU, écrans, audio, inputs et validation finale.</p>
  <p><a class="button" href="/first-run">🚀 Ouvrir l’assistant Premier Démarrage</a></p>
</div>

<div class="card">
    <h2>Audio / SSF V2</h2>
    <table>
      <tr><th style="text-align:left;">Service</th><th style="text-align:left;">État</th><th style="text-align:left;">PID</th><th style="text-align:right;">Contrôle</th></tr>
      <tr>
        <td>Audio Router / SSF V2</td>
        <td>{st}</td>
        <td><code>{esc(pid)}</code></td>
        <td style="text-align:right;">{service_buttons("audio-ssf", True, True)}</td>
      </tr>
    </table>
    <p><a class="button secondary" href="/audio-ssf">Ouvrir Audio / SSF V2</a></p>
  </div>
"""




# PinCabOs Audio / SSF V2 dashboard integration
def pincabos_audio_run(cmd, timeout=5):
    import subprocess
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


def pincabos_audio_detect_rows(esc):
    import re

    # Force une sortie anglaise si possible, mais supporte aussi Ubuntu en français.
    output = pincabos_audio_run("LC_ALL=C aplay -l 2>/dev/null || aplay -l 2>/dev/null || true")

    rx = re.compile(
        r"^(?:card|carte)\s+(\d+)\s*:\s*"
        r"(.+?)\s+\[(.+?)\]\s*,\s*"
        r"(?:device|périphérique|peripherique)\s+(\d+)\s*:\s*"
        r"(.+?)\s+\[(.+?)\]",
        re.IGNORECASE
    )

    rows = []
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        m = rx.match(line)
        if not m:
            continue

        card_num = m.group(1).strip()
        card_short = m.group(2).strip()
        card_name = m.group(3).strip()
        device_num = m.group(4).strip()
        device_short = m.group(5).strip()
        device_name = m.group(6).strip()

        alsa_hw = f"hw:{card_num},{device_num}"
        alsa_plug = f"plughw:{card_num},{device_num}"

        rows.append(
            "<tr>"
            f"<td><code>{esc(alsa_hw)}</code><br><small><code>{esc(alsa_plug)}</code></small></td>"
            f"<td>{esc(card_name)}</td>"
            f"<td>{esc(device_name)}</td>"
            f"<td>{esc(card_short)} / {esc(device_short)}</td>"
            "</tr>"
        )

    if not rows:
        rows.append(
            '<tr><td colspan="4"><span class="warn">'
            'Aucune sortie audio ALSA détectée par le dashboard.'
            '</span></td></tr>'
        )

    return "\n".join(rows)


def pincabos_audio_config_summary(esc):
    import json
    from pathlib import Path

    cfg = Path("/opt/pincabos/config/audio-router.json")
    if not cfg.exists():
        return '<span class="warn">Aucune configuration audio sauvegardée.</span>'

    try:
        data = json.loads(cfg.read_text(errors="replace"))
    except Exception as e:
        return f'<span class="bad">Erreur lecture config audio : {esc(e)}</span>'

    mode = data.get("audio_mode", "-")
    backend = data.get("audio_backend", "-")
    ssf = data.get("ssf_mode", "-")
    backbox = data.get("backbox_device", "-") or "-"
    playfield = data.get("playfield_device", "-") or "-"
    surround = data.get("surround_device", "-") or "-"
    bass = data.get("bass_device", "-") or "-"

    return f"""
    <table>
      <tr><td>Mode</td><td><code>{esc(mode)}</code></td></tr>
      <tr><td>Backend</td><td><code>{esc(backend)}</code></td></tr>
      <tr><td>Mode SSF</td><td><code>{esc(ssf)}</code></td></tr>
      <tr><td>Backbox / ROM / Musique</td><td><code>{esc(backbox)}</code></td></tr>
      <tr><td>Playfield / SSF</td><td><code>{esc(playfield)}</code></td></tr>
      <tr><td>Surround VPX</td><td><code>{esc(surround)}</code></td></tr>
      <tr><td>Bass shaker</td><td><code>{esc(bass)}</code></td></tr>
    </table>
    """


def pincabos_audio_dashboard_card(esc):
    return f"""
  <div class="card" style="margin-top:5px;">
    <h2>Audio / SSF V2</h2>
    <p>
      Détection des cartes audio ALSA et résumé de la configuration SSF V2.
    </p>

    <h3>Cartes audio détectées</h3>
    <table>
      <tr>
        <th style="text-align:left;">ID ALSA</th>
        <th style="text-align:left;">Carte</th>
        <th style="text-align:left;">Sortie</th>
        <th style="text-align:left;">Description</th>
      </tr>
      {pincabos_audio_detect_rows(esc)}
    </table>

    <h3 style="margin-top:5px;">Configuration active</h3>
    {pincabos_audio_config_summary(esc)}

    <p style="margin-top:5px;">
      <a class="button secondary" href="/audio-ssf">Ouvrir Audio / SSF V2</a>
    </p>
  </div>
"""


def pincabos_audio_service_row(esc):
    import subprocess
    import psutil

    svc = "pincabos-webapp.service"

    def show(prop):
        try:
            r = subprocess.run(
                ["systemctl", "show", svc, "-p", prop, "--value"],
                capture_output=True,
                text=True,
                timeout=3
            )
            return (r.stdout or "").strip()
        except Exception:
            return ""

    pid = show("MainPID")
    if not pid or pid == "0":
        pid = "-"

    state = show("ActiveState") or "unknown"
    state_html = '<span class="ok">active / intégré</span>' if state == "active" else f'<span class="bad">{esc(state)}</span>'

    mem = "-"
    tasks = "-"
    if pid != "-":
        try:
            p = psutil.Process(int(pid))
            mem = f"{p.memory_info().rss / 1024 / 1024:.1f} MiB"
            tasks = str(p.num_threads())
        except Exception:
            pass

    resources = f"{esc(mem)}<br><small>Tasks : {esc(tasks)}</small>"

    controls = '<a class="button secondary svc-btn" href="/audio-ssf" title="Ouvrir Audio / SSF V2">🔊</a>'

    return f"""
      <tr>
        <td><strong>Audio / SSF V2</strong><br><small>intégré à pincabos-webapp.service</small></td>
        <td>{state_html}</td>
        <td><code>{esc(pid)}</code></td>
        <td>{resources}</td>
        <td style="text-align:right;">{controls}</td>
      </tr>
    """



# === PINCABOS DASHBOARD SERVICES FULLWIDTH START ===

def pco_status_class(st):
    st = str(st or "").strip().lower()
    if st in ["active", "running"]:
        return "ok"
    if st in ["inactive", "exited", "stopped"]:
        return "warn"
    return "bad"


def pco_short_cmd(args, limit=170):
    txt = " ".join(str(args or "").split())
    return txt if len(txt) <= limit else txt[:limit - 3] + "..."


def pco_systemd_info(service, service_status):
    st = service_display_status(service_status, service)
    sub = systemctl_show_value(service, "SubState") or "-"
    main_pid = systemctl_show_value(service, "MainPID") or "-"
    if main_pid == "0":
        main_pid = "-"
    mem = human_bytes(systemctl_show_value(service, "MemoryCurrent"))
    tasks = systemctl_show_value(service, "TasksCurrent") or "-"
    if tasks == "[not set]":
        tasks = "-"
    cgroup = systemctl_show_value(service, "ControlGroup") or ""
    return {"state": st, "sub": sub, "main_pid": main_pid, "mem": mem, "tasks": tasks, "cgroup": cgroup}


def pco_pids_from_cgroup(cgroup):
    if not cgroup:
        return []
    path = Path("/sys/fs/cgroup" + cgroup + "/cgroup.procs")
    if not path.exists():
        return []
    try:
        return [x.strip() for x in path.read_text(errors="replace").splitlines() if x.strip().isdigit()]
    except Exception:
        return []


def pco_ps_info(pid):
    try:
        out = read_first([
            "bash", "--noprofile", "--norc", "-c",
            "ps -p " + str(int(pid)) + " -o pid=,ppid=,user=,stat=,rss=,comm=,args= 2>/dev/null"
        ], "")
        parts = out.split(None, 6)
        if len(parts) < 7:
            return None
        return {"pid": parts[0], "ppid": parts[1], "user": parts[2], "stat": parts[3], "rss": parts[4], "comm": parts[5], "args": parts[6]}
    except Exception:
        return None


def pco_pid_rows(esc, pids):
    rows = []
    for pid in pids[:100]:
        info = pco_ps_info(pid)
        if not info:
            continue
        try:
            rss = human_bytes(int(info["rss"]) * 1024)
        except Exception:
            rss = "-"
        rows.append(
            "<tr class='svc-pid-row'>"
            "<td><code>" + esc(info["pid"]) + "</code></td>"
            "<td><code>" + esc(info["ppid"]) + "</code></td>"
            "<td>" + esc(info["user"]) + "</td>"
            "<td>" + esc(info["stat"]) + "</td>"
            "<td>" + esc(rss) + "</td>"
            "<td><code>" + esc(info["comm"]) + "</code></td>"
            "<td><small>" + esc(pco_short_cmd(info["args"])) + "</small></td>"
            "</tr>"
        )
    if not rows:
        rows.append("<tr><td colspan='7'><span class='warn'>Aucun PID détaillé détecté.</span></td></tr>")
    return "\n".join(rows)


def pco_vpx_processes():
    out = read_first([
        "bash", "--noprofile", "--norc", "-c",
        "ps -eo pid=,ppid=,user=,stat=,rss=,comm=,args= | grep -E 'VPinballX' | grep -v grep"
    ], "")
    rows = []
    for line in out.splitlines():
        parts = line.split(None, 6)
        if len(parts) >= 7:
            rows.append({"pid": parts[0], "ppid": parts[1], "user": parts[2], "stat": parts[3], "rss": parts[4], "comm": parts[5], "args": parts[6]})
    return rows


def pco_vpx_buttons():
    return (
        "<div class='svc-actions'>"
        "<form action='/process-control/vpx/start' method='post' class='svc-form'><button class='button secondary svc-btn' type='submit' title='Préparer / relancer VPX'>▶</button></form>"
        "<form action='/process-control/vpx/stop' method='post' class='svc-form' onsubmit=\"return confirm('Fermer VPX / table active ?');\"><button class='button secondary svc-btn' type='submit' title='Fermer VPX'>■</button></form>"
        "<form action='/process-control/vpx/restart' method='post' class='svc-form' onsubmit=\"return confirm('Fermer VPX et redémarrer VPinFE ?');\"><button class='button svc-btn' type='submit' title='Redémarrer VPX/VPinFE'>↻</button></form>"
        "<form action='/process-control/vpx/kill' method='post' class='svc-form' onsubmit=\"return confirm('Terminer VPinballX maintenant ?');\"><button class='button secondary svc-btn svc-kill' type='submit' title='Terminer VPinballX'>✖</button></form>"
        "</div>"
    )


def pco_service_block(esc, title, unit, key, info, desc, include_stop=True, include_kill=True):
    pids = pco_pids_from_cgroup(info.get("cgroup", ""))
    cls = pco_status_class(info.get("state", "-"))
    return (
        "<div class='svc-block'>"
        "<div class='svc-head'>"
        "<div><h3>" + esc(title) + "</h3><p><code>" + esc(unit) + "</code></p><p class='svc-desc'>" + esc(desc) + "</p></div>"
        "<div class='svc-meta'>"
        "<div><span class='" + cls + "'>" + esc(info.get("state", "-")) + "</span> <small>" + esc(info.get("sub", "-")) + "</small></div>"
        "<div>MainPID : <code>" + esc(info.get("main_pid", "-")) + "</code></div>"
        "<div>Mémoire : <code>" + esc(info.get("mem", "-")) + "</code></div>"
        "<div>Tasks : <code>" + esc(info.get("tasks", "-")) + "</code></div>"
        "</div>"
        "<div class='svc-control-cell'>" + service_buttons(key, include_stop, include_kill) + "</div>"
        "</div>"
        "<details class='svc-details'><summary>Tous les PID détectés pour " + esc(title) + "</summary>"
        "<table class='svc-pid-table'><tr><th>PID</th><th>PPID</th><th>User</th><th>Stat</th><th>RSS</th><th>Process</th><th>Commande</th></tr>"
        + pco_pid_rows(esc, pids)
        + "</table></details></div>"
    )


def pco_vpx_block(esc):
    rows = pco_vpx_processes()
    if rows:
        state = "active"
        cls = "ok"
        main_pid = rows[0].get("pid", "-")
        try:
            mem = human_bytes(sum(int(x.get("rss", "0")) for x in rows) * 1024)
        except Exception:
            mem = "-"
        tasks = str(len(rows))
        pids = [x.get("pid", "") for x in rows]
    else:
        state = "inactive"
        cls = "warn"
        main_pid = "-"
        mem = "-"
        tasks = "0"
        pids = []

    return (
        "<div class='svc-block'>"
        "<div class='svc-head'>"
        "<div><h3>VPX</h3><p><code>VPinballX process</code></p><p class='svc-desc'>Moteur Visual Pinball X Linux pour la table active. Détecté par processus, pas par service systemd.</p></div>"
        "<div class='svc-meta'>"
        "<div><span class='" + cls + "'>" + esc(state) + "</span></div>"
        "<div>MainPID : <code>" + esc(main_pid) + "</code></div>"
        "<div>Mémoire : <code>" + esc(mem) + "</code></div>"
        "<div>Tasks : <code>" + esc(tasks) + "</code></div>"
        "</div>"
        "<div class='svc-control-cell'>" + pco_vpx_buttons() + "</div>"
        "</div>"
        "<details class='svc-details'><summary>Tous les PID VPX détectés</summary>"
        "<table class='svc-pid-table'><tr><th>PID</th><th>PPID</th><th>User</th><th>Stat</th><th>RSS</th><th>Process</th><th>Commande</th></tr>"
        + pco_pid_rows(esc, pids)
        + "</table></details></div>"
    )


def dashboard_services_fullwidth_card(esc, service_status):
    frontend = pco_systemd_info("pincabos-vpinfe.service", service_status)
    web = pco_systemd_info("pincabos-webapp.service", service_status)
    console = pco_systemd_info("pincabos-console.service", service_status)

    return (
        "<div class='card svc-full-card' style='margin-top:5px;min-height:740px;'>"
        "<h2>Services PinCabOS</h2>"
        "<p class='svc-desc'>Gestion des services principaux et affichage de tous les PID détectés. Les boutons agissent seulement sur les services/process autorisés PinCabOS.</p>"
        + pco_service_block(esc, "VPinFE", "pincabos-vpinfe.service", "vpinfe", frontend, "Frontend principal du cabinet. Lance l’interface VPinFE, les fenêtres backglass/DMD et peut lancer VPX.", True, True)
        + pco_service_block(esc, "Web Manager", "pincabos-webapp.service", "web", web, "WebApp PinCabOS : dashboard, configuration, outils, import, audio, inputs, outputs et mises à jour.", False, False)
        + pco_service_block(esc, "Console Web", "pincabos-console.service", "console", console, "Console Commander Web intégrée pour maintenance locale depuis le navigateur.", True, True)
        + pco_vpx_block(esc)
        + "</div>"
    )

# === PINCABOS DASHBOARD SERVICES FULLWIDTH END ===



# === PINCABOS DASHBOARD INFO QUALITY HELPERS START ===

def pco_version_rows(esc, version_info):
    import json
    cfg_path = Path("/opt/pincabos/config/version.json")
    data = {}

    if isinstance(version_info, dict):
        data.update(version_info)

    try:
        if cfg_path.exists():
            raw = json.loads(cfg_path.read_text(errors="replace"))
            if isinstance(raw, dict):
                data.update(raw)
    except Exception as e:
        data["version_json_error"] = str(e)

    wanted = [
        ("Nom", ["name", "product", "project"]),
        ("Version", ["version"]),
        ("Build", ["build", "build_id", "build_date"]),
        ("Canal", ["channel"]),
        ("Codename", ["codename", "code_name"]),
        ("Édition", ["edition"]),
        ("Date", ["date", "created_at", "updated_at"]),
    ]

    rows = []
    for label, keys in wanted:
        val = ""
        for key in keys:
            if data.get(key):
                val = data.get(key)
                break
        if val:
            rows.append(f"<tr><td>{esc(label)}</td><td><code>{esc(val)}</code></td></tr>")

    if not rows:
        rows.append("<tr><td>Version</td><td><code>non détectée</code></td></tr>")

    rows.append(f"<tr><td>Source</td><td><code>{esc(str(cfg_path))}</code></td></tr>")
    return "\n".join(rows)


def pco_vpinfe_version():
    checks = [
        "cd /opt/pincabos/apps/frontend/vpinfe 2>/dev/null && git describe --tags --always 2>/dev/null",
        "/opt/pincabos/apps/frontend/vpinfe/vpinfe --version 2>/dev/null | head -n1",
        "test -x /opt/pincabos/apps/frontend/vpinfe/vpinfe && echo 'installé / détecté'",
    ]
    for cmd in checks:
        out = read_first(["bash", "--noprofile", "--norc", "-c", cmd], "")
        if out and out.strip() and "not found" not in out.lower():
            return out.strip().splitlines()[0]
    return "non détecté"


def pco_opengl_summary(esc, gpu_mesa, gpu_vulkan, gpu_driver, gpu_version):
    mesa = str(gpu_mesa or "").strip()
    vulkan = str(gpu_vulkan or "").strip()

    if mesa:
        ogl_html = f"<pre>{esc(mesa)}</pre>"
    else:
        ogl_html = (
            "<p><span class='warn'>OpenGL direct non retourné par glxinfo.</span></p>"
            "<p>Driver actif : <code>" + esc(gpu_driver) + "</code></p>"
            "<p>Version : <code>" + esc(gpu_version) + "</code></p>"
        )

    if vulkan:
        vk_lines = []
        for line in vulkan.splitlines():
            clean = line.strip()
            if clean:
                vk_lines.append(clean)
        vk_html = f"<pre>{esc(chr(10).join(vk_lines[:12]))}</pre>"
    else:
        vk_html = "<p><span class='warn'>Vulkan non détecté ou vulkaninfo absent.</span></p>"

    return ogl_html, vk_html

# === PINCABOS DASHBOARD INFO QUALITY HELPERS END ===



# === PINCABOS CLEAN VPINFE VERSION START ===
def pco_clean_vpinfe_version_safe():
    """
    Retourne une version VPinFE propre.
    Ne lance pas vpinfe --version si ça imprime seulement des logs.
    """
    checks = [
        "cd /opt/pincabos/apps/frontend/vpinfe 2>/dev/null && git describe --tags --always 2>/dev/null",
        "test -x /opt/pincabos/apps/frontend/vpinfe/vpinfe && echo 'installé / détecté'",
    ]

    for cmd in checks:
        out = read_first(["bash", "--noprofile", "--norc", "-c", cmd], "")
        if not out:
            continue

        for line in out.splitlines():
            clean = line.strip()
            if not clean:
                continue

            low = clean.lower()
            if "logging to" in low or " info [" in low or " warning [" in low or " error [" in low:
                continue

            return clean

    return "installé / non versionné"
# === PINCABOS CLEAN VPINFE VERSION END ===


def render_dashboard(page, esc, get_ip, service_status, pincabos_version):
    hostname = read_first(["hostname"], "inconnu").splitlines()[0]
    ip = get_ip()

    os_name = read_first(["bash", "--noprofile", "--norc", "-c", ". /etc/os-release 2>/dev/null && echo \"$PRETTY_NAME\""], "Linux")
    kernel = read_first(["uname", "-r"], "")
    arch = read_first(["uname", "-m"], "")
    uptime = read_first(["uptime", "-p"], "inconnu")
    tz = read_first(["timedatectl", "show", "-p", "Timezone", "--value"], "inconnue")
    local_time = read_first(["date"], "")

    cpu_model, cpu_count, cpu_details = get_cpu_info()
    cpu_pct = get_cpu_usage()

    mem_total, mem_used, mem_pct, mem_type, mem_speed = get_memory_info()
    root_pct, root_used, opt_pct, opt_used, disk_type, disks = get_disk_info()
    gpu_model, gpu_driver, gpu_version, gpu_pct, gpu_pci, gpu_mesa, gpu_vulkan = get_gpu_info()

    vpx_version = read_first([
        "bash", "--noprofile", "--norc", "-c",
        "DISPLAY=:0 XDG_RUNTIME_DIR=/run/user/1000 LD_LIBRARY_PATH=/opt/pincabos/apps/vpinball/current "
        "/opt/pincabos/apps/vpinball/VPinballX -v 2>/dev/null | grep -i 'Visual Pinball' | tail -n1"
    ], "non détecté")
    vpinfe_version = pco_clean_vpinfe_version_safe()
    version_info = pincabos_version()
    fr_complete, fr_done, fr_total, fr_pct = firstrun_dashboard_state()
    fr_btn_bg = "#00b050" if fr_complete else "#b00020"
    fr_btn_border = "#00ff88" if fr_complete else "#ff4444"
    fr_btn_shadow = "rgba(0,255,120,.55)" if fr_complete else "rgba(255,0,60,.55)"
    fr_btn_text = "✅ Premier Démarrage" if fr_complete else "🚀 Premier Démarrage"
    fr_status = "✅ Configuration terminée" if fr_complete else "⚠️ Configuration incomplète"

    body = f"""
<div class="grid" style="gap:5px;margin-top:5px;margin-bottom:5px;">
  <div class="card" style="position:relative;">
    <a href="/first-run"
       class="button"
       title="{fr_status} — {fr_done}/{fr_total} étapes"
       style="position:absolute;top:12px;right:12px;background:{fr_btn_bg};color:white;border:2px solid {fr_btn_border};box-shadow:0 0 18px {fr_btn_shadow};z-index:5;font-size:22px;padding:14px 22px;border-radius:14px;font-weight:900;">
       {fr_btn_text}
       <span style="display:block;font-size:11px;margin-top:3px;">{fr_done}/{fr_total} — {fr_pct}%</span>
    </a>
    <h2>Système</h2>
    <p>Hostname : <code>{esc(hostname)}</code></p>
    <p>IP : <code>{esc(ip)}</code></p>
    <p>OS : <code>{esc(os_name)}</code></p>
    <p>Kernel : <code>{esc(kernel)} / {esc(arch)}</code></p>
    <p>Uptime : <code>{esc(uptime)}</code></p>
    <p>Timezone : <code>{esc(tz)}</code></p>
    <p>Heure locale : <code>{esc(local_time)}</code></p>
  </div>

  <div class="card">
    <h2>Utilisation</h2>
    {pct_bar(esc, cpu_pct, "CPU")}
    {pct_bar(esc, mem_pct, "Mémoire RAM")}
    {pct_bar(esc, root_pct, "Disque /")}
    {pct_bar(esc, opt_pct, "Disque /opt")}
    {pct_bar(esc, gpu_pct, "GPU")}
  </div>
</div>

<div class="grid" style="gap:5px;margin-top:5px;margin-bottom:5px;">
  <div class="card">
    <h2>Versions</h2>
    <p>VPX : <code>{esc(vpx_version)}</code></p>
    <p>VPinFE : <code>{esc(vpinfe_version)}</code></p>
    <p>PinCabOs : <code>{esc(version_info.get("version", "Beta 1.0"))}</code></p>
    <p>Pilote GPU : <code>{esc(gpu_driver)} / {esc(gpu_version)}</code></p>
  </div>
</div>

  {dashboard_services_fullwidth_card(esc, service_status)}

<div class="grid" style="margin-top:5px;gap:5px;">
  <div class="card">
    <h2>CPU</h2>
    <p>Modèle : <code>{esc(cpu_model)}</code></p>
    <p>CPU logiques : <code>{esc(cpu_count)}</code></p>
    <pre>{esc(cpu_details)}</pre>
  </div>

  <div class="card">
    <h2>Mémoire</h2>
    <p>Total : <code>{esc(mem_total)}</code></p>
    <p>Utilisée : <code>{esc(mem_used)}</code></p>
    <p>Type : <code>{esc(mem_type)}</code></p>
    <p>Vitesse : <code>{esc(mem_speed)}</code></p>
  </div>
</div>

<div class="grid" style="margin-top:5px;gap:5px;">
  <div class="card">
    <h2>Disques</h2>
    <p>Type principal : <code>{esc(disk_type)}</code></p>
    <p>Racine / : <code>{esc(root_used)}</code></p>
    <p>/opt : <code>{esc(opt_used)}</code></p>
    <pre>{esc(disks)}</pre>
  </div>

  <div class="card">
    <h2>GPU / Drivers</h2>
    <p>GPU : <code>{esc(gpu_model)}</code></p>
    <p>Driver actif : <code>{esc(gpu_driver)}</code></p>
    <p>Version driver/OpenGL : <code>{esc(gpu_version)}</code></p>
    <pre>{esc(gpu_pci)}</pre>
  </div>
</div>

{pincabos_audio_dashboard_card(esc)}



<div class="grid" style="margin-top:5px;gap:5px;">
  <div class="card">
    <h2>OpenGL / Mesa</h2>
    <pre>{esc(gpu_mesa)}</pre>
  </div>

  <div class="card">
    <h2>Vulkan</h2>
    <pre>{esc(gpu_vulkan)}</pre>
  </div>
</div>
  <div class="card pco-paths-bottom" style="margin-top:5px;">
    <h2>Chemins essentiels</h2>
    <table style="width:100%; border-collapse:collapse;">
      <tr><th style="text-align:left;">Élément</th><th style="text-align:left;">Chemin</th><th style="text-align:left;">État</th></tr>
      {dashboard_path_rows(esc)}
    </table>
  </div>


"""
    return page("Dashboard", body)

# PinCabOS direct dashboard_plus render fix v2
# Created by Karots Sugarpie
# Purpose:
# - Fix stale dashboard VPX detection display.
# - Fix stale WebApp service name.
# - Fix stale VPX runtime path.
# - Clarify ALSA audio state when a card exists but no playback device is exposed.

try:
    _PCO_DASHBOARD_PLUS_ORIGINAL_RENDER_DASHBOARD
except NameError:
    _PCO_DASHBOARD_PLUS_ORIGINAL_RENDER_DASHBOARD = render_dashboard


def _pco_dashboard_plus_vpx_label():
    import os

    checks = [
        ("/opt/pincabos/apps/vpinball/VPinballX-BGFX", "installé - VPinballX-BGFX"),
        ("/opt/pincabos/apps/vpinball/VPinballX", "installé - VPinballX"),
        ("/opt/pincabos/apps/vpinball/current/VPinballX-BGFX", "installé - VPinballX-BGFX current"),
        ("/opt/pincabos/bin/vpx.sh", "installé - wrapper vpx.sh"),
    ]

    for path, label in checks:
        if os.path.exists(path):
            return label

    return "non détecté"


def _pco_dashboard_plus_audio_message():
    import os
    import subprocess
    import re

    cards = ""
    try:
        if os.path.exists("/proc/asound/cards"):
            cards = open("/proc/asound/cards", "r", errors="replace").read().strip()
    except Exception:
        cards = ""

    try:
        r = subprocess.run(
            ["aplay", "-l"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=3,
        )
        aplay = (r.stdout or "").strip()
    except Exception as exc:
        aplay = str(exc)

    has_card = bool(cards and "no soundcards" not in cards.lower())
    has_playback = bool(re.search(r"card\s+\d+:", aplay, re.I))

    if has_playback:
        return None

    if has_card:
        first = cards.splitlines()[0].strip() if cards.splitlines() else "carte audio détectée"
        return (
            "Carte audio détectée par Linux (" + first + "), mais aucune sortie playback ALSA utilisable "
            "n’est exposée à la session WebApp. En VM, ajoute un périphérique audio playback; sur cabinet réel, "
            "vérifie aplay -l, PipeWire/PulseAudio et les permissions audio."
        )

    return (
        "Aucune carte audio ALSA détectée par Linux. En VM c’est normal si aucun périphérique audio "
        "n’est attaché; sur cabinet réel, vérifier BIOS/USB/audio et aplay -l."
    )


def _pco_dashboard_plus_fix_html(html):
    import re

    if not isinstance(html, str):
        return html

    vpx_label = _pco_dashboard_plus_vpx_label()
    audio_msg = _pco_dashboard_plus_audio_message()

    html = html.replace("pincabos-web.service", "pincabos-webapp.service")
    html = html.replace("/opt/pincabos/apps/vpx", "/opt/pincabos/apps/vpinball")
    html = html.replace("VPinballX_BGFX", "VPinballX-BGFX")

    html = html.replace(
        "VPX : <code>non détecté</code>",
        "VPX : <code>" + vpx_label + "</code>",
    )

    html = re.sub(
        r'(<p>\s*VPX\s*:\s*<code>)(non détecté|non detecte|not detected)(</code>\s*</p>)',
        r'\1' + vpx_label + r'\3',
        html,
        flags=re.I,
    )

    if audio_msg:
        html = html.replace(
            "Aucune sortie audio ALSA détectée par le dashboard.",
            audio_msg,
        )

    html = re.sub(
        r'(<h3>Web Manager</h3>.*?<code>pincabos-webapp\.service</code>.*?<span class=[\'"]ok[\'"]>)active(</span>\s*<small>)exited(</small>)',
        r'\1active\2running\3',
        html,
        flags=re.S,
    )

    return html


def render_dashboard(page, esc, get_ip, service_status, pincabos_version):
    html = _PCO_DASHBOARD_PLUS_ORIGINAL_RENDER_DASHBOARD(
        page,
        esc,
        get_ip,
        service_status,
        pincabos_version,
    )
    return _pco_dashboard_plus_fix_html(html)

