# Management Meeting Minutes and Action Tracking System (Intranet)

A production-ready Django monolith for managing weekly management meeting
minutes, action items, department updates, sales performance, and
related reporting.

## Prerequisites

- Python **3.12+**
- PostgreSQL (production) — SQLite works for local development
- Optional: [WeasyPrint native deps](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html) if you need PDF export

## Installation

### 1. Clone & create virtual environment

```bash
cd intranet
python3 -m venv venv
source venv/bin/activate   # macOS / Linux
# venv\Scripts\activate    # Windows
```

### 2. Install dependencies

```bash
pip install --upgrade pip
pip install -e ".[dev]"
```

### 3. Environment variables

```bash
cp .env.example .env
# edit .env and set SECRET_KEY, DATABASE_URL, etc.
```

For a real deployment, always change `SECRET_KEY` to a long random value.

### 4. Create the database

With SQLite (default dev), no extra step is required.

With PostgreSQL:

```sql
CREATE DATABASE intranet OWNER youruser;
```

Then set `DATABASE_URL=postgres://youruser:password@localhost:5432/intranet`.

### 5. Run migrations

```bash
python manage.py migrate
```

### 6. Seed data (Phase 2+)

Seed data command is provided in later phases. For now just create a
superuser.

### 7. Create a superuser

```bash
python manage.py createsuperuser
```

Follow the prompts. The username and email are both required.

### 8. Static files (dev only)

Static files are served automatically by Django runserver + WhiteNoise in
development. For production:

```bash
python manage.py collectstatic --noinput
```

### 9. Run the development server

```bash
python manage.py runserver
```

Open <http://127.0.0.1:8000/>. You'll be prompted to log in.

The Django admin is at <http://127.0.0.1:8000/admin/>.

## Running tests

```bash
pytest
pytest --cov=apps --cov-report=term-missing
```

## Linting & formatting

```bash
# Lint
ruff check apps config tests manage.py

# Fix fixable issues
ruff check --fix apps config tests manage.py

# Format
ruff format apps config tests manage.py
```

## Project structure

```
intranet/
├── manage.py
├── pyproject.toml
├── .env.example
├── config/
│   ├── settings/
│   │   ├── base.py
│   │   ├── development.py
│   │   └── production.py
│   ├── urls.py
│   ├── asgi.py
│   └── wsgi.py
├── apps/
│   ├── core/            # Time-stamped base models, shared mixins, home + health views
│   ├── accounts/        # Custom User, Department, Position, ManagementTeam
│   ├── meetings/        # Meeting lifecycle, agenda, attendance, snapshots
│   ├── action_items/    # Reusable action items with full status workflow
│   ├── sales_updates/   # Delivery, sales order, weekly commitment data
│   ├── notifications/   # In-app notification service abstraction
│   └── audit/           # Structured audit log records
├── templates/           # Jinja2-style Django templates (Bootstrap 5)
├── static/              # Project CSS / JS / vendor assets
├── media/               # User-uploaded attachments & generated exports
├── fixtures/            # Development seed fixtures
├── docs/                # Architecture, data model, permissions, workflows
├── scripts/             # Operational helper scripts
└── tests/               # Pytest suite
```

## Production deployment summary

1. Set `DJANGO_SETTINGS_MODULE=config.settings.production`.
2. Use a PostgreSQL `DATABASE_URL`.
3. Set a long random `SECRET_KEY`, correct `ALLOWED_HOSTS`, and
   `CSRF_TRUSTED_ORIGINS`.
4. Run migrations: `python manage.py migrate --noinput`.
5. Collect static: `python manage.py collectstatic --noinput`.
6. Serve with Gunicorn + WhiteNoise behind a TLS-terminating reverse proxy:
   ```bash
   gunicorn config.wsgi:application -w 4 -b 0.0.0.0:8000
   ```
7. Add a systemd/process supervisor and periodic health check against
   `/health/`.

A full checklist lives in `docs/deployment.md` (Phase 2+).

## Environment variable reference

| Variable | Default | Purpose |
| --- | --- | --- |
| `SECRET_KEY` | *insecure placeholder* | Django secret — **must be set in production** |
| `DEBUG` | `False` | Django debug mode |
| `ALLOWED_HOSTS` | `[]` | Comma-separated host list |
| `DATABASE_URL` | `sqlite:///db.sqlite3` | Any URL supported by `django-environ` |
| `TIME_ZONE` | `Asia/Manila` | IANA timezone |
| `LANGUAGE_CODE` | `en-us` | UI language |
| `EMAIL_BACKEND` | console | Django email backend |
| `DEFAULT_FROM_EMAIL` | `no-reply@intranet.local` | From address |
| `CORS_ALLOWED_ORIGINS` | `[]` | CORS origins (comma separated) |
| `CSRF_TRUSTED_ORIGINS` | `[]` | CSRF origins (comma separated) |
| `LOG_LEVEL` | `INFO` | Root logger level |

## Phase progress

- **Phase 1 — Project foundation** ✅ (this file)
- Phase 2+ — Follow the instructions in `instructions/PHASE*.md`.

## Support

Internal documentation lives in `docs/` (populated from Phase 2 onward).
For issues, first check the application audit log via the Django admin.
