import subprocess
from flask import redirect, url_for


def init_vpinfe_routes(app):
    @app.route("/restart-vpinfe", methods=["POST"])
    def restart_vpinfe():
        subprocess.Popen(
            ["/usr/bin/sudo", "/bin/systemctl", "restart", "pincabos-frontend.service"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return redirect(url_for("gpu_page"))
