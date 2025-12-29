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
from rest_framework_simplejwt.tokens import RefreshToken
from django.utils.translation import gettext as _ 
import logging

from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from allauth.socialaccount.providers.apple.views import AppleOAuth2Adapter
from allauth.socialaccount.providers.apple.client import AppleOAuth2Client
from allauth.socialaccount.providers.oauth2.client import OAuth2Client

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
    PasswordResetFormSerializer
)
from subscription.models import Subscription
from django.utils import timezone
from datetime import timedelta
from django.core.cache import cache
from rest_framework.throttling import ScopedRateThrottle
from notifications.tasks import create_and_send_notification_task

logger = logging.getLogger(__name__)

class MyTokenObtainPairView(APIView):
    permission_classes = [AllowAny]
    serializer_class = MyTokenObtainPairSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'login'

    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        return Response(serializer.validated_data, status=status.HTTP_200_OK)


class SignupAPIView(APIView):
    permission_classes = [AllowAny]
    def post(self, request):
        serializer = SignupSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            
            # Note: Subscription and UserProfile are created via signals.py to prevent race conditions
            
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
    def post(self, request):
        serializer = ResendVerificationSerializer(data=request.data)
        if serializer.is_valid():
            try:
                # Username is now the email address
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
    def get(self, request):
        cache_key = f"user_profile_{request.user.id}"
        cached_profile = cache.get(cache_key)

        if cached_profile:
            return Response(cached_profile, status=status.HTTP_200_OK)

        try:
            profile = UserProfile.objects.get(user=request.user)
            serializer = ProfileSerializer(profile)
            
            # Combine First and Last name into Full Name for response
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
                send_email('Password Reset Request', f'Click to reset: {reset_url}', [user.email])
            except User.DoesNotExist:
                pass
        return Response({'message': _('If an account exists, a reset link has been sent.')}, status=status.HTTP_200_OK)

class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]
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

class GoogleLoginView(APIView):
    permission_classes = [AllowAny]
    def post(self, request):
        access_token = request.data.get("access_token")
        if not access_token:
            return Response({"detail": _("An access token from Google is required.")}, status=status.HTTP_400_BAD_REQUEST)
        try:
            adapter = GoogleOAuth2Adapter(request)
            app = adapter.get_provider().get_app(request)
            client = OAuth2Client(
                request, app.client_id, app.secret,
                adapter.access_token_method, adapter.access_token_url,
                adapter.callback_url, adapter.scope
            )
            social_token = client.parse_token({"access_token": access_token})
            social_token.app = app
            login = adapter.complete_login(request, app, social_token)
            login.state = {} 
            login.save(request)
            user = login.user
            refresh = RefreshToken.for_user(user)
            access_token_obj = refresh.access_token
            access_token_obj['username'] = user.username
            try:
                subscription = user.subscription
                access_token_obj['plan'] = subscription.plan
                access_token_obj['subscription_status'] = subscription.status
            except (AttributeError, User.subscription.RelatedObjectDoesNotExist):
                access_token_obj['plan'] = None
                access_token_obj['subscription_status'] = 'inactive'
            
            return Response({'refresh': str(refresh), 'access': str(access_token_obj)}, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Google authentication error: {e}")
            return Response({"detail": _("An error occurred during Google authentication. Please try again.")}, status=status.HTTP_400_BAD_REQUEST)

class AppleLoginView(APIView):
    permission_classes = [AllowAny]
    
    def post(self, request):
        access_token = request.data.get("access_token")
        id_token = request.data.get("id_token")
        
        if not access_token and not id_token:
            return Response({"detail": _("An access_token or id_token is required.")}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            adapter = AppleOAuth2Adapter(request)
            app = adapter.get_provider().get_app(request)
            client = AppleOAuth2Client(
                request, app.client_id, app.secret,
                adapter.access_token_method, adapter.access_token_url,
                adapter.callback_url, adapter.scope
            )
            
            token_payload = {}
            if access_token:
                token_payload["code"] = access_token
            if id_token:
                token_payload["id_token"] = id_token
                
            social_token = client.parse_token(token_payload)
            social_token.app = app
            
            login = adapter.complete_login(request, app, social_token)
            login.state = {} 
            login.save(request)
            user = login.user
            
            refresh = RefreshToken.for_user(user)
            access_token_obj = refresh.access_token
            access_token_obj['username'] = user.username
            try:
                subscription = user.subscription
                access_token_obj['plan'] = subscription.plan
                access_token_obj['subscription_status'] = subscription.status
            except (AttributeError, User.subscription.RelatedObjectDoesNotExist):
                access_token_obj['plan'] = None
                access_token_obj['subscription_status'] = 'inactive'
            
            return Response({'refresh': str(refresh), 'access': str(access_token_obj)}, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Apple authentication error: {e}")
            return Response({"detail": _("An error occurred during Apple authentication. Please try again.")}, status=status.HTTP_400_BAD_REQUEST)