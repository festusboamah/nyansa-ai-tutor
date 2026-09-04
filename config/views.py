from django.conf import settings
from django.db import connection
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.urls import reverse


ROBOTS_TXT = """User-agent: *
Disallow: /accounts/
Allow: /accounts/signup/
Allow: /accounts/signup/school/
Allow: /accounts/login/
Disallow: /admin/
Disallow: /schools/
Disallow: /dashboard/
Disallow: /courses/
Disallow: /quizzes/
Disallow: /tutor/
Disallow: /gradebook/
Disallow: /attendance/
Disallow: /reports/
Disallow: /guardian/
Disallow: /communications/
Disallow: /finance/
Disallow: /analytics/
Disallow: /mastery/
Disallow: /integrations/
Disallow: /billing/
Disallow: /ai-usage/

Sitemap: {sitemap_url}
"""

# (url name, priority) for the pages that are genuinely public and worth a
# search engine indexing - everything else needs a login.
SITEMAP_URL_NAMES = (
    ("home", "1.0"),
    ("signup", "0.8"),
    ("school_signup", "0.8"),
    ("login", "0.3"),
    ("terms", "0.2"),
    ("privacy", "0.2"),
)


def robots_txt_view(request):
    sitemap_url = request.build_absolute_uri(reverse("sitemap_xml"))
    return HttpResponse(ROBOTS_TXT.format(sitemap_url=sitemap_url), content_type="text/plain")


def sitemap_xml_view(request):
    urls = "".join(
        f"<url><loc>{request.build_absolute_uri(reverse(name))}</loc><priority>{priority}</priority></url>"
        for name, priority in SITEMAP_URL_NAMES
    )
    xml = f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>'
    return HttpResponse(xml, content_type="application/xml")


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
