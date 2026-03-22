from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("families", "0021_life_story_time_capsule"),
    ]

    operations = [
        migrations.AddField(
            model_name="album",
            name="media_focus",
            field=models.CharField(
                choices=[
                    ("MIXED", "Mixed Media"),
                    ("PHOTOS", "Photos"),
                    ("VIDEOS", "Videos"),
                    ("DOCUMENTS", "Documents"),
                ],
                default="MIXED",
                help_text="Primary media type for this album",
                max_length=15,
            ),
        ),
    ]
