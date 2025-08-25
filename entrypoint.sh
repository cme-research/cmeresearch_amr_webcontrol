#!/bin/sh
set -e

# Start Mosquitto broker in the background
echo "Starting Mosquitto MQTT broker..."
# Ensure runtime dir exists (usually created by package, but safe to ensure)
mkdir -p /var/run/mosquitto || true
mosquitto -c /etc/mosquitto/mosquitto.conf -v &
MOSQ_PID=$!

# Small delay to allow broker to initialize
sleep 1

# Run Django migrations
echo "Running Django migrations..."
python3 manage.py migrate --noinput

# Start Django dev server in the foreground
echo "Starting Django development server..."
exec python3 manage.py runserver 0.0.0.0:8000
