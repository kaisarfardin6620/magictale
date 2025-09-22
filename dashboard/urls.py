from django.urls import path
from .views import (
    DashboardStatsAPIView,
    SubscriptionManagementView,
    AnalyticsAPIView,
    SiteSettingsView,
)

urlpatterns = [
    path('stats/', DashboardStatsAPIView.as_view(), name='dashboard-stats'),
    path('subscriptions/', SubscriptionManagementView.as_view(), name='dashboard-subscriptions'),
    path('reports/', AnalyticsAPIView.as_view(), name='dashboard-reports'),
    path('settings/', SiteSettingsView.as_view(), name='dashboard-settings'),
]