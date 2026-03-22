from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("families", "0019_event_calendar_reminders"),
    ]

    operations = [
        migrations.AddField(
            model_name="album",
            name="event",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="albums",
                to="families.event",
            ),
        ),
        migrations.AddField(
            model_name="album",
            name="primary_person",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="person_albums",
                to="families.person",
            ),
        ),
        migrations.AddField(
            model_name="photo",
            name="media_type",
            field=models.CharField(
                choices=[("PHOTO", "Photo"), ("VIDEO", "Video"), ("DOCUMENT", "Document")],
                default="PHOTO",
                help_text="Type of media",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="photo",
            name="file",
            field=models.FileField(
                blank=True,
                help_text="Uploaded video or document file",
                null=True,
                upload_to="media/files/%Y/%m/",
            ),
        ),
        migrations.AlterField(
            model_name="photo",
            name="image",
            field=models.ImageField(
                blank=True,
                help_text="The photo image file",
                null=True,
                upload_to="photos/%Y/%m/",
            ),
        ),
        migrations.AddField(
            model_name="photo",
            name="event",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="media_items",
                to="families.event",
            ),
        ),
        migrations.AddField(
            model_name="photo",
            name="primary_person",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="primary_media_items",
                to="families.person",
            ),
        ),
    ]
