from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0006_adminaccesslog"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SiteAccessLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("username", models.CharField(blank=True, help_text="Username or identifier used for the site auth event.", max_length=150)),
                ("email", models.EmailField(blank=True, help_text="Email address associated with the auth event when known.", max_length=254)),
                ("ip_address", models.CharField(blank=True, help_text="Best-effort client IP address for the auth event.", max_length=64)),
                ("forwarded_for", models.CharField(blank=True, help_text="Raw X-Forwarded-For header for the auth event.", max_length=255)),
                ("user_agent", models.CharField(blank=True, help_text="Browser or client user agent string.", max_length=255)),
                ("path", models.CharField(blank=True, help_text="Request path that triggered the auth event.", max_length=255)),
                ("event_type", models.CharField(choices=[("LOGIN_SUCCESS", "Login Success"), ("LOGIN_FAILED", "Login Failed"), ("SIGNUP_CREATED", "Signup Created")], db_index=True, max_length=20)),
                ("was_successful", models.BooleanField(default=False, help_text="Whether the auth event succeeded.")),
                ("detail", models.CharField(blank=True, help_text="Extra diagnostic detail about the auth event.", max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("user", models.ForeignKey(blank=True, help_text="Authenticated user associated with the event when known.", null=True, on_delete=models.SET_NULL, related_name="site_access_logs", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Site Access Log",
                "verbose_name_plural": "Site Access Logs",
                "ordering": ["-created_at"],
            },
        ),
    ]
