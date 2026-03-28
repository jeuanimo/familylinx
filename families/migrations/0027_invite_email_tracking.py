from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("families", "0026_family_kudos"),
    ]

    operations = [
        migrations.AddField(
            model_name="invite",
            name="last_email_attempt_at",
            field=models.DateTimeField(
                blank=True,
                help_text="When the system last attempted to send the invite email",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="invite",
            name="last_email_error",
            field=models.TextField(
                blank=True,
                help_text="Last email delivery error, if sending failed",
            ),
        ),
    ]
