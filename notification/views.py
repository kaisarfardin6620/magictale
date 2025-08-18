# notification/views.py

# =================================================================
# === THE FAULTY INITIALIZATION BLOCK HAS BEEN REMOVED
# =================================================================
# The app is now correctly initialized only once in settings.py.
# We only need to import the 'messaging' module to use its functions.

from firebase_admin import messaging
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import DeviceToken

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

        # Correctly create or update the token for the user.
        # Using 'defaults' ensures that if a user already has a token,
        # it doesn't try to create a duplicate.
        try:
            device_token, created = DeviceToken.objects.update_or_create(
                user=request.user,
                defaults={'token': token}
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