from django.conf import settings


def deployment_mode(request):
    return {"nyansa_demo_mode": settings.NYANSA_DEMO_MODE}
