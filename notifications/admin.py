from django.contrib import admin
from .models import Notification

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'title', 'read', 'created_at')
    list_filter = ('read', 'created_at')
    search_fields = ('user__username', 'title', 'body')
    readonly_fields = ('user', 'title', 'body', 'created_at', 'data')
    list_per_page = 50
    actions = ['mark_as_read', 'mark_as_unread']

    fieldsets = (
        (None, {
            'fields': ('user', 'title', 'body')
        }),
        ('Status', {
            'fields': ('read', 'created_at')
        }),
        ('Metadata', {
            'fields': ('data',)
        }),
    )

    def mark_as_read(self, request, queryset):
        queryset.update(read=True)
    mark_as_read.short_description = "Mark selected notifications as read"

    def mark_as_unread(self, request, queryset):
        queryset.update(read=False)
    mark_as_unread.short_description = "Mark selected notifications as unread"