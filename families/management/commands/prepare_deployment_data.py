import json
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.core.management import BaseCommand, call_command
from django.db.models import FileField
from django.utils import timezone


DEFAULT_EXCLUDES = [
    "contenttypes",
    "auth.permission",
    "admin.logentry",
    "sessions",
]


class Command(BaseCommand):
    help = (
        "Export a deployment-ready data fixture and media manifest so an existing "
        "local tree can be moved into production."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--output-dir",
            default="deployment_exports",
            help="Directory where the JSON fixture and media manifest will be written.",
        )
        parser.add_argument(
            "--fixture-name",
            default="render_seed.json",
            help="Filename for the exported database fixture.",
        )
        parser.add_argument(
            "--manifest-name",
            default="media_manifest.json",
            help="Filename for the exported media manifest.",
        )
        parser.add_argument(
            "--include-system-data",
            action="store_true",
            help="Include Django system tables that are skipped by default.",
        )

    def handle(self, *args, **options):
        output_dir = Path(options["output_dir"]).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        fixture_path = output_dir / options["fixture_name"]
        manifest_path = output_dir / options["manifest_name"]
        excludes = [] if options["include_system_data"] else DEFAULT_EXCLUDES

        call_command(
            "dumpdata",
            format="json",
            indent=2,
            natural_foreign=True,
            natural_primary=True,
            exclude=excludes,
            output=str(fixture_path),
        )

        manifest = self._build_media_manifest()
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        self.stdout.write(
            self.style.SUCCESS(
                f"Fixture written to {fixture_path}\n"
                f"Media manifest written to {manifest_path}\n"
                f"Referenced media files: {manifest['file_count']} "
                f"({manifest['missing_count']} missing locally)"
            )
        )

    def _build_media_manifest(self):
        media_root = Path(settings.MEDIA_ROOT)
        files = []

        for model in apps.get_models():
            file_fields = [field for field in model._meta.fields if isinstance(field, FileField)]
            if not file_fields:
                continue

            for instance in model.objects.all().iterator():
                for field in file_fields:
                    field_file = getattr(instance, field.name)
                    if not field_file or not field_file.name:
                        continue

                    local_path = media_root / field_file.name
                    files.append(
                        {
                            "model": model._meta.label_lower,
                            "pk": instance.pk,
                            "field": field.name,
                            "name": field_file.name,
                            "local_path": str(local_path),
                            "exists": local_path.exists(),
                        }
                    )

        files.sort(key=lambda item: (item["model"], item["field"], item["pk"], item["name"]))

        return {
            "generated_at": timezone.now().isoformat(),
            "media_root": str(media_root),
            "file_count": len(files),
            "missing_count": sum(1 for item in files if not item["exists"]),
            "files": files,
        }
