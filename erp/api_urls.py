from django.urls import include, path
from rest_framework.authentication import SessionAuthentication
from rest_framework.routers import DefaultRouter
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from .api import (
    DocumentViewSet,
    IsPlatformAdminOrOrganizationAdmin,
    TaskViewSet,
    TimesheetViewSet,
)
from .api_auth import (
    AdminTokenObtainPairView,
    DocumentedTokenRefreshView,
    DocumentedTokenVerifyView,
)

router = DefaultRouter()
router.register("tasks", TaskViewSet, basename="api-task")
router.register("timesheets", TimesheetViewSet, basename="api-timesheet")
router.register("documents", DocumentViewSet, basename="api-document")

app_name = "api"

urlpatterns = [
    path("token/", AdminTokenObtainPairView.as_view(), name="token-obtain-pair"),
    path("token/refresh/", DocumentedTokenRefreshView.as_view(), name="token-refresh"),
    path("token/verify/", DocumentedTokenVerifyView.as_view(), name="token-verify"),
    path(
        "schema/",
        SpectacularAPIView.as_view(
            permission_classes=[IsPlatformAdminOrOrganizationAdmin],
            authentication_classes=[SessionAuthentication],
        ),
        name="schema",
    ),
    path(
        "docs/",
        SpectacularSwaggerView.as_view(
            url_name="api:schema",
            permission_classes=[IsPlatformAdminOrOrganizationAdmin],
            authentication_classes=[SessionAuthentication],
        ),
        name="swagger-ui",
    ),
    path("", include(router.urls)),
]
