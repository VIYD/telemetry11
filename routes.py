from flask import jsonify, render_template, request

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
        minutes = request.args.get("minutes", default=15, type=int)
        if minutes is None or minutes <= 0:
            minutes = 15

        data = None
        if metric:
            data = metrics.query.get_series_for_chart(metrics.storage.metrics_storage, metric, minutes)
            logger.debug("Query request metric=%s minutes=%s has_data=%s", metric, minutes, data is not None)

        return render_template(
            "query.html",
            active_page="query",
            metric=metric,
            minutes=minutes,
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

        minutes = request.args.get("minutes", default=15, type=int)
        if minutes is None or minutes <= 0:
            return jsonify({"error": "minutes must be a positive integer"}), 400

        data = metrics.query.get_series_for_api(metrics.storage.metrics_storage, metric, minutes)

        if data is None:
            return jsonify(
                {
                    "metric": metric,
                    "series": [],
                    "start": None,
                    "end": None,
                    "window_minutes": minutes,
                }
            )

        return jsonify(data)

    @app.route("/push", methods=["POST"])
    def push_metrics():
        if not app.config.get("PUSH_API_ENABLED", True):
            logger.warning("Push request rejected because push-api is disabled")
            return jsonify({"error": "push api is disabled"}), 503
        logger.debug("Push request accepted")
        return metrics.ingester.ingest_metric(request, forced_labels={"method": "push"})

    @app.route("/debug/populate")
    def debug_populate():
        metrics.storage.debug_populate()
        logger.info("Debug population invoked")
        return "Debug population completed."
