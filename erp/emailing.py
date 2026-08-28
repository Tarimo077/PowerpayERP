from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags

def send_html_email(subject,template,to,context):
    html=render_to_string(template,context)
    message=EmailMultiAlternatives(subject,strip_tags(html),settings.DEFAULT_FROM_EMAIL,[to])
    message.attach_alternative(html,"text/html")
    return message.send()


def send_otp_email(user,code): 
    send_html_email("Your PowerpayERP verification code","emails/otp.html",user.email,{"user":user,"otp":code})


def send_invite_email(invite):
    url=f"{settings.SITE_URL.rstrip('/')}/accept-invite/{invite.token}/"
    send_html_email("You're invited to PowerpayERP","emails/invite.html",invite.email,{"invite":invite,"invite_url":url,"organization":invite.organization.name})


def send_task_assignment_email(task):
    if not task.assigned_to.user.email: 
        return 0
    url=f"{settings.SITE_URL.rstrip('/')}/tasks/{task.pk}/"
    return send_html_email(f"New task assigned: {task.title}","emails/task_assigned.html",task.assigned_to.user.email,{"task":task,"task_url":url,"assignee":task.assigned_to,"assigned_by":task.created_by})


def send_leave_email(leave_request,event):
    recipient=leave_request.requested_approver.user if event=="submitted" else leave_request.employee.user
    if not recipient.email: 
        return 0
    url=f"{settings.SITE_URL.rstrip('/')}/leave/"
    subject=f"Leave request from {leave_request.employee}" if event=="submitted" else f"Leave request {leave_request.get_status_display().lower()}"
    return send_html_email(subject,"emails/leave.html",recipient.email,{"leave":leave_request,"recipient":recipient,"event":event,"leave_url":url})
