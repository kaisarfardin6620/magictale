from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import UserReportViewSet, LegalDocumentView, AdminLegalDocumentView

router = DefaultRouter()
router.register(r'reports', UserReportViewSet, basename='user-reports')

urlpatterns = [
    path('', include(router.urls)),
    path('legal/public/<str:doc_type>/', LegalDocumentView.as_view(), name='legal-docs-public'),
    path('legal/manage/', AdminLegalDocumentView.as_view(), name='legal-docs-manage'),
]