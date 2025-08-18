from django.urls import path
from .views import (
    SignupAPIView,
    EmailVerificationAPIView,
    ResendVerificationEmailAPIView,
    MyTokenObtainPairView,
    
    # === UPDATED PASSWORD RESET IMPORTS ===
    PasswordResetInitiateAPIView,   # Renamed from PasswordResetRequestAPIView
    PasswordResetVerifyAPIView,     # The new verification step
    PasswordResetConfirmAPIView,
    # ======================================

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
    # Auth
    path('signup/', SignupAPIView.as_view(), name='signup'),
    path('email-verify/', EmailVerificationAPIView.as_view(), name='email_verification'),
    path('resend-verification/', ResendVerificationEmailAPIView.as_view(), name='resend_verification'),
    path('login/', MyTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('login/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # Password Management
    path('change-password/', ChangePasswordAPIView.as_view(), name='change_password'),
    
    # === NEW PASSWORD RESET URLS ===
    # Step 1: User submits their email to start the process
    path('password-reset/', PasswordResetInitiateAPIView.as_view(), name='password_reset_initiate'),
    # Step 2: User clicks the link in their email, which hits this endpoint
    path('password-reset/verify/', PasswordResetVerifyAPIView.as_view(), name='password_reset_verify'),
    # Step 3: User submits the token from step 2 and their new password
    path('password-reset/confirm/', PasswordResetConfirmAPIView.as_view(), name='password_reset_confirm'),
    # ===============================

    # Profile Management
    path('profile/', ProfileView.as_view(), name='profile'),
    path('profile/full-name/', FullNameUpdateAPIView.as_view(), name='update_full_name'),
    path('profile/picture/', ProfilePictureView.as_view(), name='profile_picture'),
    path('activity-log/', UserActivityLogAPIView.as_view(), name='activity_log'),
    path('delete-account/', DeleteAccountView.as_view(), name='delete_account'),

    # Email Change
    path('email-change/', EmailChangeRequestAPIView.as_view(), name='email_change_request'),
    path('email-change/confirm/', EmailChangeConfirmAPIView.as_view(), name='email_change_confirm'),
    path('onboarding/', OnboardingStatusView.as_view(), name='onboarding_status'),
]