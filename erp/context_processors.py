from .models import ChatInvitation, ChatMembership

def erp_context(request):
    if not request.user.is_authenticated: 
        return {}
    p=getattr(request.user,"profile",None)
    unread_chats=0
    if p:
        unread_chats=ChatInvitation.objects.filter(invitee=p,status="pending").count()
        for membership in ChatMembership.objects.filter(profile=p).select_related("thread"):
            unread_chats += membership.thread.messages.filter(created_at__gt=membership.last_read_at).exclude(sender=p).count()
    notifications=request.user.notifications.all()
    return {
        "current_profile":p,
        "current_org":getattr(p,"organization",None),
        "unread_notifications":notifications.filter(is_read=False).count(),
        "recent_notifications":notifications[:6],
        "unread_chat_count":unread_chats}
