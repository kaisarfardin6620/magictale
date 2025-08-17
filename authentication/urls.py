# urls.py
from django.urls import path
from rest_framework_simplejwt.views import (
    TokenRefreshView,
    TokenVerifyView,
)
from .views import (
    MyTokenObtainPairView,
    SignupAPIView,
    EmailVerificationAPIView,
    ResendVerificationEmailAPIView,
    PasswordResetRequestAPIView,
    PasswordResetConfirmAPIView,
    ChangePasswordAPIView,
    ProfileView,
    DeleteAccountView,
    ProfilePictureView,
    UserActivityLogAPIView,
    EmailChangeRequestAPIView,
    EmailChangeConfirmAPIView,
    FullNameUpdateAPIView
)

urlpatterns = [
    # JWT authentication paths
    path('token/', MyTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('token/verify/', TokenVerifyView.as_view(), name='token_verify'),

    # User signup and verification
    path('signup/', SignupAPIView.as_view(), name='signup'),
    path('verify-email/', EmailVerificationAPIView.as_view(), name='email_verification'),
    path('verify-email/resend/', ResendVerificationEmailAPIView.as_view(), name='resend_verification_email'),

    # Password and profile management
    path('password/change/', ChangePasswordAPIView.as_view(), name='password_change'),
    path('password/reset/', PasswordResetRequestAPIView.as_view(), name='password_reset_request'),
    path('password/reset/confirm/', PasswordResetConfirmAPIView.as_view(), name='password_reset_confirm'),

    # Profile management
    path('profile/', ProfileView.as_view(), name='user_profile'),
    path('profile/picture/', ProfilePictureView.as_view(), name='profile_picture'),
    path('profile/activity-log/', UserActivityLogAPIView.as_view(), name='user_activity_log'),
    path('profile/delete/', DeleteAccountView.as_view(), name='delete_account'),
    path('profile/update-full-name/', FullNameUpdateAPIView.as_view(), name='full_name_update'), # Added missing URL path

    # Email change
    path('email/change/request/', EmailChangeRequestAPIView.as_view(), name='email_change_request'),
    path('email/change/confirm/', EmailChangeConfirmAPIView.as_view(), name='email_change_confirm'),
]