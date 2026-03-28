from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("families", "0027_invite_email_tracking"),
    ]

    operations = [
        migrations.AddField(
            model_name="invite",
            name="accepted_by",
            field=models.ForeignKey(
                blank=True,
                help_text="User who accepted the invite",
                null=True,
                on_delete=models.SET_NULL,
                related_name="accepted_family_invites",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
