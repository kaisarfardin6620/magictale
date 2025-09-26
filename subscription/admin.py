from django.contrib import admin
from .models import Subscription, ProcessedStripeEvent

@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ["user", "plan", "status", "current_period_end", "stripe_customer_id"]
    search_fields = ["user__username", "plan", "status"]
    list_filter = ["plan", "status"]

@admin.register(ProcessedStripeEvent)
class ProcessedStripeEventAdmin(admin.ModelAdmin):
    list_display = ('event_id', 'processed_at')
    search_fields = ('event_id',)
    ordering = ('-processed_at',)
    readonly_fields = ('event_id', 'processed_at')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False