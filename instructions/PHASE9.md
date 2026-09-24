PHASE 9: NOTIFICATIONS, AUDIT, AND SECURITY HARDENING

Implement:

1. In-app notifications.
2. Notification preferences.
3. Read and unread states.
4. Department submission reminders.
5. Upcoming due-date reminders.
6. Overdue action-item alerts.
7. Review and approval notifications.
8. Published-minutes notifications.
9. Audit-log interface for authorized users.
10. Security review.

Security tasks:

- Review every create, read, update, delete, approve, publish, export, and
  attachment endpoint.
- Test object-level access.
- Validate file content types and sizes.
- Use safe generated filenames.
- Prevent path traversal.
- Enforce secure production cookies.
- Configure trusted origins.
- Configure allowed hosts.
- Configure security headers.
- Confirm DEBUG is disabled in production.
- Review CSRF protection.
- Review session expiry.
- Add login rate-limit integration point.
- Sanitize rich text.
- Protect confidential agenda content.
- Prevent unauthorized exports.
- Prevent insecure direct object references.
- Confirm secrets are environment-based.

Audit:

- Meeting lifecycle
- Agenda changes
- Action-item changes
- Due-date changes
- Assignment changes
- Department submissions
- Approvals
- Publications
- Exports
- Permission changes
- Reopening and archiving

Add security-focused tests.
Update docs/security.md and stop after Phase 9.