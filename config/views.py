from django.db import connection
from django.http import JsonResponse


def health_live(request):
    return JsonResponse({"status": "ok", "service": "nyansa-web"})


def health_ready(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        return JsonResponse({"status": "unavailable", "database": "error"}, status=503)
    return JsonResponse({"status": "ok", "database": "ready"})
