#!/bin/sh
set -e

# Start Mosquitto broker in the background
echo "Starting Mosquitto MQTT broker..."
# Ensure runtime dir exists (usually created by package, but safe to ensure)
mkdir -p /var/run/mosquitto || true
mosquitto -c /etc/mosquitto/mosquitto.conf -v &
MOSQ_PID=$!

# Start lightweight redirect server on port 80 -> 8000 in the background
echo "Starting HTTP redirect server on port 80 (-> 8000)..."
python3 /app/redirect_server.py &
REDIR_PID=$!

# Small delay to allow services to initialize
sleep 1

# Run Django migrations
echo "Running Django migrations..."
python3 manage.py migrate --noinput

# Start Django dev server in the foreground
echo "Starting Django development server..."
exec python3 manage.py runserver 0.0.0.0:8000
