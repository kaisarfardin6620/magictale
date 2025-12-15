import time
import logging
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from django.utils.translation import gettext as _

logger = logging.getLogger(__name__)

def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    logger.error(
        f"Exception occurred: {exc}",
        exc_info=True,
        extra={'request': context['request'].__str__()}
    )

    if response is not None:
        status_code = response.status_code
        data = None
        
        if isinstance(exc, ValidationError):
            message = _("Invalid input. Please check the provided data.")
            data = response.data 
        elif isinstance(response.data, dict) and 'detail' in response.data:
            message = response.data['detail']
        elif isinstance(response.data, list) and response.data:
            message = response.data[0]
        else:
            message = _("An error occurred.")

        response.data = {
            "success": False,
            "code": status_code,
            "message": str(message),
            "timestamp": int(time.time()),
            "data": data
        }
        response.status_code = status_code

    else:
        response = Response({
            "success": False,
            "code": 500,
            "message": _("A critical server error occurred. Our team has been notified."),
            "timestamp": int(time.time()),
            "data": None
        }, status=500)

    return response