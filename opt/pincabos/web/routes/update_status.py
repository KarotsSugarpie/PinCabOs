from flask import jsonify


def init_update_status_routes(app, get_job_status_func):
    @app.route("/api/update-status")
    def api_update_status():
        return jsonify(get_job_status_func())
