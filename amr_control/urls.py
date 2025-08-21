from django.urls import path
from . import views

urlpatterns = [
    path('', views.button_view, name='button_page'),  # Route for the button HTML page
    path('handle_button/', views.handle_button, name='handle_button'),  # Route to handle button clicks
    path('mqtt_stream/', views.mqtt_stream_view, name='mqtt_stream'),  # SSE endpoint
    path('get_map/', views.get_map_view, name='get_map'),  # Route to get the 2D SLAM map data
    path('map_image/', views.map_image, name='map_image'),  # Route to serve map.png image
    path('shutdown/', views.shutdown_pi, name='shutdown_pi'),  # Shutdown Raspberry Pi host
    path('restart/', views.restart_pi, name='restart_pi'),  # Restart Raspberry Pi host
]
