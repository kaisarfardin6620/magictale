# dashboard/views.py

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser
from rest_framework import generics, filters
from django_filters.rest_framework import DjangoFilterBackend

from django.contrib.auth.models import User
from subscription.models import Subscription
from ai.models import StoryProject
from .models import SiteSettings
from .serializers import SubscriptionManagementSerializer, SiteSettingsSerializer

from datetime import timedelta
from django.utils import timezone
from django.db.models import Count
from django.db.models.functions import TruncMonth

# --- View for the Main Dashboard Page ---
class DashboardStatsAPIView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        now = timezone.now()
        last_month_start = now - timedelta(days=30)

        total_users = User.objects.count()
        users_this_month = User.objects.filter(date_joined__gte=last_month_start).count()
        
        active_subscriptions = Subscription.objects.filter(status__in=['active', 'trialing']).count()
        active_subs_this_month = Subscription.objects.filter(status__in=['active', 'trialing'], trial_start__gte=last_month_start).count()

        total_stories = StoryProject.objects.count()
        stories_this_month = StoryProject.objects.filter(created_at__gte=last_month_start).count()

        recent_users = User.objects.select_related('profile', 'subscription').order_by('-date_joined')[:5]
        recent_signups_data = [{
            'name': user.get_full_name() or user.username, 'email': user.email,
            'date': user.date_joined.strftime('%b %d, %Y'),
            'plan': user.subscription.get_plan_display() if hasattr(user, 'subscription') else 'Free'
        } for user in recent_users]

        recent_stories = StoryProject.objects.select_related('user').order_by('-created_at')[:5]
        recent_stories_data = [{
            'title': story.theme or "Custom Story",
            'creator': story.user.get_full_name() or story.user.username,
            'date': story.created_at.strftime('%b %d, %Y'),
            'status': story.get_status_display()
        } for story in recent_stories]

        data = {
            'stats': {
                'total_users': {'value': total_users, 'change': self._calculate_change(total_users - users_this_month, users_this_month)},
                'active_subscriptions': {'value': active_subscriptions, 'change': self._calculate_change(active_subscriptions - active_subs_this_month, active_subs_this_month)},
                'stories_created': {'value': total_stories, 'change': self._calculate_change(total_stories - stories_this_month, stories_this_month)},
                'reported_content': {'value': 0, 'change': 0.0}
            },
            'recent_signups': recent_signups_data,
            'recent_stories': recent_stories_data,
        }
        return Response(data)

    def _calculate_change(self, old, new):
        if old <= 0:
            return 100.0 if new > 0 else 0.0
        return round((new / old) * 100, 2)

# --- View for the Subscription Management Page ---
class SubscriptionManagementView(generics.ListAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = SubscriptionManagementSerializer
    queryset = Subscription.objects.select_related('user', 'user__profile').order_by('-id')
    
    # These backends enable the dropdown filters and search bar
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['plan', 'status']
    search_fields = ['user__first_name', 'user__last_name', 'user__email']
    
    # NOTE: Pagination is handled automatically by the 'PAGE_SIZE' setting in settings.py

    def list(self, request, *args, **kwargs):
        """
        Overrides the default list method to add the top-level card stats to the response.
        """
        all_subscriptions = Subscription.objects.all()
        total_subscribers = all_subscriptions.count()
        trials_active = all_subscriptions.filter(status='trialing').count()
        canceled_subscriptions = all_subscriptions.filter(status='canceled').count()
        
        expiring_this_week = all_subscriptions.filter(
            status='trialing',
            trial_end__lte=timezone.now() + timedelta(days=7),
            trial_end__gte=timezone.now()
        ).count()
        
        stats = {
            'total_subscribers': total_subscribers,
            'trials_active': trials_active,
            'canceled_subscriptions': canceled_subscriptions,
            'expiring_this_week': expiring_this_week,
        }

        # The parent 'list' method handles the filtering, searching, and pagination
        paginated_response = super().list(request, *args, **kwargs)
        
        # We combine our custom stats with the standard paginated response
        combined_data = {
            'stats': stats,
            **paginated_response.data 
        }
        
        return Response(combined_data)

# --- Views for the Analytics & Reports Page ---
class AnalyticsAPIView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        one_year_ago = timezone.now() - timedelta(days=365)
        
        user_growth = User.objects.filter(date_joined__gte=one_year_ago) \
            .annotate(month=TruncMonth('date_joined')) \
            .values('month') \
            .annotate(count=Count('id')) \
            .order_by('month')

        stories_by_age = StoryProject.objects.values('age') \
            .annotate(count=Count('id')) \
            .order_by('age')

        top_stories = StoryProject.objects.order_by('-read_count', '-likes_count')[:5] \
            .values('theme', 'read_count', 'likes_count', 'shares_count')

        data = {
            'user_growth_over_time': list(user_growth),
            'stories_created_by_age_group': list(stories_by_age),
            'top_performing_stories': list(top_stories)
        }
        return Response(data)

# --- View for the Admin Settings Page ---
class SiteSettingsView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = SiteSettingsSerializer

    def get_object(self):
        return SiteSettings.load()

    def get(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def put(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)