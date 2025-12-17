from django.contrib import admin
from .models import UserReport, LegalDocument

@admin.register(UserReport)
class UserReportAdmin(admin.ModelAdmin):
    list_display = ('user', 'created_at', 'is_resolved', 'has_screenshot')
    list_filter = ('is_resolved', 'created_at')
    search_fields = ('user__username', 'user__email', 'message')
    readonly_fields = ('created_at',)

    def has_screenshot(self, obj):
        return bool(obj.screenshot)
    has_screenshot.boolean = True

@admin.register(LegalDocument)
class LegalDocumentAdmin(admin.ModelAdmin):
    list_display = ('title', 'doc_type', 'last_updated')