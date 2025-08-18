from django.urls import path
from .views import (
    SignupAPIView,
    EmailVerificationAPIView,
    ResendVerificationEmailAPIView,
    MyTokenObtainPairView,
    
    PasswordResetInitiateAPIView,   # Renamed from PasswordResetRequestAPIView
    PasswordResetVerifyAPIView,     # The new verification step
    PasswordResetConfirmAPIView,

    ChangePasswordAPIView,
    ProfileView,
    FullNameUpdateAPIView,
    ProfilePictureView,
    UserActivityLogAPIView,
    DeleteAccountView,
    EmailChangeRequestAPIView,
    EmailChangeConfirmAPIView,
    OnboardingStatusView,
)
from rest_framework_simplejwt.views import TokenRefreshView

urlpatterns = [
    path('signup/', SignupAPIView.as_view(), name='signup'),
    path('email-verify/', EmailVerificationAPIView.as_view(), name='email_verification'),
    path('resend-verification/', ResendVerificationEmailAPIView.as_view(), name='resend_verification'),
    path('login/', MyTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('login/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    path('change-password/', ChangePasswordAPIView.as_view(), name='change_password'),
    path('password-reset/', PasswordResetInitiateAPIView.as_view(), name='password_reset_initiate'),
    path('password-reset/verify/', PasswordResetVerifyAPIView.as_view(), name='password_reset_verify'),
    path('password-reset/confirm/', PasswordResetConfirmAPIView.as_view(), name='password_reset_confirm'),
    
    path('profile/', ProfileView.as_view(), name='profile'),
    path('profile/full-name/', FullNameUpdateAPIView.as_view(), name='update_full_name'),
    path('profile/picture/', ProfilePictureView.as_view(), name='profile_picture'),
    path('activity-log/', UserActivityLogAPIView.as_view(), name='activity_log'),
    path('delete-account/', DeleteAccountView.as_view(), name='delete_account'),

    path('email-change/', EmailChangeRequestAPIView.as_view(), name='email_change_request'),
    path('email-change/confirm/', EmailChangeConfirmAPIView.as_view(), name='email_change_confirm'),
    path('onboarding/', OnboardingStatusView.as_view(), name='onboarding_status'),
]