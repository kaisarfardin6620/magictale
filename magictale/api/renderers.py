import ujson
import time
from rest_framework.renderers import JSONRenderer
from django.utils.translation import gettext as _

class CustomJSONRenderer(JSONRenderer):
    def render(self, data, accepted_media_type=None, renderer_context=None):
        response = renderer_context['response']
        status_code = response.status_code

        if isinstance(data, dict) and 'success' in data:
            return ujson.dumps(data).encode('utf-8')

        is_success = (200 <= status_code < 300)
        message = _("Operation successful.") if is_success else _("Operation failed.")
        response_data = data

        if is_success:
            if isinstance(data, dict) and 'message' in data:
                message = data.pop('message')
                response_data = data if data else None
            elif status_code == 201:
                message = _("Resource created successfully.")
            elif status_code == 204:
                response_data = None 
            elif isinstance(data, dict) and 'token' in data:
                message = _("Successfully Logged in.")
        
        response_payload = {
            "success": is_success,
            "code": status_code,
            "message": str(message),
            "timestamp": int(time.time()),
            "data": response_data if is_success else None,
            "errors": data if not is_success else None
        }

        return ujson.dumps(response_payload).encode('utf-8')