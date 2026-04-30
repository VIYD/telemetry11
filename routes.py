from flask import jsonify, render_template, request

from api_docs import _openapi_spec
import metrics.query
import metrics.storage
import metrics.ingester
import metrics.explorer

import startup


def register_routes(app, logger):
    @app.before_request
    def apply_retention_policy_hook():
        metrics.storage.apply_metric_retention_policy(app, logger, startup.DEFAULT_RETENTION)

    @app.route("/")
    def home():
        return render_template("home.html", active_page="home")

    @app.route("/dashboard")
    @app.route("/query")
    def query_page():
        metric = request.args.get("metric")
        range_params = metrics.query._parse_query_range(request.args)
        query_error = range_params.get("error")
        mode = range_params.get("mode", "relative")
        duration_raw = range_params.get("duration_raw")
        start_raw = range_params.get("start_raw")
        end_raw = range_params.get("end_raw")
        timezone_mode = range_params.get("timezone_mode", "browser")
        tz_offset_minutes = range_params.get("tz_offset_minutes")
        minutes = range_params.get("minutes", 15)
        start_time = range_params.get("start_time")
        end_time = range_params.get("end_time")

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
            duration=duration_raw,
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

    @app.route("/api/explorer")
    def explorer_api():
        return jsonify({"metrics": metrics.explorer.build_metrics_catalog(metrics.storage.metrics_storage)})

    @app.route("/federate")
    def federate_metrics():
        return metrics.storage.federate_metrics()

    @app.route("/api/metrics")
    def api_metrics():
        metric = request.args.get("metric")
        if not metric:
            return jsonify({"error": "metric query parameter is required"}), 400

        range_params = metrics.query._parse_query_range(request.args)
        if range_params.get("error"):
            return jsonify({"error": range_params["error"]}), range_params.get("status", 400)

        mode = range_params["mode"]
        minutes = range_params["minutes"]
        start_time = range_params["start_time"]
        end_time = range_params["end_time"]

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
        data["window_minutes"] = minutes
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
