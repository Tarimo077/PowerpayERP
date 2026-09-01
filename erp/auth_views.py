import secrets
from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.mail import BadHeaderError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from .emailing import send_otp_email
from .forms import EmailLoginForm, OTPForm, SetInvitePasswordForm
from .models import AuditLog, EmailOTP, Notification, Profile, UserInvite

MAX_OTP_ATTEMPTS = 5
MAX_LOGIN_ATTEMPTS = 5
LOGIN_LOCK_SECONDS = 15 * 60
OTP_RESEND_SECONDS = 60


def _client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return (
        forwarded.split(",")[0].strip()
        if forwarded
        else request.META.get("REMOTE_ADDR", "unknown")
    )


def _login_cache_key(request, email):
    return f"login-attempt:{_client_ip(request)}:{email.strip().lower()}"


def login_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = EmailLoginForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"].strip().lower()
        attempt_key = _login_cache_key(request, email)
        attempts = cache.get(attempt_key, 0)
        if attempts >= MAX_LOGIN_ATTEMPTS:
            messages.error(
                request, "Too many sign-in attempts. Try again in 15 minutes."
            )
            return render(
                request, "registration/login.html", {"form": form}, status=429
            )

        user = authenticate(
            request, email=email, password=form.cleaned_data["password"]
        )
        if user:
            cache.delete(attempt_key)
            EmailOTP.objects.filter(user=user).delete()
            code = f"{secrets.randbelow(900000)+100000:06d}"
            otp = EmailOTP(user=user)
            otp.set_code(code)
            otp.save()
            if not send_otp_email(user, code):
                otp.delete()
                messages.error(
                    request,
                    "The verification email could not be sent. Please try again shortly.",
                )
                return render(
                    request, "registration/login.html", {"form": form}, status=503
                )
            request.session["otp_user_id"] = user.pk
            request.session.set_expiry(600)
            messages.success(
                request, "A verification code has been sent to your email."
            )
            return redirect("verify_otp")
        cache.set(attempt_key, attempts + 1, LOGIN_LOCK_SECONDS)
        messages.error(request, "Invalid email or password.")
    return render(request, "registration/login.html", {"form": form})


def verify_otp(request):
    user_id = request.session.get("otp_user_id")
    if not user_id:
        return redirect("login")
    otp = get_object_or_404(EmailOTP, user_id=user_id)
    form = OTPForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if otp.is_expired():
            messages.error(request, "That code has expired. Request a new one.")
        elif otp.attempts >= MAX_OTP_ATTEMPTS:
            messages.error(request, "Too many attempts. Request a new code.")
        elif otp.matches(form.cleaned_data["otp"]):
            user = otp.user
            login(request, user, backend="erp.auth_backends.EmailBackend")
            request.session.pop("otp_user_id", None)
            request.session["otp_verified"] = True
            otp.delete()
            p = getattr(user, "profile", None)
            AuditLog.objects.create(
                organization=getattr(p, "organization", None),
                actor=user,
                action="otp_login",
                entity_type="user",
                entity_id=str(user.pk),
                ip_address=request.META.get("REMOTE_ADDR"),
            )
            return redirect("dashboard")
        else:
            otp.attempts += 1
        otp.save(update_fields=["attempts"])
        messages.error(
            request,
            f"Invalid code. {MAX_OTP_ATTEMPTS-otp.attempts} attempts remaining.",
        )
    return render(
        request, "registration/verify_otp.html", {"form": form, "email": otp.user.email}
    )


@require_POST
def resend_otp(request):
    user_id = request.session.get("otp_user_id")
    if not user_id:
        return redirect("login")
    user = get_object_or_404(User, pk=user_id)
    resend_key = f"otp-resend:{user.pk}:{_client_ip(request)}"
    if cache.get(resend_key):
        messages.info(request, "Please wait one minute before requesting another code.")
        return redirect("verify_otp")
    EmailOTP.objects.filter(user=user).delete()
    code = f"{secrets.randbelow(900000)+100000:06d}"
    otp = EmailOTP(user=user)
    otp.set_code(code)
    otp.save()
    if not send_otp_email(user, code):
        otp.delete()
        messages.error(
            request,
            "The verification email could not be sent. Please try again shortly.",
        )
        return redirect("verify_otp")
    cache.set(resend_key, True, OTP_RESEND_SECONDS)
    messages.success(request, "A new verification code has been sent.")
    return redirect("verify_otp")


@transaction.atomic
def accept_invite(request, token):
    invite = get_object_or_404(UserInvite, token=token)
    if not invite.is_valid():
        messages.error(request, "This invitation has expired or was already used.")
        return redirect("login")
    form = SetInvitePasswordForm(request.POST or None, email=invite.email)
    if request.method == "POST" and form.is_valid():
        user = User.objects.create_user(
            username=invite.email,
            email=invite.email,
            password=form.cleaned_data["password1"],
            first_name=form.cleaned_data["first_name"],
            last_name=form.cleaned_data["last_name"],
        )
        Profile.objects.create(
            user=user,
            organization=invite.organization,
            role=invite.role,
            department=invite.department,
            manager=invite.manager,
            employee_id=invite.employee_id,
            position=invite.position,
        )
        invite.is_used = True
        invite.save(update_fields=["is_used"])
        Notification.objects.create(
            user=invite.invited_by,
            title="Invitation accepted",
            message=f"{invite.email} joined {invite.organization.name}",
        )
        messages.success(request, "Your account is active. Sign in to continue.")
        return redirect("login")
    return render(
        request, "registration/accept_invite.html", {"form": form, "invite": invite}
    )
