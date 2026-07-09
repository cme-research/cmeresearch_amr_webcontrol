from django.shortcuts import render, redirect
from django.urls import reverse
from django.contrib import messages

# Create your views here.
from django.http import HttpResponse, JsonResponse, FileResponse, Http404
from django.views.decorators.csrf import csrf_exempt
import time
from django.http import StreamingHttpResponse
from django.views.decorators.http import require_POST, require_GET
import subprocess
import shutil
import os


def is_ajax(request):
    """Check if the request is an AJAX request."""
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest'

from django_project.mqtt_client import (
    register_subscriber, unregister_subscriber, get_connection_status,
    send_movement_command,
    send_move_base_goal, get_current_pose, get_map_data, mqtt_client,
    VELOCITY_DEFAULTS, send_robot_command, get_current_robot_state,
    get_nav_status, get_system_stats, get_motor_feedback,
)
from .models import RobotPose
import json
import paho.mqtt.client as mqtt


# Server-side velocity caps. Browser-side clamps exist too, but never trust
# the browser — these are the authoritative limits enforced before MQTT publish.
MAX_LINEAR_X = 0.31  # m/s, forward/backward (hardware ceiling: stepper
                     # max_step_vel=8000 microsteps/s -> ~0.314 m/s wheel surface)
MAX_LINEAR_Y = 0.3   # m/s, lateral strafe (mecanum), already under the 0.31 cap
MAX_ANGULAR_Z = 0.8  # rad/s, yaw


def _clamp(value, limit):
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0.0
    if v != v:  # NaN
        return 0.0
    if v > limit:
        return limit
    if v < -limit:
        return -limit
    return v

def teleop_view(request):
    """Phone-first teleop page: status mini-row + joystick."""
    return render(request, 'amr_control/teleop.html', {'active_page': 'teleop'})


def mission_view(request):
    """Mission control: start mission, e-stop, reset."""
    return render(request, 'amr_control/mission.html', {'active_page': 'mission'})


def navigation_view(request):
    """Navigation: map, position, nav status, velocity, saved poses."""
    saved_poses = RobotPose.objects.all().order_by('-created_at')
    return render(request, 'amr_control/navigation.html', {
        'active_page': 'navigation',
        'saved_poses': saved_poses,
    })


def logs_view(request):
    """Docker container logs (SSE)."""
    return render(request, 'amr_control/logs.html', {'active_page': 'logs'})


# Backwards-compatible alias: old code paths / templates that still reference
# button_page resolve here. Renders the new teleop page.
def button_view(request):
    return teleop_view(request)


@csrf_exempt
def handle_button(request):
    """Handle button clicks and call corresponding methods."""
    if request.method == 'POST':
        button_type = request.POST.get('button_type')  # Get the button clicked

        # Original buttons
        if button_type == 'button1':
            return button1_action(request)
        elif button_type == 'button2':
            return button2_action(request)
        elif button_type == 'button3':
            return button3_action(request)

        # Movement control buttons
        elif button_type == 'move_forward':
            return move_forward(request)
        elif button_type == 'move_backward':
            return move_backward(request)
        elif button_type == 'move_left':
            return move_left(request)
        elif button_type == 'move_right':
            return move_right(request)
        elif button_type == 'rotate_clockwise':
            return rotate_clockwise(request)
        elif button_type == 'rotate_counterclockwise':
            return rotate_counterclockwise(request)
        elif button_type == 'stop_robot':
            return stop_robot(request)

        # Pose management buttons
        elif button_type == 'save_pose':
            pose_name = request.POST.get('pose_name', 'Unnamed Pose')
            return save_current_pose(request, pose_name)
        elif button_type == 'navigate_to_pose':
            pose_id = request.POST.get('pose_id')
            if pose_id:
                return navigate_to_pose(request, pose_id)
            else:
                messages.error(request, "No pose selected")
                return redirect('button_page')

    return HttpResponse("Invalid request.", status=400)


def button1_action(request):
    """Send start_mission command to the robot state machine via MQTT."""
    success = send_robot_command("start_mission")
    message = "Mission started" if success else "Failed to send start_mission command"
    status = "success" if success else "error"
    if is_ajax(request):
        return JsonResponse({'status': status, 'message': message})
    if success:
        messages.success(request, message)
    else:
        messages.error(request, message)
    return redirect('button_page')


def button2_action(request):
    """Send emergency_stop command to the robot state machine via MQTT."""
    success = send_robot_command("emergency_stop")
    message = "Emergency stop sent" if success else "Failed to send emergency_stop command"
    status = "success" if success else "error"
    if is_ajax(request):
        return JsonResponse({'status': status, 'message': message})
    if success:
        messages.success(request, message)
    else:
        messages.error(request, message)
    return redirect('button_page')


def button3_action(request):
    """Send reset command to clear emergency stop and return to idle via MQTT."""
    success = send_robot_command("reset")
    message = "Reset sent" if success else "Failed to send reset command"
    status = "success" if success else "error"
    if is_ajax(request):
        return JsonResponse({'status': status, 'message': message})
    if success:
        messages.success(request, message)
    else:
        messages.error(request, message)
    return redirect('button_page')


# Movement control functions
def move_forward(request):
    """Send command to move the robot forward."""
    success = send_movement_command(linear_x=VELOCITY_DEFAULTS.get('forward', 0.2), linear_y=0.0, angular_z=0.0)

    message = "Moving forward" if success else "Failed to send movement command"
    status = "success" if success else "error"

    if success:
        messages.success(request, message)
    else:
        messages.error(request, message)

    # Return JSON response for AJAX requests
    if is_ajax(request):
        return JsonResponse({
            'status': status,
            'message': message
        })

    # Return redirect for non-AJAX requests
    return redirect('button_page')


def move_backward(request):
    """Send command to move the robot backward."""
    success = send_movement_command(linear_x=VELOCITY_DEFAULTS.get('backward', -0.2), linear_y=0.0, angular_z=0.0)

    message = "Moving backward" if success else "Failed to send movement command"
    status = "success" if success else "error"

    if success:
        messages.success(request, message)
    else:
        messages.error(request, message)

    # Return JSON response for AJAX requests
    if is_ajax(request):
        return JsonResponse({
            'status': status,
            'message': message
        })

    # Return redirect for non-AJAX requests
    return redirect('button_page')


def move_left(request):
    """Send command to move the robot left (sideways)."""
    success = send_movement_command(linear_x=0.0, linear_y=VELOCITY_DEFAULTS.get('left', 0.2), angular_z=0.0)

    message = "Moving left" if success else "Failed to send movement command"
    status = "success" if success else "error"

    if success:
        messages.success(request, message)
    else:
        messages.error(request, message)

    # Return JSON response for AJAX requests
    if is_ajax(request):
        return JsonResponse({
            'status': status,
            'message': message
        })

    # Return redirect for non-AJAX requests
    return redirect('button_page')


def move_right(request):
    """Send command to move the robot right (sideways)."""
    success = send_movement_command(linear_x=0.0, linear_y=VELOCITY_DEFAULTS.get('right', -0.2), angular_z=0.0)

    message = "Moving right" if success else "Failed to send movement command"
    status = "success" if success else "error"

    if success:
        messages.success(request, message)
    else:
        messages.error(request, message)

    # Return JSON response for AJAX requests
    if is_ajax(request):
        return JsonResponse({
            'status': status,
            'message': message
        })

    # Return redirect for non-AJAX requests
    return redirect('button_page')


def rotate_clockwise(request):
    """Send command to rotate the robot clockwise."""
    success = send_movement_command(linear_x=0.0, linear_y=0.0, angular_z=-0.5)

    message = "Rotating clockwise" if success else "Failed to send movement command"
    status = "success" if success else "error"

    if success:
        messages.success(request, message)
    else:
        messages.error(request, message)

    # Return JSON response for AJAX requests
    if is_ajax(request):
        return JsonResponse({
            'status': status,
            'message': message
        })

    # Return redirect for non-AJAX requests
    return redirect('button_page')


def rotate_counterclockwise(request):
    """Send command to rotate the robot counter-clockwise."""
    success = send_movement_command(linear_x=0.0, linear_y=0.0, angular_z=0.5)

    message = "Rotating counter-clockwise" if success else "Failed to send movement command"
    status = "success" if success else "error"

    if success:
        messages.success(request, message)
    else:
        messages.error(request, message)

    # Return JSON response for AJAX requests
    if is_ajax(request):
        return JsonResponse({
            'status': status,
            'message': message
        })

    # Return redirect for non-AJAX requests
    return redirect('button_page')


def stop_robot(request):
    """Send command to stop the robot."""
    success = send_movement_command(linear_x=0.0, linear_y=0.0, angular_z=0.0)

    message = "Robot stopped" if success else "Failed to send movement command"
    status = "success" if success else "error"

    if success:
        messages.success(request, message)
    else:
        messages.error(request, message)

    # Return JSON response for AJAX requests
    if is_ajax(request):
        return JsonResponse({
            'status': status,
            'message': message
        })

    # Return redirect for non-AJAX requests
    return redirect('button_page')


@csrf_exempt
@require_POST
def joystick_cmd(request):
    """Continuous teleop endpoint for the touch-joystick UI.

    Accepts JSON {linear_x, linear_y, angular_z}. Each axis is clamped to the
    server-side maximum before the TwistStamped is published. Returns the
    actually-published values so the browser can show clamp feedback.
    """
    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)

    lx = _clamp(payload.get('linear_x', 0.0), MAX_LINEAR_X)
    ly = _clamp(payload.get('linear_y', 0.0), MAX_LINEAR_Y)
    az = _clamp(payload.get('angular_z', 0.0), MAX_ANGULAR_Z)

    ok = send_movement_command(linear_x=lx, linear_y=ly, angular_z=az)
    return JsonResponse({
        'status': 'success' if ok else 'error',
        'sent': {'linear_x': lx, 'linear_y': ly, 'angular_z': az},
        'mqtt_connected': get_connection_status(),
    }, status=200 if ok else 503)


def save_current_pose(request, pose_name):
    """
    Save the current robot pose to the database.

    Args:
        request: The HTTP request object
        pose_name (str): Name for the saved pose

    Returns:
        HttpResponse: Redirect to the main page with a success message
    """
    # Get the current pose from the MQTT client
    current_pose = get_current_pose()

    try:
        # Create a new RobotPose object
        pose = RobotPose(
            name=pose_name,
            position_x=current_pose['position']['x'],
            position_y=current_pose['position']['y'],
            orientation_z=current_pose['orientation']['z']
        )
        pose.save()
        # Add success message
        messages.success(request, f"Pose '{pose_name}' saved successfully!")
        # Redirect to the main page
        return redirect('button_page')
    except Exception as e:
        print(f"Error saving pose: {e}")
        messages.error(request, f"Error saving pose: {e}")
        return redirect('button_page')


def navigate_to_pose(request, pose_id):
    """
    Send a navigation goal to move the robot to a saved pose.

    Args:
        request: The HTTP request object
        pose_id (int): ID of the saved pose

    Returns:
        HttpResponse: Redirect to the main page with a success or error message
    """
    try:
        # Get the pose from the database
        pose = RobotPose.objects.get(id=pose_id)

        # Send the move_base_goal command
        success = send_move_base_goal(
            position_x=pose.position_x,
            position_y=pose.position_y,
            orientation_z=pose.orientation_z
        )

        if success:
            messages.success(request, f"Navigating to pose '{pose.name}'")
        else:
            messages.error(request, "Failed to send navigation goal")
        return redirect('button_page')
    except RobotPose.DoesNotExist:
        messages.error(request, "Pose not found")
        return redirect('button_page')
    except Exception as e:
        print(f"Error navigating to pose: {e}")
        messages.error(request, f"Error navigating to pose: {e}")
        return redirect('button_page')


def get_map_view(request):
    """Return the current 2D SLAM map data as JSON."""
    map_data = get_map_data()
    return JsonResponse(map_data)


@require_POST
def shutdown_pi(request):
    """Request shutdown via MQTT instead of directly calling system shutdown.

    Publishes a message to the MQTT topic 'amr_control/system/shutdown'.
    An external supervisor should handle the actual shutdown.
    """
    topic = 'amr_control/system/shutdown'
    payload = 'true'

    try:
        if not get_connection_status():
            message = 'Cannot send shutdown: MQTT client not connected'
            status = 'error'
            code = 200
        else:
            result = mqtt_client.publish(topic, payload)
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                message = 'Shutdown request sent via MQTT.'
                status = 'success'
                code = 200
            else:
                message = f'Failed to publish shutdown MQTT message (rc={result.rc}).'
                status = 'error'
                code = 200
    except Exception as e:
        message = f'Error sending shutdown MQTT message: {e}'
        status = 'error'
        code = 200

    if is_ajax(request):
        return JsonResponse({'status': status, 'message': message}, status=code)

    if status == 'success':
        messages.success(request, message)
    else:
        messages.error(request, message)
    return redirect('button_page')


@require_POST
def restart_pi(request):
    """Request restart via MQTT instead of directly calling system shutdown.

    Publishes a message to the MQTT topic 'amr_control/system/shutdown' with payload 'restart'.
    An external supervisor should handle the actual reboot.
    """
    topic = 'amr_control/system/reboot'
    payload = 'true'

    try:
        if not get_connection_status():
            message = 'Cannot send restart: MQTT client not connected'
            status = 'error'
            code = 200
        else:
            result = mqtt_client.publish(topic, payload)
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                message = 'Restart request sent via MQTT.'
                status = 'success'
                code = 200
            else:
                message = f'Failed to publish restart MQTT message (rc={result.rc}).'
                status = 'error'
                code = 200
    except Exception as e:
        message = f'Error sending restart MQTT message: {e}'
        status = 'error'
        code = 200

    if is_ajax(request):
        return JsonResponse({'status': status, 'message': message}, status=code)

    if status == 'success':
        messages.success(request, message)
    else:
        messages.error(request, message)
    return redirect('button_page')


@require_GET
def map_image(request):
    """Serve the map image from /robot/data/map.png.

    Returns 404 if the file is missing. Intended for display in the dashboard.
    """
    import os
    img_path = '/robot/data/map.png'
    if not os.path.exists(img_path):
        return HttpResponse(status=404)
    try:
        return FileResponse(open(img_path, 'rb'), content_type='image/png')
    except Exception:
        # If file cannot be opened/read for some reason
        return HttpResponse(status=404)


def docker_logs_stream(request):
    """Stream Docker container logs to the frontend using SSE."""
    container = request.GET.get('container', 'cmexaiii-robot')
    tail = request.GET.get('tail', '100')

    def event_stream():
        try:
            proc = subprocess.Popen(
                ['docker', 'logs', '-f', '--tail', tail, container],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            for line in proc.stdout:
                escaped = json.dumps(line.rstrip('\n'))
                yield f"data: {escaped}\n\n"
        except Exception as e:
            yield f"data: {json.dumps(f'Error: {e}')}\n\n"

    return StreamingHttpResponse(event_stream(), content_type='text/event-stream')


def versions_view(request):
    """Return the deployed version of every service container as JSON.

    Read via the Docker socket (see amr_control.versions); reflects exactly
    what is running on the robot. `?refresh=1` bypasses the short cache.
    """
    from .versions import get_service_versions
    force = request.GET.get('refresh') in ('1', 'true', 'yes')
    return JsonResponse({'services': get_service_versions(force=force)})


def mqtt_stream_view(request):
    """Stream MQTT messages to the frontend using SSE."""

    def event_stream():
        # Each SSE connection gets its own bounded queue. MQTT callbacks
        # broadcast to every registered subscriber, so multiple browser tabs
        # each receive the full stream instead of stealing messages from one
        # another via a single shared queue. The queue is unregistered in the
        # finally block when the client disconnects (the generator is closed),
        # so subscribers don't accumulate.
        subscriber = register_subscriber()
        last_status = None
        last_status_time = 0

        try:
            while True:
                current_time = time.time()
                current_status = get_connection_status()

                # Drain the whole backlog each tick and keep only the newest
                # sample. on_message enqueues odometry at the controller's
                # 50 Hz publish_rate; the display only needs the latest value,
                # so coalescing to it keeps the panels live (rather than
                # replaying a growing backlog) and keeps the queue near-empty.
                # State carried separately in module globals (robot_state /
                # nav_status / system_stats / motor_feedback) is re-attached
                # below and also re-sent by the heartbeat, so dropping the
                # older queued items loses nothing.
                latest_any = None
                latest_odom = None
                while not subscriber.empty():
                    item = subscriber.get()
                    latest_any = item
                    if 'linear' in item:      # odometry sample (twist + pose)
                        latest_odom = item
                message = latest_odom if latest_odom is not None else latest_any

                # Send a message if there's one in the queue
                if message is not None:
                    # Copy before mutating: the same dict object is broadcast
                    # to every subscriber, so adding keys must not touch the
                    # shared instance.
                    message = dict(message)
                    rs = get_current_robot_state()
                    message['mqtt_connected'] = current_status
                    message.setdefault('robot_state', rs['state'])
                    message.setdefault('driver_names', rs.get('driver_names', []))
                    message.setdefault('driver_states', rs.get('driver_states', []))
                    message.setdefault('nav_status', get_nav_status())
                    message.setdefault('system_stats', get_system_stats())
                    message.setdefault('motor_feedback', get_motor_feedback())
                    yield f"data: {json.dumps(message)}\n\n"
                    last_status = current_status
                    last_status_time = current_time
                # Send a status update every 5 seconds if status changed or no message was sent in the last 5 seconds
                elif current_status != last_status or (current_time - last_status_time) > 5:
                    rs = get_current_robot_state()
                    status_message = {
                        'mqtt_connected': current_status,
                        'status_update': True,
                        'robot_state': rs['state'],
                        'driver_names': rs.get('driver_names', []),
                        'driver_states': rs.get('driver_states', []),
                        'nav_status': get_nav_status(),
                        'system_stats': get_system_stats(),
                        'motor_feedback': get_motor_feedback(),
                    }
                    yield f"data: {json.dumps(status_message)}\n\n"
                    last_status = current_status
                    last_status_time = current_time

                time.sleep(0.1)  # ~10 Hz: responsive display, queue stays empty
        finally:
            unregister_subscriber(subscriber)

    return StreamingHttpResponse(event_stream(), content_type='text/event-stream')
