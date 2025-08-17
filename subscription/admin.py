from django.contrib import admin
from .models import Subscription

# Register the Subscription model
# This makes the model visible and editable in the Django admin panel
@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    # This list controls which fields are displayed in the list view of the admin
    list_display = ["user", "plan", "status", "current_period_end", "stripe_customer_id"]
    # This adds a search box to the admin page for the specified fields
    search_fields = ["user__username", "plan", "status"]
    # This adds filters on the side of the page for quick filtering
    list_filter = ["plan", "status"]