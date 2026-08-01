# Production readiness and release runbook

## Supported runtime

- Python 3.13
- Django 6.0 latest patch in the declared range
- PostgreSQL 14 or newer through psycopg 3
- Gunicorn web process on Linux
- WhiteNoise for versioned static assets
- A persistent, backed-up private volume mounted at `NYANSA_MEDIA_ROOT`
- A continuously supervised communication worker

SQLite and `manage.py runserver` are development-only. Production startup fails unless `DJANGO_ENV=production`, debug is disabled, allowed hosts are set, and `DATABASE_URL` uses PostgreSQL.

The Docker build runs `collectstatic` with production storage enabled and a non-connected placeholder PostgreSQL URL. This produces WhiteNoise's hashed static-file manifest inside the immutable image; runtime database credentials are never used during image construction.

## Required environment

At minimum configure:

```env
DJANGO_ENV=production
DJANGO_DEBUG=False
DJANGO_SECRET_KEY=a-unique-random-value-of-at-least-50-characters
DJANGO_ALLOWED_HOSTS=school.example.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://school.example.com
DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DATABASE?sslmode=require
NYANSA_MEDIA_ROOT=/var/lib/nyansa/media
DJANGO_TRUST_PROXY_SSL_HEADER=True
DJANGO_SECURE_SSL_REDIRECT=True
```

Configure SMTP, Arkesel, Paystack, and Anthropic variables only for enabled capabilities. Secrets belong in the hosting platform's secret manager, never the image, repository, build log, or browser.

Start HSTS with a short value after HTTPS is verified, then increase toward one year. Enable subdomains and preload only after confirming every subdomain supports HTTPS.

## Processes

Release command:

```sh
sh deploy/release.sh
```

Web process:

```sh
gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3 --timeout 120
```

Worker process:

```sh
sh deploy/worker.sh
```

The release command applies migrations, collects static assets, and runs `production_check`. It must complete successfully before new web instances receive traffic.

## Probes

- `/health/live/` verifies that the web process can answer HTTP without touching external services.
- `/health/ready/` performs a minimal database query and returns HTTP 503 when the database is unavailable.

Neither endpoint returns credentials, versions, tenant data, queue contents, or exception details.

## Database migration

Do not point production at the development SQLite file. Create an empty PostgreSQL database, rehearse all migrations in staging, and import only reviewed legacy data through a separate migration/export procedure. Validate school, membership, enrollment, grade, attendance, report, guardian, message, finance, and analytics counts before opening traffic.

CI runs the entire suite against PostgreSQL. A release must not proceed if migrations are missing or tests fail.

## Backup and restoration

Create a PostgreSQL custom-format backup:

```powershell
.\scripts\postgres_backup.ps1 -DatabaseUrl $env:DATABASE_URL -OutputDirectory C:\secure-backups\nyansa
```

The script writes a `.dump` and SHA-256 sidecar. Store encrypted copies outside the application host. Back up the private media volume on the same retention schedule.

Restore only into an explicitly identified empty recovery or staging database first:

```powershell
.\scripts\postgres_restore.ps1 -DatabaseUrl $env:RECOVERY_DATABASE_URL -BackupPath C:\secure-backups\nyansa\nyansa-TIMESTAMP.dump -Confirm RESTORE
```

After restoration, run `production_check`, compare record counts and ledger totals, verify private media, and exercise tenant isolation before declaring the drill successful. Never test restoration first against production.

## Release sequence

1. Confirm a recent database and media backup and a previously successful restoration drill.
2. Run CI and dependency/security scanning.
3. Deploy to staging with sandbox provider credentials.
4. Run `python manage.py production_check` and pilot smoke tests.
5. Place write-heavy workflows in a maintenance window if a migration requires it.
6. Run the release command once, then roll web and worker processes.
7. Verify probes, login, school selection, grade entry, attendance, reports, guardian access, queued email, sandbox payment, receipt, and analytics.
8. Monitor HTTP errors, latency, database connections, disk/media use, failed messages, payment exceptions, and backup completion.
9. Roll back application images only when migrations are backward compatible. Otherwise follow the migration-specific recovery plan and restore only as a last resort.

## Remaining external gates

Code readiness does not create production accounts or legal approval. Before a live pilot, select the host and PostgreSQL service, provision persistent private media storage, configure DNS/TLS, connect monitoring, approve Paystack/Arkesel accounts, complete Ghana privacy/legal review, seed administrator memberships, and perform school acceptance testing with synthetic data before importing real student records.

## Temporary Render demo

The repository includes `render.yaml` for a free Render Blueprint containing the web service and a free PostgreSQL database. Create it from Render's **New Blueprint Instance** screen and select this repository. Render generates the Django secret, connects the database automatically, and starts the service through `deploy/render_start.sh`.

This configuration sets `NYANSA_DEMO_MODE=True`, which displays a warning on every HTML page. Use synthetic sample records only. Render's free PostgreSQL database expires after 30 days and the service filesystem is ephemeral, so this Blueprint is not approved for real student, guardian, finance, attendance, or academic data. Upgrade PostgreSQL, configure external private media storage, validate backups, and complete the external gates above before a live school pilot.

Render generates the demo's secret automatically. Demo mode accepts a generated secret of at least 32 characters; non-demo production retains the stricter minimum of 50 characters.

After Render assigns the service URL, keep the generated `.onrender.com` settings for the demo. If a custom domain is added, replace `DJANGO_ALLOWED_HOSTS` and `DJANGO_CSRF_TRUSTED_ORIGINS` with that exact hostname and HTTPS origin.

To create the synthetic demonstration school, configure `DEMO_ADMIN_USERNAME`, `DEMO_ADMIN_PASSWORD`, and optionally `DEMO_ADMIN_EMAIL` as secret environment variables on the Render web service. Use a unique password of at least 12 characters. The startup command runs `seed_demo` after migrations; it safely creates or updates one demonstration school, its administrator membership, a demo academic year, term, class, and three subjects. It refuses to run outside demo mode and never stores credentials in GitHub.
