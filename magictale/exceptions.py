import logging
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status

logger = logging.getLogger(__name__)

def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if response is not None:
        
        if response.status_code == 400:
            error_message = "Invalid input provided. Please check the details below."
            errors = response.data
        elif response.status_code == 401:
            error_message = response.data.get('detail', "Authentication credentials were not provided or were invalid.")
            errors = None
        elif response.status_code == 403:
            error_message = response.data.get('detail', "You do not have permission to perform this action.")
            errors = None
        elif response.status_code == 404:
            error_message = response.data.get('detail', "The requested resource was not found.")
            errors = None
        else:
            error_message = "An error occurred."
            errors = response.data.get('detail') if isinstance(response.data, dict) else response.data

        custom_response_data = {
            'success': False,
            'message': error_message,
            'errors': errors
        }
        
        response.data = custom_response_data
    
    else:
        view_name = context['view'].__class__.__name__ if 'view' in context else 'unknown_view'
        logger.error(
            f"Unhandled API exception in view '{view_name}': {exc}",
            exc_info=True
        )
        
        custom_response_data = {
            'success': False,
            'message': 'An unexpected server error occurred. Our team has been notified.',
            'errors': None
        }
        response = Response(custom_response_data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return response