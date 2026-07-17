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

    def test_navigation_suggests_pose_name(self):
        # Empty DB -> the form suggests "Pose 1" as placeholder.
        resp = self.client.get(reverse('navigation'))
        self.assertContains(resp, 'placeholder="Pose 1"')

    def test_save_pose_autoname_and_mapid(self):
        from .models import RobotPose
        from django_project.mqtt_client import get_map_id
        # Empty name -> auto "Pose 1", with map_id captured from config.
        self.client.post(reverse('handle_button'),
                         {'button_type': 'save_pose', 'pose_name': ''})
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
