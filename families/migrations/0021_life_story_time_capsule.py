from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("families", "0020_media_vault"),
    ]

    operations = [
        migrations.CreateModel(
            name="LifeStory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(default="Life Story", max_length=200)),
                ("summary", models.TextField(blank=True, help_text="Optional overview paragraph")),
                ("release_at", models.DateTimeField(blank=True, help_text="Future release date (time capsule unlock)", null=True)),
                ("is_published", models.BooleanField(default=True, help_text="Show to family now")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_life_stories", to="accounts.user")),
                ("person", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="life_stories", to="families.person")),
            ],
            options={
                "verbose_name": "Life Story",
                "verbose_name_plural": "Life Stories",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="TimeCapsule",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=200)),
                ("message", models.TextField(blank=True)),
                ("open_at", models.DateTimeField(help_text="When this capsule unlocks")),
                ("is_opened", models.BooleanField(default=False)),
                ("attachment", models.FileField(blank=True, help_text="Optional attachment (letter, video, zip)", null=True, upload_to="timecapsules/%Y/%m/")),
                ("audio", models.FileField(blank=True, help_text="Optional audio recording", null=True, upload_to="timecapsules/audio/%Y/%m/")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("created_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_time_capsules", to="accounts.user")),
                ("family", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="time_capsules", to="families.familyspace")),
            ],
            options={
                "ordering": ["open_at"],
            },
        ),
        migrations.CreateModel(
            name="LifeStorySection",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("heading", models.CharField(max_length=200)),
                ("content", models.TextField(blank=True)),
                ("order", models.PositiveIntegerField(default=0)),
                ("audio", models.FileField(blank=True, help_text="Optional audio recording", null=True, upload_to="lifestories/audio/%Y/%m/")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("life_story", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="sections", to="families.lifestory")),
            ],
            options={
                "ordering": ["order", "created_at"],
            },
        ),
    ]
