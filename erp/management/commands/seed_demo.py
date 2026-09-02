from datetime import timedelta
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone
from erp.models import (
    Department,
    Organization,
    Profile,
    Task,
    Timesheet,
    TimesheetEntry,
    Notification,
)


class Command(BaseCommand):
    help = "Create a complete demo organization (safe to run repeatedly)"

    def handle(self, *args, **kwargs):
        org, _ = Organization.objects.get_or_create(
            slug="acme-demo",
            defaults={
                "name": "Acme Operations",
                "business_email": "hello@acme.test",
                "industry": "Professional Services",
                "phone": "+254 700 000 000",
            },
        )
        ops, _ = Department.objects.get_or_create(
            organization=org,
            name="Operations",
            defaults={"description": "Client delivery and operations"},
        )

        def person(username, password, first, last, role, emp, position, manager=None):
            u, _ = User.objects.get_or_create(
                username=username,
                defaults={
                    "first_name": first,
                    "last_name": last,
                    "email": f"{username}@acme.test",
                },
            )
            u.set_password(password)
            u.save()
            p, _ = Profile.objects.update_or_create(
                user=u,
                defaults={
                    "organization": org,
                    "role": role,
                    "employee_id": emp,
                    "position": position,
                    "department": ops,
                    "manager": manager,
                },
            )
            return p

        admin = person(
            "admin",
            "Powerpay123!",
            "Amina",
            "Otieno",
            "admin",
            "AC-001",
            "Organization Admin",
        )
        manager = person(
            "manager",
            "Powerpay123!",
            "David",
            "Kamau",
            "manager",
            "AC-002",
            "Operations Manager",
            admin,
        )
        employee = person(
            "employee",
            "Powerpay123!",
            "Grace",
            "Wanjiku",
            "employee",
            "AC-003",
            "Operations Associate",
            manager,
        )
        task, _ = Task.objects.get_or_create(
            organization=org,
            title="Prepare August client activity report",
            defaults={
                "description": "Consolidate completed work and delivery metrics for the monthly review.",
                "instructions": "Attach source notes and submit for manager approval.",
                "assigned_to": employee,
                "department": ops,
                "created_by": manager.user,
                "priority": "high",
                "status": "in_progress",
                "due_date": timezone.localdate() + timedelta(days=3),
            },
        )
        sheet, _ = Timesheet.objects.get_or_create(
            organization=org,
            employee=employee,
            period_start=timezone.localdate() - timedelta(days=6),
            period_end=timezone.localdate(),
            defaults={"status": "draft"},
        )
        TimesheetEntry.objects.get_or_create(
            timesheet=sheet,
            date=timezone.localdate(),
            task_performed="Client activity analysis",
            defaults={
                "task": task,
                "hours": 4,
                "description": "Reviewed delivery records and prepared monthly totals.",
            },
        )
        Notification.objects.get_or_create(
            user=employee.user,
            title="Welcome to PowerpayERP",
            defaults={
                "message": "Your workspace is ready. Review your assigned task.",
                "url": "/tasks/",
            },
        )
        self.stdout.write(
            self.style.SUCCESS(
                "Demo ready: admin / manager / employee — password Powerpay123!"
            )
        )
