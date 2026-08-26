from rest_framework import serializers, viewsets
from rest_framework.exceptions import PermissionDenied
from .models import Task, Timesheet, Document, Profile

class TaskSerializer(serializers.ModelSerializer):
    assignee_name=serializers.CharField(source="assigned_to.user.get_full_name",read_only=True)
    class Meta: 
        model=Task

    fields=["id","title","description","priority","status","assigned_to","assignee_name","department","start_date","due_date","created_at"]
    read_only_fields=["created_at"]

class TimesheetSerializer(serializers.ModelSerializer):
    total_hours=serializers.DecimalField(max_digits=7,decimal_places=2,read_only=True)
    class Meta: 
        model=Timesheet

    fields=["id","employee","period_start","period_end","status","total_hours","submitted_at","reviewed_at"]

class DocumentSerializer(serializers.ModelSerializer):
    class Meta: 
        model=Document
    fields=["id","title","category","file","visibility","department","owner","created_at"]

class TenantViewSet(viewsets.ModelViewSet):
    def profile(self):
        try:return self.request.user.profile
        except Profile.DoesNotExist: 
            raise PermissionDenied("Organization membership required")

    def perform_create(self,serializer): 
        serializer.save(organization=self.profile().organization)

class TaskViewSet(TenantViewSet):
    serializer_class=TaskSerializer
    def get_queryset(self):
        p=self.profile()
        qs=Task.objects.filter(organization=p.organization).order_by("-created_at")
        return qs.filter(assigned_to=p) if p.role=="employee" else qs

    def perform_create(self,serializer):
        p=self.profile()
        if p.role not in ["admin","manager"]: 
            raise PermissionDenied()
        serializer.save(organization=p.organization,created_by=self.request.user)

class TimesheetViewSet(TenantViewSet):
    serializer_class=TimesheetSerializer
    def get_queryset(self):
        p=self.profile()
        qs=Timesheet.objects.filter(organization=p.organization).order_by("-period_start")
        return qs.filter(employee=p) if p.role=="employee" else qs

    def perform_create(self,serializer): 
        serializer.save(organization=self.profile().organization,employee=self.profile())

class DocumentViewSet(TenantViewSet):
    serializer_class=DocumentSerializer
    def get_queryset(self): 
        return Document.objects.filter(organization=self.profile().organization).order_by("-created_at")

    def perform_create(self,serializer): 
        serializer.save(organization=self.profile().organization,uploaded_by=self.request.user)
