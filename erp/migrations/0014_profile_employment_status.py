from django.db import migrations, models


def mark_inactive_profiles_suspended(apps, schema_editor):
    profile = apps.get_model("erp", "Profile")
    profile.objects.filter(user__is_active=False).update(employment_status="suspended")


class Migration(migrations.Migration):
    dependencies = [("erp", "0013_outboundemail")]

    operations = [
        migrations.AddField(
            model_name="profile",
            name="employment_status",
            field=models.CharField(
                choices=[
                    ("active", "Active"),
                    ("suspended", "Suspended"),
                    ("removed", "Removed"),
                ],
                default="active",
                max_length=20,
            ),
        ),
        migrations.RunPython(
            mark_inactive_profiles_suspended,
            migrations.RunPython.noop,
        ),
    ]
