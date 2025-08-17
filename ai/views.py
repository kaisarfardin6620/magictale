from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.utils import timezone
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from .models import StoryProject
from .serializers import (
    StoryProjectCreateSerializer,
    StoryProjectDetailSerializer,
)
from .engine import run_generation_async  

class IsOwner(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        return getattr(obj, "user_id", None) == request.user.id

class StoryProjectViewSet(viewsets.ModelViewSet):
    queryset = StoryProject.objects.all()
    permission_classes = [permissions.IsAuthenticated, IsOwner]

    def get_queryset(self):
        return StoryProject.objects.filter(user=self.request.user).order_by("-created_at")

    def get_serializer_class(self):
        if self.action in ["create"]:
            return StoryProjectCreateSerializer
        return StoryProjectDetailSerializer

    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        project = get_object_or_404(self.get_queryset(), pk=pk)
        if project.status not in ("pending", "failed", "canceled"):
            return Response({"detail": "Already started or finished."}, status=400)

        project.status = StoryProject.Status.RUNNING
        project.started_at = timezone.now()
        project.progress = 1
        project.save(update_fields=["status","started_at","progress"])

        async_to_sync(run_generation_async)(project.id)  
        return Response({"detail": "Generation started."}, status=202)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        project = get_object_or_404(self.get_queryset(), pk=pk)
        if project.status == StoryProject.Status.RUNNING:
            project.status = StoryProject.Status.CANCELED
            project.save(update_fields=["status"])
            layer = get_channel_layer()
            async_to_sync(layer.group_send)(f"story_{project.id}", {"type": "progress", "event": {"progress": project.progress, "status": "canceled"}})
        return Response({"detail": "Canceled (if it was running)."})
