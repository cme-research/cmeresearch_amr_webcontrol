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
            "topics": {"movement": "t/move", "move_base_goal": "t/goal"},
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
        self.fake_client.subscribe.assert_called_with('test_topic')

    def test_on_message_updates_pose_and_queue(self):
        # Build a fake message payload
        payload = {
            "twist": {"twist": {"linear": {"x": 0.3, "y": -0.2}, "angular": {"z": 0.8}}},
            "pose": {"pose": {"position": {"x": 1.2, "y": 2.5}, "orientation": {"z": 0.5}}},
            "header": {"stamp": {"secs": 123456}}
        }
        msg = mock.Mock()
        msg.payload = json.dumps(payload).encode('utf-8')
        # Call handler
        self.mqtt_module.on_message(self.fake_client, None, msg)
        # Check current_pose was updated
        pose = self.mqtt_module.get_current_pose()
        self.assertAlmostEqual(pose['position']['x'], 1.2)
        self.assertAlmostEqual(pose['position']['y'], 2.5)
        self.assertAlmostEqual(pose['orientation']['z'], 0.5)
        # Check something was put into the queue
        q = self.mqtt_module.message_queue
        self.assertFalse(q.empty())
        item = q.get_nowait()
        self.assertIn('linear', item)
        self.assertIn('angular', item)

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
