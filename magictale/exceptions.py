import logging
import time
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status

logger = logging.getLogger(__name__)

def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    request = context.get('request')
    view_name = context['view'].__class__.__name__ if 'view' in context else 'unknown_view'
    user = request.user if request else 'anonymous'
    path = request.path if request else 'unknown_path'

    if response is not None:
        error_payload = response.data
        
        if response.status_code == 400:
            message = "Invalid input provided. Please check the details."
        elif response.status_code == 401:
            message = error_payload.get('detail', "Authentication credentials were not provided or were invalid.")
        elif response.status_code == 403:
            message = error_payload.get('detail', "You do not have permission to perform this action.")
        elif response.status_code == 404:
            message = error_payload.get('detail', "The requested resource was not found.")
        else:
            message = "An error occurred while processing your request."

        logger.warning(
            f"Handled API exception in {view_name} for user {user} on path {path}. "
            f"Status: {response.status_code}, Error: {exc}, Details: {error_payload}"
        )

        response.data = {
            'success': False,
            'code': response.status_code,
            'message': message,
            'timestamp': int(time.time()),
            'data': {'errors': error_payload}
        }
    else:
        logger.error(
            f"Unhandled API exception in {view_name} for user {user} on path {path}. Error: {exc}",
            exc_info=True
        )
        
        response_data = {
            'success': False,
            'code': status.HTTP_500_INTERNAL_SERVER_ERROR,
            'message': 'An unexpected server error occurred. Our team has been notified.',
            'timestamp': int(time.time()),
            'data': None
        }
        response = Response(response_data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return response