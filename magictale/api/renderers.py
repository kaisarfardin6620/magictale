import time
from rest_framework.renderers import JSONRenderer

class CustomJSONRenderer(JSONRenderer):
    def render(self, data, accepted_media_type=None, renderer_context=None):
        response = renderer_context['response']
        status_code = response.status_code

        if isinstance(data, dict) and 'success' in data or not (200 <= status_code < 300):
            return super().render(data, accepted_media_type, renderer_context)

        message = "Operation successful."
        response_data = data

        if isinstance(data, dict) and 'message' in data:
            message = data.pop('message')
            response_data = data if data else None

        elif status_code == 201:
            message = "Resource created successfully."
        elif status_code == 204:
            response_data = None 
        elif isinstance(data, dict) and 'token' in data:
            message = "Successfully Logged in."
    

        response_payload = {
            "success": True,
            "code": status_code,
            "message": message,
            "timestamp": int(time.time()),
            "data": response_data
        }

        return super().render(response_payload, accepted_media_type, renderer_context)