# Multi-arch base: works on Raspberry Pi 5 (arm64) and x86_64
FROM ubuntu:22.04
RUN apt update && apt install -y python3 python3-pip systemd util-linux curl jq

# Prevent Python from writing .pyc files and enable unbuffered logs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install Mosquitto MQTT broker and clients
RUN apt-get update \
    && apt-get install -y --no-install-recommends mosquitto mosquitto-clients docker.io \
    && rm -rf /var/lib/apt/lists/*

#COPY ./configs/mosquitto.conf /etc/mosquitto/mosquitto.conf
COPY ./configs/bridge.conf /etc/mosquitto/mosquitto.conf
# Set work directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# create folder for mqtt pid file
RUN mkdir -p /var/run/mosquitto && chown -R mosquitto:mosquitto /var/run/mosquitto


# Copy project files
COPY . .

# Add entrypoint script
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# Expose HTTP redirect port (80), Django port (8000), and MQTT broker port
EXPOSE 80 8000 1883

# Optional: define settings module explicitly (manage.py sets it too)
ENV DJANGO_SETTINGS_MODULE=django_project.settings

# Run Mosquitto broker and Django server via entrypoint
# For production, consider using gunicorn/uvicorn and proper static handling
CMD ["/usr/local/bin/entrypoint.sh"]
