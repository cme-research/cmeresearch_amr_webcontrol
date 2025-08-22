# Unico AMR Control (Django + MQTT)

A lightweight Django web dashboard to control and monitor an AMR (Autonomous Mobile Robot) via MQTT. It provides:
- Live connection status over Server-Sent Events (SSE)
- Manual movement controls and navigation goals published to MQTT
- A simple 2D map renderer (demo) and pose display
- Power menu to issue Shutdown and Restart commands on the Raspberry Pi host


## Requirements
- Python 3.11+
- pip
- An MQTT broker reachable by the server (e.g., Mosquitto)
- (Optional) Docker

Install Python dependencies:

```
pip install -r requirements.txt
```


## Configuration
The application reads configuration from a single JSON file: app_config.json (nested structure).

You can point to a custom file via environment variable:
- APP_CONFIG_FILE=/path/to/app_config.json

Precedence: APP_CONFIG_FILE > app_config.json (repo root).

Example app_config.json:

```
{
  "mqtt": {
    "broker_url": "localhost",
    "broker_port": 1883,
    "subscribe_topic": "fake_odom"
  },
  "topics": {
    "movement": "amr_control/cmd_vel",
    "move_base_goal": "amr_control/move_base_goal"
  },
  "map": {
    "width": 20,
    "height": 20,
    "resolution": 0.05,
    "origin_x": -10.0,
    "origin_y": -10.0,
    "obstacles": []
  }
}
```

Details:
- mqtt.broker_url: Hostname or IP of your MQTT broker.
- mqtt.broker_port: Port (default 1883).
- mqtt.subscribe_topic: Topic to subscribe for robot state/odometry (default "fake_odom").
- topics.movement: Topic used to publish velocity commands.
- topics.move_base_goal: Topic used to publish navigation goals.
- map: Demo map settings used by the frontend visualizer.

The loader applies sensible defaults if keys are missing or if the config file is not present.


## Running the server (development)
Run database migrations and start Django locally:

```
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

Open http://localhost:8000/ to access the dashboard.

Environment variables:
- DJANGO_SETTINGS_MODULE: Defaults to django_project.settings (already set in manage.py). Override if needed.
- APP_CONFIG_FILE: Path to app_config.json as described above.

Static files: This repo uses Django’s development server for static assets. For production, use a proper static files setup.


## Running with Docker
Build and start:

```
docker build -t unico-amr-control .
docker run --rm -p 8000:8000 \
  -e APP_CONFIG_FILE=/app/app_config.json \
  -v $(pwd)/app_config.json:/app/app_config.json:ro \
  unico-amr-control
```

Notes:
- The Docker image runs database migrations on startup and serves via Django’s development server.
- For production, consider running gunicorn/uvicorn behind a reverse proxy and configure static files properly.
- If you intend to use the Power menu (Shutdown/Restart) to control the host from inside a container, you will need additional privileges and a proper sudoers setup. This is generally not recommended; prefer host-level services.


## Power menu (Shutdown/Restart) and sudo configuration
The endpoints POST /shutdown/ and POST /restart/ trigger:
- sudo /sbin/shutdown -h now (shutdown)
- sudo /sbin/shutdown -r now (restart)

To allow the Django process (e.g., running as www-data) to execute shutdown without a password, configure sudoers accordingly on the host:

```
www-data ALL=(root) NOPASSWD: /sbin/shutdown
```

Caveats:
- The process must have access to the shutdown binary (usually /sbin/shutdown) and to sudo.
- In containers, host shutdown/restart typically does not work without special privileges (--privileged or equivalent) and is discouraged.


## Running tests
This is a standard Django project. To run the test suite:

```
python manage.py test
```

You can target specific apps:

```
python manage.py test accounts
python manage.py test amr_control
python manage.py test django_project
```

## enable reboot, shutdown via webapp

Add the following to /etc/sudoers

```
sudo visudo
```

```
robot ALL=(ALL) NOPASSWD: /sbin/shutdown
robot ALL=(ALL) NOPASSWD: /sbin/restart
```


## Project layout
Key paths relative to repo root:
- manage.py: Django entrypoint
- django_project/: Settings, URLs, WSGI/ASGI, MQTT client integration
- amr_control/: Core views, URLs, templates entrypoint
- templates/amr_control/viewport.html: Frontend dashboard
- app_config.json: Runtime configuration (see example)
- Dockerfile: Containerized development runtime


## Troubleshooting
- MQTT not connecting: Verify broker_url/port and network reachability. Check broker logs. The app logs a message when connecting and subscribes to the configured SUBSCRIBE_TOPIC.
- CSRF issues: The dashboard uses the CSRF cookie to POST control actions. Ensure cookies are enabled and the site is served from a consistent host.
- 400/403 on POST actions: Confirm you are using the dashboard UI; it injects X-Requested-With and CSRF headers.
- Shutdown/Restart has no effect: Ensure sudoers is configured and that the process has permissions. In Docker, this typically won’t affect the host without extra privileges.


## License
Add your project’s license here.
