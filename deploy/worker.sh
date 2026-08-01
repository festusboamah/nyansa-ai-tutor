#!/bin/sh
set -eu
while true; do
  python manage.py process_messages --limit 50
  sleep "${MESSAGE_WORKER_INTERVAL_SECONDS:-15}"
done
