from django.contrib.auth import get_user_model
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    TokenVerifyView,
)
from drf_spectacular.utils import extend_schema


class AdminTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Issue JWTs only to organization admins and platform superusers."""

    username_field = "email"

    def validate(self, attrs):
        email = attrs.get("email", "").strip()
        user = get_user_model().objects.filter(email__iexact=email).first()
        if user:
            attrs["email"] = user.email
        data = super().validate(attrs)
        profile = getattr(self.user, "profile", None)
        allowed = self.user.is_superuser or bool(
            profile
            and profile.role == "admin"
            and profile.organization_id
            and profile.organization.is_active
        )
        if not allowed:
            raise AuthenticationFailed(
                "API tokens are available only to organization administrators and platform administrators."
            )
        data["access_expires_in"] = 24 * 60 * 60
        data["refresh_expires_in"] = 3 * 24 * 60 * 60
        return data

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["email"] = user.email
        token["platform_admin"] = user.is_superuser
        profile = getattr(user, "profile", None)
        token["role"] = "platform_admin" if user.is_superuser else profile.role
        token["organization_id"] = (
            None if user.is_superuser else profile.organization_id
        )
        return token


class AdminTokenObtainPairView(TokenObtainPairView):
    serializer_class = AdminTokenObtainPairSerializer
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Authentication"],
        summary="Get an access and refresh token",
        description=(
            "Submit an organization administrator or platform administrator email and "
            "password. Returns a Bearer access token valid for 24 hours and a rotating "
            "refresh token valid for 3 days. Employees and managers cannot obtain API tokens."
        ),
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


class DocumentedTokenRefreshView(TokenRefreshView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Authentication"],
        summary="Refresh an access token",
        description=(
            "Submit a valid refresh token to obtain a new 24-hour access token. The "
            "refresh token rotates, the previous refresh token is blacklisted, and the "
            "replacement remains within the configured 3-day refresh lifetime."
        ),
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


class DocumentedTokenVerifyView(TokenVerifyView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Authentication"],
        summary="Verify a token",
        description=(
            "Checks whether an access or refresh token is correctly signed and has not "
            "expired. A successful response has an empty body and HTTP 200 status."
        ),
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)
