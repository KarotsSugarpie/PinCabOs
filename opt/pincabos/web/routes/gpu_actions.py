import subprocess
from flask import redirect, url_for


def init_gpu_actions_routes(app):
    @app.route("/auto-screens", methods=["POST"])
    def auto_screens():
        subprocess.Popen(
            ["/usr/bin/sudo", "/opt/pincabos/tools/auto-detect-screens.sh"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return redirect(url_for("gpu_page"))
