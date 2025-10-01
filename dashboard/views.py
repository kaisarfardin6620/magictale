from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser
from rest_framework import generics, filters
from django_filters.rest_framework import DjangoFilterBackend
import pytz
from django.contrib.auth.models import User
from subscription.models import Subscription
from ai.models import StoryProject
from .models import SiteSettings
from .serializers import (
    SubscriptionManagementSerializer,
    SiteSettingsSerializer,
    DashboardUserSerializer,
    DashboardStorySerializer
)

from datetime import timedelta, datetime
from django.utils import timezone
from django.db.models import Count
from django.db.models.functions import TruncMonth
from django.conf import settings
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

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

        user_list = User.objects.select_related('profile', 'subscription').order_by('-date_joined')
        user_paginator = Paginator(user_list, 10)
        user_page_number = request.query_params.get('user_page', 1)
        try:
            paginated_users = user_paginator.page(user_page_number)
        except (PageNotAnInteger, EmptyPage):
            paginated_users = user_paginator.page(1)
        user_serializer = DashboardUserSerializer(paginated_users, many=True)
        
        story_list = StoryProject.objects.select_related('user').order_by('-created_at')
        story_paginator = Paginator(story_list, 10)
        story_page_number = request.query_params.get('story_page', 1)
        try:
            paginated_stories = story_paginator.page(story_page_number)
        except (PageNotAnInteger, EmptyPage):
            paginated_stories = story_paginator.page(1)
        story_serializer = DashboardStorySerializer(paginated_stories, many=True)

        scheme = request.scheme
        host = request.get_host()
        path = request.path
        
        def get_next_url(paginated_qs, page_param_name):
            if paginated_qs.has_next():
                params = request.query_params.copy()
                params[page_param_name] = paginated_qs.next_page_number()
                return f"{scheme}://{host}{path}?{params.urlencode()}"
            return None

        def get_previous_url(paginated_qs, page_param_name):
            if paginated_qs.has_previous():
                params = request.query_params.copy()
                params[page_param_name] = paginated_qs.previous_page_number()
                return f"{scheme}://{host}{path}?{params.urlencode()}"
            return None

        data = {
            'stats': {
                'total_users': {'value': total_users, 'change': self._calculate_change(total_users - users_this_month, users_this_month)},
                'active_subscriptions': {'value': active_subscriptions, 'change': self._calculate_change(active_subscriptions - active_subs_this_month, active_subs_this_month)},
                'stories_created': {'value': total_stories, 'change': self._calculate_change(total_stories - stories_this_month, stories_this_month)},
                'reported_content': {'value': 0, 'change': 0.0}
            },
            'recent_signups': {
                'count': user_paginator.count,
                'num_pages': user_paginator.num_pages,
                'current_page': paginated_users.number,
                'next': get_next_url(paginated_users, 'user_page'),
                'previous': get_previous_url(paginated_users, 'user_page'),
                'results': user_serializer.data
            },
            'recent_stories': {
                'count': story_paginator.count,
                'num_pages': story_paginator.num_pages,
                'current_page': paginated_stories.number,
                'next': get_next_url(paginated_stories, 'story_page'),
                'previous': get_previous_url(paginated_stories, 'story_page'),
                'results': story_serializer.data
            }
        }
        return Response(data)

    def _calculate_change(self, old, new):
        if old <= 0:
            return 100.0 if new > 0 else 0.0
        return round((new / old) * 100, 2)

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
            'total_subscribers': {'value': total_subscribers, 'change': total_subscribers_change},
            'trials_active': {'value': trials_active, 'expiring_this_week': expiring_this_week},
            'canceled_subscriptions': {'value': canceled_subscriptions, 'change': canceled_subscriptions_change}
        }
        paginated_response = super().list(request, *args, **kwargs)
        combined_data = {'stats': stats, **paginated_response.data}
        return Response(combined_data)

class AnalyticsAPIView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        now = timezone.now()
        one_year_ago = now - timedelta(days=365)
        user_growth_query = User.objects.filter(date_joined__gte=one_year_ago) \
            .annotate(month=TruncMonth('date_joined')) \
            .values('month') \
            .annotate(count=Count('id')) \
            .order_by('month')
        user_growth_map = {item['month'].month: item['count'] for item in user_growth_query}
        user_growth_data = []
        for month_num in range(1, 13):
            month_name = datetime(now.year, month_num, 1).strftime('%b')
            user_growth_data.append({"month": month_name, "count": user_growth_map.get(month_num, 0)})
        stories_by_month_query = StoryProject.objects.filter(created_at__gte=one_year_ago) \
            .annotate(month=TruncMonth('created_at')) \
            .values('month') \
            .annotate(count=Count('id')) \
            .order_by('month')
        stories_by_month_map = {item['month'].month: item['count'] for item in stories_by_month_query}
        stories_by_month_data = []
        for month_num in range(1, 13):
            month_name = datetime(now.year, month_num, 1).strftime('%b')
            stories_by_month_data.append({"month": month_name, "count": stories_by_month_map.get(month_num, 0)})
        top_stories_query = StoryProject.objects.order_by('-read_count', '-likes_count')[:5] \
            .values('theme', 'read_count', 'likes_count', 'shares_count', 'tags', 'audio_duration_seconds')
        top_stories_data = []
        for story in top_stories_query:
            reading_time = "N/A"
            if story.get('audio_duration_seconds'):
                minutes = round(story['audio_duration_seconds'] / 60)
                reading_time = f"{minutes} min"
            top_stories_data.append({
                "theme": story.get('theme'), "read_count": story.get('read_count'),
                "likes_count": story.get('likes_count'), "shares_count": story.get('shares_count'),
                "tags": story.get('tags'), "reading_time": reading_time
            })
        data = {
            'user_growth_over_time': user_growth_data,
            'stories_created_over_time': stories_by_month_data,
            'top_performing_stories': top_stories_data
        }
        return Response(data)

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

class TimezoneListView(APIView):
    permission_classes = [IsAdminUser]
    def get(self, request):
        return Response(pytz.all_timezones)

class LanguageListView(APIView):
    permission_classes = [IsAdminUser]
    def get(self, request):
        languages = [
            {"code": "en", "name": "English"}, {"code": "es", "name": "Spanish"},
            {"code": "fr", "name": "French"}, {"code": "de", "name": "German"},
            {"code": "it", "name": "Italian"}, {"code": "pt", "name": "Portuguese"},
        ]
        return Response(languages)