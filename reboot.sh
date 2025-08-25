#!/bin/bash
set -e

# -------------------------------
# CONFIGURATION
# -------------------------------
HELPER_IMAGE="ubuntu:22.04"
DOCKER_SOCKET="/var/run/docker.sock"

# -------------------------------
# CHECKS
# -------------------------------
if [ ! -S "$DOCKER_SOCKET" ]; then
    echo "❌ Docker socket not found at $DOCKER_SOCKET"
    echo "Run the container with:  -v /var/run/docker.sock:/var/run/docker.sock"
    exit 1
fi

# Check if curl is installed, otherwise install it
if ! command -v curl &>/dev/null; then
    echo "⚡ Installing curl..."
    apt-get update -qq && apt-get install -y curl || \
    apk add --no-cache curl || \
    yum install -y curl
fi

# Check if jq is installed, otherwise install it
if ! command -v jq &>/dev/null; then
    echo "⚡ Installing jq..."
    apt-get update -qq && apt-get install -y jq || \
    apk add --no-cache jq || \
    yum install -y jq
fi

# -------------------------------
# PULL HELPER IMAGE IF MISSING
# -------------------------------
echo "⚡ Checking if helper image ($HELPER_IMAGE) is available..."
PULL_RESULT=$(curl --silent --unix-socket $DOCKER_SOCKET \
  -X POST "http://localhost/images/create?fromImage=$HELPER_IMAGE")

if [[ "$PULL_RESULT" == *"error"* ]]; then
    echo "❌ Failed to pull $HELPER_IMAGE. Check your network or permissions."
    echo "Response: $PULL_RESULT"
    exit 1
fi

# -------------------------------
# CREATE HELPER CONTAINER
# -------------------------------
echo "⚡ Creating helper container to reboot the host..."
CID=$(curl --silent --unix-socket $DOCKER_SOCKET \
  -H "Content-Type: application/json" \
  -d "{
        \"Image\": \"$HELPER_IMAGE\",
        \"HostConfig\": {
            \"Privileged\": true,
            \"PidMode\": \"host\"
        },
        \"Cmd\": [\"bash\", \"-c\", \"\
            if command -v systemctl >/dev/null 2>&1; then \
                echo 'Using systemctl to reboot...'; \
                systemctl reboot; \
            elif command -v reboot >/dev/null 2>&1; then \
                echo 'Using reboot binary...'; \
                reboot; \
            else \
                echo 'Using sysrq-trigger to force reboot...'; \
                echo 1 > /proc/sys/kernel/sysrq; \
                echo b > /proc/sysrq-trigger; \
            fi
        \"]
    }" \
  -X POST http://localhost/containers/create | jq -r '.Id')

if [ "$CID" == "null" ] || [ -z "$CID" ]; then
    echo "❌ Failed to create helper container"
    exit 1
fi

# -------------------------------
# START HELPER CONTAINER
# -------------------------------
echo "⚡ Starting helper container: $CID"
START_RESULT=$(curl --silent --unix-socket $DOCKER_SOCKET \
    -X POST http://localhost/containers/$CID/start)

if [ -n "$START_RESULT" ]; then
    echo "❌ Failed to start helper container: $START_RESULT"
    exit 1
fi

echo "✅ Reboot command sent to the host! The system should restart shortly."
