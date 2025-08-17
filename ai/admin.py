from django.contrib import admin
from .models import StoryProject, StoryPage, GenerationEvent

@admin.register(StoryProject)
class StoryProjectAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "status", "progress", "theme", "art_style", "model_used", "created_at")
    list_filter = ("status", "model_used", "language")
    search_fields = ("user__username", "theme", "art_style")

@admin.register(StoryPage)
class StoryPageAdmin(admin.ModelAdmin):
    list_display = ("id", "project", "index")
    list_filter = ("project",)
    ordering = ("project", "index")

@admin.register(GenerationEvent)
class GenerationEventAdmin(admin.ModelAdmin):
    list_display = ("id", "project", "kind", "ts")
    list_filter = ("kind",)