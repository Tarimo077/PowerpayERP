from django.contrib import admin

from .models import (
    AuditLog,
    ChatInvitation,
    ChatMembership,
    ChatMessage,
    ChatPresence,
    ChatThread,
    Department,
    Document,
    DocumentTemplate,
    EmailOTP,
    ItemRequest,
    ItemRequestLine,
    LeaveAllocation,
    LeaveRequest,
    Notification,
    OutboundEmail,
    Organization,
    PaymentVoucher,
    PaymentVoucherLine,
    PaymentVoucherReceipt,
    Profile,
    Task,
    Timesheet,
    TimesheetEntry,
    UserInvite,
)


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "organization",
        "actor",
        "action",
        "entity_type",
        "entity_id",
    )
    list_filter = ("action", "entity_type", "organization")
    search_fields = ("action", "entity_type", "entity_id", "actor__email")
    readonly_fields = (
        "organization",
        "actor",
        "action",
        "entity_type",
        "entity_id",
        "details",
        "ip_address",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


MODELS = [
    Organization,
    Department,
    Profile,
    Task,
    Timesheet,
    TimesheetEntry,
    LeaveAllocation,
    LeaveRequest,
    PaymentVoucher,
    PaymentVoucherLine,
    PaymentVoucherReceipt,
    ItemRequest,
    ItemRequestLine,
    ChatThread,
    ChatMembership,
    ChatInvitation,
    ChatMessage,
    ChatPresence,
    DocumentTemplate,
    Document,
    Notification,
    OutboundEmail,
    EmailOTP,
    UserInvite,
]

for model in MODELS:
    admin.site.register(model)
