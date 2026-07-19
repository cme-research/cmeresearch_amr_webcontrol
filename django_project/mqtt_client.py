import paho.mqtt.client as mqtt
from queue import Queue, Full, Empty
import json
import math
import random
import os
import threading
import time
from pathlib import Path

# Fan-out registry: one bounded queue per active SSE connection.
#
# Previously a single global Queue was shared by every SSE consumer, so N
# open browser tabs stole each other's messages (each MQTT message was
# delivered to only one of them, round-robin). Instead, every SSE connection
# registers its own queue and MQTT callbacks broadcast to all of them, so
# each tab sees the full stream independently. The queues are bounded and
# drop their oldest item under backpressure, which also caps memory if a
# consumer stalls.
_subscribers = []
_subscribers_lock = threading.Lock()
_SUBSCRIBER_MAXSIZE = 100


def register_subscriber():
    """Register a new SSE consumer; returns its private bounded queue."""
    q = Queue(maxsize=_SUBSCRIBER_MAXSIZE)
    with _subscribers_lock:
        _subscribers.append(q)
    return q


def unregister_subscriber(q):
    """Drop an SSE consumer's queue when its connection closes."""
    with _subscribers_lock:
        try:
            _subscribers.remove(q)
        except ValueError:
            pass


def broadcast_message(message):
    """Fan a message out to every registered SSE consumer.

    Each consumer has its own bounded queue. If one is full (a slow or
    stalled client) its oldest item is dropped to make room, so a bad
    consumer can never block the MQTT callback thread or grow without bound.
    """
    with _subscribers_lock:
        subs = list(_subscribers)
    for q in subs:
        try:
            q.put_nowait(message)
        except Full:
            try:
                q.get_nowait()
            except Empty:
                pass
            try:
                q.put_nowait(message)
            except Full:
                pass

# Global variable to track connection status
is_connected = False

# Topics for sending commands (defaults, can be overridden by app_config.json)
MOVEMENT_TOPIC = "amr_control/cmd_vel"
MOVE_BASE_GOAL_TOPIC = "amr_control/move_base_goal"
SUBSCRIBE_TOPIC = "fake_odom"
ROBOT_STATE_TOPIC = "robot_state"
ROBOT_CMD_TOPIC = "robot_cmd"
NAV_STATUS_TOPIC = "navigation/status"
SYSTEM_STATS_TOPIC = "system/stats"
POSE_TOPIC = "base/robot_pose"
MOTOR_FEEDBACK_TOPICS = {
    "front_left": "base/front_left/feedback",
    "front_right": "base/front_right/feedback",
    "rear_left": "base/rear_left/feedback",
    "rear_right": "base/rear_right/feedback",
}

# Global variable to store the latest robot pose
current_pose = {
    "position": {"x": 0.0, "y": 0.0},
    "orientation": {"z": 0.0}
}

current_nav_status = "idle"
# Live NavigateToPose feedback (all zero unless navigating).
current_nav_feedback = {
    "distance_remaining": 0.0,
    "estimated_time_remaining": 0.0,
    "navigation_time": 0.0,
    "number_of_recoveries": 0,
}
current_system_stats = {}
current_motor_feedback = {
    "front_left": {}, "front_right": {}, "rear_left": {}, "rear_right": {}
}

# Global variable to store the latest robot state from the state machine
current_robot_state = {
    "state": "unknown",
    "timestamp": None,
    "driver_names": [],
    "driver_states": [],
}

# Global variable to store the 2D SLAM map data
# This is a simple example map with obstacles
# In a real implementation, this would be updated from actual SLAM data
map_data = {
    "width": 20,  # meters
    "height": 20,  # meters
    "resolution": 0.05,  # meters per pixel
    "origin_x": -10.0,  # meters
    "origin_y": -10.0,  # meters
    "obstacles": []  # List of obstacle coordinates (x, y)
}

# Generate some random obstacles for the example map
for _ in range(20):
    x = random.uniform(-9.0, 9.0)
    y = random.uniform(-9.0, 9.0)
    radius = random.uniform(0.2, 1.0)
    map_data["obstacles"].append({"x": x, "y": y, "radius": radius})


def on_connect(client, userdata, flags, rc):
    global is_connected
    print("Connected with result code " + str(rc))
    try:
        client.subscribe(SUBSCRIBE_TOPIC)
        client.subscribe(ROBOT_STATE_TOPIC)
        client.subscribe(NAV_STATUS_TOPIC)
        client.subscribe(SYSTEM_STATS_TOPIC)
        client.subscribe(POSE_TOPIC)
        for topic in MOTOR_FEEDBACK_TOPICS.values():
            client.subscribe(topic)
    except Exception as e:
        print(f"Failed to subscribe: {e}")
    is_connected = True


def on_disconnect(client, userdata, rc):
    global is_connected
    print("Disconnected with result code " + str(rc))
    is_connected = False


# Function to get the current connection status
def get_connection_status():
    return is_connected


def send_movement_command(linear_x=0.0, linear_y=0.0, angular_z=0.0):
    """
    Send a movement command to the robot.

    Args:
        linear_x (float): Forward/backward velocity in m/s
        linear_y (float): Left/right velocity in m/s
        angular_z (float): Rotational velocity in rad/s

    Returns:
        bool: True if the command was sent successfully, False otherwise
    """
    if not is_connected:
        print("Cannot send command: MQTT client not connected")
        return False

    command = {
        "header": {
            "frame_id": "base_link",
            "stamp": {"sec": 0, "nanosec": 0}
        },
        "twist": {
            "linear":  {"x": linear_x, "y": linear_y, "z": 0.0},
            "angular": {"x": 0.0, "y": 0.0, "z": angular_z}
        }
    }

    try:
        result = mqtt_client.publish(MOVEMENT_TOPIC, json.dumps(command))
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            print(f"Movement command sent: {command}")
            return True
        else:
            print(f"Failed to send movement command: {result}")
            return False
    except Exception as e:
        print(f"Error sending movement command: {e}")
        return False


def send_move_base_goal(position_x, position_y, orientation_z):
    """
    Send a move_base_goal command to navigate the robot to a specific pose.

    Args:
        position_x (float): Target X position in meters
        position_y (float): Target Y position in meters
        orientation_z (float): Target orientation in radians

    Returns:
        bool: True if the command was sent successfully, False otherwise
    """
    if not is_connected:
        print("Cannot send goal: MQTT client not connected")
        return False

    # Create a ROS2-compatible move_base_goal message
    goal = {
        "pose": {
            "position": {
                "x": position_x,
                "y": position_y,
                "z": 0.0
            },
            "orientation": {
                "x": 0.0,
                "y": 0.0,
                "z": orientation_z,
                "w": 1.0  # Simplified quaternion
            }
        }
    }

    try:
        result = mqtt_client.publish(MOVE_BASE_GOAL_TOPIC, json.dumps(goal))
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            print(f"Move base goal sent: {goal}")
            return True
        else:
            print(f"Failed to send move base goal: {result}")
            return False
    except Exception as e:
        print(f"Error sending move base goal: {e}")
        return False


def get_current_pose():
    """
    Get the current pose of the robot.

    Returns:
        dict: A dictionary containing the current position and orientation
    """
    return current_pose


def get_current_robot_state():
    return current_robot_state


def send_robot_command(cmd: str) -> bool:
    if not is_connected:
        print("Cannot send robot command: MQTT client not connected")
        return False
    try:
        payload = json.dumps({"data": cmd})
        result = mqtt_client.publish(ROBOT_CMD_TOPIC, payload)
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            print(f"Robot command sent: {cmd}")
            return True
        print(f"Failed to send robot command: {result}")
        return False
    except Exception as e:
        print(f"Error sending robot command: {e}")
        return False


def on_robot_state_message(client, userdata, msg):
    global current_robot_state
    try:
        data = json.loads(msg.payload.decode())
        state = data.get("state", "unknown")
        stamp = data.get("header", {}).get("stamp", {})
        driver_names = data.get("driver_names", [])
        driver_states = data.get("driver_states", [])
        current_robot_state = {
            "state": state,
            "timestamp": stamp,
            "driver_names": driver_names,
            "driver_states": driver_states,
        }
        broadcast_message({
            "type": "robot_state",
            "robot_state": state,
            "robot_state_stamp": stamp,
            "driver_names": driver_names,
            "driver_states": driver_states,
        })
        print(f"Robot state: {state}, drivers: {list(zip(driver_names, driver_states))}")
    except json.JSONDecodeError:
        print("Invalid JSON in robot state message")


def on_nav_status_message(client, userdata, msg):
    global current_nav_status, current_nav_feedback
    try:
        data = json.loads(msg.payload.decode())
    except (json.JSONDecodeError, AttributeError):
        current_nav_status = msg.payload.decode()
        broadcast_message({"type": "nav_status", "nav_status": current_nav_status})
        return
    # Typed cmeresearch_msgs/NavStatus uses "status" + feedback fields; the
    # legacy std_msgs/String bridge used "data". Accept both.
    current_nav_status = data.get("status", data.get("data", "idle"))
    current_nav_feedback = {
        "distance_remaining": data.get("distance_remaining", 0.0),
        "estimated_time_remaining": data.get("estimated_time_remaining", 0.0),
        "navigation_time": data.get("navigation_time", 0.0),
        "number_of_recoveries": data.get("number_of_recoveries", 0),
    }
    broadcast_message({
        "type": "nav_status",
        "nav_status": current_nav_status,
        "nav_feedback": current_nav_feedback,
    })


def on_system_stats_message(client, userdata, msg):
    global current_system_stats
    try:
        current_system_stats = json.loads(msg.payload.decode())
        broadcast_message({"type": "system_stats", "system_stats": current_system_stats})
    except json.JSONDecodeError:
        pass


def _make_motor_feedback_callback(wheel_name):
    def callback(client, userdata, msg):
        try:
            data = json.loads(msg.payload.decode())
            current_motor_feedback[wheel_name] = {
                "velocity": data.get("current_velocity", 0.0),
                "position": data.get("current_position", 0),
                "input_voltage": data.get("input_voltage", 0),
                "current_consumption": data.get("current_consumption", 0),
            }
        except json.JSONDecodeError:
            pass
    return callback


def get_nav_status():
    return current_nav_status


def get_nav_feedback():
    return current_nav_feedback


def get_system_stats():
    return current_system_stats


def get_motor_feedback():
    return current_motor_feedback


def get_map_data():
    """
    Get the current 2D SLAM map data.

    Returns:
        dict: A dictionary containing the map data
    """
    return map_data


# The mecanum controller publishes odometry at ~50 Hz, but the SSE consumer
# (mqtt_stream_view) only drains its queue at ~10 Hz. Forwarding every sample
# keeps the bounded per-client queue permanently full, so the browser is served
# the *oldest* retained sample — velocity/pose end up lagging ~1-2 s behind the
# robot. Throttle the odometry broadcast to match the consumer rate.
_ODOM_BROADCAST_MIN_INTERVAL = 0.1  # seconds -> ~10 Hz
_last_odom_broadcast = 0.0


def on_message(client, userdata, msg):
    # Default handler: this fires for the odometry subscription
    # (mqtt.subscribe_topic, e.g. cmeresearch/cmexaiii-001/base/odometry).
    # Provides the *measured* velocity twist from nav_msgs/Odometry (NOT
    # cmd_vel). The Position tile is driven separately by on_pose_message
    # (map-frame pose), because odometry is in the drifting odom frame.
    global _last_odom_broadcast
    try:
        data = json.loads(msg.payload.decode())

        # nav_msgs/Odometry: twist.twist is the body-frame velocity.
        linear_x = data.get("twist", {}).get("twist", {}).get("linear", {}).get("x", 0.0)
        linear_y = data.get("twist", {}).get("twist", {}).get("linear", {}).get("y", 0.0)
        angular_z = data.get("twist", {}).get("twist", {}).get("angular", {}).get("z", 0.0)

        # Throttle the SSE broadcast to ~10 Hz to avoid flooding the queue.
        now = time.time()
        if now - _last_odom_broadcast < _ODOM_BROADCAST_MIN_INTERVAL:
            return
        _last_odom_broadcast = now

        broadcast_message({
            "linear": {"x": linear_x, "y": linear_y},
            "angular": {"z": angular_z},
        })
    except json.JSONDecodeError:
        print("Invalid JSON message received")


def on_pose_message(client, userdata, msg):
    # Map-frame robot pose from cmeresearch_robot_state/map_pose_node, bridged to
    # the configured pose topic (e.g. cmeresearch/cmexaiii-001/base/robot_pose).
    # geometry_msgs/PoseStamped -> Position tile + the pose used by "save pose".
    # This is the robot's true pose on the map (valid in mapping and
    # localization modes), unlike the drifting odometry pose.
    global current_pose
    try:
        data = json.loads(msg.payload.decode())
    except (json.JSONDecodeError, AttributeError):
        return
    pose = data.get("pose", {})
    position = pose.get("position", {})
    q = pose.get("orientation", {})
    px = position.get("x", 0.0)
    py = position.get("y", 0.0)
    # Quaternion -> yaw (rotation about z); this is what the tile shows as rad.
    qx = q.get("x", 0.0)
    qy = q.get("y", 0.0)
    qz = q.get("z", 0.0)
    qw = q.get("w", 1.0)
    yaw = math.atan2(2.0 * (qw * qz + qx * qy), 1.0 - 2.0 * (qy * qy + qz * qz))

    current_pose = {"position": {"x": px, "y": py}, "orientation": {"z": yaw}}
    broadcast_message({
        "position": {"x": px, "y": py},
        "orientation": {"z": yaw},
    })


# Set up the MQTT client
mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
mqtt_client.on_connect = on_connect
mqtt_client.on_disconnect = on_disconnect
mqtt_client.on_message = on_message
mqtt_client.message_callback_add(ROBOT_STATE_TOPIC, on_robot_state_message)
mqtt_client.message_callback_add(NAV_STATUS_TOPIC, on_nav_status_message)
mqtt_client.message_callback_add(SYSTEM_STATS_TOPIC, on_system_stats_message)
mqtt_client.message_callback_add(POSE_TOPIC, on_pose_message)
for _wheel, _topic in MOTOR_FEEDBACK_TOPICS.items():
    mqtt_client.message_callback_add(_topic, _make_motor_feedback_callback(_wheel))

# Unified application configuration loader.
# Precedence for config file path:
#   1) APP_CONFIG_FILE env var
#   2) app_config.json at project root
# app_config.json expected structure:
# {
#   "mqtt": {"broker_url": "localhost", "broker_port": 1883, "subscribe_topic": "fake_odom"},
#   "topics": {"movement": "amr_control/cmd_vel", "move_base_goal": "amr_control/move_base_goal"},
#   "map": {"width":20,"height":20,"resolution":0.05,"origin_x":-10.0,"origin_y":-10.0,"obstacles": []}
# }

def _read_robot_yaml(path):
    """Parse robot.yaml; return the dict, or None if missing/unreadable/no PyYAML."""
    try:
        import yaml
    except ImportError:
        print("robot.yaml present but PyYAML not installed; using app_config.json.")
        return None
    try:
        with open(path) as f:
            data = yaml.safe_load(f) or {}
    except Exception as e:
        print(f"Error reading robot.yaml {path}: {e}; using app_config.json.")
        return None
    return data if isinstance(data, dict) else None


def _topics_for_instance(instance):
    """The cmeresearch/<instance>/... MQTT layout — the one place it's encoded,
    so robot.yaml only needs to carry the instance id."""
    p = f"cmeresearch/{instance}"
    return {
        'subscribe_topic': f"{p}/base/odometry",
        'movement': f"{p}/mqtt/cmd_vel",
        'move_base_goal': f"{p}/amr_control/move_base_goal",
        'robot_state': f"{p}/robot_state",
        'robot_cmd': f"{p}/robot_cmd",
        'nav_status': f"{p}/navigation/status",
        'system_stats': f"{p}/system/stats",
        'robot_pose': f"{p}/base/robot_pose",
        'motor_feedback_prefix': f"{p}/base",
    }


def _apply_robot_yaml_data(cfg, data):
    """Overlay robot.yaml onto cfg: derive the MQTT topics from identity.instance
    and apply mqtt/control/map overrides (robot.yaml wins where it sets a value)."""
    identity = data.get('identity', {}) or {}
    instance = str(identity.get('instance') or '').strip()
    if instance:
        t = _topics_for_instance(instance)
        cfg['mqtt']['subscribe_topic'] = t.pop('subscribe_topic')
        cfg['topics'].update(t)

    mqttd = data.get('mqtt', {}) or {}
    if isinstance(mqttd, dict):
        if isinstance(mqttd.get('broker_url'), str) and mqttd['broker_url']:
            cfg['mqtt']['broker_url'] = mqttd['broker_url']
        if 'broker_port' in mqttd:
            try:
                cfg['mqtt']['broker_port'] = int(mqttd['broker_port'])
            except (ValueError, TypeError):
                pass

    control = data.get('control', {}) or {}
    if isinstance(control, dict):
        if isinstance(control.get('drive_type'), str) and control['drive_type']:
            cfg['drive_type'] = control['drive_type']
        if isinstance(control.get('docker_log_container'), str) and control['docker_log_container']:
            cfg['docker_log_container'] = control['docker_log_container']
        wheels = control.get('motor_feedback_wheels')
        if isinstance(wheels, list) and wheels and all(isinstance(w, str) and w for w in wheels):
            cfg['motor_feedback_wheels'] = wheels
        for section in ('limits', 'velocities'):
            src = control.get(section, {})
            if isinstance(src, dict):
                for k in list(cfg[section].keys()):
                    if k in src:
                        try:
                            cfg[section][k] = float(src[k])
                        except (ValueError, TypeError):
                            pass

    mp = data.get('map', {}) or {}
    if isinstance(mp, dict):
        for k in ['width', 'height', 'resolution', 'origin_x', 'origin_y']:
            if k in mp:
                try:
                    cfg['map'][k] = float(mp[k]) if k in ['resolution', 'origin_x', 'origin_y'] else int(mp[k])
                except (ValueError, TypeError):
                    pass
        if isinstance(mp.get('obstacles'), list):
            cfg['map']['obstacles'] = mp['obstacles']
        # map_id intentionally not wired yet — keeps the saved-pose namespace at
        # 'default' across the app_config -> robot.yaml switch (no orphaned poses).


def _load_app_config():
    base_dir = Path(__file__).resolve().parent.parent

    # robot.yaml is the single source of truth (Phase 1), mounted by compose at
    # /robot/config/robot.yaml (override with ROBOT_CONFIG_FILE). It is overlaid
    # ON TOP of the app_config JSON below: robot.yaml wins for identity/topics and
    # anything it sets, while the JSON still supplies control defaults for robots
    # not yet fully migrated. APP_CONFIG_FILE (explicit) disables the overlay.
    explicit = os.getenv('APP_CONFIG_FILE')
    robot_yaml_path = os.getenv('ROBOT_CONFIG_FILE', '/robot/config/robot.yaml')
    _yaml_data = None
    if not explicit and robot_yaml_path and os.path.exists(robot_yaml_path):
        _yaml_data = _read_robot_yaml(robot_yaml_path)

    # Base JSON layer. Instance hint prefers robot.yaml, then the ROBOT_INSTANCE
    # env, so the matching app_config.<instance>.json is picked.
    if explicit:
        path = explicit
    else:
        instance = ''
        if _yaml_data:
            instance = str((_yaml_data.get('identity') or {}).get('instance') or '').strip()
        instance = instance or (os.getenv('ROBOT_INSTANCE') or '').strip()
        per_instance = (base_dir / f'app_config.{instance}.json') if instance else None
        if per_instance is not None and per_instance.exists():
            path = str(per_instance)
        else:
            path = str(base_dir / 'app_config.json')

    # Defaults (mecanum cmexaiii-shaped, to preserve behaviour when unset)
    cfg = {
        'mqtt': {
            'broker_url': 'localhost',
            'broker_port': 1883,
            'subscribe_topic': 'fake_odom',
        },
        'topics': {
            'movement': 'amr_control/cmd_vel',
            'move_base_goal': 'amr_control/move_base_goal',
            'robot_state': 'robot_state',
            'robot_cmd': 'robot_cmd',
        },
        # Server-side velocity caps (see views.py). Defaults match cmexaiii's
        # stepper ceiling; a diff robot with different hardware overrides them.
        'limits': {
            'max_linear_x': 0.31,
            'max_linear_y': 0.3,
            'max_angular_z': 0.8,
        },
        # 'mecanum' (holonomic, has strafe) or 'diff' (no lateral motion).
        'drive_type': 'mecanum',
        # Container the Docker-logs viewer tails by default.
        'docker_log_container': 'cmexaiii-hardware',
        # Wheels exposed in the motor-feedback panel (mecanum = 4; a 2-motor
        # diff base overrides this to its driven wheels).
        'motor_feedback_wheels': ['front_left', 'front_right', 'rear_left', 'rear_right'],
        'velocities': {
            # Defaults for button movements
            'forward': 0.2,   # linear_x m/s
            'backward': -0.2, # linear_x m/s (negative)
            'left': 0.2,      # linear_y m/s
            'right': -0.2,    # linear_y m/s (negative)
            'rotate_cw': -0.5,   # angular_z rad/s (negative = clockwise)
            'rotate_ccw': 0.5,   # angular_z rad/s
        },
        'map': {
            'width': 20,
            'height': 20,
            'resolution': 0.05,
            'origin_x': -10.0,
            'origin_y': -10.0,
            'obstacles': [],
        }
    }

    try:
        with open(path, 'r') as f:
            data = json.load(f)
            if isinstance(data, dict):
                # Normal nested structure
                mqttd = data.get('mqtt', {})
                if isinstance(mqttd, dict):
                    if isinstance(mqttd.get('broker_url'), str) and mqttd.get('broker_url'):
                        cfg['mqtt']['broker_url'] = mqttd['broker_url']
                    if 'broker_port' in mqttd:
                        try:
                            cfg['mqtt']['broker_port'] = int(mqttd['broker_port'])
                        except (ValueError, TypeError):
                            pass
                    if isinstance(mqttd.get('subscribe_topic'), str) and mqttd.get('subscribe_topic'):
                        cfg['mqtt']['subscribe_topic'] = mqttd['subscribe_topic']

                topics = data.get('topics', {})
                if isinstance(topics, dict):
                    # Nimmt alle string-valued Topic-Einträge aus app_config in
                    # cfg['topics'] auf, damit die nachgelagerten
                    # `_app_conf['topics'].get(...)` Aufrufe sie auch finden.
                    # Frühere Versionen haben hier nur movement/move_base_goal/
                    # robot_state/robot_cmd übertragen, sodass nav_status,
                    # system_stats und motor_feedback_prefix auf die
                    # initialen Hard-coded-Defaults zurückgefallen sind
                    # (z. B. "system/stats" statt
                    # "cmeresearch/cmexaiii-001/system/stats") — Webapp
                    # subscribete dadurch leere Topics und zeigte permanent
                    # "Waiting for data…".
                    for _k, _v in topics.items():
                        if isinstance(_v, str) and _v:
                            cfg['topics'][_k] = _v

                # Velocities configuration (optional)
                vels = data.get('velocities', {})
                if isinstance(vels, dict):
                    for key in list(cfg['velocities'].keys()):
                        if key in vels:
                            try:
                                cfg['velocities'][key] = float(vels[key])
                            except (ValueError, TypeError):
                                pass

                mp = data.get('map', {})
                if isinstance(mp, dict):
                    for key in ['width', 'height', 'resolution', 'origin_x', 'origin_y']:
                        if key in mp:
                            try:
                                cfg['map'][key] = float(mp[key]) if key in ['resolution','origin_x','origin_y'] else int(mp[key])
                            except (ValueError, TypeError):
                                pass
                    if 'obstacles' in mp and isinstance(mp['obstacles'], list):
                        cfg['map']['obstacles'] = mp['obstacles']

                # Velocity caps (optional)
                lims = data.get('limits', {})
                if isinstance(lims, dict):
                    for key in list(cfg['limits'].keys()):
                        if key in lims:
                            try:
                                cfg['limits'][key] = float(lims[key])
                            except (ValueError, TypeError):
                                pass

                # Drive type / docker-logs container (optional strings)
                if isinstance(data.get('drive_type'), str) and data['drive_type']:
                    cfg['drive_type'] = data['drive_type']
                if isinstance(data.get('docker_log_container'), str) and data['docker_log_container']:
                    cfg['docker_log_container'] = data['docker_log_container']

                # Motor-feedback wheel set (optional list of strings)
                wheels = data.get('motor_feedback_wheels')
                if isinstance(wheels, list) and wheels and all(isinstance(w, str) and w for w in wheels):
                    cfg['motor_feedback_wheels'] = wheels
    except FileNotFoundError:
        print(f"App config file not found at {path}. Using defaults.")
    except json.JSONDecodeError as e:
        print(f"Invalid JSON in app config file {path}: {e}. Using defaults.")
    except Exception as e:
        print(f"Error reading app config file {path}: {e}. Using defaults.")

    # Phase 1: overlay robot.yaml on top of the JSON base (it wins where set).
    if _yaml_data is not None:
        _apply_robot_yaml_data(cfg, _yaml_data)

    return cfg

_app_conf = _load_app_config()

# Apply MQTT config
broker_url = _app_conf['mqtt']['broker_url']
broker_port = _app_conf['mqtt']['broker_port']
SUBSCRIBE_TOPIC = _app_conf['mqtt'].get('subscribe_topic', SUBSCRIBE_TOPIC)

# Apply topics config
MOVEMENT_TOPIC = _app_conf['topics']['movement']
MOVE_BASE_GOAL_TOPIC = _app_conf['topics']['move_base_goal']
ROBOT_STATE_TOPIC = _app_conf['topics']['robot_state']
ROBOT_CMD_TOPIC = _app_conf['topics']['robot_cmd']
NAV_STATUS_TOPIC = _app_conf['topics'].get('nav_status', NAV_STATUS_TOPIC)
SYSTEM_STATS_TOPIC = _app_conf['topics'].get('system_stats', SYSTEM_STATS_TOPIC)
POSE_TOPIC = _app_conf['topics'].get('robot_pose', POSE_TOPIC)
_prefix = _app_conf['topics'].get('motor_feedback_prefix', 'base')
# Wheel set is config-driven: mecanum exposes 4, a 2-motor diff base exposes its
# driven wheels only. The dashboard renders whatever wheels the backend exposes.
MOTOR_FEEDBACK_WHEELS = _app_conf.get(
    'motor_feedback_wheels', ["front_left", "front_right", "rear_left", "rear_right"])
MOTOR_FEEDBACK_TOPICS = {
    w: f"{_prefix}/{w}/feedback" for w in MOTOR_FEEDBACK_WHEELS
}
# Re-scope the live feedback store to the configured wheels.
current_motor_feedback = {w: {} for w in MOTOR_FEEDBACK_WHEELS}
# Re-register callbacks with resolved topic names
mqtt_client.message_callback_add(ROBOT_STATE_TOPIC, on_robot_state_message)
mqtt_client.message_callback_add(NAV_STATUS_TOPIC, on_nav_status_message)
mqtt_client.message_callback_add(SYSTEM_STATS_TOPIC, on_system_stats_message)
mqtt_client.message_callback_add(POSE_TOPIC, on_pose_message)
for _wheel, _topic in MOTOR_FEEDBACK_TOPICS.items():
    mqtt_client.message_callback_add(_topic, _make_motor_feedback_callback(_wheel))

# Expose velocity defaults + robot-shape config for views/templates.
VELOCITY_DEFAULTS = _app_conf.get('velocities', {})
LIMITS = _app_conf.get('limits', {})
DRIVE_TYPE = _app_conf.get('drive_type', 'mecanum')
DOCKER_LOG_CONTAINER = _app_conf.get('docker_log_container', 'cmexaiii-hardware')

# Apply map config (override defaults defined above)
map_conf = _app_conf['map']
map_data['width'] = map_conf.get('width', map_data['width'])
map_data['height'] = map_conf.get('height', map_data['height'])
map_data['resolution'] = map_conf.get('resolution', map_data['resolution'])
map_data['origin_x'] = map_conf.get('origin_x', map_data['origin_x'])
map_data['origin_y'] = map_conf.get('origin_y', map_data['origin_y'])
# Obstacles: use provided list if any; otherwise leave default generation in place
if map_conf.get('obstacles'):
    map_data['obstacles'] = map_conf['obstacles']

# Identifier of the map poses are saved against, so a pose recorded on one map
# is not silently reused on another. Configured per deployment via
# app_config.json ("map": {"map_id": "..."}); defaults to "default".
MAP_ID = map_conf.get('map_id', 'default')


def get_map_id():
    """Return the configured id of the map poses are saved against."""
    return MAP_ID


def reload_runtime_config():
    """Re-read robot.yaml and refresh the RUNTIME globals in place (limits,
    velocities, drive type, docker-log container, map) so a config save takes
    effect without restarting the webapp. Boot-time bits (MQTT topics /
    subscriptions, broker connection) are deliberately NOT touched — changing
    the instance still needs a restart."""
    global VELOCITY_DEFAULTS, LIMITS, DRIVE_TYPE, DOCKER_LOG_CONTAINER, MAP_ID
    conf = _load_app_config()
    VELOCITY_DEFAULTS = conf.get('velocities', {})
    LIMITS = conf.get('limits', {})
    DRIVE_TYPE = conf.get('drive_type', 'mecanum')
    DOCKER_LOG_CONTAINER = conf.get('docker_log_container', 'cmexaiii-hardware')
    mc = conf.get('map', {})
    for _k in ('width', 'height', 'resolution', 'origin_x', 'origin_y'):
        if _k in mc:
            map_data[_k] = mc[_k]
    if mc.get('obstacles'):
        map_data['obstacles'] = mc['obstacles']
    MAP_ID = mc.get('map_id', MAP_ID)
    return {'limits': LIMITS, 'drive_type': DRIVE_TYPE, 'velocities': VELOCITY_DEFAULTS}

# Last Will & Testament: if this MQTT client dies ungracefully (Django crash,
# container OOM, broker link drop), the broker publishes a zero TwistStamped
# on cmd_vel on our behalf. twist_mux's 0.5s timeout then brakes the robot.
# Defense-in-depth alongside the robot-side watchdog and the browser-side
# visibilitychange/pagehide handlers.
_LWT_TWIST = {
    "header": {"frame_id": "base_link", "stamp": {"sec": 0, "nanosec": 0}},
    "twist": {
        "linear":  {"x": 0.0, "y": 0.0, "z": 0.0},
        "angular": {"x": 0.0, "y": 0.0, "z": 0.0},
    },
}
mqtt_client.will_set(MOVEMENT_TOPIC, json.dumps(_LWT_TWIST), qos=1, retain=False)

def _connect_with_retry():
    """Try to connect to the MQTT broker in the background, retrying on failure."""
    retry_delay = 5
    max_retry_delay = int(os.getenv('MQTT_MAX_RETRY_DELAY', '60'))
    while True:
        try:
            print(f"Connecting to MQTT broker {broker_url}:{broker_port} ...")
            mqtt_client.connect(broker_url, broker_port, 60)
            mqtt_client.loop_start()
            print("MQTT connection initiated.")
            return
        except (ConnectionRefusedError, OSError) as e:
            print(f"MQTT broker not available ({e}). Retrying in {retry_delay}s ...")
            time.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, max_retry_delay)


# Avoid auto-connecting only when explicitly disabled via env
_disable_flag = os.getenv('DISABLE_MQTT')
if not (_disable_flag and _disable_flag.lower() in ('1', 'true', 'yes')):
    _mqtt_thread = threading.Thread(target=_connect_with_retry, daemon=True)
    _mqtt_thread.start()
else:
    print("MQTT auto-connect disabled (DISABLE_MQTT set).")
