from datetime import datetime, time
from django.db import migrations, models
from django.utils import timezone


def backfill_task_timestamps(apps, schema_editor):
    Task = apps.get_model("erp", "Task")
    for task in Task.objects.filter(
        status__in=["in_progress", "submitted", "approved", "rejected", "completed"]
    ).iterator():
        started = datetime.combine(task.start_date, time.min)
        if timezone.is_naive(started):
            started = timezone.make_aware(started)
        task.actual_started_at = started
        fields = ["actual_started_at"]
        if task.status in ["approved", "completed"]:
            task.actual_completed_at = task.updated_at
            fields.append("actual_completed_at")
        task.save(update_fields=fields)


class Migration(migrations.Migration):
    dependencies = [("erp", "0011_itemrequest_itemrequestline_and_more")]
    operations = [
        migrations.AddField(
            model_name="task",
            name="actual_started_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="task",
            name="actual_completed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(backfill_task_timestamps, migrations.RunPython.noop),
    ]
