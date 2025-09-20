# magictale/api/renderers.py

import time
from rest_framework.renderers import JSONRenderer

class CustomJSONRenderer(JSONRenderer):
    """
    A custom renderer to create a standard API response structure.
    """
    def render(self, data, accepted_media_type=None, renderer_context=None):
        response = renderer_context['response']
        
        # Determine the success status based on the HTTP status code
        success = 200 <= response.status_code < 300

        # This structure will be used for all successful responses
        # Errors are handled by the custom exception handler
        if success:
            response_data = {
                "success": True,
                "code": response.status_code,
                "message": data.pop('message', "Success") if isinstance(data, dict) else "Success",
                "timestamp": int(time.time()),
                "data": data
            }
        else:
            # For non-successful responses, the exception handler will format it.
            # We just pass the data through as is.
            response_data = data

        # Call the parent class's render method to serialize the data to JSON
        return super().render(response_data, accepted_media_type, renderer_context)