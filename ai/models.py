from django.conf import settings
from django.db import models

class StoryProject(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending"
        RUNNING = "running"
        DONE = "done"
        FAILED = "failed"
        CANCELED = "canceled"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="story_projects")
    onboarding = models.ForeignKey("authentication.OnboardingStatus", on_delete=models.PROTECT, related_name="stories")  # TODO: replace app label
    theme = models.CharField(max_length=80)
    art_style = models.CharField(max_length=80)
    language = models.CharField(max_length=40, default="English")
    voice = models.CharField(max_length=80, blank=True, default="")
    length = models.CharField(max_length=20, choices=[("short","short"),("medium","medium"),("long","long")], default="short")
    difficulty = models.PositiveSmallIntegerField(default=1) 
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    progress = models.PositiveSmallIntegerField(default=0)  
    custom_prompt = models.TextField(blank=True, default="") 
    model_used = models.CharField(max_length=80, default="gpt-4o-mini")  
    error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"StoryProject#{self.pk} ({self.user}) - {self.status}"


class StoryPage(models.Model):
    project = models.ForeignKey(StoryProject, on_delete=models.CASCADE, related_name="pages")
    index = models.PositiveIntegerField()
    text = models.TextField()
    image_url = models.URLField(blank=True, default="")  
    audio_url = models.URLField(blank=True, default="")  

    class Meta:
        unique_together = ("project", "index")
        ordering = ["index"]


class GenerationEvent(models.Model):
    project = models.ForeignKey(StoryProject, on_delete=models.CASCADE, related_name="events")
    ts = models.DateTimeField(auto_now_add=True)
    kind = models.CharField(max_length=40)  
    payload = models.JSONField(default=dict, blank=True)