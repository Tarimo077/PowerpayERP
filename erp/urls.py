from django.contrib.auth import views as auth
from django.urls import path
from . import views
from . import auth_views

urlpatterns = [
    path("", views.home, name="home"),
    path("register/", views.register, name="register"),
    path("login/", auth_views.login_view, name="login"),
    path("verify-otp/", auth_views.verify_otp, name="verify_otp"),
    path("resend-otp/", auth_views.resend_otp, name="resend_otp"),
    path("accept-invite/<uuid:token>/", auth_views.accept_invite, name="accept_invite"),
    path(
        "password-reset/",
        auth.PasswordResetView.as_view(
            template_name="registration/password_reset.html",
            email_template_name="emails/password_reset.txt",
            html_email_template_name="emails/password_reset.html",
            subject_template_name="emails/password_reset_subject.txt",
        ),
        name="password_reset",
    ),
    path(
        "password-reset/done/",
        auth.PasswordResetDoneView.as_view(
            template_name="registration/password_reset_done.html"
        ),
        name="password_reset_done",
    ),
    path(
        "reset/<uidb64>/<token>/",
        auth.PasswordResetConfirmView.as_view(
            template_name="registration/password_reset_confirm.html"
        ),
        name="password_reset_confirm",
    ),
    path(
        "reset/done/",
        auth.PasswordResetCompleteView.as_view(
            template_name="registration/password_reset_complete.html"
        ),
        name="password_reset_complete",
    ),
    path("logout/", auth.LogoutView.as_view(), name="logout"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("profile/", views.profile_page, name="profile"),
    path("search/", views.global_search, name="global_search"),
    path("storyboard/", views.storyboard, name="storyboard"),
    path("chats/", views.chats, name="chats"),
    path("chats/direct/new/", views.direct_chat_create, name="direct_chat_create"),
    path("chats/groups/new/", views.group_chat_create, name="group_chat_create"),
    path(
        "chats/invitations/<int:pk>/<str:action>/",
        views.chat_invitation_action,
        name="chat_invitation_action",
    ),
    path(
        "chats/messages/<int:pk>/attachment/",
        views.chat_attachment,
        name="chat_attachment",
    ),
    path("chats/<int:pk>/", views.chat_detail, name="chat_detail"),
    path("chats/<int:pk>/messages/", views.chat_message_feed, name="chat_message_feed"),
    path("chats/<int:pk>/invite/", views.chat_invite, name="chat_invite"),
    path("chats/<int:pk>/leave/", views.chat_leave, name="chat_leave"),
    path(
        "platform/organizations/",
        views.platform_organizations,
        name="platform_organizations",
    ),
    path(
        "platform/organizations/<int:pk>/",
        views.platform_organization_detail,
        name="platform_organization_detail",
    ),
    path(
        "platform/organizations/<int:pk>/status/",
        views.platform_organization_status,
        name="platform_organization_status",
    ),
    path("platform/users/", views.platform_users, name="platform_users"),
    path(
        "platform/users/<int:pk>/status/",
        views.platform_user_status,
        name="platform_user_status",
    ),
    path("platform/activity/", views.platform_activity, name="platform_activity"),
    path("tasks/", views.tasks, name="tasks"),
    path("tasks/new/", views.task_create, name="task_create"),
    path("tasks/<int:pk>/", views.task_detail, name="task_detail"),
    path("tasks/<int:pk>/attachment/", views.task_attachment, name="task_attachment"),
    path("tasks/<int:pk>/status/", views.task_status, name="task_status"),
    path("timesheets/", views.timesheets, name="timesheets"),
    path("timesheets/new/", views.timesheet_create, name="timesheet_create"),
    path("timesheets/request/", views.timesheet_request, name="timesheet_request"),
    path("timesheets/<int:pk>/", views.timesheet_detail, name="timesheet_detail"),
    path("timesheets/<int:pk>/edit/", views.timesheet_edit, name="timesheet_edit"),
    path(
        "timesheets/<int:pk>/delete/", views.timesheet_delete, name="timesheet_delete"
    ),
    path(
        "timesheets/<int:pk>/entries/<int:entry_pk>/edit/",
        views.timesheet_entry_edit,
        name="timesheet_entry_edit",
    ),
    path(
        "timesheets/<int:pk>/entries/<int:entry_pk>/delete/",
        views.timesheet_entry_delete,
        name="timesheet_entry_delete",
    ),
    path(
        "timesheets/<int:pk>/action/", views.timesheet_action, name="timesheet_action"
    ),
    path(
        "timesheets/<int:pk>/signature/",
        views.timesheet_signature_upload,
        name="timesheet_signature_upload",
    ),
    path(
        "timesheets/<int:pk>/signature/<str:kind>/",
        views.timesheet_signature,
        name="timesheet_signature",
    ),
    path(
        "timesheets/<int:pk>/review/", views.timesheet_review, name="timesheet_review"
    ),
    path(
        "timesheets/<int:pk>/export/<str:fmt>/",
        views.timesheet_export,
        name="timesheet_export",
    ),
    path(
        "timesheets/<int:pk>/export-year/",
        views.timesheet_export_year,
        name="timesheet_export_year",
    ),
    path("leave/", views.leave_dashboard, name="leave_dashboard"),
    path(
        "leave/allocations/new/",
        views.leave_allocation_create,
        name="leave_allocation_create",
    ),
    path(
        "leave/requests/new/", views.leave_request_create, name="leave_request_create"
    ),
    path(
        "leave/requests/<int:pk>/review/",
        views.leave_request_review,
        name="leave_request_review",
    ),
    path("payment-vouchers/", views.payment_vouchers, name="payment_vouchers"),
    path(
        "payment-vouchers/new/",
        views.payment_voucher_create,
        name="payment_voucher_create",
    ),
    path(
        "payment-vouchers/<int:pk>/",
        views.payment_voucher_detail,
        name="payment_voucher_detail",
    ),
    path(
        "payment-vouchers/<int:pk>/receipts/add/",
        views.payment_voucher_receipt_add,
        name="payment_voucher_receipt_add",
    ),
    path(
        "payment-vouchers/<int:pk>/receipts/<int:receipt_pk>/",
        views.payment_voucher_receipt,
        name="payment_voucher_receipt",
    ),
    path(
        "payment-vouchers/<int:pk>/action/<str:action>/",
        views.payment_voucher_action,
        name="payment_voucher_action",
    ),
    path(
        "payment-vouchers/<int:pk>/pdf/",
        views.payment_voucher_pdf,
        name="payment_voucher_pdf",
    ),
    path("item-requests/", views.item_requests, name="item_requests"),
    path("item-requests/new/", views.item_request_create, name="item_request_create"),
    path(
        "item-requests/<int:pk>/", views.item_request_detail, name="item_request_detail"
    ),
    path(
        "item-requests/<int:pk>/action/<str:action>/",
        views.item_request_action,
        name="item_request_action",
    ),
    path(
        "item-requests/<int:pk>/export/<str:fmt>/",
        views.item_request_export,
        name="item_request_export",
    ),
    path("employees/", views.employees, name="employees"),
    path("employees/new/", views.employee_create, name="employee_create"),
    path(
        "employees/<int:pk>/access/<str:action>/",
        views.employee_access_action,
        name="employee_access_action",
    ),
    path("departments/", views.departments, name="departments"),
    path("documents/", views.documents, name="documents"),
    path("documents/upload/", views.document_upload, name="document_upload"),
    path(
        "documents/<int:pk>/download/",
        views.document_download,
        name="document_download",
    ),
    path("templates/", views.templates, name="templates"),
    path(
        "templates/<int:pk>/download/",
        views.template_download,
        name="template_download",
    ),
    path("notifications/", views.notifications, name="notifications"),
    path(
        "notifications/read-all/",
        views.notifications_read_all,
        name="notifications_read_all",
    ),
    path(
        "notifications/<int:pk>/read/",
        views.notification_read,
        name="notification_read",
    ),
    path("audit/", views.audit_logs, name="audit_logs"),
]
