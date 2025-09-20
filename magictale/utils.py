import time
from rest_framework.response import Response

def api_response(success, code, message, data=None):
    return Response({
        "success": success,
        "code": code,
        "message": message,
        "timestamp": int(time.time()),
        "data": data
    }, status=code)
