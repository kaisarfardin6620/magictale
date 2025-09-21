from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import HttpResponse

def index(request):
    return HttpResponse("Welcome to the MagicTale API!")

urlpatterns = [
    path('', index),
    path('admin/', admin.site.urls),
    path('api/auth/', include('authentication.urls')),
    path("api/ai/", include("ai.urls")),
    path("api/subscriptions/", include("subscription.urls")),
    path("api/support/", include("support.urls")),
    path('accounts/', include('allauth.urls')),
]


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)