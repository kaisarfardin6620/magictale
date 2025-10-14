import time
from rest_framework.renderers import JSONRenderer

class CustomJSONRenderer(JSONRenderer):
    """
    Custom JSON renderer for Django Rest Framework that formats success responses
    into a standard structure. Error responses are expected to be handled by the
    custom_exception_handler.
    """
    def render(self, data, accepted_media_type=None, renderer_context=None):
        response = renderer_context['response']
        status_code = response.status_code

        # If the response data is already formatted (e.g., by the exception handler),
        # or if it's an error status code, pass it through without re-formatting.
        if isinstance(data, dict) and 'success' in data or not (200 <= status_code < 300):
            return super().render(data, accepted_media_type, renderer_context)

        message = "Operation successful."
        if status_code == 201:
            message = "Resource created successfully."
        
        # Handle cases where the data is not a dict (e.g., DELETE returning 204 No Content)
        if data is None:
            data = None # Explicitly set data to None for 204 or other cases

        # Special case for login response to match the user's requested message
        if isinstance(data, dict) and 'token' in data and 'refresh_token' in data:
            message = "Successfully Logged in."

        response_data = {
            "success": True,
            "code": status_code,
            "message": message,
            "timestamp": int(time.time()),
            "data": data
        }

        return super().render(response_data, accepted_media_type, renderer_context)