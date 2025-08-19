# ai/views.py

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
from .tasks import run_generation_task # Make sure this import is here
from authentication.permissions import HasActiveSubscription


class IsOwner(permissions.BasePermission):
    """
    Custom permission to only allow owners of an object to edit it.
    """
    def has_object_permission(self, request, view, obj):
        return getattr(obj, "user", None) == request.user

class StoryProjectViewSet(viewsets.ModelViewSet):
    """
    A ViewSet for viewing, creating, and managing story projects.
    """
    queryset = StoryProject.objects.all()
    serializer_class = StoryProjectDetailSerializer
    
    # === STEP 2: ADD THE SUBSCRIPTION PERMISSION TO THE VIEWSET ===
    # Now, all actions in this ViewSet require an active subscription.
    permission_classes = [permissions.IsAuthenticated, IsOwner, HasActiveSubscription]

    def get_queryset(self):
        """
        This view should return a list of all the story projects
        for the currently authenticated user.
        """
        return self.queryset.filter(user=self.request.user).order_by("-created_at")

    def get_serializer_class(self):
        """
        Return the appropriate serializer class based on the action.
        For creating a new project, we use a simpler serializer.
        For all other actions, we use the default detailed serializer.
        """
        if self.action == "create":
            return StoryProjectCreateSerializer
        return super().get_serializer_class()

    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        """
        Custom action to start the AI generation for a story project.
        """
        # === STEP 3: REMOVE THE MANUAL SUBSCRIPTION CHECK ===
        # The HasActiveSubscription permission class now handles this for the entire view.
        # This makes the code much cleaner.

        project = self.get_object() # Use get_object() which handles 404s for you
        if project.status not in ("pending", "failed", "canceled"):
            return Response({"detail": "This story has already been started or is complete."}, status=status.HTTP_400_BAD_REQUEST)

        project.status = StoryProject.Status.RUNNING
        project.started_at = timezone.now()
        project.progress = 1
        project.save(update_fields=["status", "started_at", "progress"])

        # This now only runs if the subscription check passes
        async_to_sync(run_generation_async)(project.id)
        
        return Response({"detail": "Story generation has started."}, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        """
        Custom action to cancel a running story generation.
        """
        project = self.get_object()
        if project.status == StoryProject.Status.RUNNING:
            project.status = StoryProject.Status.CANCELED
            project.save(update_fields=["status"])
            
            # Send a real-time update to the client
            layer = get_channel_layer()
            async_to_sync(layer.group_send)(
                f"story_{project.id}", 
                {"type": "progress", "event": {"progress": project.progress, "status": "canceled"}}
            )
        return Response({"detail": "Cancellation request sent."}, status=status.HTTP_200_OK)


class StoryProjectViewSet(viewsets.ModelViewSet):
    # ...
    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        # ... your existing logic to get the project and update its status ...
        
        # This is the line that sends the job to the background worker
        run_generation_task.delay(project.id)
        
        return Response({"detail": "Story generation has started."}, status=status.HTTP_202_ACCEPTED)    