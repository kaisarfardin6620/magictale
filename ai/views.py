from django.http import HttpResponse
from django.template.loader import render_to_string
from django.db import transaction
from django.utils import timezone
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from weasyprint import HTML
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import StoryProject
from .serializers import (
    StoryProjectCreateSerializer,
    StoryProjectDetailSerializer,
)
from .tasks import run_generation_task
from authentication.permissions import HasActiveSubscription, IsOwner, IsStoryMaster
from django.utils.translation import gettext_lazy as _

class StoryProjectViewSet(viewsets.ModelViewSet):
    queryset = StoryProject.objects.all()
    serializer_class = StoryProjectDetailSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwner, HasActiveSubscription]

    def get_queryset(self):
        queryset = self.queryset.filter(user=self.request.user).order_by("-created_at")

        if self.action == 'list':
            return queryset.filter(is_saved=True)
        
        return queryset

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
        transaction.on_commit(lambda: run_generation_task.delay(project.id))

    def create(self, request, *args, **kwargs):
        story_master_permission = IsStoryMaster()
        if request.data.get('length') == 'long':
            if not story_master_permission.has_permission(request, self):
                return Response({"detail": IsStoryMaster.message}, status=status.HTTP_403_FORBIDDEN)
        
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    @action(detail=False, methods=['get'])
    def latest(self, request):
        latest_story = StoryProject.objects.filter(user=request.user).order_by('-created_at').first()
        if not latest_story:
            return Response({"detail": _("No stories found for this user.")}, status=status.HTTP_404_NOT_FOUND)
        
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
        return Response({"message": _("Cancellation request processed.")}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='save-to-library')
    def save_to_library(self, request, pk=None):
        project = self.get_object()
        if project.status != StoryProject.Status.DONE:
            return Response({"detail": _("This story cannot be saved as it is not complete.")}, status=status.HTTP_400_BAD_REQUEST)
        project.is_saved = True
        project.save(update_fields=['is_saved'])
        return Response({"message": _("Story successfully saved to your library.")}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'], url_path='download-pdf')
    def download_pdf(self, request, pk=None):
        story_master_permission = IsStoryMaster()
        if not story_master_permission.has_permission(request, self):
            return Response({"detail": IsStoryMaster.message}, status=status.HTTP_403_FORBIDDEN)
        
        project = self.get_object()
        if project.status != StoryProject.Status.DONE:
            return Response({"detail": _("Cannot generate PDF. Story is not yet complete.")}, status=status.HTTP_400_BAD_REQUEST)
        
        context = {"project": project}
        html_string = render_to_string("ai/story_pdf_template.html", context)
        pdf_file = HTML(string=html_string).write_pdf()
        
        response = HttpResponse(pdf_file, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{project.child_name}_story.pdf"'
        return response