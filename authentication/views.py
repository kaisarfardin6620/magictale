from django.conf import settings
from django.contrib.auth.models import User
from django.urls import reverse
from django.shortcuts import render
from django.template.loader import render_to_string
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
from drf_spectacular.utils import extend_schema, OpenApiResponse, inline_serializer
from drf_spectacular.types import OpenApiTypes
from rest_framework import serializers
from django.utils.translation import gettext as _
import logging
import requests
import jwt
from django.db import transaction
from jwt.algorithms import RSAAlgorithm
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from .utils import get_client_ip, send_email
from .models import AuthToken, UserProfile, PasswordHistory, UserActivityLog
from .serializers import (
    SignupSerializer,
    PasswordResetRequestSerializer,
    ProfileSerializer,
    ResendVerificationSerializer,
    MyTokenObtainPairSerializer,
    UserActivityLogSerializer,
    UnifiedProfileUpdateSerializer,
    PasswordResetFormSerializer,
    FCMDeviceSerializer
)
from django.core.cache import cache
from rest_framework.throttling import ScopedRateThrottle
from notifications.tasks import create_and_send_notification_task
from fcm_django.models import FCMDevice

logger = logging.getLogger(__name__)

class MyTokenObtainPairView(APIView):
    permission_classes = [AllowAny]
    serializer_class = MyTokenObtainPairSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'login'

    @extend_schema(
        request=MyTokenObtainPairSerializer,
        responses={200: MyTokenObtainPairSerializer}
    )
    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        return Response(serializer.validated_data, status=status.HTTP_200_OK)

class RegisterDeviceView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=FCMDeviceSerializer,
        responses={
            200: OpenApiResponse(description="Device registered successfully."),
            400: OpenApiResponse(description="Validation errors.")
        }
    )
    def post(self, request):
        serializer = FCMDeviceSerializer(data=request.data)
        if serializer.is_valid():
            registration_id = serializer.validated_data['registration_id']
            device_type = serializer.validated_data.get('type', 'web')

            FCMDevice.objects.update_or_create(
                registration_id=registration_id,
                defaults={
                    'user': request.user,
                    'type': device_type,
                    'active': True
                }
            )
            return Response({"message": _("Device registered successfully.")}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class SignupAPIView(APIView):
    permission_classes = [AllowAny]
    
    @extend_schema(
        request=SignupSerializer,
        responses={
            201: OpenApiResponse(description="User created successfully. Please check your email for verification."),
            400: OpenApiResponse(description="Validation errors.")
        }
    )
    def post(self, request):
        serializer = SignupSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            
            UserActivityLog.objects.create(user=user, activity_type='signup', ip_address=get_client_ip(request))
            token = AuthToken.objects.create(user=user, token_type='email_verification')
            verification_path = reverse('email_verification') + f'?token={token.token}'
            verification_url = f"{settings.BACKEND_BASE_URL}{verification_path}"
            html_message = render_to_string('emails/signup_verification_email.html', {'username': user.first_name, 'verification_url': verification_url})
            plain_message = f'Please click the link to verify your email: {verification_url}'
            send_email('Verify your email for MagicTale', plain_message, [user.email], html_message=html_message)
            create_and_send_notification_task.delay(
                user.id,
                "Welcome to MagicTale!",
                "Your account has been created successfully."
            )
            return Response({"message": _("User created successfully. Please check your email for verification.")}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class EmailVerificationAPIView(APIView):
    permission_classes = [AllowAny]
    
    @extend_schema(exclude=True)
    def get(self, request):
        token_uuid = request.GET.get('token')
        context = {'home_url': settings.FRONTEND_URL, 'login_url': f"{settings.FRONTEND_URL}/login"}
        if not token_uuid:
            context['error_message'] = _('No verification token was provided.')
            return render(request, 'verification/verification_error.html', context, status=status.HTTP_400_BAD_REQUEST)
        try:
            token = AuthToken.objects.get(token=token_uuid, token_type='email_verification')
            if not token.is_valid():
                context['error_message'] = _('This verification link is invalid or has expired.')
                return render(request, 'verification/verification_error.html', context, status=status.HTTP_400_BAD_REQUEST)
            user = token.user
            user.is_active = True
            user.save()
            token.is_used = True
            token.save()
            UserActivityLog.objects.create(user=user, activity_type='email_verification_success', ip_address=get_client_ip(request))
            context.update({'title': _('Account Verified!'), 'message': _('Your account is now active.')})
            return render(request, 'verification/verification_success.html', context)
        except AuthToken.DoesNotExist:
            context['error_message'] = _('This verification link is invalid or has expired.')
            return render(request, 'verification/verification_error.html', context, status=status.HTTP_400_BAD_REQUEST)

class ResendVerificationEmailAPIView(APIView):
    permission_classes = [AllowAny]
    
    @extend_schema(
        request=ResendVerificationSerializer,
        responses={
            200: OpenApiResponse(description="Verification email has been resent."),
            400: OpenApiResponse(description="Account already active or validation errors."),
            404: OpenApiResponse(description="User not found.")
        }
    )
    def post(self, request):
        serializer = ResendVerificationSerializer(data=request.data)
        if serializer.is_valid():
            try:
                user = User.objects.get(email__iexact=serializer.validated_data['username'])
                if user.is_active:
                    return Response({'detail': _('This account is already active.')}, status=status.HTTP_400_BAD_REQUEST)
                AuthToken.objects.filter(user=user, token_type='email_verification', is_used=False).delete()
                token = AuthToken.objects.create(user=user, token_type='email_verification')
                verification_path = reverse('email_verification') + f'?token={token.token}'
                verification_url = f"{settings.BACKEND_BASE_URL}{verification_path}"
                html_message = render_to_string('emails/signup_verification_email.html', {'username': user.first_name, 'verification_url': verification_url})
                send_email('Verify your email', f'Link: {verification_url}', [user.email], html_message=html_message)
                return Response({"message": _("Verification email has been resent.")}, status=status.HTTP_200_OK)
            except User.DoesNotExist:
                return Response({'detail': _('User not found.')}, status=status.HTTP_404_NOT_FOUND)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ProfileView(APIView):
    permission_classes = [IsAuthenticated]
    
    @extend_schema(
        responses={
            200: ProfileSerializer,
            404: OpenApiResponse(description="User profile not found.")
        }
    )
    def get(self, request):
        cache_key = f"user_profile_{request.user.id}"
        cached_profile = cache.get(cache_key)

        if cached_profile:
            return Response(cached_profile, status=status.HTTP_200_OK)

        try:
            profile = UserProfile.objects.get(user=request.user)
            serializer = ProfileSerializer(profile)
            
            full_name = f"{request.user.first_name} {request.user.last_name}".strip()
            
            user_data = {
                'full_name': full_name,
                'email': request.user.email,
            }
            response_data = {**user_data, **serializer.data}
            cache.set(cache_key, response_data, timeout=3600) 
            return Response(response_data, status=status.HTTP_200_OK)
        except UserProfile.DoesNotExist:
            return Response({'detail': _('User profile not found.')}, status=status.HTTP_404_NOT_FOUND)
    
    @extend_schema(
        request=UnifiedProfileUpdateSerializer,
        responses={
            200: OpenApiResponse(description="Profile updated successfully."),
            400: OpenApiResponse(description="Validation errors."),
            404: OpenApiResponse(description="User profile not found.")
        }
    )
    def put(self, request):
        try:
            profile = UserProfile.objects.get(user=request.user)
            serializer = UnifiedProfileUpdateSerializer(instance=profile, data=request.data, context={'request': request}, partial=True)
            if serializer.is_valid():
                serializer.save()

                create_and_send_notification_task.delay(
                request.user.id,
                "Profile Updated",
                "Your account details have been changed."
            )
                cache.delete(f"user_profile_{request.user.id}") 
                return Response({'message': _('Profile updated successfully.')}, status=status.HTTP_200_OK)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except UserProfile.DoesNotExist:
            return Response({'detail': _('User profile not found.')}, status=status.HTTP_404_NOT_FOUND)

class PasswordResetInitiateAPIView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle] 
    throttle_scope = 'password_reset'      
    
    @extend_schema(
        request=PasswordResetRequestSerializer,
        responses={
            200: OpenApiResponse(description="If an account exists, a reset link has been sent.")
        }
    )
    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            try:
                user = User.objects.get(email=email)
                AuthToken.objects.filter(user=user, token_type='password_reset').delete()
                token = AuthToken.objects.create(user=user, token_type='password_reset')
                reset_path = reverse('password_reset_confirm', kwargs={'token': token.token})
                reset_url = f"{settings.BACKEND_BASE_URL}{reset_path}"
                send_email('Password Reset Request', f'Click to reset: {reset_url}',[user.email])
            except User.DoesNotExist:
                pass
        return Response({'message': _('If an account exists, a reset link has been sent.')}, status=status.HTTP_200_OK)

class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]
    
    @extend_schema(exclude=True)
    def get(self, request, token=None):
        try:
            token_obj = AuthToken.objects.get(token=token, token_type="password_reset", is_used=False)
            if not token_obj.is_valid():
                context = {'error_message': _('This password reset link is invalid or has expired.'), 'home_url': settings.FRONTEND_URL}
                return render(request, 'verification/verification_error.html', context, status=status.HTTP_400_BAD_REQUEST)
            return render(request, 'verification/password_reset_form.html', {'token': token})
        except AuthToken.DoesNotExist:
            context = {'error_message': _('This password reset link is invalid or has expired.'), 'home_url': settings.FRONTEND_URL}
            return render(request, 'verification/verification_error.html', context, status=status.HTTP_400_BAD_REQUEST)
            
    @extend_schema(exclude=True)
    def post(self, request, token=None):
        try:
            token_obj = AuthToken.objects.get(token=token, token_type="password_reset", is_used=False)
            if not token_obj.is_valid():
                context = {'error_message': _('This password reset session is invalid or has expired.'), 'home_url': settings.FRONTEND_URL}
                return render(request, 'verification/verification_error.html', context, status=status.HTTP_400_BAD_REQUEST)
            serializer = PasswordResetFormSerializer(data=request.data)
            if serializer.is_valid():
                user = token_obj.user
                user.set_password(serializer.validated_data['new_password'])
                user.save()
                PasswordHistory.objects.create(user=user, password_hash=user.password)
                token_obj.is_used = True
                token_obj.save()
                OutstandingToken.objects.filter(user=user).delete()
                create_and_send_notification_task.delay(
                    user.id,
                    "Password Reset",
                    "Your password has been changed successfully."
                )
                context = {
                    'title': _('Password Reset Successful!'),
                    'message': _('Your password has been changed. You can now log in with your new password.'),
                    'login_url': f"{settings.FRONTEND_URL}/login"
                }
                return render(request, 'verification/verification_success.html', context)
            else:
                return render(request, 'verification/password_reset_form.html', {'token': token, 'errors': serializer.errors})
        except AuthToken.DoesNotExist:
            context = {'error_message': _('This password reset session is invalid or has expired.'), 'home_url': settings.FRONTEND_URL}
            return render(request, 'verification/verification_error.html', context, status=status.HTTP_400_BAD_REQUEST)

class UserActivityLogAPIView(APIView):
    permission_classes =[IsAuthenticated]
    
    @extend_schema(
        responses={200: UserActivityLogSerializer(many=True)}
    )
    def get(self, request):
        logs = UserActivityLog.objects.filter(user=request.user).order_by('-timestamp')
        serializer = UserActivityLogSerializer(logs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

class DeleteAccountView(APIView):
    permission_classes = [IsAuthenticated]
    
    @extend_schema(
        responses={204: OpenApiResponse(description="Account deleted successfully.")}
    )
    def delete(self, request):
        request.user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

class GoogleLoginView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        request=inline_serializer(
            name='GoogleLoginRequest',
            fields={'id_token': serializers.CharField()}
        ),
        responses={
            200: inline_serializer(
                name='GoogleLoginResponse',
                fields={
                    'refresh': serializers.CharField(),
                    'access': serializers.CharField()
                }
            ),
            400: OpenApiResponse(description="Bad request"),
            401: OpenApiResponse(description="Unauthorized"),
            403: OpenApiResponse(description="Forbidden")
        }
    )
    def post(self, request):
        token_str = request.data.get("id_token")
        if not token_str:
            return Response({"detail": _("id_token is required")}, status=status.HTTP_400_BAD_REQUEST)

        try:
            decoded = {}
            if token_str.startswith("ya29"):
                user_info_resp = requests.get(f"https://www.googleapis.com/oauth2/v3/userinfo?access_token={token_str}")
                user_info_resp.raise_for_status()
                decoded = user_info_resp.json()
            else:
                decoded = google_id_token.verify_oauth2_token(
                    token_str,
                    google_requests.Request(),
                    settings.GOOGLE_CLIENT_ID
                )
                if decoded.get("aud") != settings.GOOGLE_CLIENT_ID:
                    return Response({"detail": _("Invalid token audience")}, status=status.HTTP_401_UNAUTHORIZED)

            if not decoded.get("email_verified", False):
                return Response({"detail": _("Google email not verified")}, status=status.HTTP_401_UNAUTHORIZED)

            email = decoded.get("email")
            if not email:
                return Response({"detail": _("Email not provided by Google")}, status=status.HTTP_400_BAD_REQUEST)

            first_name = decoded.get("given_name", "")
            last_name = decoded.get("family_name", "")

            with transaction.atomic():
                user, created = User.objects.get_or_create(
                    email=email,
                    defaults={
                        "username": email,
                        "first_name": first_name,
                        "last_name": last_name,
                        "is_active": True
                    }
                )

            if not user.is_active:
                return Response({"detail": _("Account is disabled")}, status=status.HTTP_403_FORBIDDEN)

            refresh = MyTokenObtainPairSerializer.get_token(user)
            tokens = {'refresh': str(refresh), 'access': str(refresh.access_token)}
            return Response(tokens, status=status.HTTP_200_OK)

        except ValueError as e:
            logger.warning(f"Google login invalid token: {e}")
            return Response({"detail": _("Invalid or expired Google token")}, status=status.HTTP_401_UNAUTHORIZED)
        except Exception as e:
            logger.error(f"Google authentication failed: {e}")
            return Response({"detail": _("Google authentication failed")}, status=status.HTTP_400_BAD_REQUEST)


class AppleLoginView(APIView):
    permission_classes =[AllowAny]
    APPLE_KEYS_CACHE_KEY = "apple_public_keys"
    APPLE_KEYS_URL = "https://appleid.apple.com/auth/keys"

    @extend_schema(
        request=inline_serializer(
            name='AppleLoginRequest',
            fields={
                'id_token': serializers.CharField(),
                'email': serializers.CharField(required=False, allow_null=True)
            }
        ),
        responses={
            200: inline_serializer(
                name='AppleLoginResponse',
                fields={
                    'refresh': serializers.CharField(),
                    'access': serializers.CharField()
                }
            ),
            400: OpenApiResponse(description="Bad request"),
            401: OpenApiResponse(description="Unauthorized"),
            403: OpenApiResponse(description="Forbidden")
        }
    )
    def post(self, request):
        id_token_str = request.data.get("id_token")
        if not id_token_str:
            return Response({"detail": _("id_token is required")}, status=status.HTTP_400_BAD_REQUEST)

        try:
            decoded = self._verify_apple_token(id_token_str)
        except ValueError as e:
            logger.warning(f"Apple login invalid token: {e}")
            return Response({"detail": str(e)}, status=status.HTTP_401_UNAUTHORIZED)
        except Exception as e:
            logger.error(f"Apple token verification failed: {e}")
            return Response({"detail": _("Apple authentication failed")}, status=status.HTTP_400_BAD_REQUEST)

        apple_user_id = decoded.get("sub")
        if not apple_user_id:
            return Response({"detail": _("Invalid token: missing sub")}, status=status.HTTP_400_BAD_REQUEST)

        email = decoded.get("email") or request.data.get("email")

        try:
            with transaction.atomic():
                user, created = self._get_or_create_user(apple_user_id, email)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Apple user creation failed: {e}")
            return Response({"detail": _("Apple authentication failed")}, status=status.HTTP_400_BAD_REQUEST)

        if not user.is_active:
            return Response({"detail": _("Account is disabled")}, status=status.HTTP_403_FORBIDDEN)

        refresh = MyTokenObtainPairSerializer.get_token(user)
        tokens = {'refresh': str(refresh), 'access': str(refresh.access_token)}
        return Response(tokens, status=status.HTTP_200_OK)

    def _verify_apple_token(self, id_token_str: str) -> dict:
        apple_keys = cache.get(self.APPLE_KEYS_CACHE_KEY)
        if not apple_keys:
            response = requests.get(self.APPLE_KEYS_URL, timeout=5)
            response.raise_for_status()
            apple_keys = response.json()
            cache.set(self.APPLE_KEYS_CACHE_KEY, apple_keys, timeout=3600 * 24)

        headers = jwt.get_unverified_header(id_token_str)
        kid = headers.get("kid")

        matching_key = next((k for k in apple_keys["keys"] if k["kid"] == kid), None)
        if not matching_key:
            cache.delete(self.APPLE_KEYS_CACHE_KEY)
            raise ValueError("Apple public key not found — please retry")

        public_key = RSAAlgorithm.from_jwk(matching_key)

        decoded = jwt.decode(
            id_token_str,
            public_key,
            algorithms=["RS256"],
            audience=settings.APPLE_CLIENT_ID,
            issuer="https://appleid.apple.com"
        )
        return decoded

    def _get_or_create_user(self, apple_user_id: str, email: str | None):
        if not email:
            raise ValueError("Email is required on first Apple login")

        user = User.objects.filter(email=email).first()
        if user:
            return user, False

        return User.objects.create(
            username=email,
            email=email,
            is_active=True,
        ), True