# PowerpayERP

PowerpayERP is an internal, multi-tenant enterprise resource planning system built with Django. It brings employee administration, reporting hierarchies, task management, timesheets, leave, payment vouchers, consumable/item requests, documents, notifications, audit records, and internal chat into one organization-scoped workspace.

The interface uses PowerPay-inspired green and orange styling, Tailwind CSS, and DaisyUI. Operational forms open in modal dialogs so users can complete work without losing their place.

## Contents

- [Core concepts](#core-concepts)
- [Roles and permissions](#roles-and-permissions)
- [Authentication and employee onboarding](#authentication-and-employee-onboarding)
- [Dashboard and calendars](#dashboard-and-calendars)
- [Employees and hierarchy](#employees-and-hierarchy)
- [Tasks](#tasks)
- [Timesheets](#timesheets)
- [Leave management](#leave-management)
- [Payment vouchers](#payment-vouchers)
- [Item requests](#item-requests)
- [Chat and channels](#chat-and-channels)
- [Documents and templates](#documents-and-templates)
- [Notifications, email, and audit logs](#notifications-email-and-audit-logs)
- [Platform administration](#platform-administration)
- [REST API](#rest-api)
- [Installation and configuration](#installation-and-configuration)
- [Testing and production](#testing-and-production)
- [Project structure](#project-structure)

## Core concepts

### Multi-tenancy

Every business record belongs to an organization. Queries, forms, downloads, search results, and API endpoints are restricted to the signed-in user's organization. Users cannot select, view, update, or download another organization's data.

Platform superusers are separate from organization users. They manage the overall PowerpayERP platform and can review organizations, platform accounts, and system-wide activity.

### Reporting hierarchy

Each employee can be assigned a manager. Managers can report to another manager, forming an organization-wide reporting tree. The system rejects self-management, cross-organization managers, and circular reporting chains.

This hierarchy controls manager dashboards, team calendars, task visibility, timesheet requests, and the approval chains for timesheets, leave, payment vouchers, and item requests.

### Workflow tasks

Tasks may be created directly or generated automatically by a workflow. For example, submitting a payment voucher creates a medium-priority review task for the employee's manager. Escalating an approval reassigns that task to the next manager. A terminal approval or rejection completes the related review task where appropriate.

## Roles and permissions

| Role | Scope | Main abilities |
| --- | --- | --- |
| Employee | Their work and records they created | Work on tasks, create timesheets, request leave, create vouchers/item requests, chat, and use permitted documents |
| Manager | Their work plus reporting descendants | Team calendars, task oversight, timesheet requests, leave allocation, reviews, submitted-timesheet editing, and escalation |
| Organization admin | Entire organization | Employee and department administration, organization-wide records, templates, approvals, and audit logs |
| Platform superuser | Entire platform | Organization/user status management and platform-wide activity |

Managers can see submitted, approved, or rejected timesheets for employees below them, but cannot see those employees' drafts. Organization administrators have organization-wide visibility.

## Authentication and employee onboarding

### Organization registration

`/register/` creates a new organization and its first organization administrator. Passwords are checked with Django's configured similarity, minimum-length, common-password, and numeric-password validators.

### Employee invitations

There is no separate generic “invite user” action. An organization administrator uses **Employees → Add employee**:

1. Enter the employee's email, role, position, department, and manager.
2. PowerpayERP generates a unique employee ID.
3. The application emails a single-use activation link.
4. The employee chooses their own name and password.
5. The invitation is marked used and cannot be reused.

Administrators never choose or handle employee passwords. Invitations expire, and managers/departments must belong to the same organization.

### Email, password, and OTP login

Users sign in with email and password. A correct password triggers a six-digit one-time password sent by email; the session is created only after OTP verification.

- OTP codes expire after five minutes.
- Codes are stored as hashes, not readable text.
- The screen uses six individual OTP boxes and supports pasting a complete code.
- Repeated login failures are rate-limited.
- OTP resend has a cooldown.
- Password fields have show/hide controls.
- Standard Django password reset is available.

Inactive users cannot sign in. Suspending an organization prevents its members from continuing to access the workspace.

## Dashboard and calendars

`/dashboard/` adapts to the user's role and summarizes active tasks, overdue work, pending timesheet approvals, and team size.

The **Personal** task calendar shows active assignments with start date, due date, priority, status, assignee, and a link to the task. Managers and administrators can switch to a **Team** calendar. A manager's team includes indirect reports, not only direct reports. Only one calendar is displayed at a time.

Superusers see platform-level organization, active-user, task, and audit counts instead of an employee dashboard.

### Global search

The top navigation links to `/search/`. A query of at least two characters searches within the user's permissions across tasks, accessible employees, documents, vouchers, and item requests/line items. Search never broadens existing access.

## Employees and hierarchy

The employee module lists personnel with automatically generated employee IDs, roles, positions, departments, and managers. Employee IDs are unique inside an organization.

Organization administrators create departments and descriptions. Departments can be attached to employees, tasks, vouchers, item requests, documents, and templates.

The hierarchy tree visualizes departments and reporting relationships. The same tree determines which employees appear in a manager's team and approval/request scope.

## Tasks

Each task contains a title, description, instructions, assignee, department, priority, start/due dates, status, and optional protected attachment.

Priorities are **Low**, **Medium**, **High**, and **Urgent**; Medium is the default. A newly delegated task begins as **Assigned**, because work has not started.

An employee can assign work to themselves or their manager. Managers and administrators have broader organization-scoped choices. The assignee receives an in-app notification and email.

### Status workflow

```text
Pending → Assigned → In progress → Submitted → Approved / Rejected → Completed
```

Available transitions depend on the current user and state:

- an assignee can start/resume and submit their task;
- a manager can update tasks in their management scope;
- an organization administrator can update organization tasks; and
- generated voucher/item approval tasks cannot be bypassed through the generic task-status form.

The first active transition records `actual_started_at`; approval or completion records `actual_completed_at`. Timesheet prefill uses these dates.

## Timesheets

Timesheets follow the supplied expert-timesheet layout. Every month has its own sheet in a yearly Excel export. Spreadsheet cells are fully bordered, without PowerPay branding or green/orange worksheet headers.

### Creation and prefill

An employee selects a month and year. The year selector always includes 2025, 2026, and 2027, plus other years represented by stored timesheets.

Generation:

- prefills applicable tasks using actual in-progress-to-completed dates;
- formats activity as `TASK: DESCRIPTION`;
- defaults place of assignment to Kenya while keeping it editable;
- divides daily capacity between concurrent tasks; and
- permits editing/removing prefilled rows and adding work unrelated to a system task.

Entries support date, linked or manual task, activity, hours, days worked, description, notes, location, overnight/per-diem fields, and supporting documentation.

### Draft and submission rules

Employees can edit or delete their draft and rejected timesheets. Submission requires at least one entry, positive hours, no more than one combined workday per date, and an employee/expert signature. Capacity conflicts are highlighted on the detail page. Managers do not see employee drafts.

On submission, the timesheet goes to the employee's manager and creates a medium-priority review task. The requested approver can edit the submitted sheet, approve it, reject it with notes, or move it to their manager. Escalation can continue upward; the review task moves with the approval.

### Manager requests

A manager can request multiple months from multiple active employees in one action. Eligible employees include direct and indirect reports. Each request creates or associates a medium-priority task for the employee.

### Signatures and export

Timesheets support expert, consultant, and manager signatures as appropriate. Users can export:

- one month as Excel;
- one month as PDF; or
- selected months as a multi-sheet yearly Excel workbook.

CSV is intentionally unavailable because it cannot preserve the required layout, sheets, borders, and signatures.

## Leave management

Managers and administrators allocate employee leave by type and calendar year. Types include annual, sick, maternity, paternity, compassionate, study, and other leave. The dashboard calculates allocated, used, pending, and remaining balances.

Employees select a leave type, date range, and reason. The application counts weekdays, rejects ranges with no workday, prevents one request spanning two years, detects overlaps, and prevents requests beyond the allocation.

The employee's manager can approve, reject, or escalate the request to their own manager with an optional message. Escalation can continue through the management chain.

## Payment vouchers

Every employee can prepare a voucher. Numbers are generated uniquely per organization. A voucher records date, payee, optional ID number, department, multiple particulars/amount lines, total, review/payment information, and PDF receipts.

### Approval flow

```text
Draft → Submitted to employee's manager → Approved / Rejected
                                      ↘ Escalated upward
Approved → Paid
```

Submission automatically selects the employee's manager and creates a medium-priority task, notification, and email. A manager may approve, reject, or move it to their manager. The related task follows the approver and completes at the workflow's terminal outcome. Authorized users can export the voucher as PDF.

Receipts are protected PDFs for human review. Receipt OCR is not implemented.

## Item requests

This module replaces the consumables spreadsheet with structured requests. Each request has a generated number, department, purpose, needed-by date, delivery location, and multiple item lines containing quantity, estimated cost, source link, and notes. Total estimated cost is calculated automatically.

Submission sends the request to the employee's manager and creates a medium-priority approval task. Managers can approve, reject, or escalate upward. If rejected, the request is retained with **Rejected** status and review notes, and the generated review task is marked complete.

Authorized users can export item requests as PDF, Word, or Excel.

## Chat and channels

The chat page separates **Private chats** and **Groups / channels** into tabs. Existing direct chats are reused so the same pair of users does not create duplicate threads.

A user can create a named group and invite organization colleagues. Group invitations can be accepted or declined and are distinct from employee account invitations. Members can leave groups according to membership rules.

Messages support text, protected attachments, or both. The sender's bubble is green; messages from others are orange with white text. Recent authenticated activity updates presence: recently seen users appear online, otherwise their last-seen time is shown. Only thread members can access its feed or attachments.

## Documents and templates

Documents have organization, department, or private visibility:

| Visibility | Access |
| --- | --- |
| Organization | Permitted users in the organization |
| Department | The selected department and authorized broader roles |
| Private | The owner and authorized administrative users |

Department visibility requires a department; private visibility requires an owner. Files are delivered through protected Django views, not direct public media links.

Organization administrators upload reusable document templates, optionally associate them with departments, and mark defaults. Template downloads are protected and admin-controlled.

## Notifications, email, and audit logs

The topbar notification dropdown displays unread events. Users can open one notification, mark it read, or mark all read. Success, warning, information, and error messages use the application's modern modal treatment.

Email events include OTPs, employee invitations, password resets, task assignments, generated review tasks, and leave workflow activity.

Every application email is recorded in `OutboundEmail` with status, attempts, error, and sent time. Immediate failures can be retried:

```powershell
python manage.py retry_failed_email
python manage.py retry_failed_email --limit 25
```

Important operations create tenant-scoped audit records with actor, action, entity, request details, IP address, and timestamp. Organization admins can view `/audit/`; audit records are immutable in Django admin.

## Platform administration

Superusers have dedicated controls:

- `/platform/organizations/` searches organizations and shows usage counts;
- `/platform/organizations/<id>/` displays an organization's employees and activity;
- `/platform/users/` searches and activates/deactivates users; and
- `/platform/activity/` filters platform-wide audit activity.

A superuser can suspend/reactivate an organization and deactivate users, but cannot deactivate their own current account.

Create a platform superuser with:

```powershell
python manage.py createsuperuser
```

### Storyboard

The authenticated `/storyboard/` page is an interactive guide explaining modules, roles, screens, and representative workflows. It is intended for onboarding and demonstrations.

## REST API

Interactive Swagger documentation is available at `/api/docs/`, with the machine-readable OpenAPI schema at `/api/schema/`. Both pages and every API endpoint require authentication plus one of these roles:

- an organization administrator, who is always restricted to their own organization; or
- a platform superuser, who can read, create, update, delete, and filter records across all organizations.

Employees and managers cannot access the API or its documentation. The session-authenticated Django REST Framework API exposes:

### Token authentication

API clients can obtain JSON Web Tokens with an organization administrator or platform-superuser email and password:

```http
POST /api/token/
Content-Type: application/json

{
  "email": "admin@example.com",
  "password": "your-password"
}
```

The response contains an access token valid for **24 hours**, a rotating refresh token valid for **3 days**, and the lifetimes in seconds. Send the access token with API requests:

```http
Authorization: Bearer <access-token>
```

Refresh and verify endpoints are:

```text
POST /api/token/refresh/
POST /api/token/verify/
```

Refresh tokens rotate on use and the previous token is blacklisted. Employees and managers cannot obtain API tokens. The Swagger documentation page can be opened from an authorized ERP browser session, but API operations use JWT exclusively. Enter the access token in Swagger's **Authorize** control; session/cookie authorization is not offered for API requests.

| Endpoint | Resource |
| --- | --- |
| `/api/tasks/` | Visible tasks |
| `/api/timesheets/` | Visible timesheets |
| `/api/documents/` | Accessible documents |

CRUD operations are constrained by organization, role, ownership, and workflow state. Task status changes use:

```text
POST /api/tasks/<id>/transition/
```

```json
{
  "status": "in_progress"
}
```

Related IDs from another tenant are rejected. Document files are write-only in API payloads; responses expose an authorized `download_url`. Unsafe session-authenticated requests require a CSRF token.

### API filtering, search, and ordering

Swagger lists every supported parameter. All list APIs support `search`, `ordering`, and page-based pagination. Filters include:

- **Tasks:** organization, assignee, department/null department, priority, status, start-date ranges, due-date ranges, and created-date ranges.
- **Timesheets:** organization, employee, status, period start/end ranges, year, month, requested approver, reviewer, submission-date ranges, and null-state filters.
- **Documents:** organization, visibility, department/null department, owner/null owner, uploader, category/exact or contains, and created-date ranges.

Comma-separated `in` filters are available for task priority/status and document/timesheet status-style fields. Ordering is limited to explicitly documented fields for each resource. Organization filters never override tenant isolation for organization administrators.

## Installation and configuration

### Requirements

- Python 3.11 or newer recommended
- pip
- SQLite for local development
- SMTP credentials for real email delivery

### Windows PowerShell setup

```powershell
git clone <repository-url>
Set-Location PowerpayERP
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). Tailwind CSS, DaisyUI, and Font Awesome are loaded from CDNs, so the browser needs network access for those assets.

### Environment variables

| Variable | Purpose |
| --- | --- |
| `SECRET_KEY` | Long random Django signing secret |
| `DEBUG` | `True` locally; `False` in production |
| `ALLOWED_HOSTS` | Comma-separated allowed hosts |
| `SITE_URL` | Public origin used in email links |
| `EMAIL_BACKEND` | Django email backend |
| `EMAIL_HOST`, `EMAIL_PORT` | SMTP endpoint |
| `EMAIL_USE_TLS` | Enables SMTP TLS |
| `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` | SMTP credentials |
| `DEFAULT_FROM_EMAIL` | Application sender |
| `SECURE_SSL_REDIRECT` | Redirect HTTP to HTTPS |
| `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` | HTTPS-only cookies |
| `SECURE_HSTS_SECONDS` | HSTS duration |

The application timezone is `Africa/Nairobi`.

To inspect emails locally without SMTP, use:

```dotenv
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
```

Messages, including OTP codes, will print in the server terminal.

### Demo data

```powershell
python manage.py seed_demo
```

This repeatably creates Acme Operations, a department, reporting hierarchy, task, timesheet, and notification.

| Email | Role | Password |
| --- | --- | --- |
| `admin@acme.test` | Organization admin | `Powerpay123!` |
| `manager@acme.test` | Manager | `Powerpay123!` |
| `employee@acme.test` | Employee | `Powerpay123!` |

Login still requires the emailed OTP. These credentials are development-only.

## Testing and production

The repository includes a complete Docker production bundle for `erp.powerpayafrica.com`. Follow [DEPLOYMENT.md](DEPLOYMENT.md) for DNS, secrets, PostgreSQL migrations, static files, TLS, backups, updates, and rollback instructions.

Run verification with:

```powershell
python manage.py test
python manage.py check
python manage.py makemigrations --check --dry-run
python -m black --check erp powerpayerp manage.py
python -m djlint templates --profile=django --check --format-js --format-css --indent=2
```

Run `python manage.py check --deploy` with production environment values before release.

### Production checklist

The repository currently uses SQLite. PostgreSQL conversion is intentionally deferred to production deployment.

1. Set a strong `SECRET_KEY`, `DEBUG=False`, real `ALLOWED_HOSTS`, and `SITE_URL`.
2. Configure/test SMTP.
3. Configure the production database and run `python manage.py migrate` in the release.
4. Run `python manage.py collectstatic --noinput`.
5. Serve WSGI through Gunicorn or another supported server.
6. Terminate TLS and enable secure cookies/HSTS.
7. Configure durable media storage and backups while preserving protected downloads.
8. Use a shared cache across application processes so rate limits are consistent.
9. Schedule `python manage.py retry_failed_email`.
10. Run tests and `python manage.py check --deploy`.

General uploads are restricted by extension and size; PDFs also receive a file-signature check. Sensitive task, timesheet, voucher, chat, document, and template files use authorization-aware download endpoints. Production media rules must not bypass those views.

## Project structure

```text
PowerpayERP/
├── erp/
│   ├── management/commands/  # Demo seed and email retry commands
│   ├── migrations/           # Schema migrations
│   ├── admin.py              # Admin registrations
│   ├── api.py                # API serializers and viewsets
│   ├── auth_views.py         # Login, OTP, and invitations
│   ├── emailing.py           # Email rendering and delivery tracking
│   ├── forms.py              # Forms and validation
│   ├── middleware.py         # Tenant access and chat presence
│   ├── models.py             # ERP data model
│   ├── tests.py              # Workflow and isolation tests
│   ├── urls.py               # Application routes
│   └── views.py              # UI workflows, exports, downloads
├── powerpayerp/              # Django settings, root URLs, WSGI/ASGI
├── static/                   # Images and static assets
├── templates/
│   ├── emails/               # HTML/text emails
│   ├── erp/                  # ERP pages and modal forms
│   └── registration/         # Authentication pages
├── .env.example
├── manage.py
└── requirements.txt
```

## Interface and operational notes

- Create, edit, and review forms generally open in modal dialogs.
- Supported forms retain **Cancel**, **Save/Create**, and **Save/Create and add another** actions.
- Green action buttons use white text, including hover states.
- Inputs retain visible borders when unfocused.
- Approval operations use transactions and row locks to reduce conflicting decisions.
- Notifications/email supplement workflow state; database records remain the source of truth.
- Back up uploaded media and the database together.

For an interactive tour after signing in, open `/storyboard/`.
