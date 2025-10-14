import time
import logging
import json

logger = logging.getLogger(__name__)

class APILoggingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start_time = time.time()

        # Read request body and keep it for logging
        request_body = request.body.decode('utf-8', errors='ignore')

        response = self.get_response(request)

        duration = time.time() - start_time

        try:
            response_content = json.loads(response.content.decode('utf-8', errors='ignore'))
        except (json.JSONDecodeError, UnicodeDecodeError):
            response_content = "Non-JSON or binary response"

        logger.info({
            "message": "API Request/Response Log",
            "path": request.path,
            "method": request.method,
            "status_code": response.status_code,
            "duration_ms": round(duration * 1000, 2),
            "user": request.user.id if request.user.is_authenticated else "Anonymous",
            "request_body": request_body,
            "response_body": response_content,
        })

        return response