def erp_context(request):
    if not request.user.is_authenticated: 
        return {}
    p=getattr(request.user,"profile",None)
    return {"current_profile":p,"current_org":getattr(p,"organization",None),"unread_notifications":request.user.notifications.filter(is_read=False).count()}
