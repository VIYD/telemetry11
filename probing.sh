# script to randomly generate value and push it every 10 seconds
#!/bin/bash
if [ -z "$1" ]; then
    SLEEP_INTERVAL=10
    echo "No sleep interval provided. Defaulting to $SLEEP_INTERVAL seconds."
else
    SLEEP_INTERVAL=$1
fi

if [ -z "$2" ]; then
    METRIC_NAME="cpu"
    echo "No metric name provided. Defaulting to '$METRIC_NAME'."
else
    METRIC_NAME=$2
fi

echo "Will be sleeping for $SLEEP_INTERVAL seconds between pushes of metric '$METRIC_NAME'."

push_metric() {
    curl -X POST http://127.0.0.1:5000/push -H "Content-Type: application/json" -d '{"name": "'$METRIC_NAME'", "value": '$METRIC_VALUE'}'
}

while true; do
    METRIC_VALUE=$((RANDOM % 100))
    echo "Pushing metric value: $METRIC_VALUE"
    push_metric $METRIC_VALUE
    sleep $SLEEP_INTERVAL
done
