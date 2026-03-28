# Render First Deploy

This project can keep your existing local family-tree data, but the first production deploy needs a one-time export/import step.

## 1. Secrets and services

- `render.yaml` now uses a generated `SECRET_KEY` for new Blueprint installs.
- `DATABASE_URL` is already wired to the Render Postgres service.
- `CLOUDINARY_URL` should stay manual because it is your Cloudinary credential.

## 2. Export your current local data

Run:

```bash
python manage.py prepare_deployment_data
```

This writes:

- `deployment_exports/render_seed.json`
- `deployment_exports/media_manifest.json`

The JSON fixture is for the database import.
The media manifest is a checklist of every file path still living under local `MEDIA_ROOT`.

## 3. Import the database into production

After the Render Postgres database exists, load the exported fixture into that database one time.

Recommended approach:

1. Open the Render Postgres dashboard and copy the external database URL for a one-time import.
2. From your local machine, point Django at that database:

```bash
export DATABASE_URL="your-render-postgres-external-url"
python manage.py migrate
python manage.py loaddata deployment_exports/render_seed.json
```

After this completes, remove the temporary `DATABASE_URL` from your local shell so local development returns to SQLite.

## 4. Move existing media to Cloudinary

Existing files in local `media/` do not upload automatically just because production uses Cloudinary.

Use `deployment_exports/media_manifest.json` to move those files into Cloudinary before you rely on them in production. New uploads will use Cloudinary automatically once `CLOUDINARY_URL` is configured on Render.

## 5. Deploy the app

Once the database import is done and Cloudinary is configured:

1. Push the repo.
2. Sync or create the Render Blueprint.
3. Let Render run migrations and collect static files.

## Notes

- Do not commit `deployment_exports/`; it is gitignored on purpose.
- If the Blueprint already exists, Render keeps existing secret env vars unless you change them manually in the dashboard.
