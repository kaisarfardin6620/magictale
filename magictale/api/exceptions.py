# magictale/api/exceptions.py

import time
from rest_framework.views import exception_handler
from rest_framework.response import Response

def custom_exception_handler(exc, context):
    # First, get the standard error response from DRF
    response = exception_handler(exc, context)

    # If DRF did not handle the exception, re-raise it
    if response is None:
        return None

    # Prepare the custom response format
    # The 'data' will contain the specific error details from DRF
    custom_response = {
        "success": False,
        "code": response.status_code,
        "message": "An error occurred.", # Default message
        "timestamp": int(time.time()),
        "data": response.data
    }

    # Use a more specific message if available
    if isinstance(response.data, dict):
        # For validation errors, the message is often in a 'detail' key
        if 'detail' in response.data:
            custom_response['message'] = response.data['detail']
        else:
            # For other errors, try to create a summary
            first_key = next(iter(response.data))
            first_error = response.data[first_key]
            if isinstance(first_error, list):
                custom_response['message'] = f"{first_key}: {first_error[0]}"
            else:
                custom_response['message'] = f"{first_key}: {first_error}"
    
    # Replace the original data with our custom structured data
    response.data = custom_response
    
    return response