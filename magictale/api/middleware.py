import time
import logging
import json

logger = logging.getLogger(__name__)

class APILoggingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start_time = time.time()

        request_body_log = None
        if 'multipart/form-data' in request.content_type:
            request_body_log = "[Multipart form data]"
        elif request.body:
            try:
                request_body_log = json.loads(request.body.decode('utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError):
                request_body_log = "[Non-JSON body]"
        
        response = self.get_response(request)
        duration = time.time() - start_time
        status_code = response.status_code

        log_data = {
            "message": "API Request Log",
            "path": request.path,
            "method": request.method,
            "status_code": status_code,
            "duration_ms": round(duration * 1000, 2),
            "user": request.user.id if request.user.is_authenticated else "Anonymous",
            "request_body": request_body_log,
        }

        if 400 <= status_code < 600:
            log_data["message"] = "API Error Log"
            try:
                log_data["response_body"] = json.loads(response.content.decode('utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError):
                log_data["response_body"] = "[Non-JSON error response]"

        logger.info(log_data)
        return response