from flask import jsonify, render_template, request

from api_docs import _openapi_spec
import metrics.query
import metrics.storage
import metrics.ingester
import metrics.explorer

import startup


def register_routes(app, logger):
    @app.before_request
    def apply_metric_retention_policy():
        retention = app.config.get("METRIC_RETENTION", startup.DEFAULT_RETENTION)
        metrics.storage.prune_old_metrics(retention)
        logger.debug("Applied retention pruning retention=%s", retention)

    @app.route("/")
    def home():
        return render_template("home.html", active_page="home")

    @app.route("/dashboard")
    @app.route("/query")
    def query_page():
        metric = request.args.get("metric")
        mode = (request.args.get("mode") or "relative").strip().lower()
        if mode not in {"relative", "absolute"}:
            mode = "relative"
        start_raw = request.args.get("start")
        end_raw = request.args.get("end")
        timezone_mode = (request.args.get("timezone") or "browser").strip().lower()
        if timezone_mode not in {"browser", "utc"}:
            timezone_mode = "browser"
        tz_offset_minutes = request.args.get("tz_offset_minutes", type=int)
        minutes = request.args.get("minutes", default=15, type=int)
        if minutes is None or minutes <= 0:
            minutes = 15

        query_error = None
        start_time = None
        end_time = None
        if mode == "absolute":
            if not start_raw or not end_raw:
                query_error = "absolute mode requires both start and end"
            else:
                try:
                    browser_offset = tz_offset_minutes if timezone_mode == "browser" else None
                    start_time = metrics.query.parse_time_param(
                        start_raw, browser_tz_offset_minutes=browser_offset
                    )
                    end_time = metrics.query.parse_time_param(
                        end_raw, browser_tz_offset_minutes=browser_offset
                    )
                except ValueError as exc:
                    query_error = f"invalid time format: {exc}"

        data = None
        if metric and query_error is None:
            try:
                data = metrics.query.get_series_for_chart(
                    metrics.storage.metrics_storage,
                    metric,
                    minutes,
                    start_time=start_time,
                    end_time=end_time,
                )
                logger.debug(
                    "Query request metric=%s mode=%s minutes=%s start=%s end=%s has_data=%s",
                    metric,
                    mode,
                    minutes,
                    start_raw,
                    end_raw,
                    data is not None,
                )
            except ValueError as exc:
                query_error = str(exc)

        return render_template(
            "query.html",
            active_page="query",
            metric=metric,
            minutes=minutes,
            mode=mode,
            start=start_raw,
            end=end_raw,
            timezone_mode=timezone_mode,
            tz_offset_minutes=tz_offset_minutes,
            query_error=query_error,
            data=data,
        )

    @app.route("/status")
    def status_page():
        raw_config = app.config.get("RAW_CONFIG", {})
        retention = app.config.get("METRIC_RETENTION", startup.DEFAULT_RETENTION)

        effective_settings = {
            "push-api": app.config.get("PUSH_API_ENABLED", True),
            "metric-retention": startup.format_retention(retention),
            "app-port": app.config.get("APP_PORT", 5000),
            "federate-refresh-seconds": app.config.get("FEDERATE_REFRESH_SECONDS", 60),
            "federate-age-window-seconds": app.config.get("FEDERATE_MAX_AGE_SECONDS", 60),
            "pull.endpoint": app.config.get("SCRAPE_ENDPOINT") or "(disabled)",
            "pull.scrape-interval-seconds": app.config.get("SCRAPE_INTERVAL_SECONDS"),
            "pull.targets": len(app.config.get("PULL_TARGETS") or []),
            "log-level": app.config.get("LOG_LEVEL", "INFO"),
        }

        return render_template(
            "status.html",
            active_page="status",
            config_path=app.config.get("CONFIG_PATH") or "(no --config provided)",
            raw_config=raw_config,
            effective_settings=effective_settings,
        )

    @app.route("/targets")
    def targets_page():
        targets = app.config.get("PULL_TARGETS") or []
        target_rows = startup.snapshot_target_statuses(targets)
        return render_template(
            "targets.html",
            active_page="targets",
            targets=target_rows,
        )

    @app.route("/explorer")
    def explorer_page():
        catalog = metrics.explorer.build_metrics_catalog(metrics.storage.metrics_storage)
        return render_template(
            "explorer.html",
            active_page="explorer",
            metrics_catalog=catalog,
            metrics_total=len(catalog),
        )

    @app.route("/federate")
    def federate_metrics():
        return metrics.storage.federate_metrics()

    @app.route("/api/metrics")
    def api_metrics():
        metric = request.args.get("metric")
        if not metric:
            return jsonify({"error": "metric query parameter is required"}), 400

        mode = (request.args.get("mode") or "relative").strip().lower()
        if mode not in {"relative", "absolute"}:
            return jsonify({"error": "mode must be either 'relative' or 'absolute'"}), 400

        start_raw = request.args.get("start")
        end_raw = request.args.get("end")
        timezone_mode = (request.args.get("timezone") or "browser").strip().lower()
        tz_offset_minutes = request.args.get("tz_offset_minutes", type=int)
        minutes = request.args.get("minutes", default=15, type=int)
        if minutes is None or minutes <= 0:
            return jsonify({"error": "minutes must be a positive integer"}), 400

        start_time = None
        end_time = None
        if mode == "absolute":
            if not start_raw or not end_raw:
                return jsonify({"error": "absolute mode requires both start and end"}), 400
            try:
                browser_offset = tz_offset_minutes if timezone_mode == "browser" else None
                start_time = metrics.query.parse_time_param(
                    start_raw, browser_tz_offset_minutes=browser_offset
                )
                end_time = metrics.query.parse_time_param(
                    end_raw, browser_tz_offset_minutes=browser_offset
                )
            except ValueError as exc:
                return jsonify({"error": f"invalid time format: {exc}"}), 400

        try:
            data = metrics.query.get_series_for_api(
                metrics.storage.metrics_storage,
                metric,
                minutes,
                start_time=start_time,
                end_time=end_time,
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        if data is None:
            return jsonify(
                {
                    "metric": metric,
                    "series": [],
                    "start": start_time.isoformat() if start_time else None,
                    "end": end_time.isoformat() if end_time else None,
                    "window_minutes": minutes,
                    "mode": mode,
                }
            )

        data["mode"] = mode
        return jsonify(data)

    @app.route("/api/push", methods=["POST"])
    def push_metrics():
        if not app.config.get("PUSH_API_ENABLED", True):
            logger.warning("Push request rejected because push-api is disabled")
            return jsonify({"error": "push api is disabled"}), 503
        logger.debug("Push request accepted")
        return metrics.ingester.ingest_metric(request, forced_labels={"method": "push"})

    @app.route("/api/reload", methods=["POST"])
    def reload_config_api():
        try:
            result = startup.reload_runtime_config(app, logger)
            logger.info("Runtime config reloaded path=%s", result.get("config_path"))
            return jsonify(result), 200
        except Exception as exc:
            logger.warning("Runtime config reload failed path=%s error=%s", app.config.get("CONFIG_PATH"), exc)
            return (
                jsonify(
                    {
                        "status": "error",
                        "error": str(exc),
                        "config_path": app.config.get("CONFIG_PATH"),
                    }
                ),
                400,
            )

    @app.route("/debug/populate")
    def debug_populate():
        metrics.storage.debug_populate()
        logger.info("Debug population invoked")
        return "Debug population completed."
    
    @app.route("/openapi.json")
    def openapi_json():
        return jsonify(_openapi_spec())

    @app.route("/swagger")
    def swagger_ui():
        return render_template("swagger.html", active_page="swagger")
