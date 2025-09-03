# authentication/views.py
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth.hashers import check_password
from django.urls import reverse
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework import status
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken
import uuid
from django.core.mail import send_mail
from .permissions import HasActiveSubscription
from .models import OnboardingStatus
from .serializers import OnboardingStatusSerializer

from .models import AuthToken, UserProfile, PasswordHistory, UserActivityLog
from .serializers import (
    SignupSerializer, PasswordResetRequestSerializer, PasswordResetConfirmSerializer,
    ChangePasswordSerializer, ProfileSerializer, UpdateProfileSerializer,
    ProfilePictureSerializer, EmailChangeRequestSerializer, ResendVerificationSerializer,
    MyTokenObtainPairSerializer, UserActivityLogSerializer, FullNameUpdateSerializer,
    EmailChangeConfirmSerializer,LanguagePreferenceSerializer
)
from .models import OnboardingStatus
from .serializers import OnboardingStatusSerializer
from .permissions import HasActiveSubscription

def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

def send_email(subject, message, recipient_list):
    try:
        send_mail(
            subject, message, settings.DEFAULT_FROM_EMAIL,
            recipient_list, fail_silently=False,
        )
    except Exception as e:
        print(f"Error sending email: {e}")

class MyTokenObtainPairView(TokenObtainPairView):
    serializer_class = MyTokenObtainPairSerializer

class SignupAPIView(APIView):
    permission_classes = [AllowAny]
    def post(self, request):
        serializer = SignupSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            UserActivityLog.objects.create(
                user=user, activity_type='signup', ip_address=get_client_ip(request)
            )
            token = AuthToken.objects.create(
                user=user, token=uuid.uuid4(), token_type='email_verification'
            )
            verification_url = request.build_absolute_uri(
                reverse('email_verification') + f'?token={token.token}'
            )
            send_email(
                'Verify your email',
                f'Please click the following link to verify your email: {verification_url}',
                [user.email]
            )
            return Response(
                {"message": "User created successfully. Please check your email for verification."},
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class EmailVerificationAPIView(APIView):
    permission_classes = [AllowAny]
    def get(self, request):
        token_uuid = request.GET.get('token')
        if not token_uuid:
            return Response({'error': 'Token is required.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            token = AuthToken.objects.get(token=token_uuid, token_type='email_verification')
            if not token.is_valid():
                return Response({'error': 'Invalid or expired token'}, status=status.HTTP_400_BAD_REQUEST)
            user = token.user
            user.is_active = True
            user.save()
            token.is_used = True
            token.save()
            UserActivityLog.objects.create(
                user=user, activity_type='email_verification_success', ip_address=get_client_ip(request)
            )
            return Response(
                {'message': 'Email verified successfully. You can now log in.'}, status=status.HTTP_200_OK
            )
        except AuthToken.DoesNotExist:
            return Response({'error': 'Invalid or expired token'}, status=status.HTTP_400_BAD_REQUEST)

class ResendVerificationEmailAPIView(APIView):
    permission_classes = [AllowAny]
    def post(self, request):
        serializer = ResendVerificationSerializer(data=request.data)
        if serializer.is_valid():
            try:
                user = User.objects.get(username=serializer.validated_data['username'])
                if user.is_active:
                    return Response({'message': 'This account is already active.'}, status=status.HTTP_400_BAD_REQUEST)
                AuthToken.objects.filter(user=user, token_type='email_verification', is_used=False).delete()
                token = AuthToken.objects.create(
                    user=user, token=uuid.uuid4(), token_type='email_verification'
                )
                verification_url = request.build_absolute_uri(
                    reverse('email_verification') + f'?token={token.token}'
                )
                send_email(
                    'Verify your email',
                    f'Please click the following link to verify your email: {verification_url}',
                    [user.email]
                )
                return Response({"message": "Verification email has been resent."}, status=status.HTTP_200_OK)
            except User.DoesNotExist:
                return Response({'error': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class PasswordResetInitiateAPIView(APIView):
    permission_classes = [AllowAny]
    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        email = serializer.validated_data['email']
        try:
            user = User.objects.get(email=email)
            AuthToken.objects.filter(user=user, token_type='password_reset', is_used=False).delete()
            token = AuthToken.objects.create(user=user, token=uuid.uuid4(), token_type='password_reset')
            reset_verification_url = request.build_absolute_uri(
                reverse('password_reset_verify') + f'?token={token.token}'
            )
            send_email(
                'Password Reset Request',
                f'Please click the following link to reset your password: {reset_verification_url}',
                [user.email]
            )
        except User.DoesNotExist:
            pass
        return Response(
            {'message': 'If an account with that email exists, a password reset link has been sent.'},
            status=status.HTTP_200_OK
        )

class PasswordResetVerifyAPIView(APIView):
    permission_classes = [AllowAny]
    def get(self, request):
        token_value = request.query_params.get("token")
        if not token_value:
            return Response({"error": "Token is required in the link."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            token = AuthToken.objects.get(token=token_value, token_type="password_reset", is_used=False)
            if not token.is_valid():
                return Response({"error": "The password reset link is invalid or has expired."}, status=status.HTTP_400_BAD_REQUEST)
            return Response(
                {"message": "Token verified. You may now set your new password.", "reset_id": str(token.token)},
                status=status.HTTP_200_OK,
            )
        except AuthToken.DoesNotExist:
            return Response({"error": "The password reset link is invalid or has expired."}, status=status.HTTP_400_BAD_REQUEST)

class PasswordResetConfirmAPIView(APIView):
    permission_classes = [AllowAny]
    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        reset_id = serializer.validated_data['reset_id']
        new_password = serializer.validated_data['new_password']

        try:
            token = AuthToken.objects.get(token=reset_id, token_type="password_reset", is_used=False)
            if not token.is_valid():
                return Response({"error": "The password reset session is invalid or has expired."}, status=status.HTTP_400_BAD_REQUEST)
            user = token.user
            if check_password(new_password, user.password):
                return Response({"error": "New password cannot be the same as the old one."}, status=status.HTTP_400_BAD_REQUEST)
            user.set_password(new_password)
            user.save()
            PasswordHistory.objects.create(user=user, password_hash=user.password)
            token.is_used = True
            token.save()
            for jwt_token in OutstandingToken.objects.filter(user=user):
                BlacklistedToken.objects.get_or_create(token=jwt_token)
            UserActivityLog.objects.create(user=user, activity_type="password_reset", ip_address=get_client_ip(request))
            return Response({"message": "Password has been reset successfully."}, status=status.HTTP_200_OK)
        except AuthToken.DoesNotExist:
            return Response({"error": "The password reset session is invalid or has expired."}, status=status.HTTP_400_BAD_REQUEST)

class ChangePasswordAPIView(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            user = request.user
            user.set_password(serializer.validated_data['new_password'])
            user.save()
            PasswordHistory.objects.create(user=user, password_hash=user.password)
            for jwt_token in OutstandingToken.objects.filter(user=user):
                BlacklistedToken.objects.get_or_create(token=jwt_token)
            UserActivityLog.objects.create(
                user=user, activity_type='password_change', ip_address=get_client_ip(request)
            )
            return Response({'message': 'Password changed successfully.'}, status=status.HTTP_200_OK)
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
            return Response({'error': 'User profile not found.'}, status=status.HTTP_404_NOT_FOUND)

    def put(self, request):
        try:
            profile = UserProfile.objects.get(user=request.user)
            serializer = UpdateProfileSerializer(profile, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response({'message': 'Profile updated successfully.'}, status=status.HTTP_200_OK)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except UserProfile.DoesNotExist:
            return Response({'error': 'User profile not found.'}, status=status.HTTP_404_NOT_FOUND)

class FullNameUpdateAPIView(APIView):
    permission_classes = [IsAuthenticated]
    def put(self, request):
        serializer = FullNameUpdateSerializer(request.user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({'message': 'Full name updated successfully.'}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ProfilePictureView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        try:
            profile = UserProfile.objects.get(user=request.user)
            serializer = ProfilePictureSerializer(profile)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except UserProfile.DoesNotExist:
            return Response({'error': 'User profile not found.'}, status=status.HTTP_404_NOT_FOUND)
    def put(self, request):
        try:
            profile = UserProfile.objects.get(user=request.user)
            serializer = ProfilePictureSerializer(profile, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response({'message': 'Profile picture updated successfully.'}, status=status.HTTP_200_OK)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except UserProfile.DoesNotExist:
            return Response({'error': 'User profile not found.'}, status=status.HTTP_404_NOT_FOUND)

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
        return Response({'message': 'Account deleted successfully.'}, status=status.HTTP_204_NO_CONTENT)

class EmailChangeRequestAPIView(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request):
        serializer = EmailChangeRequestSerializer(data=request.data)
        if serializer.is_valid():
            new_email = serializer.validated_data['new_email']
            user = request.user
            if User.objects.filter(email=new_email).exists():
                return Response({'error': 'This email address is already in use.'}, status=status.HTTP_400_BAD_REQUEST)
            AuthToken.objects.filter(user=user, token_type='email_change', is_used=False).delete()
            token = AuthToken.objects.create(
                user=user, token=uuid.uuid4(), token_type='email_change', new_email=new_email
            )
            email_change_url = request.build_absolute_uri(
                reverse('email_change_confirm') + f'?token={token.token}'
            )
            send_email(
                'Confirm your email change',
                f'Please click the following link to confirm your email change: {email_change_url}',
                [new_email]
            )
            return Response(
                {'message': 'A confirmation link has been sent to your new email address.'},
                status=status.HTTP_200_OK
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
class EmailChangeConfirmAPIView(APIView):
    permission_classes = [AllowAny]
    def get(self, request):
        serializer = EmailChangeConfirmSerializer(data=request.query_params)
        if not serializer.is_valid():
            return Response({'error': 'A valid token is required in the URL.'}, status=status.HTTP_400_BAD_REQUEST)
        
        token_value = serializer.validated_data.get('token')
        
        try:
            token = AuthToken.objects.get(token=token_value, token_type='email_change', is_used=False)
            if not token.is_valid():
                return Response({'error': 'Invalid or expired token.'}, status=status.HTTP_400_BAD_REQUEST)
            user = token.user
            new_email = token.new_email
            if User.objects.filter(email=new_email).exclude(id=user.id).exists():
                return Response({'error': 'This email address is already in use by another account.'}, status=status.HTTP_400_BAD_REQUEST)
            user.email = new_email
            user.save()
            token.is_used = True
            token.save()
            return Response({'message': 'Your email has been changed successfully.'}, status=status.HTTP_200_OK)
        except AuthToken.DoesNotExist:
            return Response({'error': 'Invalid or expired token.'}, status=status.HTTP_400_BAD_REQUEST)
class OnboardingStatusView(APIView):
    permission_classes = [IsAuthenticated, HasActiveSubscription]

    def get(self, request):
        onboarding_status, created = OnboardingStatus.objects.get_or_create(user=request.user)
        serializer = OnboardingStatusSerializer(onboarding_status)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        onboarding_status, created = OnboardingStatus.objects.get_or_create(user=request.user)
        serializer = OnboardingStatusSerializer(onboarding_status, data=request.data, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
class LanguagePreferenceView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        profile = request.user.profile
        serializer = LanguagePreferenceSerializer(profile)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request):
        profile = request.user.profile
        serializer = LanguagePreferenceSerializer(profile, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)