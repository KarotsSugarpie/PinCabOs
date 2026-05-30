from flask import redirect, url_for


def init_gpu_screens_routes(app):
    @app.route("/gpu/screens")
    def gpu_screens_page():
        return redirect(url_for("gpu_page"), code=302)
