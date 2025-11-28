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
    parent_project = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True, related_name="variants")
    onboarding = models.ForeignKey(
        "authentication.OnboardingStatus",
        on_delete=models.SET_NULL,
        related_name="stories",
        null=True,
        blank=True
    )
    title = models.CharField(max_length=200, blank=True, default="")
    child_name = models.CharField(max_length=100)
    age = models.PositiveIntegerField()
    pronouns = models.CharField(max_length=50)
    favorite_animal = models.CharField(max_length=100)
    favorite_color = models.CharField(max_length=50)
    theme = models.CharField(max_length=80)
    art_style = models.CharField(max_length=80)
    language = models.CharField(max_length=40, default="English")
    voice = models.CharField(max_length=80, blank=True, default="")
    length = models.CharField(max_length=20, choices=[("short","short"),("medium","medium"),("long","long")], default="short")
    difficulty = models.PositiveSmallIntegerField(default=1)
    custom_prompt = models.TextField(blank=True, default="")
    text = models.TextField(blank=True, null=True)
    image_url = models.URLField(max_length=1024, blank=True, null=True)
    audio_url = models.URLField(max_length=1024, blank=True, null=True)
    audio_duration_seconds = models.PositiveIntegerField(null=True, blank=True, help_text="The duration of the generated audio in seconds.")
    synopsis = models.TextField(blank=True, default="")
    tags = models.CharField(max_length=255, blank=True, default="")
    cover_image_url = models.URLField(max_length=1024, blank=True, default="")
    is_saved = models.BooleanField(default=False)
    read_count = models.PositiveIntegerField(default=0)
    likes_count = models.PositiveIntegerField(default=0)
    shares_count = models.PositiveIntegerField(default=0)
    model_used = models.CharField(max_length=80, default="gpt-4o-2024-08-06")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    progress = models.PositiveSmallIntegerField(default=0)
    error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        display_title = self.title if self.title else f"Story for {self.child_name}"
        return f"{display_title} ({self.user.username}) - {self.status}"

class StoryPage(models.Model):
    project = models.ForeignKey(StoryProject, on_delete=models.CASCADE, related_name="pages")
    index = models.PositiveIntegerField()
    text = models.TextField()
    audio_url = models.URLField(max_length=1024, blank=True, default="")
    audio_duration = models.FloatField(null=True, blank=True, help_text="Duration in seconds")
    
    class Meta:
        unique_together = ("project", "index")
        ordering = ["index"]

    def __str__(self):
        return f"Page {self.index} for project {self.project.id}"

class GenerationEvent(models.Model):
    project = models.ForeignKey(StoryProject, on_delete=models.CASCADE, related_name="events")
    ts = models.DateTimeField(auto_now_add=True)
    kind = models.CharField(max_length=40)
    payload = models.JSONField(default=dict, blank=True)