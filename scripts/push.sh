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

if [ -z "$3" ]; then
    METRIC_SOURCE="push.sh"
    echo "No metric source label provided. Defaulting to '$METRIC_SOURCE'."
else
    METRIC_SOURCE=$3
fi

HOST_LABEL=$(hostname)

echo "Will be sleeping for $SLEEP_INTERVAL seconds between pushes of metric '$METRIC_NAME' with labels source='$METRIC_SOURCE', host='$HOST_LABEL'."

push_metric() {
    local metric_value=$1

    curl -X POST http://127.0.0.1:5000/api/push \
        -H "Content-Type: application/json" \
        -d "$(printf '{\"name\":\"%s\",\"value\":%s,\"labels\":{\"source\":\"%s\",\"host\":\"%s\"}}' "$METRIC_NAME" "$metric_value" "$METRIC_SOURCE" "$HOST_LABEL")"
}

SEQ=1
while true; do
    METRIC_VALUE=$((RANDOM % 20))
    echo "Pushing metric value: $METRIC_VALUE"
    push_metric "$METRIC_VALUE" "$SEQ"
    SEQ=$((SEQ + 1))
    sleep "$SLEEP_INTERVAL"
done
