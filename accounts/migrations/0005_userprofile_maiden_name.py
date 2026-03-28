from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0004_userprofile_middle_name"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="maiden_name",
            field=models.CharField(blank=True, help_text="Your maiden name", max_length=100),
        ),
    ]
