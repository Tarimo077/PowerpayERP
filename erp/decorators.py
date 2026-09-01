from functools import wraps
from django.contrib import messages
from django.shortcuts import redirect


def roles_allowed(*roles):
    def deco(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if request.user.is_superuser or (
                hasattr(request.user, "profile") and request.user.profile.role in roles
            ):
                return view(request, *args, **kwargs)

            messages.error(
                request, "You do not have permission to perform that action."
            )
            return redirect("dashboard")

        return wrapper

    return deco
