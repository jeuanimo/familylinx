from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0005_userprofile_maiden_name"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AdminAccessLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("username", models.CharField(blank=True, help_text="Username or identifier used for the admin attempt.", max_length=150)),
                ("email", models.EmailField(blank=True, help_text="Email address associated with the admin attempt when known.", max_length=254)),
                ("ip_address", models.CharField(blank=True, help_text="Best-effort client IP address for the admin request.", max_length=64)),
                ("forwarded_for", models.CharField(blank=True, help_text="Raw X-Forwarded-For header for the admin request.", max_length=255)),
                ("user_agent", models.CharField(blank=True, help_text="Browser or client user agent string.", max_length=255)),
                ("path", models.CharField(blank=True, help_text="Request path that triggered the admin event.", max_length=255)),
                ("event_type", models.CharField(choices=[("LOGIN_SUCCESS", "Admin Login Success"), ("LOGIN_FAILED", "Admin Login Failed"), ("IP_BLOCKED", "Admin IP Blocked")], db_index=True, max_length=20)),
                ("was_successful", models.BooleanField(default=False, help_text="Whether the admin access attempt succeeded.")),
                ("detail", models.CharField(blank=True, help_text="Extra diagnostic detail about the admin event.", max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("user", models.ForeignKey(blank=True, help_text="Authenticated user when the admin event succeeded.", null=True, on_delete=models.SET_NULL, related_name="admin_access_logs", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Admin Access Log",
                "verbose_name_plural": "Admin Access Logs",
                "ordering": ["-created_at"],
            },
        ),
    ]
