# views.py
from django.conf import settings
from django.contrib.auth import authenticate
from django.core.mail import send_mail
from django.utils import timezone
from django.contrib.auth.models import User
from django.contrib.auth.hashers import check_password, make_password
from django.urls import reverse
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken

from .models import AuthToken, UserProfile, PasswordHistory, UserActivityLog
from .serializers import (
    SignupSerializer,
    PasswordResetRequestSerializer, PasswordResetConfirmSerializer,
    ChangePasswordSerializer, ProfileSerializer, UpdateProfileSerializer,
    ProfilePictureSerializer, EmailChangeRequestSerializer, ResendVerificationSerializer,
    MyTokenObtainPairSerializer,
    UserActivityLogSerializer,
    FullNameUpdateSerializer,
    EmailChangeConfirmSerializer
)
import uuid
import random


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
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            recipient_list,
            fail_silently=False,
        )
    except Exception as e:
        print(f"Error sending email: {e}")


# JWT authentication views
class MyTokenObtainPairView(TokenObtainPairView):
    serializer_class = MyTokenObtainPairSerializer


# User signup and verification views
class SignupAPIView(APIView):
    """
    API view to handle user signup.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = SignupSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            
            # Log user activity
            UserActivityLog.objects.create(
                user=user,
                activity_type='signup',
                ip_address=get_client_ip(request)
            )

            token = AuthToken.objects.create(
                user=user,
                token=uuid.uuid4(),
                token_type='email_verification',
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
    """
    API view to verify user email with a token.
    """
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

            # Log user activity
            UserActivityLog.objects.create(
                user=user,
                activity_type='email_verification_success',
                ip_address=get_client_ip(request)
            )

            return Response(
                {'message': 'Email verified successfully. You can now log in.'},
                status=status.HTTP_200_OK
            )
        except AuthToken.DoesNotExist:
            return Response({'error': 'Invalid or expired token'}, status=status.HTTP_400_BAD_REQUEST)


class ResendVerificationEmailAPIView(APIView):
    """
    API view to resend a verification email.
    """
    permission_classes = [AllowAny]
    def post(self, request):
        serializer = ResendVerificationSerializer(data=request.data)
        if serializer.is_valid():
            try:
                user = User.objects.get(username=serializer.validated_data['username'])
                if user.is_active:
                    return Response({'message': 'This account is already active.'}, status=status.HTTP_400_BAD_REQUEST)
                
                # Delete any old, unused tokens of the same type
                AuthToken.objects.filter(user=user, token_type='email_verification', is_used=False).delete()

                token = AuthToken.objects.create(
                    user=user,
                    token=uuid.uuid4(),
                    token_type='email_verification',
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
                    {"message": "Verification email has been resent."},
                    status=status.HTTP_200_OK
                )
            except User.DoesNotExist:
                return Response({'error': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# Password management views
class PasswordResetRequestAPIView(APIView):
    """
    Step 1: Verify token from the reset link.
    Called when the user clicks the email link.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        token_value = request.query_params.get("token")
        if not token_value:
            return Response({"error": "Token is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            token = AuthToken.objects.get(token=token_value, token_type="password_reset", is_used=False)
            if not token.is_valid():
                return Response({"error": "Invalid or expired token."}, status=status.HTTP_400_BAD_REQUEST)

            # ✅ Instead of asking user to type token later, return a short-lived session token / ID
            # (frontend will save this in localStorage or memory temporarily)
            return Response(
                {"message": "Token verified. You may now reset your password.", "reset_id": str(token.token)},
                status=status.HTTP_200_OK,
            )
        except AuthToken.DoesNotExist:
            return Response({"error": "Invalid or expired token."}, status=status.HTTP_400_BAD_REQUEST)


class PasswordResetConfirmAPIView(APIView):
    """
    Step 2: Reset the password.
    User only sends new password + confirm password.
    The reset_id (token) is sent automatically by frontend (hidden from user).
    """
    permission_classes = [AllowAny]

    def post(self, request):
        reset_id = request.data.get("reset_id")  # frontend keeps this hidden
        new_password = request.data.get("new_password")
        confirm_password = request.data.get("confirm_password")

        if not reset_id or not new_password or not confirm_password:
            return Response({"error": "reset_id, new_password, and confirm_password are required."},
                            status=status.HTTP_400_BAD_REQUEST)

        if new_password != confirm_password:
            return Response({"error": "Passwords do not match."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            token = AuthToken.objects.get(token=reset_id, token_type="password_reset", is_used=False)
            if not token.is_valid():
                return Response({"error": "Invalid or expired token."}, status=status.HTTP_400_BAD_REQUEST)

            user = token.user

            # Prevent reusing same password
            from django.contrib.auth.hashers import check_password
            if check_password(new_password, user.password):
                return Response({"error": "New password cannot be the same as the old one."},
                                status=status.HTTP_400_BAD_REQUEST)

            user.set_password(new_password)
            user.save()

            # Save to password history
            PasswordHistory.objects.create(user=user, password_hash=user.password)

            token.is_used = True
            token.save()

            # Blacklist all outstanding JWTs (force logout everywhere)
            outstanding_tokens = OutstandingToken.objects.filter(user=user)
            for jwt_token in outstanding_tokens:
                BlacklistedToken.objects.get_or_create(token=jwt_token)

            UserActivityLog.objects.create(user=user, activity_type="password_reset", ip_address=get_client_ip(request))

            return Response({"message": "Password reset successfully."}, status=status.HTTP_200_OK)

        except AuthToken.DoesNotExist:
            return Response({"error": "Invalid or expired token."}, status=status.HTTP_400_BAD_REQUEST)


class ChangePasswordAPIView(APIView):
    """
    API view to change a user's password.
    """
    permission_classes = [IsAuthenticated]
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            user = request.user
            user.set_password(serializer.validated_data['new_password'])
            user.save()

            # Add password to history
            PasswordHistory.objects.create(user=user, password_hash=user.password)

            # Blacklist all outstanding JWT tokens for this user
            outstanding_tokens = OutstandingToken.objects.filter(user=user)
            for jwt_token in outstanding_tokens:
                BlacklistedToken.objects.get_or_create(token=jwt_token)

            # Log user activity
            UserActivityLog.objects.create(
                user=user,
                activity_type='password_change',
                ip_address=get_client_ip(request)
            )

            return Response({'message': 'Password changed successfully.'}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# Profile management views
class ProfileView(APIView):
    """
    API view to get and update a user's profile and basic info.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            profile = UserProfile.objects.get(user=request.user)
            # Combine user and profile data
            data = {
                'first_name': request.user.first_name,
                'last_name': request.user.last_name,
                'email': request.user.email,
                'phone_number': profile.phone_number
            }
            return Response(data, status=status.HTTP_200_OK)
        except UserProfile.DoesNotExist:
            return Response({'error': 'User profile not found.'}, status=status.HTTP_404_NOT_FOUND)

    def put(self, request):
        serializer = UpdateProfileSerializer(request.user.profile, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({'message': 'Profile updated successfully.'}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class FullNameUpdateAPIView(APIView):
    """
    API view to update a user's first and last name.
    """
    permission_classes = [IsAuthenticated]

    def put(self, request):
        serializer = FullNameUpdateSerializer(request.user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({'message': 'Full name updated successfully.'}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ProfilePictureView(APIView):
    """
    API view to get and update a user's profile picture.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            profile = UserProfile.objects.get(user=request.user)
            serializer = ProfilePictureSerializer(profile)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except UserProfile.DoesNotExist:
            return Response({'error': 'User profile not found.'}, status=status.HTTP_404_NOT_REQUEST)

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
    """
    API view to retrieve a user's activity log.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        logs = UserActivityLog.objects.filter(user=request.user).order_by('-timestamp')
        serializer = UserActivityLogSerializer(logs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class DeleteAccountView(APIView):
    """
    API view to delete a user's account.
    """
    permission_classes = [IsAuthenticated]

    def delete(self, request):
        user = request.user
        user.delete()
        return Response({'message': 'Account deleted successfully.'}, status=status.HTTP_204_NO_CONTENT)


# Email change views
class EmailChangeRequestAPIView(APIView):
    """
    API view to request an email change.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = EmailChangeRequestSerializer(data=request.data)
        if serializer.is_valid():
            new_email = serializer.validated_data['new_email']
            user = request.user

            # Check if the new email is already in use
            if User.objects.filter(email=new_email).exists():
                return Response(
                    {'error': 'This email address is already in use.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Delete any old, unused email change tokens
            AuthToken.objects.filter(
                user=user, token_type='email_change', is_used=False
            ).delete()

            token = AuthToken.objects.create(
                user=user,
                token=uuid.uuid4(),
                token_type='email_change',
                new_email=new_email
            )

            # Build clickable link with token in query param
            email_change_url = request.build_absolute_uri(
                reverse('email_change_confirm') + f'?token={token.token}'
            )

            send_email(
                'Confirm your email change',
                f'Please click the following link to confirm your email change: {email_change_url}',
                [new_email]
            )

            return Response(
                {'message': 'Email change confirmation link sent to your new email.'},
                status=status.HTTP_200_OK
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class EmailChangeConfirmAPIView(APIView):
    """
    API view to confirm an email change (via link).
    """
    permission_classes = [AllowAny]

    def get(self, request):  # <-- changed from post() to get()
        token_value = request.query_params.get('token')

        if not token_value:
            return Response(
                {'error': 'Token is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            token = AuthToken.objects.get(
                token=token_value, token_type='email_change'
            )

            if not token.is_valid():
                return Response(
                    {'error': 'Invalid or expired token.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            user = token.user
            new_email = token.new_email

            # Ensure email still not in use
            if User.objects.filter(email=new_email).exclude(id=user.id).exists():
                return Response(
                    {'error': 'This email address is already in use.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Update user's email
            user.email = new_email
            user.save()

            # Mark token as used
            token.is_used = True
            token.save()

            return Response(
                {'message': 'Email changed successfully.'},
                status=status.HTTP_200_OK
            )

        except AuthToken.DoesNotExist:
            return Response(
                {'error': 'Invalid or expired token.'},
                status=status.HTTP_400_BAD_REQUEST
            )


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