from celery import shared_task
from django.contrib.auth.models import User
from fcm_django.models import FCMDevice
from .models import Notification

@shared_task
def create_and_send_notification_task(user_id, title, body, data=None):
    try:
        user = User.objects.select_related('profile').get(id=user_id)

        Notification.objects.create(
            user=user,
            title=title,
            body=body,
            data=data or {}
        )
        print(f"Saved notification for user {user_id}")

        if user.profile.allow_push_notifications:
            devices = FCMDevice.objects.filter(user=user, active=True)
            if devices:
                devices.send_message(
                    title=title,
                    body=body,
                    data=data or {}
                )
                print(f"Sent PUSH notification to user {user_id}")
            else:
                print(f"User {user_id} has push notifications enabled but no active devices.")
        else:
            print(f"Skipping PUSH notification for user {user_id} (disabled in profile).")

    except User.DoesNotExist:
        print(f"Could not process notification: User with id={user_id} not found.")
    except Exception as e:
        print(f"An error occurred while sending notification for user {user_id}: {e}")