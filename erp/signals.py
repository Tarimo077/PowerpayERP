from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from .models import AuditLog


@receiver(user_logged_in)
def log_login(sender,request,user,**kwargs):
    p=getattr(user,"profile",None)
    AuditLog.objects.create(organization=getattr(p,"organization",None),actor=user,action="login",entity_type="user",entity_id=str(user.pk),ip_address=request.META.get("REMOTE_ADDR"))
