from django.test import TestCase, Client
from django.urls import reverse
from unittest import mock


class ViewTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_root_page_renders(self):
        resp = self.client.get(reverse('teleop'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'AMR Control')
        self.assertContains(resp, 'joy-arm-btn')

    def test_mission_page_renders(self):
        resp = self.client.get(reverse('mission'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'mission-form')

    def test_navigation_page_renders(self):
        resp = self.client.get(reverse('navigation'))
        self.assertEqual(resp.status_code, 200)
        # Live SLAM map: canvas + rosbridge client, plus pose management form.
        self.assertContains(resp, 'map-canvas')
        self.assertContains(resp, 'rosbridge-status')
        self.assertContains(resp, 'slam_map.js')
        self.assertContains(resp, 'pose_name')

    def test_navigation_shows_nav_feedback(self):
        # Live NavigateToPose feedback tiles (distance / ETA / recoveries).
        resp = self.client.get(reverse('navigation'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'nav-distance-remaining')
        self.assertContains(resp, 'nav-eta')
        self.assertContains(resp, 'nav-recoveries')

    def test_pose_message_updates_current_pose(self):
        # base/robot_pose (map-frame PoseStamped) drives the Position tile and
        # the pose used for saving; quaternion is converted to a yaw angle.
        import json
        import math
        from django_project import mqtt_client as mc

        class _Msg:
            def __init__(self, payload):
                self.payload = payload.encode()

        # yaw = +90 deg -> quaternion z = w = sin/cos(45 deg)
        mc.on_pose_message(None, None, _Msg(json.dumps({
            "pose": {
                "position": {"x": 2.0, "y": -1.0},
                "orientation": {"x": 0.0, "y": 0.0, "z": 0.70710678, "w": 0.70710678},
            }
        })))
        cp = mc.get_current_pose()
        self.assertAlmostEqual(cp['position']['x'], 2.0)
        self.assertAlmostEqual(cp['position']['y'], -1.0)
        self.assertAlmostEqual(cp['orientation']['z'], math.pi / 2, places=4)

    def test_navigation_suggests_pose_name(self):
        # Empty DB -> the form suggests "Pose 1" as placeholder.
        resp = self.client.get(reverse('navigation'))
        self.assertContains(resp, 'placeholder="Pose 1"')

    def test_save_pose_autoname_and_mapid(self):
        from .models import RobotPose
        from django_project.mqtt_client import get_map_id
        # Empty name -> auto "Pose 1", with map_id captured from config.
        resp = self.client.post(reverse('handle_button'),
                                {'button_type': 'save_pose', 'pose_name': ''})
        # After saving, stay on the navigation page (not teleop/button_page).
        self.assertRedirects(resp, reverse('navigation'))
        self.assertEqual(RobotPose.objects.count(), 1)
        pose = RobotPose.objects.first()
        self.assertEqual(pose.name, 'Pose 1')
        self.assertEqual(pose.map_id, get_map_id())
        self.assertIsNotNone(pose.created_at)
        # Next empty save -> "Pose 2" (skips used names).
        self.client.post(reverse('handle_button'),
                         {'button_type': 'save_pose', 'pose_name': '   '})
        self.assertTrue(RobotPose.objects.filter(name='Pose 2').exists())
        # Explicit name is honoured.
        self.client.post(reverse('handle_button'),
                         {'button_type': 'save_pose', 'pose_name': 'Dock'})
        self.assertTrue(RobotPose.objects.filter(name='Dock').exists())

    def test_logs_page_renders(self):
        resp = self.client.get(reverse('logs'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'docker-logs')

    def test_joystick_cmd_clamps(self):
        with mock.patch('amr_control.views.send_movement_command', return_value=True) as send_cmd:
            resp = self.client.post(
                reverse('joystick_cmd'),
                data='{"linear_x":5.0,"linear_y":-9.9,"angular_z":99}',
                content_type='application/json',
            )
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data['status'], 'success')
            self.assertEqual(data['sent']['linear_x'], 0.31)
            self.assertEqual(data['sent']['linear_y'], -0.3)
            self.assertEqual(data['sent']['angular_z'], 0.8)
            send_cmd.assert_called_once_with(linear_x=0.31, linear_y=-0.3, angular_z=0.8)

    def test_get_map_view_returns_json(self):
        resp = self.client.get(reverse('get_map'))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('width', data)
        self.assertIn('height', data)
        self.assertIn('obstacles', data)

    def test_mqtt_stream_view_sse(self):
        resp = self.client.get(reverse('mqtt_stream'))
        # StreamingHttpResponse does not evaluate content immediately
        self.assertEqual(resp.status_code, 200)
        ct = resp.get('Content-Type', '')
        self.assertIn('text/event-stream', ct)

    def test_shutdown_requires_post(self):
        # GET should be method not allowed
        resp = self.client.get(reverse('shutdown_pi'))
        self.assertEqual(resp.status_code, 405)

    def test_shutdown_post_ajax_success(self):
        # Simulate connected MQTT and successful publish
        class PubResult:
            rc = 0
        with mock.patch('amr_control.views.get_connection_status', return_value=True), \
             mock.patch('amr_control.views.mqtt_client.publish', return_value=PubResult()):
            resp = self.client.post(reverse('shutdown_pi'), HTTP_X_REQUESTED_WITH='XMLHttpRequest')
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data['status'], 'success')
            self.assertIn('Shutdown request sent via MQTT', data['message'])

    def test_reset_estop_ajax(self):
        with mock.patch('amr_control.views.send_robot_command', return_value=True) as send_cmd:
            resp = self.client.post(
                reverse('handle_button'),
                data={'button_type': 'button3'},
                HTTP_X_REQUESTED_WITH='XMLHttpRequest'
            )
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data['status'], 'success')
            self.assertIn('Reset sent', data['message'])
            send_cmd.assert_called_once_with('reset')

    def test_handle_button_movement_ajax(self):
        # Patch mqtt client to simulate connected & successful publish
        with mock.patch('amr_control.views.send_movement_command', return_value=True) as send_cmd:
            resp = self.client.post(
                reverse('handle_button'),
                data={'button_type': 'move_forward'},
                HTTP_X_REQUESTED_WITH='XMLHttpRequest'
            )
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data['status'], 'success')
            self.assertIn('Moving forward', data['message'])
            send_cmd.assert_called_once()


class ConfigPageTests(TestCase):
    """Phase 2 config page: login gate, render, and save-to-robot.yaml."""

    def setUp(self):
        import tempfile
        from django.contrib.auth import get_user_model
        from django_project import robot_config as rc
        self.rc = rc
        self.client = Client()
        self.user = get_user_model().objects.create_user(username='op', password='pw12345')
        self.tmp = tempfile.NamedTemporaryFile('w', suffix='.yaml', delete=False)
        self.tmp.write(
            "identity: {robot: cmexaiii, instance: cmexaiii-001, name: X}\n"
            "ros: {domain_id: 12, nav_launch: cmexaiii_nav_mapping.launch.py}\n"
            "control: {drive_type: mecanum, limits: {max_linear_x: 0.31}, velocities: {forward: 0.2}}\n"
            "map: {map_id: cmexaiii_house, width: 20}\n")
        self.tmp.close()
        self._old_path = rc.ROBOT_CONFIG_PATH
        rc.ROBOT_CONFIG_PATH = self.tmp.name

    def tearDown(self):
        import os
        self.rc.ROBOT_CONFIG_PATH = self._old_path
        os.unlink(self.tmp.name)

    def test_config_requires_login(self):
        resp = self.client.get(reverse('config'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/accounts/login/', resp.url)

    def test_config_renders_for_operator(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('config'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Robot configuration')
        self.assertContains(resp, 'cmexaiii-001')

    def test_config_save_updates_yaml(self):
        import yaml
        self.client.force_login(self.user)
        resp = self.client.post(reverse('config'), {
            'identity__robot': 'cmexamini', 'identity__instance': 'cmexamini-001',
            'identity__name': 'Mini', 'ros__domain_id': '13', 'nav_mode': 'localization',
            'control__drive_type': 'diff', 'control__limits__max_linear_x': '0.3',
            'control__velocities__forward': '0.25', 'map__map_id': 'cmexamini_house',
            'map__width': '20',
        })
        self.assertEqual(resp.status_code, 302)
        data = yaml.safe_load(open(self.tmp.name))
        self.assertEqual(data['identity']['robot'], 'cmexamini')
        self.assertEqual(data['ros']['domain_id'], 13)
        self.assertEqual(data['ros']['nav_launch'], 'cmexamini_nav_localization.launch.py')
        self.assertEqual(data['control']['drive_type'], 'diff')


class ConfigApplyTests(TestCase):
    """Phase 3: apply endpoint auth/guard + runtime live-reload on save."""

    def setUp(self):
        import tempfile, os
        from django.contrib.auth import get_user_model
        from django_project import robot_config as rc
        self.os, self.rc = os, rc
        self.client = Client()
        self.user = get_user_model().objects.create_user(username='op2', password='pw12345')
        self.tmp = tempfile.NamedTemporaryFile('w', suffix='.yaml', delete=False)
        self.tmp.write("identity: {robot: cmexaiii, instance: cmexaiii-001, name: X}\n"
                       "control: {limits: {max_linear_x: 0.31}}\n")
        self.tmp.close()
        self._old_path = rc.ROBOT_CONFIG_PATH
        rc.ROBOT_CONFIG_PATH = self.tmp.name
        self._old_env = os.environ.get('ROBOT_CONFIG_FILE')
        os.environ['ROBOT_CONFIG_FILE'] = self.tmp.name

    def tearDown(self):
        self.rc.ROBOT_CONFIG_PATH = self._old_path
        if self._old_env is None:
            self.os.environ.pop('ROBOT_CONFIG_FILE', None)
        else:
            self.os.environ['ROBOT_CONFIG_FILE'] = self._old_env
        self.os.unlink(self.tmp.name)
        # reload_runtime_config mutates module globals; reset them from the
        # restored environment so state doesn't leak into other tests.
        from django_project import mqtt_client as m
        m.reload_runtime_config()

    def test_apply_requires_login(self):
        resp = self.client.post(reverse('config_apply'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/accounts/login/', resp.url)

    def test_apply_no_ops_without_deploy_dir(self):
        # DEPLOY_DIR unset in tests -> graceful redirect, no docker calls, no crash.
        self.client.force_login(self.user)
        resp = self.client.post(reverse('config_apply'))
        self.assertEqual(resp.status_code, 302)

    def test_runtime_save_applies_live(self):
        from django_project import mqtt_client as m
        self.client.force_login(self.user)
        self.client.post(reverse('config'), {'control__limits__max_linear_x': '0.22'})
        self.assertAlmostEqual(m.LIMITS.get('max_linear_x'), 0.22)
