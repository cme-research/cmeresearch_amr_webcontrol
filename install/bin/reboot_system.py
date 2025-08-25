#!/usr/bin/env python3
"""
reboot_system.py - Safely request a system reboot from Python.

Features:
- Requires explicit confirmation via --yes (or use --dry-run for testing).
- Checks for root privileges unless --dry-run is used.
- Tries multiple mechanisms in order:
  1) systemctl reboot
  2) reboot (or /sbin/reboot)
  3) shutdown -r now
- Provides clear messaging and exit codes.
- Optional MQTT listener mode to trigger reboot via MQTT topic.

Usage examples:
  # Preview actions without rebooting
  ./reboot_system.py --dry-run

  # Actually reboot (must be run as root)
  sudo ./reboot_system.py --yes

  # Run as MQTT listener (reboots on message trigger)
  sudo ./reboot_system.py --mqtt-listen --mqtt-topic amr_control/system/reboot

Note: The process will typically terminate immediately upon successful reboot invocation.
"""

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional


def is_root() -> bool:
    try:
        return os.geteuid() == 0  # type: ignore[attr-defined]
    except AttributeError:
        # Non-POSIX; fall back to environment heuristics
        return os.name == "nt" and "USERNAME" in os.environ and os.environ.get("USERNAME") == "Administrator"


def find_command(candidates: List[str]) -> Optional[str]:
    for c in candidates:
        path = shutil.which(c)
        if path:
            return path
    return None


def run(cmd: List[str], dry_run: bool = False) -> subprocess.CompletedProcess:
    if dry_run:
        print(f"[DRY-RUN] Would run: {' '.join(cmd)}")
        # Simulate success
        class Dummy:
            returncode = 0
        return Dummy()  # type: ignore[return-value]
    print(f"Executing: {' '.join(cmd)}")
    return subprocess.run(cmd, stdout=sys.stdout, stderr=sys.stderr)


def attempt_reboot(dry_run: bool = False) -> int:
    # 1) systemctl reboot
    systemctl = find_command(["systemctl"])  # rely on PATH
    if systemctl:
        result = run([systemctl, "reboot"], dry_run=dry_run)
        if result.returncode == 0:
            return 0
        else:
            print(f"systemctl reboot failed with code {result.returncode}")

    # 2) reboot (try PATH then common absolute path)
    reboot_cmd = find_command(["reboot"]) or ("/sbin/reboot" if os.path.exists("/sbin/reboot") else None)
    if reboot_cmd:
        result = run([reboot_cmd, "now"], dry_run=dry_run)
        if result.returncode == 0:
            return 0
        else:
            print(f"reboot command failed with code {result.returncode}")

    # 3) shutdown -r now
    shutdown_cmd = find_command(["shutdown"]) or ("/sbin/shutdown" if os.path.exists("/sbin/shutdown") else None)
    if shutdown_cmd:
        result = run([shutdown_cmd, "-r", "now"], dry_run=dry_run)
        if result.returncode == 0:
            return 0
        else:
            print(f"shutdown -r now failed with code {result.returncode}")

    print("No suitable reboot method succeeded or is available.")
    return 1


# --- MQTT support ---

def _load_app_config() -> dict:
    """Load app_config.json similar to django_project.mqtt_client, but only fields we need."""
    base_dir = Path(__file__).resolve().parents[2]  # project root
    default_app = base_dir / 'app_config.json'
    path = os.getenv('APP_CONFIG_FILE') or str(default_app)

    cfg = {
        'mqtt': {
            'broker_url': 'localhost',
            'broker_port': 1883,
        }
    }
    try:
        with open(path, 'r') as f:
            data = json.load(f)
            if isinstance(data, dict):
                mqttd = data.get('mqtt', {}) or {}
                if isinstance(mqttd.get('broker_url'), str) and mqttd.get('broker_url'):
                    cfg['mqtt']['broker_url'] = mqttd['broker_url']
                if 'broker_port' in mqttd:
                    try:
                        cfg['mqtt']['broker_port'] = int(mqttd['broker_port'])
                    except (ValueError, TypeError):
                        pass
    except FileNotFoundError:
        print(f"App config file not found at {path}. Using defaults.")
    except json.JSONDecodeError as e:
        print(f"Invalid JSON in app config file {path}: {e}. Using defaults.")
    except Exception as e:
        print(f"Error reading app config file {path}: {e}. Using defaults.")
    return cfg


def _parse_mqtt_trigger_payload(payload: bytes) -> bool:
    """Return True if payload is a reboot trigger."""
    try:
        text = payload.decode('utf-8', errors='ignore').strip().lower()
    except Exception:
        text = ''
    if text in {"reboot", "now", "true", "1", "restart"}:
        return True
    # Try JSON forms like {"action":"reboot"} or {"command":"reboot"}
    try:
        data = json.loads(payload.decode('utf-8', errors='ignore'))
        if isinstance(data, dict):
            action = str(data.get('action') or data.get('command') or '').strip().lower()
            return action == 'reboot'
    except Exception:
        pass
    return False


def _run_mqtt_listener(broker: str, port: int, topic: str, dry_run: bool) -> int:
    import paho.mqtt.client as mqtt  # lazy import

    triggered = {'done': False, 'rc': 0}

    def on_connect(client, userdata, flags, rc, properties=None):
        print(f"[MQTT] Connected rc={rc}, subscribing to {topic}")
        try:
            client.subscribe(topic)
        except Exception as e:
            print(f"[MQTT] Subscribe failed: {e}")

    def on_message(client, userdata, msg):
        print(f"[MQTT] Message on {msg.topic}: {msg.payload}")
        if _parse_mqtt_trigger_payload(msg.payload):
            print("[MQTT] Reboot trigger received")
            triggered['rc'] = attempt_reboot(dry_run=dry_run)
            triggered['done'] = True
            # After requesting reboot, stop loop (system will likely reboot)
            try:
                client.disconnect()
            except Exception:
                pass

    def on_disconnect(client, userdata, rc, properties=None):
        print(f"[MQTT] Disconnected rc={rc}")

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message
    client.on_disconnect = on_disconnect

    # Optional auth via env vars
    user = os.getenv('MQTT_USERNAME')
    pwd = os.getenv('MQTT_PASSWORD')
    if user is not None:
        try:
            client.username_pw_set(user, pwd)
        except Exception as e:
            print(f"[MQTT] username_pw_set error: {e}")

    # Optional TLS
    if os.getenv('MQTT_TLS', '').lower() in ('1', 'true', 'yes'):
        try:
            client.tls_set()
        except Exception as e:
            print(f"[MQTT] tls_set error: {e}")

    print(f"[MQTT] Connecting to {broker}:{port}, topic={topic}")
    client.connect(broker, port, keepalive=60)

    # Graceful shutdown on SIGINT/SIGTERM
    stopping = {'stop': False}

    def _stop(signum, frame):
        print(f"[MQTT] Caught signal {signum}, stopping loop...")
        stopping['stop'] = True
        try:
            client.disconnect()
        except Exception:
            pass

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    client.loop_start()
    try:
        while not stopping['stop'] and not triggered['done']:
            time.sleep(0.2)
    finally:
        try:
            client.loop_stop()
        except Exception:
            pass
    return triggered['rc']


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Request a system reboot safely or listen for MQTT trigger.")
    parser.add_argument("--yes", action="store_true", help="Confirm you really want to reboot now (CLI mode).")
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen without rebooting.")

    # MQTT options
    parser.add_argument("--mqtt-listen", action="store_true", help="Run as an MQTT listener waiting for reboot trigger.")
    parser.add_argument("--mqtt-topic", default=os.getenv('REBOOT_TOPIC', 'amr_control/system/reboot'), help="MQTT topic to subscribe for reboot trigger.")
    parser.add_argument("--mqtt-broker", default=None, help="MQTT broker hostname/IP. Overrides app_config.json.")
    parser.add_argument("--mqtt-port", type=int, default=None, help="MQTT broker port. Overrides app_config.json.")

    args = parser.parse_args(argv)

    if args.mqtt_listen:
        conf = _load_app_config()
        broker = args.mqtt_broker or conf['mqtt']['broker_url']
        port = args.mqtt_port or conf['mqtt']['broker_port']
        print("Starting MQTT listener for reboot trigger...")
        if args.dry_run:
            print("Dry-run mode: will not actually reboot upon trigger.")
        # In MQTT mode, we assume operator intent via topic, so we don't require --yes.
        return _run_mqtt_listener(broker, port, args.mqtt_topic, dry_run=args.dry_run)

    # CLI direct invocation mode
    if not args.dry_run and not args.yes:
        print("Refusing to reboot without explicit confirmation. Re-run with --yes, or use --dry-run to test.")
        return 2

    if not args.dry_run and not is_root():
        print("This script must be run as root to perform a reboot. Try: sudo ./reboot_system.py --yes")
        return 3

    if args.dry_run:
        print("Dry-run mode: no changes will be made.")

    print("System reboot requested")
    return attempt_reboot(dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
