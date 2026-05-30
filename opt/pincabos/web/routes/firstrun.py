from flask import jsonify


def init_firstrun_routes(app, firstrun_load_cfg_func, firstrun_save_cfg_func):
    @app.route("/first-run/popup-disable", methods=["POST"])
    def firstrun_popup_disable():
        cfg = firstrun_load_cfg_func()
        required = ["updates", "network", "gpu", "screens", "audio"]
        if not all(cfg.get(k) for k in required):
            cfg["show_popup"] = True
            firstrun_save_cfg_func(cfg)
            return jsonify({
                "ok": False,
                "error": "Les 5 étapes First Run doivent être complétées avant de désactiver le popup."
            }), 403
        cfg["show_popup"] = False
        firstrun_save_cfg_func(cfg)
        return jsonify({"ok": True})
