import paho.mqtt.client as mqtt
from queue import Queue
import json
import math
import random
import os
import threading
import time
from pathlib import Path

# An in-memory message queue to store MQTT messages
message_queue = Queue()

# Global variable to track connection status
is_connected = False

# Topics for sending commands (defaults, can be overridden by app_config.json)
MOVEMENT_TOPIC = "amr_control/cmd_vel"
MOVE_BASE_GOAL_TOPIC = "amr_control/move_base_goal"
SUBSCRIBE_TOPIC = "fake_odom"
ROBOT_STATE_TOPIC = "robot_state"
ROBOT_CMD_TOPIC = "robot_cmd"

# Global variable to store the latest robot pose
current_pose = {
    "position": {"x": 0.0, "y": 0.0},
    "orientation": {"z": 0.0}
}

# Global variable to store the latest robot state from the state machine
current_robot_state = {
    "state": "unknown",
    "timestamp": None,
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
        "linear": {
            "x": linear_x,
            "y": linear_y,
            "z": 0.0
        },
        "angular": {
            "x": 0.0,
            "y": 0.0,
            "z": angular_z
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
        current_robot_state = {
            "state": state,
            "timestamp": stamp,
        }
        message_queue.put({
            "type": "robot_state",
            "robot_state": state,
            "robot_state_stamp": stamp,
        })
        print(f"Robot state: {state}")
    except json.JSONDecodeError:
        print("Invalid JSON in robot state message")


def get_map_data():
    """
    Get the current 2D SLAM map data.

    Returns:
        dict: A dictionary containing the map data
    """
    return map_data


def on_message(client, userdata, msg):
    #print(f"Received message: {msg.payload.decode()}")
    try:
        data = json.loads(msg.payload.decode())

        linear_x = data.get("twist", {}).get("twist", {}).get("linear", {}).get("x", 0.0)
        linear_y = data.get("twist", {}).get("twist", {}).get("linear", {}).get("y", 0.0)
        angular_z = data.get("twist", {}).get("twist", {}).get("angular", {}).get("z", 0.0)

        position_x = data.get("pose", {}).get("pose", {}).get("position", {}).get("x", 0.0)
        position_y = data.get("pose", {}).get("pose", {}).get("position", {}).get("y", 0.0)
        orientation_z = data.get("pose", {}).get("pose", {}).get("orientation", {}).get("z", 0.0)
        header_time = data.get("header", {}).get("stamp", {}).get("secs", 0.0)

        # Update the current pose global variable
        global current_pose
        current_pose = {
            "position": {
                "x": position_x,
                "y": position_y
            },
            "orientation": {
                "z": orientation_z
            }
        }

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
        #filtered_message = f"header.time: {header_time}, linear.x: {linear_x}, linear.y: {linear_y}, angular.z: {angular_z}, position.x: {position_x}, position.y: {position_y}, orientation.z: {orientation_z}"
        print(filtered_data)
        message_queue.put(filtered_data)
    except json.JSONDecodeError:
        print("Invalid JSON message received")


# Set up the MQTT client
mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
mqtt_client.on_connect = on_connect
mqtt_client.on_disconnect = on_disconnect
mqtt_client.on_message = on_message
mqtt_client.message_callback_add(ROBOT_STATE_TOPIC, on_robot_state_message)

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
                    if isinstance(topics.get('movement'), str) and topics.get('movement'):
                        cfg['topics']['movement'] = topics['movement']
                    if isinstance(topics.get('move_base_goal'), str) and topics.get('move_base_goal'):
                        cfg['topics']['move_base_goal'] = topics['move_base_goal']
                    if isinstance(topics.get('robot_state'), str) and topics.get('robot_state'):
                        cfg['topics']['robot_state'] = topics['robot_state']
                    if isinstance(topics.get('robot_cmd'), str) and topics.get('robot_cmd'):
                        cfg['topics']['robot_cmd'] = topics['robot_cmd']

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
