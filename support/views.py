from rest_framework import viewsets, permissions
from .models import FAQItem
from .serializers import FAQItemSerializer

class FAQViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = FAQItem.objects.all()
    serializer_class = FAQItemSerializer
    permission_classes = [permissions.IsAuthenticated] 
    