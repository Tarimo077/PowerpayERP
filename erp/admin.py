from django.contrib import admin
from .models import *

for model in [Organization,Department,Profile,Task,Timesheet,TimesheetEntry,LeaveAllocation,LeaveRequest,PaymentVoucher,PaymentVoucherLine,PaymentVoucherReceipt,ItemRequest,ItemRequestLine,ChatThread,ChatMembership,ChatInvitation,ChatMessage,ChatPresence,DocumentTemplate,Document,Notification,AuditLog,EmailOTP,UserInvite]:
    admin.site.register(model)
