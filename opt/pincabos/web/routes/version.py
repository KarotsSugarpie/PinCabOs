from flask import jsonify


def init_version_routes(app, pincabos_version_func):
    @app.route("/api/pincabos-version")
    def api_pincabos_version():
        return jsonify(pincabos_version_func())
