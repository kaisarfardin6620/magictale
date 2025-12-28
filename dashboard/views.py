from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser
from rest_framework import generics, filters, status
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
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
    DashboardStorySerializer,
    AdminProfileSerializer,
    AdminProfileUpdateSerializer,
    AdminChangePasswordSerializer
)

from datetime import timedelta, datetime
from django.utils import timezone
from django.db.models import Count, Q
from django.db.models.functions import TruncMonth
from django.conf import settings
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
from rest_framework import viewsets
from rest_framework.decorators import action
from authentication.utils import send_email
from django.template.loader import render_to_string
from authentication.models import UserProfile
from django.core.cache import cache
from rest_framework.exceptions import ValidationError
from . import services
from django.utils.translation import gettext as _
from urllib.parse import urlencode


class DashboardStatsAPIView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        cache_key = 'dashboard_stats_and_recents'
        cached_data = cache.get(cache_key)

        if cached_data:
            return Response(cached_data)

        now = timezone.now()
        last_month_start = now - timedelta(days=30)

        user_stats = User.objects.aggregate(
            total_users=Count('id'),
            users_this_month=Count('id', filter=Q(date_joined__gte=last_month_start))
        )

        subscription_stats = Subscription.objects.aggregate(
            active_subscriptions=Count('id', filter=Q(status__in=['active', 'trialing'])),
            active_subs_this_month=Count('id', filter=Q(status__in=['active', 'trialing'], trial_start__gte=last_month_start))
        )

        story_stats = StoryProject.objects.aggregate(
            total_stories=Count('id'),
            stories_this_month=Count('id', filter=Q(created_at__gte=last_month_start))
        )

        total_users = user_stats['total_users']
        users_this_month = user_stats['users_this_month']
        active_subscriptions = subscription_stats['active_subscriptions']
        active_subs_this_month = subscription_stats['active_subs_this_month']
        total_stories = story_stats['total_stories']
        stories_this_month = story_stats['stories_this_month']

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
        
        base_url = request.build_absolute_uri(request.path)

        def get_next_url(paginated_qs, page_param_name):
            if paginated_qs.has_next():
                params = request.query_params.copy()
                params[page_param_name] = paginated_qs.next_page_number()
                return f"{base_url}?{params.urlencode()}"
            return None
        def get_previous_url(paginated_qs, page_param_name):
            if paginated_qs.has_previous():
                params = request.query_params.copy()
                params[page_param_name] = paginated_qs.previous_page_number()
                return f"{base_url}?{params.urlencode()}"
            return None
            
        data = {
            'stats': {
                'total_users': {'value': total_users, 'change': self._calculate_change(total_users - users_this_month, users_this_month)},
                'active_subscriptions': {'value': active_subscriptions, 'change': self._calculate_change(active_subscriptions - active_subs_this_month, active_subs_this_month)},
                'stories_created': {'value': total_stories, 'change': self._calculate_change(total_stories - stories_this_month, stories_this_month)},
                'reported_content': {'value': 0, 'change': 0.0}
            },
            'recent_signups': {'count': user_paginator.count, 'num_pages': user_paginator.num_pages, 'current_page': paginated_users.number, 'next': get_next_url(paginated_users, 'user_page'), 'previous': get_previous_url(paginated_users, 'user_page'), 'results': user_serializer.data},
            'recent_stories': {'count': story_paginator.count, 'num_pages': story_paginator.num_pages, 'current_page': paginated_stories.number, 'next': get_next_url(paginated_stories, 'story_page'), 'previous': get_previous_url(paginated_stories, 'story_page'), 'results': story_serializer.data}
        }
        cache.set(cache_key, data, timeout=900)
        return Response(data)
    def _calculate_change(self, old, new):
        if old <= 0: return 100.0 if new > 0 else 0.0
        return round(((new - old) / old) * 100, 2)

class SubscriptionManagementView(generics.ListAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = SubscriptionManagementSerializer
    queryset = Subscription.objects.select_related('user', 'user__profile').order_by('-id')
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['plan', 'status']
    search_fields = ['user__first_name', 'user__last_name', 'user__email']
    def _calculate_change(self, old, new):
        if old <= 0: return 100.0 if new > 0 else 0.0
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
        expiring_this_week = all_subscriptions.filter(status='trialing', trial_end__lte=now + timedelta(days=7), trial_end__gte=now).count()
        canceled_subscriptions = all_subscriptions.filter(status='canceled').count()
        canceled_last_30 = all_subscriptions.filter(canceled_at__gte=last_30_days_start).count()
        canceled_prev_30 = all_subscriptions.filter(canceled_at__gte=prev_30_days_start, canceled_at__lt=last_30_days_start).count()
        canceled_subscriptions_change = self._calculate_change(canceled_prev_30, canceled_last_30)
        stats = {'total_subscribers': {'value': total_subscribers, 'change': total_subscribers_change}, 'trials_active': {'value': trials_active, 'expiring_this_week': expiring_this_week}, 'canceled_subscriptions': {'value': canceled_subscriptions, 'change': canceled_subscriptions_change}}
        paginated_response = super().list(request, *args, **kwargs)
        return Response({'stats': stats, **paginated_response.data})

class AnalyticsAPIView(APIView):
    permission_classes = [IsAdminUser]
    def get(self, request):
        now = timezone.now()
        one_year_ago = now - timedelta(days=365)
        user_growth_query = User.objects.filter(date_joined__gte=one_year_ago).annotate(month=TruncMonth('date_joined')).values('month').annotate(count=Count('id')).order_by('month')
        user_growth_map = {item['month'].month: item['count'] for item in user_growth_query}
        user_growth_data = [{"month": datetime(now.year, m, 1).strftime('%b'), "count": user_growth_map.get(m, 0)} for m in range(1, 13)]
        stories_by_month_query = StoryProject.objects.filter(created_at__gte=one_year_ago).annotate(month=TruncMonth('created_at')).values('month').annotate(count=Count('id')).order_by('month')
        stories_by_month_map = {item['month'].month: item['count'] for item in stories_by_month_query}
        stories_by_month_data = [{"month": datetime(now.year, m, 1).strftime('%b'), "count": stories_by_month_map.get(m, 0)} for m in range(1, 13)]
        top_stories_query = StoryProject.objects.order_by('-read_count', '-likes_count')[:5].values('theme', 'read_count', 'likes_count', 'shares_count', 'tags', 'audio_duration_seconds')
        top_stories_data = []
        for story in top_stories_query:
            minutes = round((story.get('audio_duration_seconds') or 0) / 60)
            top_stories_data.append({"theme": story.get('theme'), "read_count": story.get('read_count'), "likes_count": story.get('likes_count'), "shares_count": story.get('shares_count'), "tags": story.get('tags'), "reading_time": f"{minutes} min" if story.get('audio_duration_seconds') else "N/A"})
        return Response({'user_growth_over_time': user_growth_data, 'stories_created_over_time': stories_by_month_data, 'top_performing_stories': top_stories_data})

class SiteSettingsView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = SiteSettingsSerializer
    def get_object(self): return SiteSettings.load()
    def get(self, request, *args, **kwargs): return Response(self.get_serializer(self.get_object()).data)
    def put(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_object(), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

class TimezoneListView(APIView):
    permission_classes = [IsAdminUser]
    def get(self, request): return Response(pytz.all_timezones)

class LanguageListView(APIView):
    permission_classes = [IsAdminUser]
    def get(self, request):
        languages = [{"code": code, "name": str(name)} for code, name in settings.LANGUAGES]
        return Response(languages)

class AdminProfileView(APIView):
    permission_classes = [IsAdminUser]
    parser_classes = [MultiPartParser, FormParser, JSONParser] 

    def get(self, request):
        user = User.objects.select_related('profile').get(id=request.user.id)
        UserProfile.objects.get_or_create(user=user)
        user = User.objects.select_related('profile').get(id=request.user.id)
        serializer = AdminProfileSerializer(user)
        return Response(serializer.data)

    def put(self, request):
        user = request.user

        try:
            if 'new_password' in request.data:
                services.change_admin_password(user, data=request.data, context={'request': request})

            services.update_admin_profile(user, data=request.data, context={'request': request})

        except ValidationError as e:
            return Response(e.detail, status=status.HTTP_400_BAD_REQUEST)

        updated_user = User.objects.select_related('profile').get(id=user.id)

        final_serializer = AdminProfileSerializer(updated_user)
        return Response(final_serializer.data, status=status.HTTP_200_OK)


class UserManagementViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAdminUser]
    serializer_class = DashboardUserSerializer
    queryset = User.objects.select_related('profile', 'subscription').order_by('-date_joined')
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['is_active']
    search_fields = ['first_name', 'last_name', 'email', 'username']

    @action(detail=True, methods=['post'], url_path='approve')
    def approve_user(self, request, pk=None):
        user = self.get_object()
        if user.is_active:
            return Response({'detail': _('User is already active.')}, status=status.HTTP_400_BAD_REQUEST)

        user.is_active = True
        user.save()

        html_message = render_to_string('emails/account_approved_email.html', {'username': user.username, 'login_url': f"{settings.FRONTEND_URL}/login"})
        plain_message = _("Congratulations! Your MagicTale account has been approved. You can now log in at {url}").format(url=f"{settings.FRONTEND_URL}/login")
        send_email(_('Your MagicTale Account is Approved!'), plain_message, [user.email], html_message=html_message)

        return Response({'status': _('User approved and notified successfully.')}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='deny')
    def deny_user(self, request, pk=None):
        user = self.get_object()
        email = user.email
        user.delete()

        send_email(_('MagicTale Account Application Update'), _('We regret to inform you that your account application was not approved at this time.'), [email])

        return Response({'status': _('User {email} has been denied and deleted.').format(email=email)}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='deactivate')
    def deactivate_user(self, request, pk=None):
        user = self.get_object()
        user.is_active = False
        user.save()
        OutstandingToken.objects.filter(user=user).delete()
        return Response({'status': _('User has been deactivated.')}, status=status.HTTP_200_OK)