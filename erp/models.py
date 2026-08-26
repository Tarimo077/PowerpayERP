from django.contrib.auth.models import User
from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from datetime import timedelta
import uuid

class TimeStamped(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta: abstract = True

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
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="departments")
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    class Meta: 
        constraints = [models.UniqueConstraint(fields=["organization", "name"], name="unique_department_per_org")]

    def __str__(self): 
        return self.name

class Profile(TimeStamped):
    ROLE_CHOICES = [("admin", "Organization admin"), ("manager", "Manager"), ("employee", "Employee")]
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="profiles", null=True, blank=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="employee")
    employee_id = models.CharField(max_length=50, blank=True)
    phone = models.CharField(max_length=40, blank=True)
    position = models.CharField(max_length=120, blank=True)
    department = models.ForeignKey(Department, null=True, blank=True, on_delete=models.SET_NULL, related_name="members")
    manager = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="direct_reports")
    hire_date = models.DateField(null=True, blank=True)

    class Meta: 
        constraints = [models.UniqueConstraint(fields=["organization", "employee_id"], condition=~models.Q(employee_id=""), name="unique_employee_id_per_org")]

    def clean(self):
        if self.department_id and self.department.organization_id != self.organization_id: 
            raise ValidationError("Department belongs to another organization.")
        
        if self.manager_id and self.manager.organization_id != self.organization_id: 
            raise ValidationError("Manager belongs to another organization.")

    def __str__(self): 
        return self.user.get_full_name() or self.user.username

class TenantModel(TimeStamped):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)

    class Meta: 
        abstract = True

class Task(TenantModel):
    STATUSES = [(x, x.replace("_", " ").title()) for x in ["pending", "assigned", "in_progress", "submitted", "approved", "rejected", "completed"]]
    PRIORITIES = [(x, x.title()) for x in ["low", "medium", "high", "urgent"]]
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    instructions = models.TextField(blank=True)
    assigned_to = models.ForeignKey(Profile, on_delete=models.PROTECT, related_name="tasks")
    department = models.ForeignKey(Department, null=True, blank=True, on_delete=models.SET_NULL, related_name="tasks")
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="created_tasks")
    priority = models.CharField(max_length=10, choices=PRIORITIES, default="medium")
    status = models.CharField(max_length=20, choices=STATUSES, default="assigned")
    start_date = models.DateField(default=timezone.localdate)
    due_date = models.DateField()
    attachment = models.FileField(upload_to="task_attachments/%Y/%m/", blank=True)
    def clean(self):
        if self.assigned_to.organization_id != self.organization_id: 
            raise ValidationError("Assignee belongs to another organization.")
        
    @property
    def is_overdue(self): 
        return self.due_date < timezone.localdate() and self.status not in ["approved", "completed"]

    def __str__(self): return self.title

class Timesheet(TenantModel):
    STATUSES = [("draft", "Draft"), ("submitted", "Submitted"), ("approved", "Approved"), ("rejected", "Rejected")]
    employee = models.ForeignKey(Profile, on_delete=models.PROTECT, related_name="timesheets")
    period_start = models.DateField()
    period_end = models.DateField()
    status = models.CharField(max_length=20, choices=STATUSES, default="draft")
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="reviewed_timesheets")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_notes = models.TextField(blank=True)

    class Meta: 
        ordering = ["-period_start"]

    @property
    def total_hours(self): 
        return sum(e.hours for e in self.entries.all())
    
    def __str__(self): 
        return f"{self.employee} · {self.period_start}"

class TimesheetEntry(TimeStamped):
    timesheet = models.ForeignKey(Timesheet, on_delete=models.CASCADE, related_name="entries")
    date = models.DateField()
    task = models.ForeignKey(Task, null=True, blank=True, on_delete=models.SET_NULL)
    task_performed = models.CharField(max_length=240)
    hours = models.DecimalField(max_digits=5, decimal_places=2)
    description = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    supporting_document = models.FileField(upload_to="timesheet_evidence/%Y/%m/", blank=True)

    def clean(self):
        if self.hours <= 0 or self.hours > 24: 
            raise ValidationError("Hours must be between 0 and 24.")
        
        if self.date < self.timesheet.period_start or self.date > self.timesheet.period_end: 
            raise ValidationError("Entry date is outside the timesheet period.")

class DocumentTemplate(TenantModel):
    name = models.CharField(max_length=180)
    file = models.FileField(upload_to="templates/%Y/%m/")
    department = models.ForeignKey(Department, null=True, blank=True, on_delete=models.SET_NULL)
    is_default = models.BooleanField(default=False)
    uploaded_by = models.ForeignKey(User, on_delete=models.PROTECT)

class Document(TenantModel):
    VISIBILITY = [("organization", "Organization"), ("department", "Department"), ("private", "Private")]
    title = models.CharField(max_length=180)
    category = models.CharField(max_length=100, blank=True)
    file = models.FileField(upload_to="documents/%Y/%m/")
    visibility = models.CharField(max_length=20, choices=VISIBILITY, default="organization")
    department = models.ForeignKey(Department, null=True, blank=True, on_delete=models.SET_NULL)
    owner = models.ForeignKey(Profile, null=True, blank=True, on_delete=models.SET_NULL)
    uploaded_by = models.ForeignKey(User, on_delete=models.PROTECT)

class Notification(TimeStamped):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    title = models.CharField(max_length=160)
    message = models.TextField(blank=True)
    url = models.CharField(max_length=240, blank=True)
    is_read = models.BooleanField(default=False)

    class Meta: 
        ordering = ["-created_at"]

class AuditLog(models.Model):
    organization = models.ForeignKey(Organization, null=True, blank=True, on_delete=models.SET_NULL)
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
    def set_code(self, code): self.code_hash = make_password(code)
    def matches(self, code): return check_password(code, self.code_hash)
    def is_expired(self): return timezone.now() > self.created_at + timedelta(minutes=5)

class UserInvite(models.Model):
    email = models.EmailField()
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="invites")
    role = models.CharField(max_length=20, choices=Profile.ROLE_CHOICES, default="employee")
    department = models.ForeignKey(Department, null=True, blank=True, on_delete=models.SET_NULL)
    manager = models.ForeignKey(Profile, null=True, blank=True, on_delete=models.SET_NULL, related_name="pending_direct_reports")
    employee_id = models.CharField(max_length=50, blank=True)
    position = models.CharField(max_length=120, blank=True)
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    invited_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="sent_invites")
    is_used = models.BooleanField(default=False)
    expires_at = models.DateTimeField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    def save(self,*args,**kwargs):
        if not self.employee_id and self.organization_id:
            number=Profile.objects.filter(organization_id=self.organization_id).count()+UserInvite.objects.filter(organization_id=self.organization_id).count()+1
            while Profile.objects.filter(organization_id=self.organization_id,employee_id=f"EMP-{number:04d}").exists() or UserInvite.objects.filter(organization_id=self.organization_id,employee_id=f"EMP-{number:04d}").exists(): number+=1
            self.employee_id=f"EMP-{number:04d}"
        if not self.expires_at: self.expires_at=timezone.now()+timedelta(days=3)
        super().save(*args,**kwargs)
    def is_valid(self): return not self.is_used and timezone.now()<self.expires_at
    def __str__(self): return f"{self.email} → {self.organization}"
