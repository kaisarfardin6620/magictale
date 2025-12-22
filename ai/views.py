from django.db import transaction
from django.db.models import F, Count
from django.utils import timezone
from asgiref.sync import async_to_sync
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied, NotFound, ValidationError
from rest_framework.views import APIView
from django.conf import settings
from django.contrib.staticfiles.storage import staticfiles_storage
from django.utils.translation import gettext as _
from django.core.cache import cache
from .tasks import start_story_generation_pipeline, generate_pdf_task, start_story_remix_pipeline
from .models import StoryProject
from .serializers import (
    StoryProjectCreateSerializer,
    StoryProjectDetailSerializer,
    StoryProjectListSerializer,
)
from authentication.permissions import HasActiveSubscription, IsOwner, IsStoryMaster
from .throttling import SubscriptionBasedThrottle
from notifications.tasks import create_and_send_notification_task

class StoryProjectViewSet(viewsets.ModelViewSet):
    queryset = StoryProject.objects.all() 
    serializer_class = StoryProjectDetailSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwner, HasActiveSubscription]
    throttle_classes = [SubscriptionBasedThrottle]

    def get_queryset(self):
        queryset = (
            super().get_queryset()
            .filter(user=self.request.user)
            .select_related('user', 'onboarding') 
            .prefetch_related('variants')
            .annotate(page_count_annotated=Count('pages'))
            .order_by("-created_at")
        )
        if self.action == 'list':
            return queryset.filter(is_saved=True)
        return queryset

    def get_serializer_class(self):
        if self.action == "create":
            return StoryProjectCreateSerializer
        if self.action == "list":
            return StoryProjectListSerializer
        return super().get_serializer_class()

    def perform_create(self, serializer):
        project = serializer.save()
        project.status = StoryProject.Status.RUNNING
        project.started_at = timezone.now()
        project.progress = 1
        project.error = ""
        project.save(update_fields=["status", "started_at", "progress", "error"])
        transaction.on_commit(lambda: start_story_generation_pipeline(project.id))

    def retrieve(self, request, *args, **kwargs):
        pk = kwargs.get('pk')
        if not pk or not pk.isdigit():
            raise NotFound(_("Invalid Story ID."))
        
        instance = self.get_object()
        instance.read_count = F('read_count') + 1
        instance.save(update_fields=['read_count'])
        
        return super().retrieve(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        story_master_permission = IsStoryMaster()
        if request.data.get('length') == 'long':
            if not story_master_permission.has_permission(request, self):
                raise PermissionDenied(_(IsStoryMaster.message))
        
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        create_and_send_notification_task.delay(
            request.user.id,
            "We're Building Your Story!",
            "Your magical adventure is now being created."
        )
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_202_ACCEPTED, headers=headers)

    @action(detail=False, methods=['get'])
    def latest(self, request):
        latest_story = StoryProject.objects.filter(user=request.user, parent_project__isnull=True).select_related('user').order_by('-created_at').first()
        if not latest_story:
            raise NotFound(_("No stories found for this user."))
        
        serializer = self.get_serializer(latest_story)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def choices(self, request, pk=None):
        project = self.get_object()
        theme_id = project.theme
        
        theme_data = settings.ALL_THEMES_DATA.get(theme_id)
        if not theme_data:
            raise NotFound(_("Choices for this story's theme could not be found."))
            
        choices_with_urls = []
        for choice in theme_data['choices']:
            choices_with_urls.append({
                "id": choice['id'],
                "name": choice['name'],
                "description": choice['description'],
                "image_url": request.build_absolute_uri(staticfiles_storage.url(f"images/themes/{choice['image_file']}"))})
        return Response(choices_with_urls)

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated, IsOwner, IsStoryMaster])
    def remix(self, request, pk=None):
        project = self.get_object()
        
        if project.status not in [StoryProject.Status.DONE, StoryProject.Status.CANCELED]:
            raise ValidationError(_("This story cannot be remixed while it is still in progress."))
            
        choice_id = request.data.get('choice_id')
        if not choice_id:
            raise ValidationError({"choice_id": _("A choice_id must be provided.")})

        if not any(choice['id'] == choice_id for theme in settings.ALL_THEMES_DATA.values() for choice in theme['choices']):
            raise ValidationError({"choice_id": _("The provided choice is invalid.")})

        project.status = StoryProject.Status.RUNNING
        project.progress = 1
        project.error = ""
        project.finished_at = None
        project.save(update_fields=["status", "progress", "error", "finished_at"])
        
        transaction.on_commit(lambda: start_story_remix_pipeline(project.id, choice_id))
        
        serializer = self.get_serializer(project)
        return Response(serializer.data, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        project = self.get_object()
        if project.status == StoryProject.Status.RUNNING:
            project.status = StoryProject.Status.CANCELED
            project.save(update_fields=["status"])
            from channels.layers import get_channel_layer
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
        
        return Response({"message": _("Story saved to library.")}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='download-pdf')
    def download_pdf(self, request, pk=None):
        story_master_permission = IsStoryMaster()
        if not story_master_permission.has_permission(request, self):
            raise PermissionDenied(_(IsStoryMaster.message))
        
        project = self.get_object()
        if project.status != StoryProject.Status.DONE:
            raise ValidationError(_("Cannot generate PDF. Story is not yet complete."))
        base_url = request.build_absolute_uri('/')[:-1]
        generate_pdf_task.delay(project.id, base_url)
        
        return Response(
            {"message": _("Your PDF is being generated. You will be notified when it is ready.")},
            status=status.HTTP_202_ACCEPTED
        )

class GenerationOptionsView(APIView):
    permission_classes = [permissions.IsAuthenticated, HasActiveSubscription]

    def get(self, request):
        cache_key = "generation_options_all_v3" 
        cached_data = cache.get(cache_key)

        if cached_data:
            return Response(cached_data, status=status.HTTP_200_OK)

        themes_response = [
            {
                "id": theme_id, 
                "name": theme_data["name"],
                "description": theme_data["choices"][0]["description"] if theme_data.get("choices") else theme_data["name"]
            }
            for theme_id, theme_data in settings.ALL_THEMES_DATA.items()
        ]
        
        art_styles_response = []
        for style in settings.ALL_ART_STYLES_DATA:
            image_path = staticfiles_storage.url(f"images/art_styles/{style['image_file']}")
            if not image_path.startswith("http"):
                full_url = f"{settings.BACKEND_BASE_URL}{image_path}"
            else:
                full_url = image_path

            art_styles_response.append({
                "id": style['id'],
                "name": style['name'],
                "description": style['description'],
                "image_url": full_url
            })

        voices_response = [
            {"id": voice_id, "name": name}
            for voice_id, name in settings.ELEVENLABS_VOICE_MAP.items()
        ]
        
        response_data = {
            "themes": themes_response,
            "art_styles": art_styles_response,
            "narrator_voices": voices_response,
        }

        cache.set(cache_key, response_data, timeout=3600)

        return Response(response_data, status=status.HTTP_200_OK)