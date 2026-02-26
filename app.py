from flask import Flask, jsonify, request, render_template_string
import json
import metrics.storage
import metrics.ingester
import metrics.query
from datetime import datetime, timezone

app = Flask(__name__)

HTML_TEMPLATE = """
<!doctype html>
<html>
<head>
  <title>Metrics Dashboard</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns"></script>
</head>
<body>

<form method="get">
  <input type="text" name="metric" value="{{ metric or '' }}" placeholder='metric selector'>
  <input type="number" name="minutes" value="{{ minutes or 15 }}" min="1" step="1">
  <button type="submit">Show</button>
</form>

{% if data_json %}
<canvas id="chart" width="900" height="400"></canvas>
<script>
  const payload = {{ data_json | safe }};

  new Chart(document.getElementById('chart'), {
    type: 'line',
    data: {
      datasets: payload.series.map(s => ({
        label: s.name + ' (last ' + payload.window_minutes + ' min)',
        data: s.points,
        parsing: false,
        borderWidth: 2,
        pointRadius: 2
      }))
    },
    options: {
      scales: {
        x: {
          type: 'time',
          min: payload.start,
          max: payload.end
        }
      }
    }
  });
</script>

{% endif %}

</body>
</html>

"""

@app.route("/federate")
def federate_metrics():
    return metrics.storage.federate_metrics()

@app.route("/dashboard")
def dashboard():
    metric = request.args.get("metric")
    minutes = request.args.get("minutes", default=15, type=int)
    if minutes is None or minutes <= 0:
        minutes = 15

    data = None

    if metric:
        data = metrics.query.get_series_for_chart(
            metrics.storage.metrics_storage, metric, minutes
        )

    return render_template_string(
        HTML_TEMPLATE,
        metric=metric,
        minutes=minutes,
        data_json=json.dumps(data),
    )


@app.route("/api/metrics")
def api_metrics():
    metric = request.args.get("metric")
    if not metric:
        return jsonify({"error": "metric query parameter is required"}), 400

    minutes = request.args.get("minutes", default=15, type=int)
    if minutes is None or minutes <= 0:
        return jsonify({"error": "minutes must be a positive integer"}), 400

    data = metrics.query.get_series_for_api(
        metrics.storage.metrics_storage, metric, minutes
    )

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
    return metrics.ingester.ingest_metric(request)

@app.route("/")
def home():
    return "<h1>Моніторинг</h1><p>Перейдіть на <a href='/federate'>/federate</a> для перегляду метрик</p><p>Перейдіть на <a href='/dashboard'>/dashboard</a> для візуалізації метрик</p>"

@app.route("/debug/populate")
def debug_populate():
    metrics.storage.debug_populate()
    return "Debug population completed."

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

