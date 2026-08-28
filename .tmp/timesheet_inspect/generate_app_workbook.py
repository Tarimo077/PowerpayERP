import os
import sys
from pathlib import Path
from datetime import date
from decimal import Decimal

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "powerpayerp.settings")
import django
django.setup()

from django.contrib.auth.models import User
from django.db import connection
from django.test import RequestFactory
from erp.models import Organization, Profile, Task, Timesheet, TimesheetEntry
from erp.views import timesheet_export_year

connection.creation.create_test_db(verbosity=0, autoclobber=True)
try:
    organization=Organization.objects.create(name="PowerPay Africa",slug="powerpay-qa",business_email="qa@powerpay.africa",address="Nairobi, Kenya",industry="Digital Energy")
    user=User.objects.create_user("expert@powerpay.africa",first_name="Alex",last_name="Expert")
    profile=Profile.objects.create(user=user,organization=organization,role="employee",employee_id="EMP-0001",position="Head of Technology")
    task=Task.objects.create(organization=organization,title="ERP implementation and validation",description="Built and verified the monthly timesheet workflow.",assigned_to=profile,created_by=user,status="in_progress",start_date=date(2026,8,3),due_date=date(2026,8,28))
    sheet=Timesheet.objects.create(organization=organization,employee=profile,period_start=date(2026,8,1),period_end=date(2026,8,31),service_contract="Digital Energy Challenge — ERP delivery and operational support",financing="PowerPay Africa",contract_number="PPA-ERP-2026",country="Kenya",place_of_assignment="Nairobi",initial_budget_days=Decimal("120"))
    TimesheetEntry.objects.create(timesheet=sheet,date=date(2026,8,3),task=task,task_performed=task.title,hours=Decimal("8"),days_worked=Decimal("1"),location="Kenya, Nairobi",description=task.description)
    request=RequestFactory().post(f"/timesheets/{sheet.pk}/export-year/",{"months":[str(month) for month in range(1,13)]}); request.user=user
    response=timesheet_export_year(request,sheet.pk)
    Path(".tmp/timesheet_inspect/app_generated.xlsx").write_bytes(response.content)
finally:
    connection.creation.destroy_test_db(verbosity=0)
