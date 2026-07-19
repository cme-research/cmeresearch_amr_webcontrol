import os
import json
import importlib
from pathlib import Path
from unittest import TestCase, mock

from django.test import SimpleTestCase


class MQTTClientModuleTests(SimpleTestCase):
    """Tests for django_project.mqtt_client module behavior without real MQTT."""

    def setUp(self):
        # Patch paho.mqtt.client.Client before importing the module to avoid real connections
        self.patcher_client = mock.patch('django_project.mqtt_client.mqtt.Client', autospec=True)
        # However, the module may not be imported yet during first patch attempt; instead patch the library
        self.patcher_lib_client = mock.patch('paho.mqtt.client.Client', autospec=True)
        self.mock_lib_client_cls = self.patcher_lib_client.start()
        # Prepare a fake client instance with desired behavior
        self.fake_client = mock.Mock()
        self.fake_client.publish.return_value = mock.Mock(rc=0)
        self.mock_lib_client_cls.return_value = self.fake_client

        # Create a temporary app_config file and point env var to it
        self.temp_dir = Path(__file__).resolve().parent
        self.temp_cfg = self.temp_dir / 'temp_app_config.json'
        cfg = {
            "mqtt": {"broker_url": "test-broker", "broker_port": 1884, "subscribe_topic": "test_topic"},
            "topics": {"movement": "t/move", "move_base_goal": "t/goal", "robot_state": "t/robot_state", "robot_cmd": "t/robot_cmd"},
            "map": {"width": 10, "height": 12, "resolution": 0.1, "origin_x": -5.0, "origin_y": -6.0, "obstacles": []}
        }
        with open(self.temp_cfg, 'w') as f:
            json.dump(cfg, f)
        self._old_env_app = os.environ.get('APP_CONFIG_FILE')
        os.environ['APP_CONFIG_FILE'] = str(self.temp_cfg)

        # Import or reload module under test
        self.mqtt_module = importlib.import_module('django_project.mqtt_client')
        self.mqtt_module = importlib.reload(self.mqtt_module)

    def tearDown(self):
        # Cleanup temp file and env
        try:
            if self.temp_cfg.exists():
                self.temp_cfg.unlink()
        except Exception:
            pass
        if self._old_env_app is None:
            os.environ.pop('APP_CONFIG_FILE', None)
        else:
            os.environ['APP_CONFIG_FILE'] = self._old_env_app
        # Stop patchers
        self.patcher_lib_client.stop()

    def test_config_loaded_and_client_connected(self):
        # Ensure broker config applied and connect called with configured port
        self.assertEqual(self.mqtt_module.broker_url, 'test-broker')
        self.assertEqual(self.mqtt_module.broker_port, 1884)
        # connect called once with configured host/port and keepalive 60
        self.fake_client.connect.assert_called_with('test-broker', 1884, 60)
        self.fake_client.loop_start.assert_called_once()
        # Subscribe topic should be updated from config on connect
        # Simulate on_connect and ensure subscribe used provided topic
        self.mqtt_module.on_connect(self.fake_client, None, None, 0)
        subscribe_calls = [c.args[0] for c in self.fake_client.subscribe.call_args_list]
        self.assertIn('test_topic', subscribe_calls)
        self.assertIn('t/robot_state', subscribe_calls)

    def test_on_message_broadcasts_velocity_only(self):
        # on_message (odometry) now provides velocity only; the pose comes from
        # on_pose_message (map-frame). It must NOT broadcast position.
        payload = {
            "twist": {"twist": {"linear": {"x": 0.3, "y": -0.2}, "angular": {"z": 0.8}}},
            "pose": {"pose": {"position": {"x": 1.2, "y": 2.5}, "orientation": {"z": 0.5}}},
        }
        msg = mock.Mock()
        msg.payload = json.dumps(payload).encode('utf-8')
        self.mqtt_module._last_odom_broadcast = 0.0  # bypass the ~10 Hz throttle
        q = self.mqtt_module.register_subscriber()
        try:
            self.mqtt_module.on_message(self.fake_client, None, msg)
            self.assertFalse(q.empty())
            item = q.get_nowait()
            self.assertIn('linear', item)
            self.assertIn('angular', item)
            self.assertNotIn('position', item)
            self.assertAlmostEqual(item['linear']['x'], 0.3)
            self.assertAlmostEqual(item['angular']['z'], 0.8)
        finally:
            self.mqtt_module.unregister_subscriber(q)

    def test_on_pose_message_updates_pose_and_queue(self):
        # base/robot_pose (map-frame PoseStamped) drives current_pose (quaternion
        # -> yaw) and broadcasts position/orientation for the Position tile.
        payload = {
            "pose": {
                "position": {"x": 1.2, "y": 2.5},
                "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
            }
        }
        msg = mock.Mock()
        msg.payload = json.dumps(payload).encode('utf-8')
        q = self.mqtt_module.register_subscriber()
        try:
            self.mqtt_module.on_pose_message(self.fake_client, None, msg)
            pose = self.mqtt_module.get_current_pose()
            self.assertAlmostEqual(pose['position']['x'], 1.2)
            self.assertAlmostEqual(pose['position']['y'], 2.5)
            self.assertAlmostEqual(pose['orientation']['z'], 0.0)  # yaw of identity quat
            self.assertFalse(q.empty())
            item = q.get_nowait()
            self.assertIn('position', item)
            self.assertIn('orientation', item)
        finally:
            self.mqtt_module.unregister_subscriber(q)

    def test_broadcast_fans_out_to_all_subscribers(self):
        # Every registered subscriber receives its own copy of the message,
        # instead of them competing over a single shared queue.
        q1 = self.mqtt_module.register_subscriber()
        q2 = self.mqtt_module.register_subscriber()
        try:
            self.mqtt_module.broadcast_message({"type": "x", "n": 1})
            self.assertEqual(q1.get_nowait()["n"], 1)
            self.assertEqual(q2.get_nowait()["n"], 1)
        finally:
            self.mqtt_module.unregister_subscriber(q1)
            self.mqtt_module.unregister_subscriber(q2)

    def test_unregister_stops_delivery(self):
        q = self.mqtt_module.register_subscriber()
        self.mqtt_module.unregister_subscriber(q)
        self.mqtt_module.broadcast_message({"type": "x"})
        self.assertTrue(q.empty())

    def test_broadcast_drops_oldest_when_full(self):
        # A slow consumer's bounded queue drops its oldest item under
        # backpressure so the newest sample always lands and memory is capped.
        q = self.mqtt_module.register_subscriber()
        try:
            cap = self.mqtt_module._SUBSCRIBER_MAXSIZE
            for i in range(cap + 5):
                self.mqtt_module.broadcast_message({"seq": i})
            self.assertEqual(q.qsize(), cap)
            seqs = []
            while not q.empty():
                seqs.append(q.get_nowait()["seq"])
            self.assertEqual(seqs[-1], cap + 4)   # newest retained
            self.assertNotIn(0, seqs)             # oldest dropped
        finally:
            self.mqtt_module.unregister_subscriber(q)

    def test_send_commands_publish_when_connected(self):
        # Mark client as connected
        self.mqtt_module.is_connected = True
        # Publish should use configured topics
        ok1 = self.mqtt_module.send_movement_command(0.1, 0.0, 0.0)
        ok2 = self.mqtt_module.send_move_base_goal(1.0, 2.0, 0.3)
        self.assertTrue(ok1)
        self.assertTrue(ok2)
        # Ensure publish called with the right topics
        calls = [mock.call('t/move', mock.ANY), mock.call('t/goal', mock.ANY)]
        self.fake_client.publish.assert_has_calls(calls, any_order=True)

    def test_config_precedence_env(self):
        # Confirm that map config was applied too
        md = self.mqtt_module.get_map_data()
        self.assertEqual(md['width'], 10)
        self.assertEqual(md['height'], 12)
        self.assertAlmostEqual(md['origin_x'], -5.0)
        self.assertAlmostEqual(md['origin_y'], -6.0)

    def test_topics_derived_from_instance(self):
        # robot.yaml only carries the instance id; the full topic set is derived.
        t = self.mqtt_module._topics_for_instance('cmexamini-001')
        self.assertEqual(t['subscribe_topic'], 'cmeresearch/cmexamini-001/base/odometry')
        self.assertEqual(t['nav_status'], 'cmeresearch/cmexamini-001/navigation/status')
        self.assertEqual(t['motor_feedback_prefix'], 'cmeresearch/cmexamini-001/base')

    def test_robot_yaml_overlay_wins(self):
        # _apply_robot_yaml_data overlays identity->topics + control onto a cfg.
        cfg = {
            'mqtt': {'broker_url': 'localhost', 'broker_port': 1883, 'subscribe_topic': 'x'},
            'topics': {'movement': 'a', 'move_base_goal': 'b', 'robot_state': 'c', 'robot_cmd': 'd'},
            'limits': {'max_linear_x': 0.31, 'max_linear_y': 0.3, 'max_angular_z': 0.8},
            'drive_type': 'mecanum',
            'docker_log_container': 'cmexaiii-hardware',
            'motor_feedback_wheels': ['front_left', 'front_right', 'rear_left', 'rear_right'],
            'velocities': {'forward': 0.2, 'backward': -0.2, 'left': 0.2, 'right': -0.2,
                           'rotate_cw': -0.5, 'rotate_ccw': 0.5},
            'map': {'width': 20, 'height': 20, 'resolution': 0.05,
                    'origin_x': -10.0, 'origin_y': -10.0, 'obstacles': []},
        }
        data = {
            'identity': {'instance': 'cmexamini-001'},
            'control': {'drive_type': 'diff',
                        'motor_feedback_wheels': ['front_right', 'rear_left'],
                        'limits': {'max_linear_x': 0.3, 'max_linear_y': 0.0, 'max_angular_z': 1.0}},
        }
        self.mqtt_module._apply_robot_yaml_data(cfg, data)
        self.assertEqual(cfg['mqtt']['subscribe_topic'], 'cmeresearch/cmexamini-001/base/odometry')
        self.assertEqual(cfg['topics']['nav_status'], 'cmeresearch/cmexamini-001/navigation/status')
        self.assertEqual(cfg['drive_type'], 'diff')
        self.assertEqual(cfg['motor_feedback_wheels'], ['front_right', 'rear_left'])
        self.assertAlmostEqual(cfg['limits']['max_linear_x'], 0.3)
