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
  <input type="text" name="metric" value="{{ metric or '' }}">
  <button type="submit">Show</button>
</form>

{% if data_json %}
<canvas id="chart" width="900" height="400"></canvas>
<script>
  const payload = {{ data_json | safe }};

  new Chart(document.getElementById('chart'), {
    type: 'line',
    data: {
      datasets: [{
        label: '{{ metric }} (last 15 min)',
        data: payload.series,
        parsing: false,
        borderWidth: 2,
        pointRadius: 2
      }]
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
    data = None

    if metric:
        data = metrics.query.get_series_for_chart(metrics.storage.metrics_storage, metric)

    return render_template_string(
        HTML_TEMPLATE,
        metric=metric,
        data_json=json.dumps(data),
    )

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

