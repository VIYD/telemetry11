from flask import Flask, jsonify, request
import metrics.storage
import metrics.ingester
from datetime import datetime, timezone

app = Flask(__name__)

@app.route("/metrics")
def get_metrics():
    return metrics.storage.return_metrics()

@app.route("/push", methods=["POST"])
def push_metrics():
    return metrics.ingester.ingest_metric(request)

@app.route("/")
def home():
    return "<h1>Моніторинг</h1><p>Перейдіть на <a href='/metrics'>/metrics</a> для перегляду метрик</p>"

@app.route("/debug/populate")
def debug_populate():
    metrics.storage.debug_populate()
    return "Debug population completed."

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

