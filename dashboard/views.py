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

from datetime import timedelta, datetime
from django.utils import timezone
from django.db.models import Count
from django.db.models.functions import TruncMonth
from django.conf import settings

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

        # --- UPDATE: ADD USER ID AND PROFILE PICTURE ---
        recent_users = User.objects.select_related('profile', 'subscription').order_by('-date_joined')[:5]
        recent_signups_data = []
        for user in recent_users:
            profile_picture_url = None
            if hasattr(user, 'profile') and user.profile.profile_picture and hasattr(user.profile.profile_picture, 'url'):
                if settings.USE_S3_STORAGE:
                    profile_picture_url = user.profile.profile_picture.url
                else:
                    profile_picture_url = f"{settings.BACKEND_BASE_URL}{user.profile.profile_picture.url}"
            
            recent_signups_data.append({
                'id': user.id,
                'profile_picture_url': profile_picture_url,
                'name': user.get_full_name() or user.username,
                'email': user.email,
                'date': user.date_joined.strftime('%b %d, %Y'),
                'plan': user.subscription.get_plan_display() if hasattr(user, 'subscription') else 'Free'
            })
        
        # --- UPDATE: CHANGE STATUS LABELS FOR RECENT STORIES ---
        recent_stories = StoryProject.objects.select_related('user').order_by('-created_at')[:5]
        recent_stories_data = [{
            'title': story.theme or "Custom Story",
            'creator': story.user.get_full_name() or story.user.username,
            'date': story.created_at.strftime('%b %d, %Y'),
            'status': 'Published' if story.status == 'done' else 'Pending'
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
    
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['plan', 'status']
    search_fields = ['user__first_name', 'user__last_name', 'user__email']
    
    def _calculate_change(self, old, new):
        if old <= 0:
            return 100.0 if new > 0 else 0.0
        return round(((new - old) / old) * 100, 2)

    def list(self, request, *args, **kwargs):
        all_subscriptions = Subscription.objects.all()
        now = timezone.now()
        last_30_days_start = now - timedelta(days=30)
        prev_30_days_start = now - timedelta(days=60)

        total_subscribers = all_subscriptions.count()
        new_subs_last_30 = all_subscriptions.filter(trial_start__gte=last_30_days_start).count()
        new_subs_prev_30 = all_subscriptions.filter(trial_start__gte=prev_30_days_start, trial_start__lt=last_30_days_start).count()
        total_subscribers_change = self._calculate_change(new_subs_prev_30, new_subs_last_30)

        trials_active = all_subscriptions.filter(status='trialing').count()
        expiring_this_week = all_subscriptions.filter(
            status='trialing',
            trial_end__lte=now + timedelta(days=7),
            trial_end__gte=now
        ).count()
        
        canceled_subscriptions = all_subscriptions.filter(status='canceled').count()
        canceled_last_30 = all_subscriptions.filter(canceled_at__gte=last_30_days_start).count()
        canceled_prev_30 = all_subscriptions.filter(canceled_at__gte=prev_30_days_start, canceled_at__lt=last_30_days_start).count()
        canceled_subscriptions_change = self._calculate_change(canceled_prev_30, canceled_last_30)

        stats = {
            'total_subscribers': {
                'value': total_subscribers,
                'change': total_subscribers_change
            },
            'trials_active': {
                'value': trials_active,
                'expiring_this_week': expiring_this_week
            },
            'canceled_subscriptions': {
                'value': canceled_subscriptions,
                'change': canceled_subscriptions_change
            }
        }

        paginated_response = super().list(request, *args, **kwargs)
        
        combined_data = {
            'stats': stats,
            **paginated_response.data
        }
        
        return Response(combined_data)

# --- Views for the Analytics & Reports Page ---
class AnalyticsAPIView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        now = timezone.now()
        one_year_ago = now - timedelta(days=365)
        
        # --- Process User Growth Data ---
        user_growth_query = User.objects.filter(date_joined__gte=one_year_ago) \
            .annotate(month=TruncMonth('date_joined')) \
            .values('month') \
            .annotate(count=Count('id')) \
            .order_by('month')
            
        user_growth_map = {item['month'].month: item['count'] for item in user_growth_query}
        
        user_growth_data = []
        for month_num in range(1, 13):
            month_name = datetime(now.year, month_num, 1).strftime('%b')
            user_growth_data.append({
                "month": month_name,
                "count": user_growth_map.get(month_num, 0)
            })
            
        # --- UPDATE: "STORIES BY AGE" TO A 12-MONTH REPORT ---
        stories_by_month_query = StoryProject.objects.filter(created_at__gte=one_year_ago) \
            .annotate(month=TruncMonth('created_at')) \
            .values('month') \
            .annotate(count=Count('id')) \
            .order_by('month')
        
        stories_by_month_map = {item['month'].month: item['count'] for item in stories_by_month_query}
        
        stories_by_month_data = []
        for month_num in range(1, 13):
            month_name = datetime(now.year, month_num, 1).strftime('%b')
            stories_by_month_data.append({
                "month": month_name,
                "count": stories_by_month_map.get(month_num, 0)
            })

        # --- UPDATE: ADD TAGS AND LENGTH TO TOP PERFORMING STORIES ---
        top_stories = StoryProject.objects.order_by('-read_count', '-likes_count')[:5] \
            .values('theme', 'read_count', 'likes_count', 'shares_count', 'tags', 'length')

        data = {
            'user_growth_over_time': user_growth_data,
            'stories_created_over_time': stories_by_month_data, # Renamed key
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