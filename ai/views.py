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
    # The default queryset for the ViewSet
    queryset = StoryProject.objects.all()
    
    # === FIX: Added the default serializer_class attribute ===
    # This is required by ModelViewSet and will be used for actions like
    # list, retrieve, update, etc.
    serializer_class = StoryProjectDetailSerializer
    
    # The permission classes control who can access the view
    permission_classes = [permissions.IsAuthenticated, IsOwner]

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
        # For 'list', 'retrieve', 'update', 'partial_update', 'destroy',
        # it will fall back to the default serializer_class defined above.
        return super().get_serializer_class()

    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        """
        Custom action to start the AI generation for a story project.
        """
        # === SUBSCRIPTION CHECK GATE ===
        try:
            subscription = request.user.subscription
            if subscription.status not in ['active', 'trialing']:
                return Response(
                    {"detail": "An active subscription is required to generate stories."},
                    status=status.HTTP_403_FORBIDDEN
                )
        except AttributeError: # Catches if user.subscription doesn't exist
            return Response(
                {"detail": "You do not have a subscription."},
                status=status.HTTP_403_FORBIDDEN
            )
        # === END OF CHECK ===

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