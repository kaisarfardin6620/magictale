# ai/admin.py

from django.contrib import admin
from .models import StoryProject, StoryPage, GenerationEvent, GalleryStory

@admin.register(StoryProject)
class StoryProjectAdmin(admin.ModelAdmin):
    """
    Admin interface for managing user-generated story projects.
    """
    list_display = (
        "id", "child_name", "user", "status", "is_saved", 
        "progress", "theme", "art_style", "created_at"
    )
    list_filter = ("status", "is_saved", "art_style", "language")
    search_fields = ("user__username", "child_name", "theme")
    readonly_fields = ("created_at", "started_at", "finished_at")

@admin.register(StoryPage)
class StoryPageAdmin(admin.ModelAdmin):
    """
    Admin interface for viewing individual story pages.
    """
    list_display = ("id", "project", "index")
    list_filter = ("project__user__username",)
    search_fields = ("text",)
    ordering = ("project", "index")

@admin.register(GenerationEvent)
class GenerationEventAdmin(admin.ModelAdmin):
    """
    Admin interface for debugging generation events.
    """
    list_display = ("id", "project", "kind", "ts")
    list_filter = ("kind",)
    search_fields = ("project__user__username",)

# === NEW: Admin for the Public Gallery Content ===
@admin.register(GalleryStory)
class GalleryStoryAdmin(admin.ModelAdmin):
    """
    Admin interface for creating and managing the pre-made stories
    that appear in the public gallery.
    """
    list_display = ("title", "creator_name", "is_premium")
    list_filter = ("is_premium",)
    search_fields = ("title", "synopsis")