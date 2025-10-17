from django.db import transaction
from django.utils import timezone
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied, NotFound, ValidationError
from rest_framework.views import APIView
from django.conf import settings
from django.contrib.staticfiles.storage import staticfiles_storage
from django.utils.translation import gettext_lazy as _
from rest_framework.throttling import ScopedRateThrottle
from django.core.cache import cache
from .tasks import start_story_generation_pipeline, generate_pdf_task
from .models import StoryProject
from .serializers import (
    StoryProjectCreateSerializer,
    StoryProjectDetailSerializer,
)
from authentication.permissions import HasActiveSubscription, IsOwner, IsStoryMaster

class StoryProjectViewSet(viewsets.ModelViewSet):
    queryset = StoryProject.objects.all() 
    serializer_class = StoryProjectDetailSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwner, HasActiveSubscription]
    throttle_classes = [ScopedRateThrottle]

    def get_queryset(self):
        queryset = (
            super().get_queryset()
            .filter(user=self.request.user)
            .select_related('user') 
            .order_by("-created_at")
        )
        if self.action == 'list':
            return queryset.filter(is_saved=True)
        return queryset

    def get_throttles(self):
        if self.action == 'create':
            self.throttle_scope = 'story_creation'
        return super().get_throttles()

    def get_serializer_class(self):
        if self.action == "create":
            return StoryProjectCreateSerializer
        return super().get_serializer_class()

    def perform_create(self, serializer):
        project = serializer.save()
        project.status = StoryProject.Status.RUNNING
        project.started_at = timezone.now()
        project.progress = 1
        project.error = ""
        project.save(update_fields=["status", "started_at", "progress", "error"])
        transaction.on_commit(lambda: start_story_generation_pipeline(project.id))

    def create(self, request, *args, **kwargs):
        story_master_permission = IsStoryMaster()
        if request.data.get('length') == 'long':
            if not story_master_permission.has_permission(request, self):
                raise PermissionDenied(IsStoryMaster.message)
        
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_202_ACCEPTED, headers=headers)

    @action(detail=False, methods=['get'])
    def latest(self, request):
        latest_story = StoryProject.objects.filter(user=request.user).select_related('user').order_by('-created_at').first()
        if not latest_story:
            raise NotFound(_("No stories found for this user."))
        
        serializer = self.get_serializer(latest_story)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        project = self.get_object()
        if project.status == StoryProject.Status.RUNNING:
            project.status = StoryProject.Status.CANCELED
            project.save(update_fields=["status"])
            layer = get_channel_layer()
            async_to_sync(layer.group_send)(
                f"story_{project.id}",
                {"type": "progress", "event": {"progress": project.progress, "status": "canceled"}}
            )
        serializer = self.get_serializer(project)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='save-to-library')
    def save_to_library(self, request, pk=None):
        project = self.get_object()
        if project.status != StoryProject.Status.DONE:
            raise ValidationError(_("This story cannot be saved as it is not complete."))
        project.is_saved = True
        project.save(update_fields=['is_saved'])
        serializer = self.get_serializer(project)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='download-pdf')
    def download_pdf(self, request, pk=None):
        story_master_permission = IsStoryMaster()
        if not story_master_permission.has_permission(request, self):
            raise PermissionDenied(IsStoryMaster.message)
        
        project = self.get_object()
        if project.status != StoryProject.Status.DONE:
            raise ValidationError(_("Cannot generate PDF. Story is not yet complete."))
        
        generate_pdf_task.delay(project.id)
        
        return Response(
            {"message": _("Your PDF is being generated. You will be notified when it is ready.")},
            status=status.HTTP_202_ACCEPTED
        )

class GenerationOptionsView(APIView):
    permission_classes = [permissions.IsAuthenticated, HasActiveSubscription]

    def get(self, request):
        user = request.user
        
        try:
            plan_key = f"{user.subscription.plan}_{user.subscription.status}"
        except (AttributeError, user.subscription.RelatedObjectDoesNotExist):
            plan_key = "default"
        
        cache_key = f"generation_options_{plan_key}"
        cached_data = cache.get(cache_key)

        if cached_data:
            return Response(cached_data, status=status.HTTP_200_OK)

        try:
            subscription = user.subscription
        except (AttributeError, user.subscription.RelatedObjectDoesNotExist):
            subscription = type('obj', (object,), {'plan': 'creator', 'status': 'trialing'})()

        themes = settings.ALL_THEMES

        is_master_plan = subscription.plan == 'master' and subscription.status == 'active'

        allowed_style_names = settings.ALL_ART_STYLES if is_master_plan else settings.TIER_1_ART_STYLES
        art_styles = [
            {
                "name": name,
                "image_url": request.build_absolute_uri(
                    staticfiles_storage.url(f"images/art_styles/{settings.ALL_ART_STYLES_DATA[name]}")
                )
            } for name in allowed_style_names
        ]

        allowed_voice_ids = settings.ALL_NARRATOR_VOICES if is_master_plan else settings.TIER_1_NARRATOR_VOICES

        voices = [
            {"id": voice_id, "name": settings.ELEVENLABS_VOICE_MAP.get(voice_id, "Unknown")}
            for voice_id in allowed_voice_ids
        ]

        response_data = {
            "themes": themes,
            "art_styles": art_styles,
            "narrator_voices": voices,
        }

        cache.set(cache_key, response_data, timeout=3600)

        return Response(response_data, status=status.HTTP_200_OK)