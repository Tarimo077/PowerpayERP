from django.db.models import Q
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, extend_schema_view

from .forms import validate_business_upload
from .models import Document, Organization, Profile, Task, Timesheet


class IsPlatformAdminOrOrganizationAdmin(BasePermission):
    """Allow platform superusers and the highest organization role only."""

    message = (
        "API access requires an organization administrator or platform administrator."
    )

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        profile = getattr(request.user, "profile", None)
        return bool(
            profile
            and profile.role == "admin"
            and profile.organization_id
            and profile.organization.is_active
        )


def reporting_descendant_ids(manager):
    relationships = Profile.objects.filter(
        organization=manager.organization,
        user__is_active=True,
    ).values_list("id", "manager_id")
    children = {}
    for profile_id, manager_id in relationships:
        children.setdefault(manager_id, []).append(profile_id)

    descendants = []
    queue = list(children.get(manager.id, []))
    seen = {manager.id}
    while queue:
        profile_id = queue.pop(0)
        if profile_id in seen:
            continue
        seen.add(profile_id)
        descendants.append(profile_id)
        queue.extend(children.get(profile_id, []))
    return descendants


class TenantRelatedFieldsMixin:
    def selected_organization(self):
        request = self.context["request"]
        if request.user.is_superuser:
            organization = self.initial_data.get("organization")
            if organization:
                try:
                    return Organization.objects.get(pk=organization)
                except (Organization.DoesNotExist, TypeError, ValueError):
                    return None
            if self.instance:
                return self.instance.organization
            return None
        return request.user.profile.organization

    def validate_assigned_to(self, value):
        organization = self.selected_organization()
        if not organization or value.organization_id != organization.id:
            raise serializers.ValidationError(
                "Assignee belongs to another organization."
            )
        return value

    def validate_organization(self, value):
        request = self.context["request"]
        if request.user.is_superuser:
            return value
        if value.pk != request.user.profile.organization_id:
            raise serializers.ValidationError(
                "Organization administrators can use only their own organization."
            )
        return value

    def validate_department(self, value):
        organization = self.selected_organization()
        if value and (not organization or value.organization_id != organization.id):
            raise serializers.ValidationError(
                "Department belongs to another organization."
            )
        return value


class TaskSerializer(TenantRelatedFieldsMixin, serializers.ModelSerializer):
    assignee_name = serializers.CharField(
        source="assigned_to.user.get_full_name",
        read_only=True,
    )

    class Meta:
        model = Task
        fields = [
            "id",
            "organization",
            "title",
            "description",
            "instructions",
            "priority",
            "status",
            "assigned_to",
            "assignee_name",
            "department",
            "start_date",
            "due_date",
            "actual_started_at",
            "actual_completed_at",
            "created_at",
        ]
        read_only_fields = [
            "status",
            "actual_started_at",
            "actual_completed_at",
            "created_at",
        ]
        extra_kwargs = {"organization": {"required": False}}

    def validate(self, attrs):
        request = self.context["request"]
        organization = attrs.get(
            "organization", getattr(self.instance, "organization", None)
        )
        if not request.user.is_superuser:
            organization = request.user.profile.organization
        if not organization:
            raise serializers.ValidationError(
                {"organization": "This field is required."}
            )
        attrs["organization"] = organization
        assigned_to = attrs.get(
            "assigned_to", getattr(self.instance, "assigned_to", None)
        )
        department = attrs.get("department", getattr(self.instance, "department", None))
        if assigned_to and assigned_to.organization_id != organization.id:
            raise serializers.ValidationError(
                {"assigned_to": "Assignee belongs to another organization."}
            )
        if department and department.organization_id != organization.id:
            raise serializers.ValidationError(
                {"department": "Department belongs to another organization."}
            )
        start = attrs.get("start_date", getattr(self.instance, "start_date", None))
        due = attrs.get("due_date", getattr(self.instance, "due_date", None))
        if start and due and due < start:
            raise serializers.ValidationError(
                {"due_date": "Due date cannot be before the start date."}
            )
        return attrs


class TaskStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Task.STATUSES)


class TimesheetSerializer(serializers.ModelSerializer):
    total_hours = serializers.DecimalField(
        max_digits=7,
        decimal_places=2,
        read_only=True,
    )

    class Meta:
        model = Timesheet
        fields = [
            "id",
            "organization",
            "employee",
            "period_start",
            "period_end",
            "status",
            "total_hours",
            "service_contract",
            "financing",
            "contract_number",
            "country",
            "place_of_assignment",
            "initial_budget_days",
            "submitted_at",
            "reviewed_at",
        ]
        read_only_fields = ["status", "submitted_at", "reviewed_at"]
        extra_kwargs = {"organization": {"required": False}}

    def validate(self, attrs):
        request = self.context["request"]
        organization = attrs.get(
            "organization", getattr(self.instance, "organization", None)
        )
        employee = attrs.get("employee", getattr(self.instance, "employee", None))
        if not request.user.is_superuser:
            organization = request.user.profile.organization
        if not organization:
            raise serializers.ValidationError(
                {"organization": "This field is required."}
            )
        if not employee:
            raise serializers.ValidationError({"employee": "This field is required."})
        if employee.organization_id != organization.id:
            raise serializers.ValidationError(
                {"employee": "Employee belongs to another organization."}
            )
        attrs["organization"] = organization
        return attrs


class DocumentSerializer(serializers.ModelSerializer):
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = [
            "id",
            "organization",
            "title",
            "category",
            "file",
            "download_url",
            "visibility",
            "department",
            "owner",
            "created_at",
        ]
        extra_kwargs = {
            "file": {"write_only": True},
            "organization": {"required": False},
        }
        read_only_fields = ["created_at"]

    def get_download_url(self, obj) -> str:
        request = self.context.get("request")
        path = f"/documents/{obj.pk}/download/"
        return request.build_absolute_uri(path) if request else path

    def validate_department(self, value):
        organization = self._organization()
        if value and (not organization or value.organization_id != organization.id):
            raise serializers.ValidationError(
                "Department belongs to another organization."
            )
        return value

    def validate_file(self, value):
        return validate_business_upload(value, 20 * 1024 * 1024)

    def validate_owner(self, value):
        organization = self._organization()
        if value and (not organization or value.organization_id != organization.id):
            raise serializers.ValidationError("Owner belongs to another organization.")
        return value

    def _organization(self):
        request = self.context["request"]
        if not request.user.is_superuser:
            return request.user.profile.organization
        organization_id = self.initial_data.get("organization")
        if organization_id:
            return Organization.objects.filter(pk=organization_id).first()
        return getattr(self.instance, "organization", None)

    def validate(self, attrs):
        request = self.context["request"]
        organization = attrs.get(
            "organization", getattr(self.instance, "organization", None)
        )
        if not request.user.is_superuser:
            organization = request.user.profile.organization
        if not organization:
            raise serializers.ValidationError(
                {"organization": "This field is required."}
            )
        visibility = attrs.get(
            "visibility", getattr(self.instance, "visibility", "organization")
        )
        department = attrs.get("department", getattr(self.instance, "department", None))
        owner = attrs.get("owner", getattr(self.instance, "owner", None))
        if visibility == "department" and not department:
            raise serializers.ValidationError(
                {"department": "Department visibility requires a department."}
            )
        if visibility == "private" and not owner:
            raise serializers.ValidationError(
                {"owner": "Private visibility requires an owner."}
            )
        if department and department.organization_id != organization.id:
            raise serializers.ValidationError(
                {"department": "Department belongs to another organization."}
            )
        if owner and owner.organization_id != organization.id:
            raise serializers.ValidationError(
                {"owner": "Owner belongs to another organization."}
            )
        attrs["organization"] = organization
        return attrs


class TenantViewSet(viewsets.ModelViewSet):
    permission_classes = [IsPlatformAdminOrOrganizationAdmin]

    def profile(self):
        try:
            return self.request.user.profile
        except Profile.DoesNotExist as exc:
            raise PermissionDenied("Organization membership required.") from exc

    def organization(self):
        return None if self.request.user.is_superuser else self.profile().organization


@extend_schema_view(
    list=extend_schema(
        tags=["Tasks"],
        summary="List tasks",
        description="Returns a paginated, filterable list of tasks. Organization administrators see only their organization; platform administrators can see and filter all organizations.",
    ),
    retrieve=extend_schema(
        tags=["Tasks"],
        summary="Get one task",
        description="Returns one task by ID if it is inside the caller's permitted organization scope.",
    ),
    create=extend_schema(
        tags=["Tasks"],
        summary="Create a task",
        description="Creates an assigned task. Organization administrators cannot assign across organizations; platform administrators must select the target organization.",
    ),
    update=extend_schema(
        tags=["Tasks"],
        summary="Replace a task",
        description="Replaces all writable fields on an existing task while preserving tenant and status safeguards.",
    ),
    partial_update=extend_schema(
        tags=["Tasks"],
        summary="Update part of a task",
        description="Updates only the supplied writable task fields. Use the transition method to change status.",
    ),
    destroy=extend_schema(
        tags=["Tasks"],
        summary="Delete a task",
        description="Permanently deletes a task inside the caller's permitted scope.",
    ),
)
class TaskViewSet(TenantViewSet):
    queryset = Task.objects.all()
    serializer_class = TaskSerializer
    http_method_names = ["get", "post", "put", "patch", "delete", "head", "options"]
    filterset_fields = {
        "organization": ["exact"],
        "assigned_to": ["exact"],
        "department": ["exact", "isnull"],
        "priority": ["exact", "in"],
        "status": ["exact", "in"],
        "start_date": ["exact", "gte", "lte"],
        "due_date": ["exact", "gte", "lte"],
        "created_at": ["date", "date__gte", "date__lte"],
    }
    search_fields = ["title", "description", "instructions", "assigned_to__user__email"]
    ordering_fields = [
        "created_at",
        "updated_at",
        "start_date",
        "due_date",
        "priority",
        "status",
        "title",
    ]
    ordering = ["-created_at"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset.none()
        queryset = Task.objects.all().order_by("-created_at")
        organization = self.organization()
        return (
            queryset
            if organization is None
            else queryset.filter(organization=organization)
        )

    def perform_create(self, serializer):
        organization = (
            serializer.validated_data.get("organization") or self.organization()
        )
        if not organization:
            raise serializers.ValidationError(
                {"organization": "This field is required."}
            )
        serializer.save(
            organization=organization, created_by=self.request.user, status="assigned"
        )

    @action(detail=True, methods=["post"])
    @extend_schema(
        tags=["Tasks"],
        summary="Transition a task status",
        description="Changes a task to another valid status. Send the target status in the request body; generic update methods keep status read-only.",
        request=TaskStatusSerializer,
        responses=TaskSerializer,
    )
    def transition(self, request, pk=None):
        task = self.get_object()
        form = TaskStatusSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        target = form.validated_data["status"]

        if target == task.status:
            raise PermissionDenied("That task transition is not allowed.")

        task.status = target
        task.save(update_fields=["status", "updated_at"])
        serializer = TaskSerializer(task, context={"request": request})
        return Response(serializer.data)


@extend_schema_view(
    list=extend_schema(
        tags=["Timesheets"],
        summary="List timesheets",
        description="Returns paginated timesheets with employee, status, period, approver, reviewer, search, and ordering filters.",
    ),
    retrieve=extend_schema(
        tags=["Timesheets"],
        summary="Get one timesheet",
        description="Returns one timesheet by ID inside the caller's organization scope.",
    ),
    create=extend_schema(
        tags=["Timesheets"],
        summary="Create a draft timesheet",
        description="Creates a monthly draft for the selected employee. Employee and organization must match.",
    ),
    update=extend_schema(
        tags=["Timesheets"],
        summary="Replace a timesheet",
        description="Replaces writable timesheet metadata. Organization administrators cannot edit approved sheets; platform administrators can.",
    ),
    partial_update=extend_schema(
        tags=["Timesheets"],
        summary="Update part of a timesheet",
        description="Updates only supplied writable timesheet fields while preserving tenant validation.",
    ),
    destroy=extend_schema(
        tags=["Timesheets"],
        summary="Delete a timesheet",
        description="Deletes a draft timesheet. Platform administrators may delete any permitted timesheet.",
    ),
)
class TimesheetViewSet(TenantViewSet):
    queryset = Timesheet.objects.all()
    serializer_class = TimesheetSerializer
    filterset_fields = {
        "organization": ["exact"],
        "employee": ["exact"],
        "status": ["exact", "in"],
        "period_start": ["exact", "gte", "lte", "year", "month"],
        "period_end": ["exact", "gte", "lte"],
        "requested_approver": ["exact", "isnull"],
        "reviewed_by": ["exact", "isnull"],
        "submitted_at": ["date", "date__gte", "date__lte", "isnull"],
    }
    search_fields = [
        "employee__user__first_name",
        "employee__user__last_name",
        "employee__user__email",
        "service_contract",
        "contract_number",
        "country",
        "place_of_assignment",
    ]
    ordering_fields = [
        "created_at",
        "updated_at",
        "period_start",
        "period_end",
        "status",
        "submitted_at",
        "reviewed_at",
    ]
    ordering = ["-period_start"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset.none()
        queryset = Timesheet.objects.all().order_by("-period_start")
        organization = self.organization()
        return (
            queryset
            if organization is None
            else queryset.filter(organization=organization)
        )

    def perform_create(self, serializer):
        serializer.save(status="draft")

    def perform_update(self, serializer):
        timesheet = self.get_object()
        if not self.request.user.is_superuser and timesheet.status == "approved":
            raise PermissionDenied("This timesheet cannot be edited.")
        serializer.save()

    def perform_destroy(self, instance):
        if not self.request.user.is_superuser and instance.status != "draft":
            raise PermissionDenied("Only an owned draft timesheet can be deleted.")
        instance.delete()


@extend_schema_view(
    list=extend_schema(
        tags=["Documents"],
        summary="List documents",
        description="Returns paginated documents with organization, visibility, department, owner, uploader, category, search, and ordering filters.",
    ),
    retrieve=extend_schema(
        tags=["Documents"],
        summary="Get one document",
        description="Returns document metadata and an authorized download URL. Raw file content is not embedded in the response.",
    ),
    create=extend_schema(
        tags=["Documents"],
        summary="Upload a document",
        description="Creates a document and validates its file, visibility, department, owner, and organization relationships.",
    ),
    update=extend_schema(
        tags=["Documents"],
        summary="Replace a document",
        description="Replaces writable document metadata/file while enforcing tenant and visibility rules.",
    ),
    partial_update=extend_schema(
        tags=["Documents"],
        summary="Update part of a document",
        description="Updates only supplied document fields while enforcing tenant and visibility rules.",
    ),
    destroy=extend_schema(
        tags=["Documents"],
        summary="Delete a document",
        description="Permanently deletes a document record inside the caller's permitted scope.",
    ),
)
class DocumentViewSet(TenantViewSet):
    queryset = Document.objects.all()
    serializer_class = DocumentSerializer
    filterset_fields = {
        "organization": ["exact"],
        "visibility": ["exact", "in"],
        "department": ["exact", "isnull"],
        "owner": ["exact", "isnull"],
        "uploaded_by": ["exact"],
        "category": ["exact", "icontains"],
        "created_at": ["date", "date__gte", "date__lte"],
    }
    search_fields = [
        "title",
        "category",
        "owner__user__first_name",
        "owner__user__last_name",
        "owner__user__email",
    ]
    ordering_fields = ["created_at", "updated_at", "title", "category", "visibility"]
    ordering = ["-created_at"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset.none()
        queryset = Document.objects.all().order_by("-created_at")
        organization = self.organization()
        return (
            queryset
            if organization is None
            else queryset.filter(organization=organization)
        )

    def perform_create(self, serializer):
        serializer.save(uploaded_by=self.request.user)

    def perform_update(self, serializer):
        self.get_object()
        serializer.save()

    def perform_destroy(self, instance):
        instance.delete()
