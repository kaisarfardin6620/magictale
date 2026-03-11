from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Notification
from .serializers import NotificationSerializer
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiResponse
from drf_spectacular.types import OpenApiTypes

@extend_schema(
    parameters=[OpenApiParameter("id", OpenApiTypes.INT, OpenApiParameter.PATH, description="ID of the notification")]
)
class NotificationViewSet(viewsets.ModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ['get', 'post', 'delete']
    lookup_url_kwarg = 'id'

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user).select_related('user')

    @extend_schema(
        parameters=[OpenApiParameter("id", OpenApiTypes.INT, OpenApiParameter.PATH, description="ID of the notification")],
        request=None,
        responses={204: OpenApiResponse(description="Notification marked as read")}
    )
    @action(detail=True, methods=['post'], url_path='mark-read')
    def mark_as_read(self, request, pk=None):
        notification = self.get_object()
        notification.read = True
        notification.save(update_fields=['read'])
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=['post'], url_path='mark-all-read')
    def mark_all_as_read(self, request):
        self.get_queryset().update(read=True)
        return Response(status=status.HTTP_204_NO_CONTENT)