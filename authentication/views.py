# authentication/views.py

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth.hashers import check_password
from django.urls import reverse
from django.shortcuts import render
from django.template.loader import render_to_string
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken

# === IMPORT HELPERS FROM THE NEW UTILS FILE ===
from .utils import get_client_ip, send_email
# ============================================

from .models import AuthToken, UserProfile, PasswordHistory, UserActivityLog, OnboardingStatus
from .permissions import HasActiveSubscription
from .serializers import (
    SignupSerializer, PasswordResetRequestSerializer, PasswordResetConfirmSerializer,
    ProfileSerializer, ResendVerificationSerializer, MyTokenObtainPairSerializer,
    UserActivityLogSerializer, EmailChangeConfirmSerializer, LanguagePreferenceSerializer,
    OnboardingStatusSerializer, UnifiedProfileUpdateSerializer
)

# --- API Views ---

class MyTokenObtainPairView(TokenObtainPairView):
    serializer_class = MyTokenObtainPairSerializer

class SignupAPIView(APIView):
    permission_classes = [AllowAny]
    def post(self, request):
        serializer = SignupSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            UserActivityLog.objects.create(user=user, activity_type='signup', ip_address=get_client_ip(request))
            token = AuthToken.objects.create(user=user, token_type='email_verification')
            verification_url = request.build_absolute_uri(reverse('email_verification') + f'?token={token.token}')

            html_message = render_to_string('emails/signup_verification_email.html', {'username': user.username, 'verification_url': verification_url})
            plain_message = f'Please click the link to verify your email: {verification_url}'
            send_email('Verify your email for MagicTale', plain_message, [user.email], html_message=html_message)

            return Response({"message": "User created successfully. Please check your email for verification."}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class EmailVerificationAPIView(APIView):
    permission_classes = [AllowAny]
    def get(self, request):
        token_uuid = request.GET.get('token')
        context = {'home_url': settings.FRONTEND_URL, 'login_url': f"{settings.FRONTEND_URL}/login"}
        if not token_uuid:
            context['error_message'] = 'No verification token was provided.'
            return render(request, 'verification/verification_error.html', context, status=status.HTTP_400_BAD_REQUEST)
        try:
            token = AuthToken.objects.get(token=token_uuid, token_type='email_verification')
            if not token.is_valid():
                context['error_message'] = 'This verification link is invalid or has expired.'
                return render(request, 'verification/verification_error.html', context, status=status.HTTP_400_BAD_REQUEST)

            user = token.user
            user.is_active = True
            user.save()
            token.is_used = True
            token.save()
            UserActivityLog.objects.create(user=user, activity_type='email_verification_success', ip_address=get_client_ip(request))

            context.update({'title': 'Account Verified!', 'message': 'Your account is now active.'})
            return render(request, 'verification/verification_success.html', context)
        except AuthToken.DoesNotExist:
            context['error_message'] = 'This verification link is invalid or has expired.'
            return render(request, 'verification/verification_error.html', context, status=status.HTTP_400_BAD_REQUEST)

class ResendVerificationEmailAPIView(APIView):
    permission_classes = [AllowAny]
    def post(self, request):
        serializer = ResendVerificationSerializer(data=request.data)
        if serializer.is_valid():
            try:
                user = User.objects.get(username=serializer.validated_data['username'])
                if user.is_active:
                    return Response({'detail': 'This account is already active.'}, status=status.HTTP_400_BAD_REQUEST)

                AuthToken.objects.filter(user=user, token_type='email_verification', is_used=False).delete()
                token = AuthToken.objects.create(user=user, token_type='email_verification')
                verification_url = request.build_absolute_uri(reverse('email_verification') + f'?token={token.token}')
                html_message = render_to_string('emails/signup_verification_email.html', {'username': user.username, 'verification_url': verification_url})
                send_email('Verify your email', f'Link: {verification_url}', [user.email], html_message=html_message)

                return Response({"message": "Verification email has been resent."}, status=status.HTTP_200_OK)
            except User.DoesNotExist:
                return Response({'detail': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            profile = UserProfile.objects.get(user=request.user)
            serializer = ProfileSerializer(profile)
            user_data = {
                'first_name': request.user.first_name,
                'last_name': request.user.last_name,
                'email': request.user.email,
            }
            response_data = {**user_data, **serializer.data}
            return Response(response_data, status=status.HTTP_200_OK)
        except UserProfile.DoesNotExist:
            return Response({'detail': 'User profile not found.'}, status=status.HTTP_404_NOT_FOUND)

    def put(self, request):
        try:
            profile = UserProfile.objects.get(user=request.user)
            serializer = UnifiedProfileUpdateSerializer(
                instance=profile,
                data=request.data,
                context={'request': request},
                partial=True
            )
            if serializer.is_valid():
                serializer.save()
                return Response({'message': 'Profile updated successfully.'}, status=status.HTTP_200_OK)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except UserProfile.DoesNotExist:
            return Response({'detail': 'User profile not found.'}, status=status.HTTP_404_NOT_FOUND)

class EmailChangeConfirmAPIView(APIView):
    permission_classes = [AllowAny]
    def get(self, request):
        serializer = EmailChangeConfirmSerializer(data=request.query_params)
        context = {'home_url': settings.FRONTEND_URL, 'login_url': f"{settings.FRONTEND_URL}/login"}
        if not serializer.is_valid():
            context['error_message'] = 'A valid confirmation token is required.'
            return render(request, 'verification/verification_error.html', context, status=status.HTTP_400_BAD_REQUEST)
        try:
            token = AuthToken.objects.get(token=serializer.validated_data.get('token'), token_type='email_change', is_used=False)
            if not token.is_valid():
                context['error_message'] = 'This confirmation link is invalid or has expired.'
                return render(request, 'verification/verification_error.html', context, status=status.HTTP_400_BAD_REQUEST)

            user = token.user
            new_email = token.new_email
            if User.objects.filter(email=new_email).exclude(id=user.id).exists():
                context['error_message'] = 'This email address is already in use by another account.'
                return render(request, 'verification/verification_error.html', context, status=status.HTTP_400_BAD_REQUEST)

            user.email = new_email
            user.save()
            token.is_used = True
            token.save()
            context.update({'title': 'Email Changed Successfully!', 'message': 'Your email address has been updated.'})
            return render(request, 'verification/verification_success.html', context)
        except AuthToken.DoesNotExist:
            context['error_message'] = 'This confirmation link is invalid or has expired.'
            return render(request, 'verification/verification_error.html', context, status=status.HTTP_400_BAD_REQUEST)

class PasswordResetInitiateAPIView(APIView):
    permission_classes = [AllowAny]
    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            try:
                user = User.objects.get(email=email)
                AuthToken.objects.filter(user=user, token_type='password_reset').delete()
                token = AuthToken.objects.create(user=user, token_type='password_reset')
                reset_url = request.build_absolute_uri(reverse('password_reset_verify') + f'?token={token.token}')
                send_email('Password Reset Request', f'Click to reset: {reset_url}', [user.email])
            except User.DoesNotExist:
                pass
        return Response({'message': 'If an account exists, a reset link has been sent.'}, status=status.HTTP_200_OK)

class PasswordResetVerifyAPIView(APIView):
    permission_classes = [AllowAny]
    def get(self, request):
        token = request.query_params.get("token")
        try:
            token_obj = AuthToken.objects.get(token=token, token_type="password_reset", is_used=False)
            if not token_obj.is_valid():
                return Response({"detail": "Link is invalid or has expired."}, status=status.HTTP_400_BAD_REQUEST)
            return Response({"reset_id": str(token_obj.token)}, status=status.HTTP_200_OK)
        except AuthToken.DoesNotExist:
            return Response({"detail": "Link is invalid or has expired."}, status=status.HTTP_400_BAD_REQUEST)

class PasswordResetConfirmAPIView(APIView):
    permission_classes = [AllowAny]
    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        if serializer.is_valid():
            try:
                token = AuthToken.objects.get(token=serializer.validated_data['reset_id'], token_type="password_reset", is_used=False)
                if not token.is_valid():
                    return Response({"detail": "Session is invalid or has expired."}, status=status.HTTP_400_BAD_REQUEST)
                user = token.user
                user.set_password(serializer.validated_data['new_password'])
                user.save()
                PasswordHistory.objects.create(user=user, password_hash=user.password)
                token.is_used = True
                token.save()
                OutstandingToken.objects.filter(user=user).delete()
                return Response({"message": "Password has been reset successfully."}, status=status.HTTP_200_OK)
            except AuthToken.DoesNotExist:
                return Response({"detail": "Session is invalid or has expired."}, status=status.HTTP_400_BAD_REQUEST)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class UserActivityLogAPIView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        logs = UserActivityLog.objects.filter(user=request.user).order_by('-timestamp')
        serializer = UserActivityLogSerializer(logs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

class DeleteAccountView(APIView):
    permission_classes = [IsAuthenticated]
    def delete(self, request):
        request.user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

class OnboardingStatusView(APIView):
    permission_classes = [IsAuthenticated, HasActiveSubscription]
    def get(self, request):
        onboarding_status, _ = OnboardingStatus.objects.get_or_create(user=request.user)
        serializer = OnboardingStatusSerializer(onboarding_status)
        return Response(serializer.data, status=status.HTTP_200_OK)
    def post(self, request):
        onboarding_status, _ = OnboardingStatus.objects.get_or_create(user=request.user)
        serializer = OnboardingStatusSerializer(onboarding_status, data=request.data, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class LanguagePreferenceView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        serializer = LanguagePreferenceSerializer(request.user.profile)
        return Response(serializer.data, status=status.HTTP_200_OK)
    def put(self, request):
        serializer = LanguagePreferenceSerializer(request.user.profile, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)