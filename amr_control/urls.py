from django.urls import path
from . import views

urlpatterns = [
    # Page routes
    path('',            views.teleop_view,     name='teleop'),
    path('mission/',    views.mission_view,    name='mission'),
    path('navigation/', views.navigation_view, name='navigation'),
    path('logs/',       views.logs_view,       name='logs'),
    path('config/',     views.config_view,     name='config'),
    # Legacy alias used by some older redirects (messages flow back here)
    path('home/',       views.button_view,     name='button_page'),

    # Action endpoints
    path('handle_button/', views.handle_button, name='handle_button'),
    path('joystick_cmd/',  views.joystick_cmd,  name='joystick_cmd'),

    # Streams + data
    path('mqtt_stream/',   views.mqtt_stream_view,    name='mqtt_stream'),
    path('docker_logs/',   views.docker_logs_stream,  name='docker_logs'),
    path('api/versions/',  views.versions_view,       name='versions'),
    path('get_map/',       views.get_map_view,        name='get_map'),
    path('map_image/',     views.map_image,           name='map_image'),

    # Power management
    path('shutdown/', views.shutdown_pi, name='shutdown_pi'),
    path('restart/',  views.restart_pi,  name='restart_pi'),
]
