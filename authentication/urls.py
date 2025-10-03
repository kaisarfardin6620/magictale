from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    SignupAPIView,
    EmailVerificationAPIView,
    ResendVerificationEmailAPIView,
    MyTokenObtainPairView,
    PasswordResetInitiateAPIView,
    PasswordResetConfirmView,  
    ProfileView,
    UserActivityLogAPIView,
    DeleteAccountView,
    LanguagePreferenceView,
    GoogleLoginView,
    UserLanguageListView, 
)

urlpatterns = [
    path('signup/', SignupAPIView.as_view(), name='signup'),
    path('login/', MyTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('login/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('delete-account/', DeleteAccountView.as_view(), name='delete_account'),
    path('email-verify/', EmailVerificationAPIView.as_view(), name='email_verification'),
    path('resend-verification/', ResendVerificationEmailAPIView.as_view(), name='resend_verification'),
    path('password-reset/', PasswordResetInitiateAPIView.as_view(), name='password_reset_initiate'),
    path('password-reset/confirm/<uuid:token>/', PasswordResetConfirmView.as_view(), name='password_reset_confirm'),
    path('profile/', ProfileView.as_view(), name='profile'),
    path('languages/', UserLanguageListView.as_view(), name='user-language-list'),
    path('profile/language/', LanguagePreferenceView.as_view(), name='language-preference'),
    path('activity-log/', UserActivityLogAPIView.as_view(), name='activity_log'),
    path('google/', GoogleLoginView.as_view(), name='google_login'),
]

