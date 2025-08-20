# ai/models.py

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
    onboarding = models.ForeignKey(
        "authentication.OnboardingStatus", 
        on_delete=models.SET_NULL,
        related_name="stories",
        null=True,
        blank=True
    )
    
    # === DENORMALIZED HERO DATA (Snapshot at creation) ===
    child_name = models.CharField(max_length=100)
    age = models.PositiveIntegerField()
    pronouns = models.CharField(max_length=50)
    favorite_animal = models.CharField(max_length=100)
    favorite_color = models.CharField(max_length=50)

    # === STORY SETTINGS ===
    theme = models.CharField(max_length=80)
    art_style = models.CharField(max_length=80)
    language = models.CharField(max_length=40, default="English")
    voice = models.CharField(max_length=80, blank=True, default="")
    length = models.CharField(max_length=20, choices=[("short","short"),("medium","medium"),("long","long")], default="short")
    difficulty = models.PositiveSmallIntegerField(default=1)
    custom_prompt = models.TextField(blank=True, default="")
    
    # === Fields for Library Display & PDF ===
    synopsis = models.TextField(blank=True, default="")
    tags = models.CharField(max_length=255, blank=True, default="")
    cover_image_url = models.URLField(max_length=1024, blank=True, default="")

    # === Flag for the "Save to Library" feature ===
    is_saved = models.BooleanField(default=False)
    
    # === Analytics Fields ===
    read_count = models.PositiveIntegerField(default=0)
    likes_count = models.PositiveIntegerField(default=0)
    shares_count = models.PositiveIntegerField(default=0)
    
    # === STATUS AND METADATA ===
    model_used = models.CharField(max_length=80, default="gpt-4o-mini")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    progress = models.PositiveSmallIntegerField(default=0)
    error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Story for '{self.child_name}' ({self.user.username}) - {self.status}"

class StoryPage(models.Model):
    project = models.ForeignKey(StoryProject, on_delete=models.CASCADE, related_name="pages")
    index = models.PositiveIntegerField()
    text = models.TextField()
    image_url = models.URLField(max_length=1024, blank=True, default="")  
    audio_url = models.URLField(max_length=1024, blank=True, default="")  

    class Meta:
        unique_together = ("project", "index")
        ordering = ["index"]

class GenerationEvent(models.Model):
    project = models.ForeignKey(StoryProject, on_delete=models.CASCADE, related_name="events")
    ts = models.DateTimeField(auto_now_add=True)
    kind = models.CharField(max_length=40)  
    payload = models.JSONField(default=dict, blank=True)

class GalleryStory(models.Model):
    title = models.CharField(max_length=200)
    creator_name = models.CharField(max_length=100, default="By MagicTales")
    synopsis = models.TextField()
    cover_image_url = models.URLField(max_length=1024)
    is_premium = models.BooleanField(default=True, help_text="Requires a subscription to access")
    
    class Meta:
        verbose_name = "Gallery Story"
        verbose_name_plural = "Gallery Stories"

    def __str__(self):
        return self.title