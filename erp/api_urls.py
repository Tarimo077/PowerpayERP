from rest_framework.routers import DefaultRouter
from .api import TaskViewSet,TimesheetViewSet,DocumentViewSet

router=DefaultRouter()
router.register("tasks",TaskViewSet,basename="api-task")
router.register("timesheets",TimesheetViewSet,basename="api-timesheet")
router.register("documents",DocumentViewSet,basename="api-document")
urlpatterns=router.urls
