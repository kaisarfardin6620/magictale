# authentication/utils.py

from django.conf import settings
from django.core.mail import send_mail

def get_client_ip(request):
    """
    A helper function to get the client's real IP address.
    """
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

def send_email(subject, message, recipient_list, html_message=None):
    """
    A helper function to send emails, supporting HTML content.
    """
    try:
        send_mail(
            subject, message, settings.DEFAULT_FROM_EMAIL,
            recipient_list, fail_silently=False,
            html_message=html_message
        )
    except Exception as e:
        # It's good practice to log this error in a real application
        print(f"Error sending email: {e}")