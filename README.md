# PowerpayERP

A multi-tenant internal ERP built with Django, Tailwind CSS and DaisyUI. It includes organization registration, role-based dashboards, employees and departments, tasks, digital timesheets with approvals and PDF/CSV exports, documents, templates, notifications, audit logs, and a tenant-scoped REST API.

Employees are provisioned through the **Add employee** workflow: the ERP assigns an `EMP-####` identifier and sends a single-use activation link. The employee chooses their own name and password; administrators never handle employee credentials.

## Run locally

```powershell
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

Open `http://127.0.0.1:8000`. Demo sign-in emails are `admin@acme.test`, `manager@acme.test`, and `employee@acme.test`; all use `Powerpay123!`. Login sends a six-digit OTP through the configured email backend. Create a platform superadmin with `python manage.py createsuperuser`.

Copy `.env.example` to `.env` and supply the SMTP values to deliver OTP, invitation, and password-reset emails. In development, the default console backend prints messages to the server terminal.

For production, set the values shown in `.env.example`, use PostgreSQL, configure object storage for media, enforce HTTPS, and run `python manage.py collectstatic`.
