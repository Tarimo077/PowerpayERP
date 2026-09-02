from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse
from django.urls import include, path
from django.views.decorators.http import require_GET


@require_GET
def healthcheck(request):
    try:
        connection.ensure_connection()
        cache.set("powerpayerp-healthcheck", "ok", timeout=10)
        cache_ok = cache.get("powerpayerp-healthcheck") == "ok"
    except Exception:
        return JsonResponse({"status": "unavailable"}, status=503)
    return JsonResponse(
        {"status": "ok" if cache_ok else "unavailable"}, status=200 if cache_ok else 503
    )


urlpatterns = [
    path("healthz/", healthcheck, name="healthcheck"),
    path("admin/", admin.site.urls),
    path("api/", include("erp.api_urls", namespace="api")),
    path("", include("erp.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
