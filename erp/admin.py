from django.contrib import admin
from .models import *

for model in [Organization,Department,Profile,Task,Timesheet,TimesheetEntry,DocumentTemplate,Document,Notification,AuditLog,EmailOTP,UserInvite]: 
    admin.site.register(model)
