from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.models import User


class EmailBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, email=None, **kwargs):
        identifier = (email or username or "").strip()
        try:
            user = User.objects.get(email__iexact=identifier)
        except (User.DoesNotExist, User.MultipleObjectsReturned):
            return None
        if not user.check_password(password) or not self.user_can_authenticate(user):
            return None
        profile = getattr(user, "profile", None)
        if profile and profile.organization and not profile.organization.is_active:
            return None
        return user
