import calendar
from datetime import timedelta
from pathlib import Path
from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.password_validation import (
    validate_password,
    password_validators_help_text_html,
)
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone
from django.utils.text import slugify
from .models import (
    ChatMessage,
    ChatThread,
    Department,
    Document,
    DocumentTemplate,
    ItemRequest,
    ItemRequestLine,
    LeaveAllocation,
    LeaveRequest,
    Organization,
    PaymentVoucher,
    PaymentVoucherLine,
    Profile,
    Task,
    Timesheet,
    TimesheetEntry,
    UserInvite,
)

SAFE_UPLOAD_EXTENSIONS = {
    ".csv",
    ".doc",
    ".docx",
    ".jpeg",
    ".jpg",
    ".pdf",
    ".png",
    ".txt",
    ".webp",
    ".xls",
    ".xlsx",
}


def validate_business_upload(upload, max_size=10 * 1024 * 1024):
    if not upload:
        return upload
    if upload.size > max_size:
        raise forms.ValidationError(
            f"Files must be {max_size // (1024 * 1024)} MB or smaller."
        )
    extension = Path(upload.name).suffix.lower()
    if extension not in SAFE_UPLOAD_EXTENSIONS:
        raise forms.ValidationError(
            "This file type is not allowed. Use PDF, Office, text, CSV, or image files."
        )
    if extension == ".pdf":
        signature = upload.read(5)
        upload.seek(0)
        if signature != b"%PDF-":
            raise forms.ValidationError("The uploaded file is not a valid PDF.")
    return upload


class StyledForm:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(
                field.widget, (forms.CheckboxInput, forms.CheckboxSelectMultiple)
            ):
                field.widget.attrs["class"] = "checkbox checkbox-primary"
            elif isinstance(field.widget, forms.Select):
                field.widget.attrs["class"] = "select select-bordered w-full"
            elif isinstance(field.widget, forms.Textarea):
                field.widget.attrs["class"] = "textarea textarea-bordered w-full"
            else:
                field.widget.attrs["class"] = "input input-bordered w-full"


class RegistrationForm(StyledForm, UserCreationForm):
    organization_name = forms.CharField(max_length=180)
    business_email = forms.EmailField()
    industry = forms.CharField(max_length=100, required=False)
    phone = forms.CharField(max_length=40, required=False)
    email = forms.EmailField()
    first_name = forms.CharField(max_length=80)
    last_name = forms.CharField(max_length=80)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = (
            "organization_name",
            "business_email",
            "industry",
            "phone",
            "first_name",
            "last_name",
            "email",
            "password1",
            "password2",
        )

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    @transaction.atomic
    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.username = self.cleaned_data["email"]
        user.first_name = self.cleaned_data["first_name"]
        user.last_name = self.cleaned_data["last_name"]
        if commit:
            user.save()
            base = slugify(self.cleaned_data["organization_name"])
            slug = base
            n = 2
            while Organization.objects.filter(slug=slug).exists():
                slug = f"{base}-{n}"
                n += 1
            org = Organization.objects.create(
                name=self.cleaned_data["organization_name"],
                slug=slug,
                business_email=self.cleaned_data["business_email"],
                industry=self.cleaned_data["industry"],
                phone=self.cleaned_data["phone"],
            )
            Profile.objects.create(
                user=user,
                organization=org,
                role="admin",
                employee_id="ADMIN-001",
                position="Organization Administrator",
            )
        return user


class ProfileNameForm(StyledForm, forms.Form):
    first_name = forms.CharField(max_length=150, label="First name")
    last_name = forms.CharField(max_length=150, label="Last name")

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        data = args[0] if args else kwargs.get("data")
        if user and data is None and "initial" not in kwargs:
            kwargs["initial"] = {
                "first_name": user.first_name,
                "last_name": user.last_name,
            }
        super().__init__(*args, **kwargs)

    def clean_first_name(self):
        value = self.cleaned_data["first_name"].strip()
        if not value:
            raise forms.ValidationError("Enter your first name.")
        return value

    def clean_last_name(self):
        value = self.cleaned_data["last_name"].strip()
        if not value:
            raise forms.ValidationError("Enter your last name.")
        return value

    def save(self):
        self.user.first_name = self.cleaned_data["first_name"]
        self.user.last_name = self.cleaned_data["last_name"]
        self.user.save(update_fields=["first_name", "last_name"])
        return self.user


class EmployeeForm(StyledForm, forms.ModelForm):
    first_name = forms.CharField(max_length=80)
    last_name = forms.CharField(max_length=80)
    email = forms.EmailField()
    username = forms.CharField(max_length=150)
    password = forms.CharField(
        widget=forms.PasswordInput,
        required=False,
        help_text="Required for new employees",
    )

    class Meta:
        model = Profile
        fields = [
            "first_name",
            "last_name",
            "email",
            "username",
            "password",
            "employee_id",
            "phone",
            "position",
            "department",
            "manager",
            "role",
            "hire_date",
        ]
        widgets = {"hire_date": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization
        self.fields["department"].queryset = Department.objects.filter(
            organization=organization
        )
        self.fields["manager"].queryset = Profile.objects.filter(
            organization=organization, role__in=["admin", "manager"]
        )
        if self.instance.pk:
            u = self.instance.user
            for k in ["first_name", "last_name", "email", "username"]:
                self.fields[k].initial = getattr(u, k)

    def clean_username(self):
        qs = User.objects.filter(username=self.cleaned_data["username"])
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.user_id)
        if qs.exists():
            raise forms.ValidationError("This username is already in use.")
        return self.cleaned_data["username"]

    @transaction.atomic
    def save(self, commit=True):
        p = super().save(False)
        if p.pk:
            u = p.user
        else:
            u = User()
        for k in ["first_name", "last_name", "email", "username"]:
            setattr(u, k, self.cleaned_data[k])
        if self.cleaned_data.get("password"):
            u.set_password(self.cleaned_data["password"])
        elif not u.pk:
            u.set_unusable_password()
        if commit:
            u.save()
            p.user = u
            p.organization = self.organization
            p.full_clean()
            p.save()
        return p


class TaskForm(StyledForm, forms.ModelForm):
    class Meta:
        model = Task
        fields = [
            "title",
            "description",
            "instructions",
            "assigned_to",
            "department",
            "priority",
            "start_date",
            "due_date",
            "attachment",
        ]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "due_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, organization=None, current_profile=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization
        assignees = Profile.objects.filter(
            organization=organization, user__is_active=True
        )
        if current_profile and current_profile.role == "employee":
            assignees = assignees.filter(
                Q(pk=current_profile.pk) | Q(pk=current_profile.manager_id)
            )
        elif current_profile and current_profile.role == "manager":
            assignees = assignees.filter(
                Q(pk=current_profile.pk) | Q(manager=current_profile)
            )
        self.fields["assigned_to"].queryset = assignees.select_related(
            "user"
        ).distinct()
        self.fields["department"].queryset = Department.objects.filter(
            organization=organization
        )

    def clean_attachment(self):
        return validate_business_upload(self.cleaned_data.get("attachment"))


class TaskStatusForm(StyledForm, forms.Form):
    status = forms.ChoiceField(
        label="Change status to", help_text="Choose the next stage for this task."
    )
    note = forms.CharField(
        required=False,
        label="Status note",
        widget=forms.Textarea(
            attrs={"rows": 3, "placeholder": "Optional note for the assignee"}
        ),
    )

    def __init__(self, *args, choices=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["status"].choices = choices or []


class TimesheetForm(StyledForm, forms.ModelForm):
    month = forms.ChoiceField(
        choices=[(number, calendar.month_name[number]) for number in range(1, 13)]
    )
    year = forms.IntegerField(
        min_value=2000, max_value=2100, initial=lambda: timezone.localdate().year
    )

    class Meta:
        model = Timesheet
        fields = [
            "service_contract",
            "financing",
            "contract_number",
            "country",
            "place_of_assignment",
            "initial_budget_days",
            "expert_signature",
        ]
        widgets = {
            "service_contract": forms.Textarea(
                attrs={
                    "rows": 2,
                    "placeholder": "Project or service-contract description",
                }
            ),
            "expert_signature": forms.FileInput(
                attrs={"accept": "image/png,image/jpeg,image/webp"}
            ),
        }

    def __init__(self, *args, organization=None, employee=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization
        self.employee = employee
        today = timezone.localdate()
        self.fields["month"].initial = today.month
        self.fields["country"].initial = (
            organization.address.split(",")[-1].strip()
            if organization and organization.address
            else ""
        )
        self.fields["place_of_assignment"].initial = "Kenya"
        self.fields["place_of_assignment"].help_text = (
            "Defaults to Kenya; change it when the assignment is elsewhere."
        )
        if self.instance.pk:
            self.fields["month"].initial = self.instance.period_start.month
            self.fields["year"].initial = self.instance.period_start.year
            self.fields["month"].disabled = True
            self.fields["year"].disabled = True
            self.fields["month"].help_text = (
                "The reporting month cannot be changed after the timesheet is generated."
            )
            self.fields["year"].help_text = (
                "The reporting year cannot be changed after the timesheet is generated."
            )
        self.order_fields(
            [
                "month",
                "year",
                "service_contract",
                "financing",
                "contract_number",
                "country",
                "place_of_assignment",
                "initial_budget_days",
                "expert_signature",
            ]
        )
        self.fields["expert_signature"].help_text = (
            "Optional now; a PNG, JPG or WebP signature is required before submission. Maximum 2 MB."
        )

    def clean(self):
        d = super().clean()
        month, year = d.get("month"), d.get("year")
        if (
            month
            and year
            and self.employee
            and Timesheet.objects.filter(
                organization=self.organization,
                employee=self.employee,
                period_start__year=year,
                period_start__month=month,
            )
            .exclude(pk=self.instance.pk)
            .exists()
        ):
            raise forms.ValidationError(
                f"A timesheet already exists for {calendar.month_name[int(month)]} {year}."
            )
        return d

    def clean_expert_signature(self):
        return _clean_signature(self.cleaned_data.get("expert_signature"))


class EntryForm(StyledForm, forms.ModelForm):
    class Meta:
        model = TimesheetEntry
        fields = [
            "date",
            "task",
            "task_performed",
            "hours",
            "days_worked",
            "location",
            "overnight_duty_station",
            "overnight_outside_duty_station",
            "per_diem_requested",
            "description",
            "notes",
            "supporting_document",
        ]
        widgets = {"date": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, organization=None, employee=None, **kwargs):
        super().__init__(*args, **kwargs)
        tasks = Task.objects.filter(organization=organization)
        if employee:
            tasks = tasks.filter(assigned_to=employee)
        self.fields["task"].queryset = tasks
        self.fields["task"].required = False
        self.fields["task"].empty_label = "No system task / manually entered activity"
        self.fields["task"].help_text = (
            "Optional. Choose an assigned system task, or leave blank when the work is not recorded in Tasks."
        )
        self.fields["task_performed"].help_text = (
            "Required activity description. Enter this manually when no system task is selected."
        )
        self.fields["hours"].help_text = "Editable working hours for internal tracking."
        self.fields["days_worked"].help_text = (
            "Use 1.0 for a full working day or a fraction such as 0.5."
        )

    def clean_supporting_document(self):
        return validate_business_upload(self.cleaned_data.get("supporting_document"))


def _clean_signature(upload):
    if upload and getattr(upload, "size", 0) > 2 * 1024 * 1024:
        raise forms.ValidationError("Signature images must be 2 MB or smaller.")
    return upload


class TimesheetSignatureForm(StyledForm, forms.ModelForm):
    class Meta:
        model = Timesheet
        fields = ["expert_signature"]
        widgets = {
            "expert_signature": forms.FileInput(
                attrs={"accept": "image/png,image/jpeg,image/webp"}
            )
        }

    def clean_expert_signature(self):
        return _clean_signature(self.cleaned_data.get("expert_signature"))


class TimesheetReviewForm(StyledForm, forms.Form):
    decision = forms.ChoiceField(
        choices=[
            ("approved", "Approve"),
            ("rejected", "Reject"),
            ("escalate", "Move to my manager"),
        ]
    )
    notes = forms.CharField(
        required=False,
        label="Review message",
        widget=forms.Textarea(
            attrs={"rows": 3, "placeholder": "Optional message to the employee"}
        ),
    )
    manager_signature = forms.ImageField(
        required=False,
        widget=forms.FileInput(attrs={"accept": "image/png,image/jpeg,image/webp"}),
        help_text="Optional head-of-mission or manager signature, maximum 2 MB.",
    )
    consultant_name = forms.CharField(required=False, max_length=180)
    consultant_signature = forms.ImageField(
        required=False,
        widget=forms.FileInput(attrs={"accept": "image/png,image/jpeg,image/webp"}),
        help_text="Optional consultant signature, maximum 2 MB.",
    )

    def __init__(self, *args, can_escalate=False, **kwargs):
        super().__init__(*args, **kwargs)
        if not can_escalate:
            self.fields["decision"].choices = [
                choice
                for choice in self.fields["decision"].choices
                if choice[0] != "escalate"
            ]

    def clean_manager_signature(self):
        return _clean_signature(self.cleaned_data.get("manager_signature"))

    def clean_consultant_signature(self):
        return _clean_signature(self.cleaned_data.get("consultant_signature"))


class TimesheetRequestForm(StyledForm, forms.Form):
    employee = forms.ModelMultipleChoiceField(
        label="Employees",
        queryset=Profile.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        help_text="Select one or more employees below you in the reporting hierarchy.",
    )
    month = forms.MultipleChoiceField(
        label="Months",
        choices=[(str(number), calendar.month_name[number]) for number in range(1, 13)],
        widget=forms.CheckboxSelectMultiple,
        help_text="A separate monthly timesheet and task will be prepared for every selected month.",
    )
    year = forms.IntegerField(
        min_value=2000, max_value=2100, initial=lambda: timezone.localdate().year
    )
    due_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    instructions = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "placeholder": "Optional guidance for completing the timesheet",
            }
        ),
    )

    def __init__(
        self,
        *args,
        organization=None,
        manager=None,
        eligible_employee_ids=None,
        selected_employee=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        employees = Profile.objects.filter(
            organization=organization, user__is_active=True
        ).exclude(pk=getattr(manager, "pk", None))
        if manager and manager.role == "manager":
            employees = employees.filter(pk__in=eligible_employee_ids or [])
        self.fields["employee"].queryset = employees.select_related(
            "user", "department"
        ).order_by("user__first_name", "user__last_name")
        if selected_employee and employees.filter(pk=selected_employee).exists():
            self.fields["employee"].initial = [selected_employee]
        self.fields["month"].initial = [str(timezone.localdate().month)]
        self.fields["due_date"].initial = timezone.localdate() + timedelta(days=3)

    def clean_due_date(self):
        due = self.cleaned_data["due_date"]
        if due < timezone.localdate():
            raise forms.ValidationError("Due date cannot be in the past.")
        return due


class TimesheetExportForm(StyledForm, forms.Form):
    months = forms.MultipleChoiceField(
        choices=[(str(number), calendar.month_name[number]) for number in range(1, 13)],
        widget=forms.CheckboxSelectMultiple,
        help_text="Select one or more months. Only selected months will be included in the Excel workbook.",
    )

    def __init__(self, *args, year=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["months"].initial = [str(number) for number in range(1, 13)]
        self.fields["months"].label = (
            f"Months to export{f' for {year}' if year else ''}"
        )


class LeaveAllocationForm(StyledForm, forms.Form):
    employee = forms.ModelChoiceField(
        queryset=Profile.objects.none(), empty_label="Choose an employee"
    )
    leave_type = forms.ChoiceField(choices=LeaveAllocation.LEAVE_TYPES)
    year = forms.IntegerField(
        min_value=2000, max_value=2100, initial=lambda: timezone.localdate().year
    )
    allocated_days = forms.IntegerField(min_value=1, label="Leave days")
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={"rows": 3, "placeholder": "Optional allocation notes"}
        ),
    )

    def __init__(self, *args, organization=None, manager=None, **kwargs):
        super().__init__(*args, **kwargs)
        employees = Profile.objects.filter(
            organization=organization, user__is_active=True
        ).exclude(role="admin")
        if manager and manager.role == "manager":
            employees = employees.filter(manager=manager)
        self.fields["employee"].queryset = employees.select_related("user").order_by(
            "user__first_name", "user__last_name", "user__username"
        )


class LeaveRequestForm(StyledForm, forms.ModelForm):
    class Meta:
        model = LeaveRequest
        fields = ["leave_type", "start_date", "end_date", "reason"]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
            "reason": forms.Textarea(
                attrs={"rows": 4, "placeholder": "Briefly explain your leave request"}
            ),
        }

    def __init__(self, *args, employee=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.employee = employee
        self.fields["leave_type"].help_text = (
            "Only leave types with an assigned balance can be requested. Weekends are not counted."
        )

    def clean(self):
        data = super().clean()
        employee = self.employee
        start, end, leave_type = (
            data.get("start_date"),
            data.get("end_date"),
            data.get("leave_type"),
        )
        if not employee or not employee.manager_id:
            raise forms.ValidationError(
                "A manager must be assigned to your employee profile before you can request leave."
            )
        if not start or not end or not leave_type:
            return data
        if start > end:
            self.add_error("end_date", "End date must be on or after the start date.")
            return data
        if start.year != end.year:
            self.add_error(
                "end_date",
                "Submit separate requests when leave crosses into a new calendar year.",
            )
            return data
        days = LeaveRequest.count_working_days(start, end)
        if days < 1:
            self.add_error(
                "end_date", "The selected dates do not contain a working day."
            )
            return data
        overlap = LeaveRequest.objects.filter(
            employee=employee,
            status__in=["pending", "approved"],
            start_date__lte=end,
            end_date__gte=start,
        )
        if self.instance.pk:
            overlap = overlap.exclude(pk=self.instance.pk)
        if overlap.exists():
            raise forms.ValidationError(
                "These dates overlap another pending or approved leave request."
            )
        allocation = LeaveAllocation.objects.filter(
            organization=employee.organization,
            employee=employee,
            leave_type=leave_type,
            year=start.year,
        ).first()
        if not allocation:
            self.add_error(
                "leave_type",
                f"No {dict(LeaveAllocation.LEAVE_TYPES).get(leave_type,'leave')} days have been assigned for {start.year}.",
            )
            return data
        committed = LeaveRequest.objects.filter(
            employee=employee,
            leave_type=leave_type,
            start_date__year=start.year,
            status__in=["pending", "approved"],
        )
        if self.instance.pk:
            committed = committed.exclude(pk=self.instance.pk)
        reserved = committed.aggregate(total=Sum("days"))["total"] or 0
        remaining = allocation.allocated_days - reserved
        if days > remaining:
            self.add_error(
                "end_date",
                f"This request needs {days} working days, but only {remaining} are available.",
            )
        self.calculated_days = days
        return data


class LeaveReviewForm(StyledForm, forms.Form):
    decision = forms.ChoiceField(
        choices=[
            ("approved", "Approve"),
            ("rejected", "Reject"),
            ("escalate", "Move to my manager"),
        ]
    )
    message = forms.CharField(
        required=False,
        label="Message to employee",
        widget=forms.Textarea(
            attrs={
                "rows": 4,
                "placeholder": "Optional message explaining your decision",
            }
        ),
    )

    def __init__(self, *args, can_escalate=False, **kwargs):
        super().__init__(*args, **kwargs)
        if not can_escalate:
            self.fields["decision"].choices = [
                choice
                for choice in self.fields["decision"].choices
                if choice[0] != "escalate"
            ]


class MultiplePDFInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultiplePDFField(forms.FileField):
    def clean(self, data, initial=None):
        files = data if isinstance(data, (list, tuple)) else ([data] if data else [])
        cleaned = []
        for upload in files:
            item = super().clean(upload, initial)
            if not item:
                continue
            if not item.name.lower().endswith(".pdf"):
                raise forms.ValidationError(f"{item.name}: receipts must be PDF files.")
            if getattr(item, "content_type", "") not in [
                "application/pdf",
                "application/x-pdf",
            ]:
                raise forms.ValidationError(
                    f"{item.name}: the uploaded file is not identified as a PDF."
                )
            if item.size > 10 * 1024 * 1024:
                raise forms.ValidationError(
                    f"{item.name}: each receipt must be 10 MB or smaller."
                )
            signature = item.read(5)
            item.seek(0)
            if signature != b"%PDF-":
                raise forms.ValidationError(
                    f"{item.name}: the file contents are not a valid PDF."
                )
            cleaned.append(item)
        if len(cleaned) > 10:
            raise forms.ValidationError("Attach no more than 10 receipts at a time.")
        if self.required and not cleaned:
            raise forms.ValidationError(
                self.error_messages["required"], code="required"
            )
        return cleaned


class PaymentVoucherForm(StyledForm, forms.ModelForm):
    receipts = MultiplePDFField(
        required=False,
        widget=MultiplePDFInput(attrs={"accept": "application/pdf,.pdf"}),
        help_text="Optional: attach up to 10 PDF receipts, maximum 10 MB each.",
    )

    class Meta:
        model = PaymentVoucher
        fields = ["date", "payee", "payee_id_number", "department"]
        widgets = {"date": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization
        self.fields["department"].queryset = Department.objects.filter(
            organization=organization
        )
        self.fields["payee"].widget.attrs[
            "placeholder"
        ] = "Person or business being paid"
        self.fields["payee_id_number"].widget.attrs[
            "placeholder"
        ] = "National ID, passport or registration number"


class PaymentVoucherReceiptForm(StyledForm, forms.Form):
    receipts = MultiplePDFField(
        widget=MultiplePDFInput(attrs={"accept": "application/pdf,.pdf"}),
        help_text="Attach up to 10 PDF receipts, maximum 10 MB each.",
    )


class PaymentVoucherLineForm(StyledForm, forms.ModelForm):
    class Meta:
        model = PaymentVoucherLine
        fields = ["particulars", "amount"]
        widgets = {
            "particulars": forms.TextInput(
                attrs={"placeholder": "Description of payment"}
            ),
            "amount": forms.NumberInput(
                attrs={"min": "0.01", "step": "0.01", "placeholder": "0.00"}
            ),
        }


PaymentVoucherLineFormSet = forms.inlineformset_factory(
    PaymentVoucher,
    PaymentVoucherLine,
    form=PaymentVoucherLineForm,
    extra=1,
    can_delete=True,
    min_num=1,
    validate_min=True,
)


class PaymentVoucherActionForm(StyledForm, forms.Form):
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={"rows": 3, "placeholder": "Optional review notes"}
        ),
    )
    payment_received_by = forms.CharField(
        required=False, max_length=180, label="Payment received by"
    )

    def __init__(self, *args, action=None, **kwargs):
        super().__init__(*args, **kwargs)
        if action != "paid":
            self.fields.pop("payment_received_by")
        else:
            self.fields["payment_received_by"].required = True


class ItemRequestForm(StyledForm, forms.ModelForm):
    class Meta:
        model = ItemRequest
        fields = ["purpose", "needed_by", "delivery_location", "department"]
        widgets = {
            "purpose": forms.Textarea(
                attrs={"rows": 3, "placeholder": "Why are these items needed?"}
            ),
            "needed_by": forms.DateInput(attrs={"type": "date"}),
            "delivery_location": forms.TextInput(
                attrs={"placeholder": "Office, site or delivery point"}
            ),
        }

    def __init__(self, *args, organization=None, profile=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["department"].queryset = Department.objects.filter(
            organization=organization
        )
        self.fields["department"].initial = getattr(profile, "department", None)
        self.fields["needed_by"].initial = timezone.localdate() + timedelta(days=7)

    def clean_needed_by(self):
        value = self.cleaned_data["needed_by"]
        if value < timezone.localdate():
            raise forms.ValidationError("Required date cannot be in the past.")
        return value


class ItemRequestLineForm(StyledForm, forms.ModelForm):
    class Meta:
        model = ItemRequestLine
        fields = ["item", "quantity", "estimated_cost", "source_link", "notes"]
        widgets = {
            "item": forms.TextInput(attrs={"placeholder": "e.g. Sugar"}),
            "quantity": forms.TextInput(attrs={"placeholder": "e.g. 2 kg, 10 rolls"}),
            "estimated_cost": forms.NumberInput(
                attrs={"min": "0.01", "step": "0.01", "placeholder": "0.00"}
            ),
            "source_link": forms.URLInput(
                attrs={"placeholder": "Optional supplier or product link"}
            ),
            "notes": forms.TextInput(attrs={"placeholder": "Optional specification"}),
        }


ItemRequestLineFormSet = forms.inlineformset_factory(
    ItemRequest,
    ItemRequestLine,
    form=ItemRequestLineForm,
    extra=1,
    can_delete=True,
    min_num=1,
    validate_min=True,
)


class ItemRequestActionForm(StyledForm, forms.Form):
    notes = forms.CharField(
        required=False,
        label="Review notes",
        widget=forms.Textarea(
            attrs={
                "rows": 4,
                "placeholder": "Optional notes for the requester or next approver",
            }
        ),
    )


class DirectChatForm(StyledForm, forms.Form):
    person = forms.ModelChoiceField(
        queryset=Profile.objects.none(), empty_label="Choose a colleague"
    )

    def __init__(self, *args, organization=None, current_profile=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["person"].queryset = (
            Profile.objects.filter(organization=organization, user__is_active=True)
            .exclude(pk=getattr(current_profile, "pk", None))
            .select_related("user", "department")
            .order_by("user__first_name", "user__last_name", "user__username")
        )


class GroupChatForm(StyledForm, forms.ModelForm):
    invitees = forms.ModelMultipleChoiceField(
        queryset=Profile.objects.none(),
        required=False,
        widget=forms.SelectMultiple(attrs={"size": 6}),
        help_text="Selected colleagues receive an invitation they can accept or decline.",
    )

    class Meta:
        model = ChatThread
        fields = ["name"]

    def __init__(self, *args, organization=None, current_profile=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].widget.attrs["placeholder"] = "e.g. Finance operations"
        self.fields["invitees"].queryset = (
            Profile.objects.filter(organization=organization, user__is_active=True)
            .exclude(pk=getattr(current_profile, "pk", None))
            .select_related("user")
            .order_by("user__first_name", "user__last_name", "user__username")
        )


class ChatInviteForm(StyledForm, forms.Form):
    people = forms.ModelMultipleChoiceField(
        queryset=Profile.objects.none(),
        widget=forms.SelectMultiple(attrs={"size": 7}),
        help_text="Invited colleagues can accept or decline from their Chats page.",
    )

    def __init__(self, *args, thread=None, **kwargs):
        super().__init__(*args, **kwargs)
        excluded = list(thread.memberships.values_list("profile_id", flat=True)) + list(
            thread.invitations.filter(status="pending").values_list(
                "invitee_id", flat=True
            )
        )
        self.fields["people"].queryset = (
            Profile.objects.filter(
                organization=thread.organization, user__is_active=True
            )
            .exclude(pk__in=excluded)
            .select_related("user")
            .order_by("user__first_name", "user__last_name", "user__username")
        )


class ChatMessageForm(StyledForm, forms.ModelForm):
    class Meta:
        model = ChatMessage
        fields = ["body", "attachment"]
        widgets = {
            "body": forms.Textarea(
                attrs={"rows": 1, "placeholder": "Write a message…", "maxlength": 4000}
            )
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["attachment"].widget.attrs["class"] = "hidden"

    def clean_attachment(self):
        attachment = self.cleaned_data.get("attachment")
        return validate_business_upload(attachment)


class DocumentForm(StyledForm, forms.ModelForm):
    class Meta:
        model = Document
        fields = ["title", "category", "file", "visibility", "department", "owner"]

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["department"].queryset = Department.objects.filter(
            organization=organization
        )
        self.fields["owner"].queryset = Profile.objects.filter(
            organization=organization
        )

    def clean_file(self):
        return validate_business_upload(self.cleaned_data.get("file"), 20 * 1024 * 1024)

    def clean(self):
        data = super().clean()
        if data.get("visibility") == "department" and not data.get("department"):
            self.add_error(
                "department", "Choose a department for department visibility."
            )
        if data.get("visibility") == "private" and not data.get("owner"):
            self.add_error("owner", "Choose an owner for a private document.")
        return data


class TemplateForm(StyledForm, forms.ModelForm):
    class Meta:
        model = DocumentTemplate
        fields = ["name", "file", "department", "is_default"]

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["department"].queryset = Department.objects.filter(
            organization=organization
        )

    def clean_file(self):
        return validate_business_upload(self.cleaned_data.get("file"), 20 * 1024 * 1024)


class DepartmentForm(StyledForm, forms.ModelForm):
    class Meta:
        model = Department
        fields = ["name", "description"]


class EmailLoginForm(StyledForm, forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(
            attrs={"autocomplete": "email", "placeholder": "you@example.com"}
        )
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"})
    )


class OTPForm(StyledForm, forms.Form):
    otp = forms.CharField(
        min_length=6,
        max_length=6,
        widget=forms.TextInput(
            attrs={
                "inputmode": "numeric",
                "autocomplete": "one-time-code",
                "placeholder": "000000",
            }
        ),
    )

    def clean_otp(self):
        value = self.cleaned_data["otp"]
        if not value.isdigit():
            raise forms.ValidationError("Enter the six-digit code.")
        return value


class SetInvitePasswordForm(StyledForm, forms.Form):
    first_name = forms.CharField(max_length=80)
    last_name = forms.CharField(max_length=80)
    password1 = forms.CharField(
        label="Password",
        help_text=password_validators_help_text_html(),
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    password2 = forms.CharField(
        label="Confirm password",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    def __init__(self, *args, email=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.email = email

    def clean_password1(self):
        password = self.cleaned_data["password1"]
        validate_password(password, User(email=self.email or ""))
        return password

    def clean(self):
        data = super().clean()
        if data.get("password1") and data.get("password1") != data.get("password2"):
            self.add_error("password2", "The two passwords do not match.")
        return data


class EmployeeForm(StyledForm, forms.ModelForm):
    """Employment details only; account credentials are chosen after invitation."""

    class Meta:
        model = UserInvite
        fields = ["email", "role", "department", "position", "manager"]

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization
        self.fields["department"].queryset = Department.objects.filter(
            organization=organization
        )
        self.fields["manager"].queryset = Profile.objects.filter(
            organization=organization, role__in=["admin", "manager"]
        )
        self.fields["manager"].required = True
        self.fields["role"].choices = [("manager", "Manager"), ("employee", "Employee")]

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("This employee already has an account.")
        if UserInvite.objects.filter(
            email__iexact=email, organization=self.organization, is_used=False
        ).exists():
            raise forms.ValidationError(
                "An activation invitation is already pending for this employee."
            )
        return email
