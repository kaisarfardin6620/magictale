from django.contrib import admin
from .models import StoryProject, GenerationEvent, StoryPage

@admin.register(StoryProject)
class StoryProjectAdmin(admin.ModelAdmin):
    list_display = (
        "id", "child_name", "user", "status", "is_saved",
        "progress", "theme", "art_style", "created_at"
    )
    list_filter = ("status", "is_saved", "art_style", "language")
    search_fields = ("user__username", "child_name", "theme")
    readonly_fields = ("created_at", "started_at", "finished_at")

@admin.register(GenerationEvent)
class GenerationEventAdmin(admin.ModelAdmin):
    list_display = ("id", "project", "kind", "ts")
    list_filter = ("kind",)
    search_fields = ("project__user__username",)

@admin.register(StoryPage)
class StoryPageAdmin(admin.ModelAdmin):
    list_display = ('id', 'project', 'index')
    list_filter = ('project__user__username',)
    search_fields = ('text',)
    ordering = ('project', 'index')