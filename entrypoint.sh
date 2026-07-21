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

# Ensure the shared login account exists. The container's SQLite DB is wiped on
# every start (no volume), so re-seed it each boot. Credentials are overridable
# via env; defaults are robot/test for the VPN-internal shared-operator model.
echo "Ensuring web login user..."
python3 manage.py shell -c "
import os
from django.contrib.auth import get_user_model
U = get_user_model()
name = os.environ.get('CONFIG_WEB_USER', 'robot')
pw = os.environ.get('CONFIG_WEB_PASSWORD', 'test')
u, _ = U.objects.get_or_create(username=name)
u.set_password(pw); u.is_active = True; u.is_staff = True; u.is_superuser = True; u.save()
print('ensured web login user:', name)
"

# Start Django dev server in the foreground
echo "Starting Django development server..."
exec python3 manage.py runserver 0.0.0.0:8000
