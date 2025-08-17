# notification/views.py
import firebase_admin
from firebase_admin import credentials
from firebase_admin import messaging
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import DeviceToken
from django.conf import settings
import os
import json

# Initialize Firebase Admin SDK
# It's best practice to load credentials from an environment variable or file
try:
    # Assuming you've saved the private key as a JSON string in an environment variable
    # Or you can load it from a file
    # For now, we'll use a placeholder to show the structure
    # You should replace this with a secure way of loading your credentials
    firebase_credentials = {
        "type": os.environ.get("FIREBASE_TYPE", "service_account"),
        "project_id": os.environ.get("FIREBASE_PROJECT_ID", "subibash-9083e"),
        "private_key_id": os.environ.get("FIREBASE_PRIVATE_KEY_ID", "f81e5ea6d53edf316859cc3bdc16172f7843d6d0"),
        "private_key": os.environ.get("FIREBASE_PRIVATE_KEY", "").replace('\\n', '\n'),
        "client_email": "firebase-adminsdk-xxxxx@subibash-9083e.iam.gserviceaccount.com", # Replace with your client email
        "client_id": "1234567890", # Replace with your client id
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/firebase-adminsdk-xxxxx%40subibash-9083e.iam.gserviceaccount.com" # Replace with your client cert url
    }
    cred = credentials.Certificate(firebase_credentials)
    if not firebase_admin._apps: # Check if app is already initialized
        firebase_admin.initialize_app(cred)
except ValueError as e:
    print(f"Error initializing Firebase Admin SDK: {e}")
except Exception as e:
    print(f"An unexpected error occurred during Firebase initialization: {e}")

class NotificationViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=False, methods=["post"])
    def register_token(self, request):
        """
        API endpoint for a user to register their device's FCM token.
        """
        token = request.data.get("token")
        if not token:
            return Response({"error": "Token is required"}, status=status.HTTP_400_BAD_REQUEST)

        # Check if the token already exists for this user and create/update it
        try:
            device_token, created = DeviceToken.objects.update_or_create(
                user=request.user,
                token=token
            )
            return Response({"message": "Token registered successfully", "created": created}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=["post"])
    def send_test_notification(self, request):
        """
        API endpoint to send a test push notification to the user's registered devices.
        This is for testing purposes.
        """
        try:
            tokens = DeviceToken.objects.filter(user=request.user).values_list("token", flat=True)
            if not tokens:
                return Response({"message": "No device tokens found for this user."}, status=status.HTTP_404_NOT_FOUND)

            message = messaging.MulticastMessage(
                notification=messaging.Notification(
                    title="Test Notification",
                    body="This is a test notification from your Django backend!"
                ),
                tokens=list(tokens),
            )
            response = messaging.send_multicast(message)

            return Response({
                "message": "Successfully sent test message",
                "success_count": response.success_count,
                "failure_count": response.failure_count
            })
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
