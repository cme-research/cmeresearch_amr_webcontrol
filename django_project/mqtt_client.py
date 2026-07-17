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
    # Velocity is the *measured* twist from nav_msgs/Odometry, NOT cmd_vel.
    global current_pose, _last_odom_broadcast
    try:
        data = json.loads(msg.payload.decode())

        # nav_msgs/Odometry: twist.twist is the body-frame velocity.
        linear_x = data.get("twist", {}).get("twist", {}).get("linear", {}).get("x", 0.0)
        linear_y = data.get("twist", {}).get("twist", {}).get("linear", {}).get("y", 0.0)
        angular_z = data.get("twist", {}).get("twist", {}).get("angular", {}).get("z", 0.0)

        position_x = data.get("pose", {}).get("pose", {}).get("position", {}).get("x", 0.0)
        position_y = data.get("pose", {}).get("pose", {}).get("position", {}).get("y", 0.0)
        orientation_z = data.get("pose", {}).get("pose", {}).get("orientation", {}).get("z", 0.0)
        # ROS 2 builtin_interfaces/Time uses sec/nanosec (ROS 1 used secs/nsecs).
        stamp = data.get("header", {}).get("stamp", {})
        header_time = stamp.get("sec", 0) + stamp.get("nanosec", 0) * 1e-9

        # Always keep the latest pose (used by "save current pose"), even on
        # throttled ticks — this is cheap and must not miss updates.
        current_pose = {
            "position": {
                "x": position_x,
                "y": position_y
            },
            "orientation": {
                "z": orientation_z
            }
        }

        # Throttle the SSE broadcast to ~10 Hz to avoid flooding the queue.
        now = time.time()
        if now - _last_odom_broadcast < _ODOM_BROADCAST_MIN_INTERVAL:
            return
        _last_odom_broadcast = now

        filtered_data = {
            "header": {
                "time": header_time,
            },
            "linear": {
                "x": linear_x,
                "y": linear_y,
            },
            "angular": {
                "z": angular_z,
            },
            "position": {
                "x": position_x,
                "y": position_y,
            },
            "orientation": {
                "z": orientation_z
            }
        }
        broadcast_message(filtered_data)
    except json.JSONDecodeError:
        print("Invalid JSON message received")


# Set up the MQTT client
mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
mqtt_client.on_connect = on_connect
mqtt_client.on_disconnect = on_disconnect
mqtt_client.on_message = on_message
mqtt_client.message_callback_add(ROBOT_STATE_TOPIC, on_robot_state_message)
mqtt_client.message_callback_add(NAV_STATUS_TOPIC, on_nav_status_message)
mqtt_client.message_callback_add(SYSTEM_STATS_TOPIC, on_system_stats_message)
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

def _load_app_config():
    base_dir = Path(__file__).resolve().parent.parent
    default_app = base_dir / 'app_config.json'

    path = os.getenv('APP_CONFIG_FILE') or str(default_app)

    # Defaults
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
    except FileNotFoundError:
        print(f"App config file not found at {path}. Using defaults.")
    except json.JSONDecodeError as e:
        print(f"Invalid JSON in app config file {path}: {e}. Using defaults.")
    except Exception as e:
        print(f"Error reading app config file {path}: {e}. Using defaults.")

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
_prefix = _app_conf['topics'].get('motor_feedback_prefix', 'base')
MOTOR_FEEDBACK_TOPICS = {
    w: f"{_prefix}/{w}/feedback" for w in ("front_left", "front_right", "rear_left", "rear_right")
}
# Re-register callbacks with resolved topic names
mqtt_client.message_callback_add(ROBOT_STATE_TOPIC, on_robot_state_message)
mqtt_client.message_callback_add(NAV_STATUS_TOPIC, on_nav_status_message)
mqtt_client.message_callback_add(SYSTEM_STATS_TOPIC, on_system_stats_message)
for _wheel, _topic in MOTOR_FEEDBACK_TOPICS.items():
    mqtt_client.message_callback_add(_topic, _make_motor_feedback_callback(_wheel))

# Expose velocity defaults
VELOCITY_DEFAULTS = _app_conf.get('velocities', {})

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
