from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags

def send_html_email(subject,template,to,context):
    html=render_to_string(template,context); message=EmailMultiAlternatives(subject,strip_tags(html),settings.DEFAULT_FROM_EMAIL,[to]); message.attach_alternative(html,"text/html"); message.send()
def send_otp_email(user,code): send_html_email("Your PowerpayERP verification code","emails/otp.html",user.email,{"user":user,"otp":code})
def send_invite_email(invite):
    url=f"{settings.SITE_URL.rstrip('/')}/accept-invite/{invite.token}/"
    send_html_email("You're invited to PowerpayERP","emails/invite.html",invite.email,{"invite":invite,"invite_url":url,"organization":invite.organization.name})
