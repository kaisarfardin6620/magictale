from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    DashboardStatsAPIView,
    SubscriptionManagementView,
    AnalyticsAPIView,
    SiteSettingsView,
    TimezoneListView,
    LanguageListView,
    AdminProfileView,
    UserManagementViewSet
)

router = DefaultRouter()
router.register(r'users', UserManagementViewSet, basename='user-management')

urlpatterns = [
    path('stats/', DashboardStatsAPIView.as_view(), name='dashboard-stats'),
    path('subscriptions/', SubscriptionManagementView.as_view(), name='dashboard-subscriptions'),
    path('reports/', AnalyticsAPIView.as_view(), name='dashboard-reports'),
    path('settings/', SiteSettingsView.as_view(), name='dashboard-settings'),
    path('timezones/', TimezoneListView.as_view(), name='dashboard-timezones'),
    path('languages/', LanguageListView.as_view(), name='dashboard-languages'),
    path('profile/', AdminProfileView.as_view(), name='admin-profile'),
    path('', include(router.urls)),
]