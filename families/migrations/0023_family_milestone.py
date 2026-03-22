from django.db import migrations, models
from django.conf import settings
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("families", "0022_album_media_focus"),
    ]

    operations = [
        migrations.CreateModel(
            name="FamilyMilestone",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=200)),
                ("description", models.TextField(blank=True)),
                ("date", models.DateField()),
                ("image", models.ImageField(blank=True, help_text="Optional milestone photo", null=True, upload_to="milestones/%Y/%m/")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_milestones", to=settings.AUTH_USER_MODEL)),
                ("event", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="milestones", to="families.event")),
                ("family", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="milestones", to="families.familyspace")),
                ("person", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="milestones", to="families.person")),
            ],
            options={
                "verbose_name": "Family Milestone",
                "verbose_name_plural": "Family Milestones",
                "ordering": ["-date", "-created_at"],
            },
        ),
    ]
