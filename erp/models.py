from django.contrib.auth.models import User
from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from datetime import timedelta
import uuid


def current_year():
    return timezone.localdate().year


class TimeStamped(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Organization(TimeStamped):
    name = models.CharField(max_length=180)
    slug = models.SlugField(unique=True)
    business_email = models.EmailField()
    phone = models.CharField(max_length=40, blank=True)
    address = models.TextField(blank=True)
    industry = models.CharField(max_length=100, blank=True)
    logo = models.ImageField(upload_to="organization_logos/", blank=True, null=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Department(TimeStamped):
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="departments"
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "name"], name="unique_department_per_org"
            )
        ]

    def __str__(self):
        return self.name


class Profile(TimeStamped):
    ROLE_CHOICES = [
        ("admin", "Organization admin"),
        ("manager", "Manager"),
        ("employee", "Employee"),
    ]
    EMPLOYMENT_STATUS_CHOICES = [
        ("active", "Active"),
        ("suspended", "Suspended"),
        ("removed", "Removed"),
    ]
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="profiles",
        null=True,
        blank=True,
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="employee")
    employee_id = models.CharField(max_length=50, blank=True)
    phone = models.CharField(max_length=40, blank=True)
    position = models.CharField(max_length=120, blank=True)
    department = models.ForeignKey(
        Department,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="members",
    )
    manager = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="direct_reports",
    )
    hire_date = models.DateField(null=True, blank=True)
    employment_status = models.CharField(
        max_length=20,
        choices=EMPLOYMENT_STATUS_CHOICES,
        default="active",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "employee_id"],
                condition=~models.Q(employee_id=""),
                name="unique_employee_id_per_org",
            )
        ]

    def clean(self):
        if (
            self.department_id
            and self.department.organization_id != self.organization_id
        ):
            raise ValidationError("Department belongs to another organization.")

        if self.manager_id and self.manager.organization_id != self.organization_id:
            raise ValidationError("Manager belongs to another organization.")
        if self.manager_id and self.manager_id == self.pk:
            raise ValidationError("An employee cannot be their own manager.")
        seen = {self.pk}
        current = self.manager if self.manager_id else None
        while current:
            if current.pk in seen:
                raise ValidationError("The reporting hierarchy cannot contain a cycle.")
            seen.add(current.pk)
            current = current.manager

    def __str__(self):
        return self.user.get_full_name() or self.user.username


class TenantModel(TimeStamped):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)

    class Meta:
        abstract = True


class Task(TenantModel):
    STATUSES = [
        (x, x.replace("_", " ").title())
        for x in [
            "pending",
            "assigned",
            "in_progress",
            "submitted",
            "approved",
            "rejected",
            "completed",
        ]
    ]
    PRIORITIES = [(x, x.title()) for x in ["low", "medium", "high", "urgent"]]
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    instructions = models.TextField(blank=True)
    assigned_to = models.ForeignKey(
        Profile, on_delete=models.PROTECT, related_name="tasks"
    )
    department = models.ForeignKey(
        Department,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="tasks",
    )
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="created_tasks"
    )
    priority = models.CharField(max_length=10, choices=PRIORITIES, default="medium")
    status = models.CharField(max_length=20, choices=STATUSES, default="assigned")
    start_date = models.DateField(default=timezone.localdate)
    due_date = models.DateField()
    actual_started_at = models.DateTimeField(null=True, blank=True)
    actual_completed_at = models.DateTimeField(null=True, blank=True)
    attachment = models.FileField(upload_to="task_attachments/%Y/%m/", blank=True)

    def clean(self):
        if (
            self.assigned_to_id
            and self.assigned_to.organization_id != self.organization_id
        ):
            raise ValidationError("Assignee belongs to another organization.")

    @property
    def is_overdue(self):
        return self.due_date < timezone.localdate() and self.status not in [
            "approved",
            "completed",
        ]

    def save(self, *args, **kwargs):
        previous_status = (
            Task.objects.filter(pk=self.pk).values_list("status", flat=True).first()
            if self.pk
            else None
        )
        now = timezone.now()
        timestamp_fields = []
        if (
            self.status in ["in_progress", "submitted", "approved", "completed"]
            and not self.actual_started_at
            and previous_status != self.status
        ):
            self.actual_started_at = now
            timestamp_fields.append("actual_started_at")
        if (
            self.status in ["approved", "completed"]
            and not self.actual_completed_at
            and previous_status != self.status
        ):
            self.actual_completed_at = now
            timestamp_fields.append("actual_completed_at")
        if kwargs.get("update_fields") is not None and timestamp_fields:
            kwargs["update_fields"] = set(kwargs["update_fields"]) | set(
                timestamp_fields
            )
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class Timesheet(TenantModel):
    STATUSES = [
        ("draft", "Draft"),
        ("submitted", "Submitted"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    ]
    employee = models.ForeignKey(
        Profile, on_delete=models.PROTECT, related_name="timesheets"
    )
    period_start = models.DateField()
    period_end = models.DateField()
    status = models.CharField(max_length=20, choices=STATUSES, default="draft")
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_timesheets",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_notes = models.TextField(blank=True)
    requested_approver = models.ForeignKey(
        Profile,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="timesheets_to_approve",
    )
    request_task = models.OneToOneField(
        Task,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="requested_timesheet",
    )
    service_contract = models.TextField(blank=True)
    financing = models.CharField(max_length=240, blank=True)
    contract_number = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, blank=True)
    place_of_assignment = models.CharField(max_length=180, blank=True)
    initial_budget_days = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )
    expert_signature = models.ImageField(
        upload_to="timesheet_signatures/%Y/%m/", blank=True
    )
    manager_signature = models.ImageField(
        upload_to="timesheet_signatures/%Y/%m/", blank=True
    )
    consultant_name = models.CharField(max_length=180, blank=True)
    consultant_signature = models.ImageField(
        upload_to="timesheet_signatures/%Y/%m/", blank=True
    )

    class Meta:
        ordering = ["-period_start"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "employee", "period_start"],
                name="unique_monthly_timesheet_per_employee",
            )
        ]

    @property
    def total_hours(self):
        return sum(e.hours for e in self.entries.all())

    @property
    def total_days_worked(self):
        return sum(e.days_worked for e in self.entries.all())

    def __str__(self):
        return f"{self.employee} · {self.period_start}"


class TimesheetEntry(TimeStamped):
    timesheet = models.ForeignKey(
        Timesheet, on_delete=models.CASCADE, related_name="entries"
    )
    date = models.DateField()
    task = models.ForeignKey(Task, null=True, blank=True, on_delete=models.SET_NULL)
    task_performed = models.CharField(max_length=240)
    hours = models.DecimalField(max_digits=5, decimal_places=2)
    description = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    supporting_document = models.FileField(
        upload_to="timesheet_evidence/%Y/%m/", blank=True
    )
    days_worked = models.DecimalField(max_digits=4, decimal_places=2, default=1)
    overnight_duty_station = models.BooleanField(
        default=False, verbose_name="Overnight stay in duty-station country"
    )
    overnight_outside_duty_station = models.BooleanField(
        default=False, verbose_name="Overnight stay outside duty-station country"
    )
    per_diem_requested = models.BooleanField(
        default=False, verbose_name="Per diem requested"
    )
    location = models.CharField(
        max_length=180,
        blank=True,
        help_text="Country, city and region where services were provided",
    )

    def clean(self):
        if self.hours <= 0 or self.hours > 24:
            raise ValidationError("Hours must be between 0 and 24.")
        if self.days_worked <= 0 or self.days_worked > 1:
            raise ValidationError(
                "Days worked must be greater than zero and no more than 1.0 per entry."
            )

        if self.timesheet_id and (
            self.date < self.timesheet.period_start
            or self.date > self.timesheet.period_end
        ):
            raise ValidationError("Entry date is outside the timesheet period.")


class LeaveAllocation(TenantModel):
    LEAVE_TYPES = [
        ("annual", "Annual leave"),
        ("sick", "Sick leave"),
        ("maternity", "Maternity leave"),
        ("paternity", "Paternity leave"),
        ("compassionate", "Compassionate leave"),
        ("study", "Study leave"),
        ("other", "Other leave"),
    ]
    employee = models.ForeignKey(
        Profile, on_delete=models.CASCADE, related_name="leave_allocations"
    )
    leave_type = models.CharField(max_length=30, choices=LEAVE_TYPES, default="annual")
    year = models.PositiveSmallIntegerField(default=current_year)
    allocated_days = models.PositiveIntegerField()
    assigned_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="assigned_leave_allocations"
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-year", "employee__user__first_name", "leave_type"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "employee", "leave_type", "year"],
                name="unique_employee_leave_allocation",
            )
        ]

    def clean(self):
        if self.employee_id and self.employee.organization_id != self.organization_id:
            raise ValidationError("Employee belongs to another organization.")
        if self.allocated_days is not None and self.allocated_days < 1:
            raise ValidationError("Allocated leave must be at least one day.")

    def __str__(self):
        return f"{self.employee} · {self.get_leave_type_display()} · {self.year}"


class LeaveRequest(TenantModel):
    STATUSES = [
        ("pending", "Pending review"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    ]
    employee = models.ForeignKey(
        Profile, on_delete=models.PROTECT, related_name="leave_requests"
    )
    requested_approver = models.ForeignKey(
        Profile, on_delete=models.PROTECT, related_name="leave_requests_to_review"
    )
    leave_type = models.CharField(
        max_length=30, choices=LeaveAllocation.LEAVE_TYPES, default="annual"
    )
    start_date = models.DateField()
    end_date = models.DateField()
    days = models.PositiveIntegerField()
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=STATUSES, default="pending")
    reviewed_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_leave_requests",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_message = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    @staticmethod
    def count_working_days(start_date, end_date):
        if not start_date or not end_date or start_date > end_date:
            return 0
        return sum(
            1
            for offset in range((end_date - start_date).days + 1)
            if (start_date + timedelta(days=offset)).weekday() < 5
        )

    def clean(self):
        if self.employee_id and self.employee.organization_id != self.organization_id:
            raise ValidationError("Employee belongs to another organization.")
        if self.requested_approver_id:
            if self.requested_approver.organization_id != self.organization_id:
                raise ValidationError("Approver belongs to another organization.")
            if self.requested_approver.role not in ["manager", "admin"]:
                raise ValidationError(
                    "Leave requests must be assigned to a manager or administrator."
                )
        if self.start_date and self.end_date:
            if self.start_date > self.end_date:
                raise ValidationError("End date must be on or after the start date.")
            if self.start_date.year != self.end_date.year:
                raise ValidationError(
                    "A leave request cannot span two calendar years. Submit a separate request for each year."
                )
            calculated = self.count_working_days(self.start_date, self.end_date)
            if calculated < 1:
                raise ValidationError(
                    "The selected dates do not contain a working day."
                )
            self.days = calculated

    def __str__(self):
        return f"{self.employee} · {self.get_leave_type_display()} · {self.start_date}"


class PaymentVoucher(TenantModel):
    STATUSES = [
        ("draft", "Draft"),
        ("submitted", "Submitted"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("paid", "Paid"),
    ]
    number = models.CharField(max_length=30)
    date = models.DateField(default=timezone.localdate)
    payee = models.CharField(max_length=180)
    payee_id_number = models.CharField("ID number", max_length=80, blank=True)
    department = models.ForeignKey(
        Department,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="payment_vouchers",
    )
    requested_approver = models.ForeignKey(
        Profile,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="payment_vouchers_to_approve",
    )
    approval_task = models.OneToOneField(
        Task,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="payment_voucher_approval",
    )
    status = models.CharField(max_length=20, choices=STATUSES, default="draft")
    prepared_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="prepared_payment_vouchers"
    )
    approved_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approved_payment_vouchers",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    payment_received_by = models.CharField(max_length=180, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    review_notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-date", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "number"], name="unique_voucher_number_per_org"
            )
        ]

    def clean(self):
        if (
            self.department_id
            and self.department.organization_id != self.organization_id
        ):
            raise ValidationError("Department belongs to another organization.")
        if self.requested_approver_id:
            if self.requested_approver.organization_id != self.organization_id:
                raise ValidationError("Approver belongs to another organization.")
            if self.requested_approver.role not in ["manager", "admin"]:
                raise ValidationError(
                    "The assigned approver must be a manager or organization administrator."
                )

    @property
    def total_amount(self):
        return sum((line.amount for line in self.lines.all()), 0)

    def __str__(self):
        return f"{self.number} · {self.payee}"


class PaymentVoucherLine(TimeStamped):
    voucher = models.ForeignKey(
        PaymentVoucher, on_delete=models.CASCADE, related_name="lines"
    )
    particulars = models.CharField(max_length=500)
    amount = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        ordering = ["id"]

    def clean(self):
        if self.amount is not None and self.amount <= 0:
            raise ValidationError("Amount must be greater than zero.")


class PaymentVoucherReceipt(TimeStamped):
    voucher = models.ForeignKey(
        PaymentVoucher, on_delete=models.CASCADE, related_name="receipts"
    )
    file = models.FileField(upload_to="payment_voucher_receipts/%Y/%m/")
    original_name = models.CharField(max_length=255)
    uploaded_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="uploaded_voucher_receipts"
    )

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.voucher.number} · {self.original_name}"


class ItemRequest(TenantModel):
    STATUSES = [
        ("submitted", "Submitted"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    ]
    number = models.CharField(max_length=30)
    requested_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="item_requests"
    )
    department = models.ForeignKey(
        Department,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="item_requests",
    )
    purpose = models.TextField()
    needed_by = models.DateField()
    delivery_location = models.CharField(max_length=180, blank=True)
    requested_approver = models.ForeignKey(
        Profile,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="item_requests_to_approve",
    )
    approval_task = models.OneToOneField(
        Task,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="item_request_approval",
    )
    status = models.CharField(max_length=20, choices=STATUSES, default="submitted")
    review_notes = models.TextField(blank=True)
    approved_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approved_item_requests",
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "number"],
                name="unique_item_request_number_per_org",
            )
        ]

    def clean(self):
        if (
            self.department_id
            and self.department.organization_id != self.organization_id
        ):
            raise ValidationError("Department belongs to another organization.")
        if (
            self.requested_approver_id
            and self.requested_approver.organization_id != self.organization_id
        ):
            raise ValidationError("Approver belongs to another organization.")

    @property
    def total_estimated_cost(self):
        return sum((line.estimated_cost for line in self.lines.all()), 0)

    def __str__(self):
        return f"{self.number} · {self.requested_by.get_full_name() or self.requested_by.username}"


class ItemRequestLine(TimeStamped):
    request = models.ForeignKey(
        ItemRequest, on_delete=models.CASCADE, related_name="lines"
    )
    item = models.CharField(max_length=240)
    quantity = models.CharField(max_length=80)
    estimated_cost = models.DecimalField(max_digits=14, decimal_places=2)
    source_link = models.URLField(max_length=1000, blank=True)
    notes = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["id"]

    def clean(self):
        if self.estimated_cost is not None and self.estimated_cost <= 0:
            raise ValidationError("Estimated cost must be greater than zero.")

    def __str__(self):
        return f"{self.item} ({self.quantity})"


class ChatThread(TenantModel):
    KINDS = [("direct", "Direct message"), ("group", "Channel / group")]
    kind = models.CharField(max_length=10, choices=KINDS)
    name = models.CharField(max_length=120, blank=True)
    direct_key = models.CharField(max_length=80, blank=True)
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="created_chat_threads"
    )
    participants = models.ManyToManyField(
        Profile, through="ChatMembership", related_name="chat_threads"
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "direct_key"],
                condition=~models.Q(direct_key=""),
                name="unique_direct_chat_per_org",
            )
        ]

    def clean(self):
        if self.kind == "group" and not self.name.strip():
            raise ValidationError("A channel or group needs a name.")

    def __str__(self):
        return self.name or f"Direct chat {self.pk or ''}".strip()


class ChatMembership(TimeStamped):
    thread = models.ForeignKey(
        ChatThread, on_delete=models.CASCADE, related_name="memberships"
    )
    profile = models.ForeignKey(
        Profile, on_delete=models.CASCADE, related_name="chat_memberships"
    )
    added_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="added_chat_memberships",
    )
    is_admin = models.BooleanField(default=False)
    last_read_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["thread", "profile"], name="unique_chat_membership"
            )
        ]

    def clean(self):
        if (
            self.thread_id
            and self.profile_id
            and self.thread.organization_id != self.profile.organization_id
        ):
            raise ValidationError("Chat member belongs to another organization.")


class ChatInvitation(TimeStamped):
    STATUSES = [
        ("pending", "Pending"),
        ("accepted", "Accepted"),
        ("declined", "Declined"),
    ]
    thread = models.ForeignKey(
        ChatThread, on_delete=models.CASCADE, related_name="invitations"
    )
    invitee = models.ForeignKey(
        Profile, on_delete=models.CASCADE, related_name="chat_invitations"
    )
    invited_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="sent_chat_invitations"
    )
    status = models.CharField(max_length=12, choices=STATUSES, default="pending")
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["thread", "invitee"],
                condition=models.Q(status="pending"),
                name="unique_pending_chat_invitation",
            )
        ]

    def clean(self):
        if (
            self.thread_id
            and self.invitee_id
            and self.thread.organization_id != self.invitee.organization_id
        ):
            raise ValidationError("Invitee belongs to another organization.")
        if self.thread_id and self.thread.kind != "group":
            raise ValidationError("Only channels and groups can have invitations.")


class ChatMessage(TimeStamped):
    thread = models.ForeignKey(
        ChatThread, on_delete=models.CASCADE, related_name="messages"
    )
    sender = models.ForeignKey(
        Profile, on_delete=models.PROTECT, related_name="chat_messages"
    )
    body = models.TextField(blank=True, max_length=4000)
    attachment = models.FileField(upload_to="chat_attachments/%Y/%m/", blank=True)

    class Meta:
        ordering = ["created_at"]

    def clean(self):
        if (
            self.thread_id
            and self.sender_id
            and self.thread.organization_id != self.sender.organization_id
        ):
            raise ValidationError("Message sender belongs to another organization.")
        if not self.body.strip() and not self.attachment:
            raise ValidationError("Enter a message or attach a file.")


class ChatPresence(models.Model):
    profile = models.OneToOneField(
        Profile, on_delete=models.CASCADE, related_name="chat_presence"
    )
    last_seen = models.DateTimeField(default=timezone.now)

    @property
    def is_online(self):
        return self.last_seen >= timezone.now() - timedelta(minutes=2)


class DocumentTemplate(TenantModel):
    name = models.CharField(max_length=180)
    file = models.FileField(upload_to="templates/%Y/%m/")
    department = models.ForeignKey(
        Department, null=True, blank=True, on_delete=models.SET_NULL
    )
    is_default = models.BooleanField(default=False)
    uploaded_by = models.ForeignKey(User, on_delete=models.PROTECT)


class Document(TenantModel):
    VISIBILITY = [
        ("organization", "Organization"),
        ("department", "Department"),
        ("private", "Private"),
    ]
    title = models.CharField(max_length=180)
    category = models.CharField(max_length=100, blank=True)
    file = models.FileField(upload_to="documents/%Y/%m/")
    visibility = models.CharField(
        max_length=20, choices=VISIBILITY, default="organization"
    )
    department = models.ForeignKey(
        Department, null=True, blank=True, on_delete=models.SET_NULL
    )
    owner = models.ForeignKey(Profile, null=True, blank=True, on_delete=models.SET_NULL)
    uploaded_by = models.ForeignKey(User, on_delete=models.PROTECT)


class Notification(TimeStamped):
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="notifications"
    )
    title = models.CharField(max_length=160)
    message = models.TextField(blank=True)
    url = models.CharField(max_length=240, blank=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]


class OutboundEmail(TimeStamped):
    STATUSES = [("pending", "Pending"), ("sent", "Sent"), ("failed", "Failed")]
    recipient = models.EmailField()
    subject = models.CharField(max_length=255)
    text_body = models.TextField()
    html_body = models.TextField()
    status = models.CharField(max_length=12, choices=STATUSES, default="pending")
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.TextField(blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]


class AuditLog(models.Model):
    organization = models.ForeignKey(
        Organization, null=True, blank=True, on_delete=models.SET_NULL
    )
    actor = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=80)
    entity_type = models.CharField(max_length=80, blank=True)
    entity_id = models.CharField(max_length=80, blank=True)
    details = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class EmailOTP(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="email_otps")
    code_hash = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)
    attempts = models.PositiveSmallIntegerField(default=0)

    def set_code(self, code):
        self.code_hash = make_password(code)

    def matches(self, code):
        return check_password(code, self.code_hash)

    def is_expired(self):
        return timezone.now() > self.created_at + timedelta(minutes=5)


class UserInvite(models.Model):
    email = models.EmailField()
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="invites"
    )
    role = models.CharField(
        max_length=20, choices=Profile.ROLE_CHOICES, default="employee"
    )
    department = models.ForeignKey(
        Department, null=True, blank=True, on_delete=models.SET_NULL
    )
    manager = models.ForeignKey(
        Profile,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="pending_direct_reports",
    )
    employee_id = models.CharField(max_length=50, blank=True)
    position = models.CharField(max_length=120, blank=True)
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    invited_by = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="sent_invites"
    )
    is_used = models.BooleanField(default=False)
    expires_at = models.DateTimeField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.employee_id and self.organization_id:
            number = (
                Profile.objects.filter(organization_id=self.organization_id).count()
                + UserInvite.objects.filter(
                    organization_id=self.organization_id
                ).count()
                + 1
            )
            while (
                Profile.objects.filter(
                    organization_id=self.organization_id,
                    employee_id=f"EMP-{number:04d}",
                ).exists()
                or UserInvite.objects.filter(
                    organization_id=self.organization_id,
                    employee_id=f"EMP-{number:04d}",
                ).exists()
            ):
                number += 1
            self.employee_id = f"EMP-{number:04d}"
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(days=3)
        super().save(*args, **kwargs)

    def is_valid(self):
        return not self.is_used and timezone.now() < self.expires_at

    def __str__(self):
        return f"{self.email} → {self.organization}"
