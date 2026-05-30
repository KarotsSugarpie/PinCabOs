from flask import jsonify, request, redirect


def init_firstrun_routes(app, firstrun_load_cfg_func, firstrun_save_cfg_func, firstrun_default_cfg_func):
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

    @app.route("/first-run/save", methods=["POST"])
    def firstrun_save():
        cfg = firstrun_default_cfg_func()
        for key in ["updates", "network", "gpu", "screens", "audio"]:
            cfg[key] = request.form.get(key) == "1"
        if all(cfg.get(k) for k in ["updates", "network", "gpu", "screens", "audio"]):
            cfg["show_popup"] = request.form.get("show_popup") == "1"
        else:
            cfg["show_popup"] = True
        firstrun_save_cfg_func(cfg)
        return redirect("/first-run")

