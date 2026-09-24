PHASE 1: PROJECT FOUNDATION

Implement only the project foundation.

Required work:

1. Create the intranet root directory.
2. Create manage.py in intranet/.
3. Create the Django project configuration inside intranet/config/.
4. Create split settings:
   - config/settings/base.py
   - config/settings/development.py
   - config/settings/production.py
5. Create these Django applications under intranet/apps/:
   - core
   - accounts
   - meetings
   - action_items
   - sales_updates
   - notifications
   - audit
6. Configure:
   - Templates
   - Static files
   - Media files
   - Environment variables
   - Logging
   - Development database
   - PostgreSQL production configuration
   - WhiteNoise
7. Add Bootstrap 5 and Bootstrap Icons using maintainable local files or a
   clearly documented CDN approach.
8. Create:
   - base template
   - navbar
   - desktop sidebar
   - mobile off-canvas menu
   - messages and toast area
   - breadcrumbs component
   - empty-state component
9. Create custom:
   - 403 page
   - 404 page
   - 500 page
10. Set up:
   - pytest
   - pytest-django
   - Ruff
   - .gitignore
   - .env.example
   - requirements files or pyproject.toml
11. Add a health-check endpoint.
12. Create the initial README.
13. Add a landing page that requires authentication.
14. Configure login and logout using Django authentication.
15. Do not implement business models yet, except a custom user model if that
    architecture is selected.

Important:

- Decide on the custom user model before creating the first production
  migration.
- Use email plus username or a documented authentication identifier.
- Do not place business logic in config/.
- Do not create a nested intranet/intranet folder.
- Verify mobile navigation.
- Do not start Phase 2.

Validation:

- Run django check.
- Run migrations.
- Run pytest.
- Run Ruff.
- Confirm development server startup.
- Report all created files and commands.
``