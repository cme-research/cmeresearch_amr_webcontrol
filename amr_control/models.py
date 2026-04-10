from django.db import models
from django.utils import timezone

# Create your models here.
class RobotPose(models.Model):
    name = models.CharField(max_length=100, default="Unnamed Pose")
    position_x = models.FloatField()
    position_y = models.FloatField()
    orientation_z = models.FloatField()
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.name} ({self.position_x:.2f}, {self.position_y:.2f}, {self.orientation_z:.2f})"
