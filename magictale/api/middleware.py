import time
import logging
import json
from urllib.parse import parse_qs, urlencode

logger = logging.getLogger(__name__)

class APILoggingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start_time = time.time()
        
        path = request.path
        if request.META.get('QUERY_STRING'):
            try:
                query_dict = parse_qs(request.META['QUERY_STRING'])
                if 'token' in query_dict:
                    query_dict['token'] = ['***']
                sanitized_query = urlencode(query_dict, doseq=True)
                path += f"?{sanitized_query}"
            except Exception:
                path += "?<malformed_query>"

        response = self.get_response(request)
        duration = time.time() - start_time
        status_code = response.status_code

        log_message = f"[{request.method}] {path} - {status_code} ({round(duration * 1000, 2)}ms)"

        if status_code >= 400:
            error_details = {
                "user": request.user.id if request.user.is_authenticated else "Anon",
            }
            try:
                if response.content:
                    error_details["response"] = json.loads(response.content.decode('utf-8'))
            except:
                error_details["response"] = "Binary/Non-JSON Content"
            
            logger.error(f"{log_message} | Details: {error_details}")
        else:
            logger.info(log_message)

        return response