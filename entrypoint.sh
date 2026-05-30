#!/bin/sh
set -e

# Note: this container does NOT run its own mosquitto broker. In the deployed
# compose stack (docker-compose.prod.yml) mosquitto runs as a dedicated
# service; this container uses network_mode: host and connects to it via
# localhost:1883. A second broker started here would race the dedicated one
# for host port 1883 (whichever lost would silently exit because it was
# backgrounded with `&`) and, when it won, would have no bridge to the
# remote broker.

# Start lightweight redirect server on port 80 -> 8000 in the background
echo "Starting HTTP redirect server on port 80 (-> 8000)..."
python3 /app/redirect_server.py &
REDIR_PID=$!

# Run Django migrations
echo "Running Django migrations..."
python3 manage.py migrate --noinput

# Start Django dev server in the foreground
echo "Starting Django development server..."
exec python3 manage.py runserver 0.0.0.0:8000
