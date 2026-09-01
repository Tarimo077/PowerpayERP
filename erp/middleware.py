from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.utils import timezone
from datetime import timedelta
from .models import ChatPresence


class ActiveOrganizationMiddleware:
    """End sessions for organization users whose tenant has been suspended."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and not request.user.is_superuser:
            profile = getattr(request.user, "profile", None)
            if profile and profile.organization and not profile.organization.is_active:
                logout(request)
                messages.error(
                    request,
                    "Your organization workspace has been suspended. Contact the platform administrator.",
                )
                return redirect("login")
        return self.get_response(request)


class ChatPresenceMiddleware:
    """Refresh authenticated employee presence without writing on every request."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and not request.user.is_superuser:
            profile = getattr(request.user, "profile", None)
            if profile:
                presence, _ = ChatPresence.objects.get_or_create(profile=profile)
                now = timezone.now()
                if presence.last_seen < now - timedelta(seconds=30):
                    ChatPresence.objects.filter(pk=presence.pk).update(last_seen=now)
        return self.get_response(request)
