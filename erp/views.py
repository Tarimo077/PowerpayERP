import csv
from io import BytesIO
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.db.models import Count, Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from .decorators import roles_allowed
from .forms import *
from .models import *
from .emailing import send_invite_email

def _profile(request): 
    return get_object_or_404(Profile.objects.select_related("organization","department"),user=request.user)


def _audit(request,action,obj):
    p=getattr(request.user,"profile",None)
    AuditLog.objects.create(organization=getattr(p,"organization",None),actor=request.user,action=action,entity_type=obj.__class__.__name__,entity_id=str(obj.pk),ip_address=request.META.get("REMOTE_ADDR"))


def home(request): 
    return redirect("dashboard") if request.user.is_authenticated else render(request,"erp/landing.html")


def register(request):
    if request.user.is_authenticated: 
        return redirect("dashboard")
    form=RegistrationForm(request.POST or None)

    if request.method=="POST" and form.is_valid():
        form.save()
        messages.success(request,"Your organization workspace is ready. Sign in with your email to continue.")
        return redirect("login")
    
    return render(request,"registration/register.html",{"form":form})


@login_required
def dashboard(request):
    if request.user.is_superuser:
        return render(request,"erp/dashboard.html",{"super_view":True,"stats":[("Organizations",Organization.objects.count()),("Active users",User.objects.filter(is_active=True).count()),("Tasks",Task.objects.count()),("Audit events",AuditLog.objects.count())],"recent_audit":AuditLog.objects.select_related("actor","organization")[:8]})

    p=_profile(request)
    org=p.organization
    tasks=Task.objects.filter(organization=org)

    if p.role=="employee": 
        tasks=tasks.filter(assigned_to=p)
    elif p.role=="manager": 
        tasks=tasks.filter(Q(department=p.department)|Q(assigned_to__manager=p)).distinct()

    sheets=Timesheet.objects.filter(organization=org)

    if p.role=="employee": 
        sheets=sheets.filter(employee=p)

    elif p.role=="manager": 
        sheets=sheets.filter(Q(employee__department=p.department)|Q(employee__manager=p)).distinct()

    stats=[("Active tasks",tasks.exclude(status__in=["completed","approved"]).count()),("Overdue",tasks.filter(due_date__lt=timezone.localdate()).exclude(status__in=["completed","approved"]).count()),("Pending approvals",sheets.filter(status="submitted").count()),("Team members",Profile.objects.filter(organization=org,user__is_active=True).count() if p.role=="admin" else Profile.objects.filter(manager=p).count())]
    return render(request,"erp/dashboard.html",{"stats":stats,"tasks":tasks.select_related("assigned_to__user")[:8],"timesheets":sheets.select_related("employee__user")[:6]})

@login_required
def storyboard(request):
    return render(request,"erp/storyboard.html")


@login_required
def tasks(request):
    p=_profile(request)

    qs=Task.objects.filter(organization=p.organization).select_related("assigned_to__user","department")

    if p.role=="employee": 
        qs=qs.filter(assigned_to=p)

    elif p.role=="manager": 
        qs=qs.filter(Q(department=p.department)|Q(assigned_to__manager=p)).distinct()

    q=request.GET.get("q","") 
    status=request.GET.get("status","")

    if q: 
        qs=qs.filter(Q(title__icontains=q)|Q(description__icontains=q)|Q(assigned_to__user__first_name__icontains=q))
    if status: 
        qs=qs.filter(status=status)

    return render(request,"erp/task_list.html",{"tasks":qs,"statuses":Task.STATUSES})

@login_required
@roles_allowed("admin","manager")
def task_create(request):
    p=_profile(request)
    form=TaskForm(request.POST or None,request.FILES or None,organization=p.organization)
    if request.method=="POST" and form.is_valid():
        obj=form.save(False)
        obj.organization=p.organization
        obj.created_by=request.user
        obj.full_clean()
        obj.save()
        Notification.objects.create(user=obj.assigned_to.user,title="New task assigned",message=obj.title,url=f"/tasks/{obj.pk}/")
        _audit(request,"task_created",obj) 
        messages.success(request,"Task assigned successfully.") 
        return redirect("task_create" if request.POST.get("_add_another") else "tasks")
    
    return render(request,"erp/form.html",{"form":form,"title":"Assign task","submit":"Create task"})

@login_required
def task_detail(request,pk):
    p=_profile(request)
    obj=get_object_or_404(Task,pk=pk,organization=p.organization)
    if p.role=="employee" and obj.assigned_to_id!=p.id: 
        return redirect("tasks")
    return render(request,"erp/task_detail.html",{"task":obj})

@login_required
@require_POST
def task_status(request,pk):
    p=_profile(request)
    obj=get_object_or_404(Task,pk=pk,organization=p.organization)
    new=request.POST.get("status")
    allowed={"employee":["in_progress","submitted"],"manager":["approved","rejected","completed"],"admin":[x[0] for x in Task.STATUSES]}
    if obj.assigned_to_id!=p.id and p.role=="employee" or new not in allowed.get(p.role,[]): 
        messages.error(request,"Invalid status transition.")

    else: 
        obj.status=new
        obj.save(update_fields=["status","updated_at"])
        _audit(request,"task_status_changed",obj)
        messages.success(request,"Task status updated.")
    return redirect("task_detail",pk=pk)

@login_required
def timesheets(request):
    p=_profile(request)
    qs=Timesheet.objects.filter(organization=p.organization).select_related("employee__user","reviewed_by").annotate(hours=Sum("entries__hours"))
    if p.role=="employee": 
        qs=qs.filter(employee=p)
    elif p.role=="manager": 
        qs=qs.filter(Q(employee__department=p.department)|Q(employee__manager=p)).distinct()
    return render(request,"erp/timesheet_list.html",{"timesheets":qs})

@login_required
def timesheet_create(request):
    p=_profile(request)
    form=TimesheetForm(request.POST or None)
    if request.method=="POST" and form.is_valid(): 
        obj=form.save(False)
        obj.organization=p.organization
        obj.employee=p
        obj.save()
        _audit(request,"timesheet_created",obj)
        messages.success(request,"Timesheet created.")
        if request.POST.get("_add_another"): return redirect("timesheet_create")
        return redirect("timesheet_detail",pk=obj.pk)
    return render(request,"erp/form.html",{"form":form,"title":"New timesheet","submit":"Create timesheet"})


@login_required
def timesheet_detail(request,pk):
    p=_profile(request)
    obj=get_object_or_404(Timesheet.objects.prefetch_related("entries"),pk=pk,organization=p.organization)
    if p.role=="employee" and obj.employee_id!=p.id: 
        return redirect("timesheets")
    form=EntryForm(request.POST or None,request.FILES or None,organization=p.organization)

    if request.method=="POST" and form.is_valid() and obj.status in ["draft","rejected"] and obj.employee_id==p.id:
        entry=form.save(False)
        entry.timesheet=obj
        entry.full_clean()
        entry.save()
        _audit(request,"timesheet_entry_added",entry)
        messages.success(request,"Timesheet entry added.")
        return redirect("timesheet_detail",pk=pk)
    return render(request,"erp/timesheet_detail.html",{"timesheet":obj,"form":form})


@login_required
@require_POST
def timesheet_action(request,pk):
    p=_profile(request)
    obj=get_object_or_404(Timesheet,pk=pk,organization=p.organization)
    action=request.POST.get("action")
    if action=="submit" and obj.employee_id==p.id and obj.status in ["draft","rejected"]:
        if not obj.entries.exists(): 
            messages.error(request,"Add at least one entry before submitting.")
        else:
            obj.status="submitted"
            obj.submitted_at=timezone.now()
            obj.save()
            recipients=User.objects.filter(profile__organization=p.organization,profile__role__in=["admin","manager"],is_active=True)
            Notification.objects.bulk_create([Notification(user=u,title="Timesheet awaiting review",message=str(obj),url=f"/timesheets/{obj.pk}/") for u in recipients])
            _audit(request,"timesheet_submitted",obj)
    elif action in ["approved","rejected"] and p.role in ["admin","manager"] and obj.status=="submitted": 
        obj.status=action
        obj.reviewed_by=request.user
        obj.reviewed_at=timezone.now()
        obj.review_notes=request.POST.get("notes","")
        obj.save()
        Notification.objects.create(user=obj.employee.user,title=f"Timesheet {action}",message=obj.review_notes,url=f"/timesheets/{obj.pk}/")
        _audit(request,f"timesheet_{action}",obj)
    else: 
        messages.error(request,"That action is not allowed.")
    return redirect("timesheet_detail",pk=pk)


@login_required
def timesheet_export(request,pk,fmt):
    p=_profile(request)
    obj=get_object_or_404(Timesheet.objects.prefetch_related("entries"),pk=pk,organization=p.organization)
    if p.role=="employee" and obj.employee_id!=p.id: 
        return redirect("timesheets")
    if fmt=="csv":
        response=HttpResponse(content_type="text/csv",headers={"Content-Disposition":f'attachment; filename="timesheet-{pk}.csv"'})
        w=csv.writer(response)
        w.writerow([p.organization.name,"Timesheet",obj.employee.user.get_full_name()])
        w.writerow(["Date","Task","Hours","Description"])
        [w.writerow([e.date,e.task_performed,e.hours,e.description]) for e in obj.entries.all()]
        w.writerow(["","Total",obj.total_hours,""])
        return response
    
    buf=BytesIO()
    c=canvas.Canvas(buf,pagesize=A4)
    c.setTitle(f"Timesheet {pk}")
    c.setFont("Helvetica-Bold",18)
    c.drawString(50,800,p.organization.name)
    c.setFont("Helvetica",11)
    c.drawString(50,778,f"Timesheet · {obj.employee.user.get_full_name()} · {obj.period_start} to {obj.period_end}")
    y=740
    for e in obj.entries.all(): 
        c.drawString(50,y,str(e.date))
        c.drawString(130,y,e.task_performed[:55])
        c.drawRightString(540,y,f"{e.hours} hrs")
        y-=22
    c.setFont("Helvetica-Bold",11)
    c.drawString(50,y-10,f"Total hours: {obj.total_hours}   Status: {obj.get_status_display()}")
    c.save()
    return HttpResponse(buf.getvalue(),content_type="application/pdf",headers={"Content-Disposition":f'attachment; filename="timesheet-{pk}.pdf"'})


@login_required
@roles_allowed("admin","manager")
def employees(request):
    p=_profile(request)
    qs=Profile.objects.filter(organization=p.organization).select_related("user","department","manager__user")
    if p.role=="manager": 
        qs=qs.filter(Q(department=p.department)|Q(manager=p)).distinct()
    pending=UserInvite.objects.filter(organization=p.organization,is_used=False).select_related("department","manager__user").order_by("-created_at") if p.role=="admin" else UserInvite.objects.none()
    return render(request,"erp/employee_list.html",{"employees":qs,"pending_invites":pending})


@login_required
@roles_allowed("admin")
def employee_create(request):
    p=_profile(request)
    form=EmployeeForm(request.POST or None,organization=p.organization)
    if request.method=="POST" and form.is_valid(): 
        obj=form.save(False)
        obj.organization=p.organization
        obj.invited_by=request.user
        obj.save()
        send_invite_email(obj)
        _audit(request,"employee_invited",obj)
        messages.success(request,f"Employee {obj.employee_id} created and an activation invitation was sent to {obj.email}.")
        return redirect("employee_create" if request.POST.get("_add_another") else "employees")
    return render(request,"erp/form.html",{"form":form,"title":"Add employee","submit":"Create and invite"})


@login_required
@roles_allowed("admin")
def departments(request):
    p=_profile(request)
    form=DepartmentForm(request.POST or None)
    if request.method=="POST" and form.is_valid(): 
        obj=form.save(False)
        obj.organization=p.organization
        obj.save()
        _audit(request,"department_created",obj)
        messages.success(request,"Department created.")
        return redirect("departments")
    return render(request,"erp/departments.html",{"departments":Department.objects.filter(organization=p.organization).annotate(member_count=Count("members")),"form":form})


@login_required
def documents(request):
    p=_profile(request)
    qs=Document.objects.filter(organization=p.organization).select_related("uploaded_by","department")
    if p.role=="employee": 
        qs=qs.filter(Q(visibility="organization")|Q(department=p.department,visibility="department")|Q(owner=p)).distinct()
    return render(request,"erp/document_list.html",{"documents":qs})


@login_required
def document_upload(request):
    p=_profile(request)
    form=DocumentForm(request.POST or None,request.FILES or None,organization=p.organization)
    if request.method=="POST" and form.is_valid(): 
        obj=form.save(False)
        obj.organization=p.organization
        obj.uploaded_by=request.user
        obj.save()
        _audit(request,"document_uploaded",obj)
        messages.success(request,"Document uploaded.")
        return redirect("document_upload" if request.POST.get("_add_another") else "documents")
    return render(request,"erp/form.html",{"form":form,"title":"Upload document","submit":"Upload"})


@login_required
@roles_allowed("admin")
def templates(request):
    p=_profile(request)
    form=TemplateForm(request.POST or None,request.FILES or None,organization=p.organization)
    if request.method=="POST" and form.is_valid(): 
        obj=form.save(False)
        obj.organization=p.organization
        obj.uploaded_by=request.user
        obj.save()
        _audit(request,"template_uploaded",obj)
        messages.success(request,"Template uploaded.")
        return redirect("templates")
    return render(request,"erp/templates.html",{"templates":DocumentTemplate.objects.filter(organization=p.organization),"form":form})


@login_required
def notifications(request): 
    request.user.notifications.filter(is_read=False).update(is_read=True)
    return render(request,"erp/notifications.html",{"notifications":request.user.notifications.all()})


@login_required
@roles_allowed("admin")
def audit_logs(request): 
    return render(request,"erp/audit.html",{"logs":AuditLog.objects.filter(organization=_profile(request).organization).select_related("actor")[:200]})

def _superuser_required(view): return user_passes_test(lambda user:user.is_superuser,login_url="login")(view)

@login_required
@_superuser_required
def platform_organizations(request):
    q=request.GET.get("q","").strip()
    organizations=Organization.objects.annotate(user_count=Count("profiles",distinct=True),department_count=Count("departments",distinct=True),task_count=Count("task",distinct=True)).order_by("name")
    if q: organizations=organizations.filter(Q(name__icontains=q)|Q(business_email__icontains=q)|Q(industry__icontains=q))
    return render(request,"erp/platform_organizations.html",{"organizations":organizations})

@login_required
@_superuser_required
def platform_organization_detail(request,pk):
    org=get_object_or_404(Organization,pk=pk)
    return render(request,"erp/platform_organization_detail.html",{"organization":org,"stats":[("Employees",Profile.objects.filter(organization=org).count()),("Departments",Department.objects.filter(organization=org).count()),("Tasks",Task.objects.filter(organization=org).count()),("Timesheets",Timesheet.objects.filter(organization=org).count()),("Documents",Document.objects.filter(organization=org).count())],"employees":Profile.objects.filter(organization=org).select_related("user","department","manager__user")[:25],"tasks":Task.objects.filter(organization=org).select_related("assigned_to__user","department")[:20],"timesheets":Timesheet.objects.filter(organization=org).select_related("employee__user","reviewed_by")[:20],"documents":Document.objects.filter(organization=org).select_related("uploaded_by","department")[:20],"activity":AuditLog.objects.filter(organization=org).select_related("actor")[:20]})

@login_required
@_superuser_required
@require_POST
def platform_organization_status(request,pk):
    org=get_object_or_404(Organization,pk=pk); org.is_active=not org.is_active; org.save(update_fields=["is_active","updated_at"])
    AuditLog.objects.create(organization=org,actor=request.user,action="organization_activated" if org.is_active else "organization_suspended",entity_type="Organization",entity_id=str(org.pk),ip_address=request.META.get("REMOTE_ADDR"))
    messages.success(request,f"{org.name} has been {'activated' if org.is_active else 'suspended'}.")
    if request.POST.get("next")==f"/platform/organizations/{org.pk}/":
        return redirect("platform_organization_detail",pk=org.pk)
    return redirect("platform_organizations")

@login_required
@_superuser_required
def platform_users(request):
    q=request.GET.get("q","").strip(); users=User.objects.select_related("profile__organization","profile__department").order_by("-date_joined")
    if q: users=users.filter(Q(email__icontains=q)|Q(username__icontains=q)|Q(first_name__icontains=q)|Q(last_name__icontains=q)|Q(profile__organization__name__icontains=q))
    return render(request,"erp/platform_users.html",{"platform_users":users})

@login_required
@_superuser_required
@require_POST
def platform_user_status(request,pk):
    user=get_object_or_404(User,pk=pk)
    if user==request.user: messages.error(request,"You cannot deactivate your own platform account.")
    else:
        user.is_active=not user.is_active; user.save(update_fields=["is_active"]); profile=getattr(user,"profile",None); AuditLog.objects.create(organization=getattr(profile,"organization",None),actor=request.user,action="user_activated" if user.is_active else "user_deactivated",entity_type="User",entity_id=str(user.pk)); messages.success(request,f"{user.email or user.username} has been {'activated' if user.is_active else 'deactivated'}.")
    return redirect("platform_users")

@login_required
@_superuser_required
def platform_activity(request):
    organization=request.GET.get("organization",""); action=request.GET.get("action","").strip(); logs=AuditLog.objects.select_related("actor","organization")
    if organization: logs=logs.filter(organization_id=organization)
    if action: logs=logs.filter(action__icontains=action)
    return render(request,"erp/platform_activity.html",{"logs":logs[:500],"organizations":Organization.objects.order_by("name")})
