from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.shortcuts import get_object_or_404
from .models import UserReport, LegalDocument
from .serializers import UserReportSerializer, LegalDocumentSerializer
from rest_framework.permissions import IsAdminUser

class UserReportViewSet(viewsets.ModelViewSet):
    queryset = UserReport.objects.all().order_by('-created_at')
    serializer_class = UserReportSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_permissions(self):
        if self.action in ['list', 'retrieve', 'resolve']:
            return [permissions.IsAuthenticated(), IsAdminUser()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        user = self.request.user
        if user.is_staff or user.is_superuser:
            return UserReport.objects.select_related('user').order_by('-created_at')
        return UserReport.objects.filter(user=user).order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=True, methods=['post'], url_path='resolve')
    def resolve(self, request, pk=None):
        report = self.get_object()
        report.is_resolved = True
        report.save()
        return Response({'status': 'Report marked as resolved'}, status=status.HTTP_200_OK)

class LegalDocumentView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, doc_type):
        document = get_object_or_404(LegalDocument, doc_type=doc_type)
        serializer = LegalDocumentSerializer(document)
        return Response(serializer.data)

class AdminLegalDocumentView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdminUser]

    def post(self, request):
        doc_type = request.data.get('doc_type')
        
        if doc_type not in ['privacy_policy', 'terms_conditions']:
            return Response(
                {"error": "Invalid doc_type. Must be 'privacy_policy' or 'terms_conditions'."}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            document = LegalDocument.objects.get(doc_type=doc_type)
            serializer = LegalDocumentSerializer(document, data=request.data, partial=True)
        except LegalDocument.DoesNotExist:
            serializer = LegalDocumentSerializer(data=request.data)

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)