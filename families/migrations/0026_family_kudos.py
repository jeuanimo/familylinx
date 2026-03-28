from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ("families", "0025_prayer_requests_testimonies"),
    ]

    operations = [
        migrations.CreateModel(
            name="FamilyKudos",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=200)),
                ("message", models.TextField(blank=True)),
                ("image", models.ImageField(blank=True, help_text="Optional image for the announcement", null=True, upload_to="kudos/%Y/%m/")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(help_text="User who added this kudos entry", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_kudos_entries", to=settings.AUTH_USER_MODEL)),
                ("family", models.ForeignKey(help_text="Family this kudos entry belongs to", on_delete=django.db.models.deletion.CASCADE, related_name="kudos_entries", to="families.familyspace")),
                ("person", models.ForeignKey(blank=True, help_text="Linked person (optional)", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="kudos_entries", to="families.person")),
            ],
            options={
                "verbose_name": "Family Kudos",
                "verbose_name_plural": "Family Kudos",
                "ordering": ["-created_at"],
            },
        ),
    ]
