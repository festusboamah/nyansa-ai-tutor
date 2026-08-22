from django.conf import settings
from django.db import connection
from django.http import JsonResponse
from django.shortcuts import render


def service_worker_view(request):
    response = render(
        request, "service-worker.js", {"static_url": settings.STATIC_URL},
        content_type="application/javascript",
    )
    response["Cache-Control"] = "no-cache"
    return response


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
