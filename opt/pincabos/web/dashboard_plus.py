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
    pci = read_first(["bash", "--noprofile", "--norc", "-c", "lspci -nnk | grep -A4 -Ei 'vga|3d|display'"], "Aucun GPU détecté")
    model = read_first(["bash", "--noprofile", "--norc", "-c", "lspci | grep -Ei 'vga|3d|display' | sed 's/^.*: //' | head -n1"], "inconnu")
    driver = read_first(["bash", "--noprofile", "--norc", "-c", "lspci -nnk | awk '/VGA|3D|Display/{f=1} f&&/Kernel driver in use/{print $NF; exit}'"], "non détecté")
    nvidia_ver = read_first(["bash", "--noprofile", "--norc", "-c", "nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null | head -n1"], "")
    nvidia_util = read_first(["bash", "--noprofile", "--norc", "-c", "nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits 2>/dev/null | head -n1"], "")
    mesa = read_first(["bash", "--noprofile", "--norc", "-c", "glxinfo -B 2>/dev/null | grep -E 'OpenGL vendor|OpenGL renderer|OpenGL core profile version|OpenGL version'"], "")
    vulkan = read_first(["bash", "--noprofile", "--norc", "-c", "vulkaninfo --summary 2>/dev/null | grep -E 'deviceName|driverName|driverInfo' | head -n20"], "")
    version = "NVIDIA " + nvidia_ver if nvidia_ver else read_first(
        ["bash", "--noprofile", "--norc", "-c", "glxinfo -B 2>/dev/null | awk -F: '/OpenGL version string/ {gsub(/^ +/,\"\",$2); print $2; exit}'"],
        "non détectée"
    )
    gpu_pct = nvidia_util if nvidia_util else "0"
    return model, driver, version, gpu_pct, pci, mesa, vulkan


def path_status(path):
    return '<span class="ok">OK</span>' if Path(path).exists() else '<span class="bad">absent</span>'


def dashboard_path_rows(esc):
    paths = [
        ("Base PinCabOs", "/opt/pincabos"),
        ("Applications", "/opt/pincabos/apps"),
        ("VPX", "/opt/pincabos/apps/vpx"),
        ("VPX courant", "/opt/pincabos/apps/vpx/current"),
        ("VPinFE", "/opt/pincabos/apps/frontend/vpinfe"),
        ("WebApp", "/opt/pincabos/web"),
        ("Scripts tools", "/opt/pincabos/tools"),
        ("Config PinCabOs", "/opt/pincabos/config"),
        ("Logs PinCabOs", "/opt/pincabos/logs"),
        ("Tables VPX", "/opt/pincabos/vpinball/Tables"),
        ("FlexDMD", "/opt/pincabos/flexdmd"),
        ("Media", "/opt/pincabos/media"),
        ("DOF config", "/home/pinball/.local/share/VPinballX/10.8/directoutputconfig"),
        ("VPinFE config", "/home/pinball/.config/vpinfe/vpinfe.ini"),
        ("VPX config", "/home/pinball/.local/share/VPinballX/10.8/VPinballX.ini"),
        ("FullDMD calibration", "/opt/pincabos/config/fulldmd-calibration.json"),
        ("Screens config", "/opt/pincabos/config/screens.json"),
        ("Version PinCabOs", "/opt/pincabos/config/version.json"),
        ("Console env", "/opt/pincabos/config/webconsole.env"),
    ]
    return "\n".join([
        f"<tr><td>{esc(label)}</td><td><code>{esc(path)}</code></td><td>{path_status(path)}</td></tr>"
        for label, path in paths
    ])



def service_display_status(service_status, svc):
    active = service_status(svc)
    enabled = read_first(["bash", "--noprofile", "--norc", "-c", f"systemctl is-enabled {svc} 2>/dev/null"], "")

    if svc == "pincabos-auto-timezone.service":
        if enabled == "enabled":
            return "enabled / exécuté au démarrage"
        return active

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
        ("VPinFE", "pincabos-frontend.service", "vpinfe", True, True),
        ("Web Manager", "pincabos-web.service", "web", False, False),
        ("Console Web", "pincabos-console.service", "console", True, True),
        ("Auto Timezone", "pincabos-auto-timezone.service", "timezone", True, True),
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
        required = ["updates", "network", "gpu", "screens", "audio"]
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
    svc = "pincabos-web.service"
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
    output = pincabos_audio_run("aplay -l || true")

    rows = []
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
        alsa_id = f"hw:{card_num},{device_num}"

        rows.append(
            "<tr>"
            f"<td><code>{esc(alsa_id)}</code></td>"
            f"<td>{esc(card_name)}</td>"
            f"<td>{esc(device_name)}</td>"
            f"<td>{esc(card_short)} / {esc(device_short)}</td>"
            "</tr>"
        )

    if not rows:
        rows.append('<tr><td colspan="4"><span class="warn">Aucune sortie audio ALSA détectée.</span></td></tr>')

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
  <div class="card" style="margin-top:20px;">
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

    <h3 style="margin-top:14px;">Configuration active</h3>
    {pincabos_audio_config_summary(esc)}

    <p style="margin-top:14px;">
      <a class="button secondary" href="/audio-ssf">Ouvrir Audio / SSF V2</a>
    </p>
  </div>
"""


def pincabos_audio_service_row(esc):
    import subprocess
    import psutil

    svc = "pincabos-web.service"

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
        <td><strong>Audio / SSF V2</strong><br><small>intégré à pincabos-web.service</small></td>
        <td>{state_html}</td>
        <td><code>{esc(pid)}</code></td>
        <td>{resources}</td>
        <td style="text-align:right;">{controls}</td>
      </tr>
    """


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
        "DISPLAY=:0 XDG_RUNTIME_DIR=/run/user/1000 LD_LIBRARY_PATH=/opt/pincabos/apps/vpx/current "
        "/opt/pincabos/apps/vpx/VPinballX -v 2>/dev/null | grep -i 'Visual Pinball' | tail -n1"
    ], "non détecté")
    vpinfe_version = read_first(["bash", "--noprofile", "--norc", "-c", "cd /opt/pincabos/apps/frontend/vpinfe 2>/dev/null && git describe --tags --always 2>/dev/null"], "non détecté")
    version_info = pincabos_version()
    fr_complete, fr_done, fr_total, fr_pct = firstrun_dashboard_state()
    fr_btn_bg = "#00b050" if fr_complete else "#b00020"
    fr_btn_border = "#00ff88" if fr_complete else "#ff4444"
    fr_btn_shadow = "rgba(0,255,120,.55)" if fr_complete else "rgba(255,0,60,.55)"
    fr_btn_text = "✅ Premier Démarrage" if fr_complete else "🚀 Premier Démarrage"
    fr_status = "✅ Configuration terminée" if fr_complete else "⚠️ Configuration incomplète"

    body = f"""
<div class="grid">
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

<div class="grid" style="margin-top:20px;">
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

<div class="grid" style="margin-top:20px;">
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

<div class="grid" style="margin-top:20px;">
  <div class="card">
    <h2>Versions</h2>
    <p>VPX : <code>{esc(vpx_version)}</code></p>
    <p>VPinFE : <code>{esc(vpinfe_version)}</code></p>
    <p>PinCabOs : <code>{esc(version_info.get("version", "Beta 1.0"))}</code></p>
    <p>Pilote GPU : <code>{esc(gpu_driver)} / {esc(gpu_version)}</code></p>
  </div>

  <div class="card">
    <h2>Services</h2>
    <table style="width:100%; border-collapse:collapse;">
      <tr><th style="text-align:left;">Service</th><th style="text-align:left;">État</th><th style="text-align:left;">PID</th><th style="text-align:left;">Ressources</th><th style="text-align:right;">Contrôle</th></tr>
      {dashboard_services_rows(esc, service_status)}
      {pincabos_audio_service_row(esc)}
    </table>
  </div>
</div>

{pincabos_audio_dashboard_card(esc)}

<div class="card" style="margin-top:20px;">
  <h2>Chemins essentiels</h2>
  <table style="width:100%; border-collapse:collapse;">
    <tr><th style="text-align:left;">Élément</th><th style="text-align:left;">Chemin</th><th style="text-align:left;">État</th></tr>
    {dashboard_path_rows(esc)}
  </table>
</div>

<div class="grid" style="margin-top:20px;">
  <div class="card">
    <h2>OpenGL / Mesa</h2>
    <pre>{esc(gpu_mesa)}</pre>
  </div>

  <div class="card">
    <h2>Vulkan</h2>
    <pre>{esc(gpu_vulkan)}</pre>
  </div>
</div>
"""
    return page("Dashboard", body)
