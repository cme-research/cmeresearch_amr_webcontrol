"""Read/write access to robot.yaml (the single source of truth) for the config
page. Phase 2: the webapp can edit robot.yaml; boot-time changes still require a
container restart (Phase 3 will trigger that from the UI)."""
import os

# Same path the runtime config loader uses (mqtt_client). Compose mounts the
# host robot.yaml here; ROBOT_CONFIG_FILE overrides it (used for local dev).
ROBOT_CONFIG_PATH = os.getenv('ROBOT_CONFIG_FILE', '/robot/config/robot.yaml')

# Which top-level.dotted fields are start-time (need a container restart to take
# effect) vs runtime (re-read on the next webapp reload). Drives the UI split.
BOOT_TIME_FIELDS = ('identity.robot', 'identity.instance', 'ros.domain_id', 'ros.nav_launch')


def _skeleton():
    """Sensible starting config if robot.yaml is missing (mirrors robot.example.yaml)."""
    return {
        'schema_version': 1,
        'identity': {'robot': 'cmexaiii', 'instance': 'cmexaiii-001', 'name': 'CMEXA III'},
        'ros': {'domain_id': 12, 'nav_launch': 'cmexaiii_nav_mapping.launch.py', 'robot_env': 'house'},
        'images': {'robot_version': 'latest', 'webapp_version': 'latest'},
        'host': {'input_gid': ''},
        'mqtt': {'broker_url': 'localhost', 'broker_port': 1883, 'remote_broker': '10.8.0.1:1883'},
        'control': {
            'drive_type': 'mecanum',
            'limits': {'max_linear_x': 0.31, 'max_linear_y': 0.3, 'max_angular_z': 0.8},
            'velocities': {'forward': 0.2, 'backward': -0.2, 'left': 0.2, 'right': -0.2,
                           'rotate_cw': -0.5, 'rotate_ccw': 0.5},
            'motor_feedback_wheels': ['front_left', 'front_right', 'rear_left', 'rear_right'],
            'docker_log_container': 'cmexaiii-hardware',
        },
        'map': {'map_id': 'cmexaiii_house', 'width': 20, 'height': 20,
                'resolution': 0.05, 'origin_x': -10.0, 'origin_y': -10.0},
    }


def load_config():
    """Return the raw robot.yaml as a dict (skeleton if absent/unreadable)."""
    import yaml
    if os.path.exists(ROBOT_CONFIG_PATH):
        try:
            with open(ROBOT_CONFIG_PATH) as f:
                data = yaml.safe_load(f) or {}
            if isinstance(data, dict):
                return data
        except Exception as e:
            print(f"robot_config: could not read {ROBOT_CONFIG_PATH}: {e}")
    return _skeleton()


def save_config(data):
    """Persist the config back to robot.yaml.

    Writes in place (truncate + rewrite the same inode) rather than temp+rename:
    robot.yaml is bind-mounted as a single file in the container, and a rename
    would swap the inode out from under the mount.
    """
    import yaml
    text = yaml.safe_dump(data, sort_keys=False, default_flow_style=False)
    with open(ROBOT_CONFIG_PATH, 'w') as f:
        f.write(text)


def get(data, dotted, default=None):
    node = data
    for k in dotted.split('.'):
        if not isinstance(node, dict) or k not in node:
            return default
        node = node[k]
    return node


def set_(data, dotted, value):
    keys = dotted.split('.')
    node = data
    for k in keys[:-1]:
        node = node.setdefault(k, {})
    node[keys[-1]] = value
