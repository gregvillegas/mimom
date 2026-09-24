You are a Senior Django Engineer, Systems Architect, Database Designer,
UI/UX Engineer, Security Engineer, and QA Engineer.

Build a production-ready internal company intranet application for managing
Minutes of Management Meetings.

PROJECT NAME

Management Meeting Minutes and Action Tracking System

BUSINESS CONTEXT

The company conducts a management meeting every Monday.

Before or during the meeting, authorized department representatives submit
or update their weekly information. The system consolidates these updates
into an organized Minutes of Management Meeting.

The current manual document includes:

1. Meeting title and reporting date
2. Sales performance based on deliveries
3. Sales performance based on sales orders
4. Annual target versus actual group performance
5. Weekly commitments
6. Delivery updates
7. Past-due accounts receivable updates
8. Marketing and rebate updates
9. Previous agenda items
10. Sales and marketing matters
11. Finance and accounting matters
12. HR, administrative, and systems matters
13. Operations and process improvements
14. Announcements and upcoming activities
15. New agenda and concerns
16. Assigned persons
17. Action items
18. Status updates such as Open, Ongoing, Completed, Deferred, and Cancelled
19. Meeting ending time
20. Final management review and distribution

The application must replace the manually updated Word file while preserving
the practical workflow and management-reporting structure.

TECHNOLOGY STACK

Use:

- Python 3.12 or the latest stable Python version supported by the selected
  stable Django version
- Django
- PostgreSQL for production
- SQLite only for local development if PostgreSQL is unavailable
- Bootstrap 5
- Bootstrap Icons
- HTMX where useful
- Alpine.js only if lightweight client-side behavior is needed
- Chart.js for management charts
- django-filter for filtering
- django-tables2 only if it materially improves reusable tabular displays
- django-environ for environment variables
- WhiteNoise for static files
- Gunicorn for production
- Pillow for uploaded images if needed
- openpyxl for Excel export
- python-docx for Word export
- WeasyPrint or another maintainable library for PDF generation
- pytest and pytest-django for automated tests
- Ruff for linting and formatting

Do not use React, Vue, Angular, or a separate frontend application.
The application must remain a maintainable Django monolith.

REQUIRED WORKING DIRECTORY

Create the project using this structure:

intranet/
    manage.py
    config/
        settings/
            base.py
            development.py
            production.py
        urls.py
        asgi.py
        wsgi.py
    apps/
        core/
        accounts/
        meetings/
        action_items/
        sales_updates/
        notifications/
        audit/
    templates/
    static/
    media/
    fixtures/
    docs/
    scripts/
    tests/

The Django project settings must live under:

intranet/config/

All Django applications must live under:

intranet/apps/

Do not create a nested intranet/intranet directory.

ARCHITECTURE REQUIREMENTS

Use a modular Django monolith.

Follow these principles:

1. Keep business logic out of views whenever practical.
2. Use service functions for complex operations.
3. Use model methods only for behavior closely related to the model.
4. Use forms or service-layer validation for business rules.
5. Use select_related and prefetch_related to avoid N+1 queries.
6. Use database constraints where appropriate.
7. Use DecimalField for financial amounts.
8. Never use float for currency.
9. Use timezone-aware DateTimeField values.
10. Use UUIDs for externally exposed records where appropriate.
11. Apply role-based permissions at both view and template level.
12. Do not trust hidden form fields for authorization.
13. Protect all create, update, delete, approve, export, and publish operations.
14. Add audit logs for important changes.
15. Use database transactions for approval, publishing, and carry-forward
    operations.

USER ROLES

Implement the following initial roles:

1. System Administrator
   - Full access
   - Manage users, groups, permissions, configuration, and audit records

2. Management Administrator
   - Create meeting records
   - Configure agenda sections
   - Consolidate updates
   - Edit draft minutes
   - Submit minutes for approval
   - Publish approved minutes
   - Export reports

3. Meeting Chairperson
   - Review the meeting
   - Approve or return minutes for correction
   - Close the meeting
   - Reopen a meeting only with a recorded reason

4. Minutes Secretary
   - Prepare agendas
   - Record discussions
   - Record decisions
   - Record attendance
   - Assign action items
   - Generate draft minutes

5. Department Contributor
   - Add and edit updates for assigned departments
   - Update assigned action items
   - Add remarks and supporting attachments
   - Cannot approve or publish minutes

6. Viewer
   - Read published minutes
   - View permitted dashboards and reports
   - Cannot modify information

Use Django Groups and Permissions as the primary authorization mechanism.
Allow a user to belong to more than one group.

USER AND ORGANIZATION MODEL

Create appropriate models for:

- User profile
- Department
- Position or job title
- Management team or working group
- Department membership
- Active or inactive status
- Preferred display name
- Signature or approval designation if required

Do not store organizational information directly in hard-coded choices if the
information is expected to change.

CORE MEETING WORKFLOW

Meeting lifecycle:

1. Draft
2. Open for Department Updates
3. Agenda Finalized
4. Meeting In Progress
5. For Review
6. Returned for Correction
7. Approved
8. Published
9. Closed
10. Archived

Enforce valid state transitions.

Each meeting must support:

- Meeting reference number
- Meeting title
- Meeting type
- Meeting date
- Scheduled start time
- Actual start time
- Actual end time
- Venue
- Online meeting link if applicable
- Chairperson
- Minutes secretary
- Reporting cut-off date
- Status
- Version number
- Confidentiality classification
- Agenda lock status
- Minutes lock status
- Notes
- Created by
- Updated by
- Approved by
- Published by
- Created, updated, approved, and published timestamps

Generate human-readable reference numbers using a configurable pattern such
as:

MIMOM-YYYYMMDD-SEQUENCE

Do not depend only on the reference number as the database primary key.

MEETING ATTENDANCE

Create an attendance model supporting:

- Meeting
- Employee or user (they 3 letter initials of their name)
- Invited status
- Attendance status
- Present
- Absent
- Excused
- Late
- Joined remotely
- Time joined
- Time left
- Remarks

Do not infer actual attendance from the invitation list.

AGENDA STRUCTURE

The system must support configurable agenda categories and sections.

Initial categories:

- Sales and Marketing Matters
- Finance and Accounting Matters
- HR, Administrative, and Systems Matters
- Operations and Process Improvements
- Announcements and Upcoming Activities
- New Agenda and Concerns

Each agenda item must support:

- Meeting
- Agenda category
- Title
- Description or background
- Discussion summary
- Decision
- Presenter or owner
- Department
- Sequence number
- Status
- Confidentiality
- Carried forward from a previous meeting
- Source agenda item
- Related action items
- Attachments
- Created by
- Updated by
- Timestamps

Use a rich-text editor only if it is secure and maintainable.
Sanitize any rich-text HTML before rendering.

ACTION ITEM MANAGEMENT

Create a reusable action-item application.

Each action item must support:

- UUID
- Reference number
- Meeting
- Agenda item
- Short title
- Detailed description
- Assigned user
- Assigned department
- Supporting users
- Priority
- Status
- Start date
- Due date
- Completion date
- Progress percentage
- Latest update
- Management remarks
- Evidence attachments
- Created by
- Updated by
- Closed by
- Timestamps

Statuses:

- Not Started
- Open
- Ongoing
- Blocked
- For Verification
- Completed
- Deferred
- Cancelled

Priorities:

- Low
- Normal
- High
- Critical

Business rules:

1. Completion requires either a completion note or supporting evidence.
2. Completed items must record the completion date and closing user.
3. Overdue is computed from due date and status.
4. Reopening an item requires a reason.
5. All important status changes must be audited.
6. Action items may be carried forward to the next meeting.
7. Carry-forward must preserve a link to the original item.
8. Progress cannot be below 0 or above 100.
9. A completed item should have 100 percent progress.
10. A cancelled item cannot be presented as completed.

ACTION ITEM UPDATE HISTORY

Do not overwrite weekly progress notes.

Create an ActionItemUpdate model with:

- Action item
- Update date
- Previous status
- New status
- Previous progress
- New progress
- Update narrative
- Blocker
- Next step
- Updated by
- Supporting attachment
- Timestamp

SALES UPDATE MODULE

Build an initial sales_updates application because the source minutes contain
several structured management tables.

Create configurable models for:

1. Sales teams
2. Sales groups
3. Annual or period targets
4. Delivery performance
5. Sales order performance
6. Weekly commitments
7. Group performance
8. Reporting periods

Delivery performance fields should include:

- Reporting period
- Team
- Group
- Target
- Actual profit
- Percentage achieved
- Deficit
- Monthly average
- As-of date
- Notes

Sales order performance fields should include:

- Reporting period
- Team
- Group
- Account executive count
- Revenue
- Profit
- Weekly commitment values
- Profit deficit
- As-of date
- Notes

Whenever possible, calculate these values rather than accepting redundant
manual inputs:

- Percentage achieved
- Deficit
- Monthly average
- Total revenue
- Total profit
- Team totals
- Overall totals

Provide server-side validation and unit tests for all calculations.

Do not hard-code a four-week month. Model commitments using a related weekly
commitment table so the system can support four-week and five-week reporting
periods.

MEETING SNAPSHOTS

Management reports must remain historically accurate.

When a meeting is approved or published, store a report snapshot or immutable
version of the data used in that meeting. Later changes to live department
records must not silently alter previously approved minutes.

Design and document the snapshot strategy.

DASHBOARD

Create a modern management dashboard with:

- Next scheduled management meeting
- Latest published minutes
- Meetings awaiting review
- Open action items
- Overdue action items
- Action items due this week
- Items by department
- Items by status
- Completion trend
- Sales target versus actual
- Weekly commitment summary
- Department update completion status
- Recently updated items

Use Chart.js only when a chart provides management value.
Every chart must have an accessible text or table equivalent.

MEETING PREPARATION DASHBOARD

Create a meeting readiness page showing:

- Department
- Assigned contributor
- Submission status
- Last update
- Missing required sections
- Open action items requiring updates
- Submitted by
- Submitted timestamp
- Management remarks

Use status indicators:

- Not Started
- In Progress
- Submitted
- Returned
- Accepted
- Locked

MINUTES EDITOR

Build a structured minutes editor, not a single unrestricted text area.

The interface must allow the secretary to:

- Reorder agenda items
- Record discussions
- Record decisions
- Create action items from an agenda item
- Assign owners and due dates
- Mark items for carry-forward
- Add management remarks
- Save drafts
- Preview minutes
- Validate missing information
- Submit minutes for review

Use inline formsets carefully.
Prevent accidental duplicate action items.
Display unsaved-change warnings where appropriate.

WEEKLY MEETING CLONING

Provide a Create Next Monday Meeting function.

It should:

1. Suggest the next Monday date.
2. Copy selected recurring agenda categories.
3. Carry forward approved open action items.
4. Carry forward selected unresolved agenda items.
5. Preserve references to source records.
6. Reset discussions and decisions for the new meeting.
7. Avoid copying attendance as confirmed attendance.
8. Avoid copying completed or cancelled items by default.
9. Show a preview before the clone operation.
10. Perform the operation in a database transaction.

REPORTS AND EXPORTS

Generate:

- Management meeting minutes
- Action item register
- Department action item report
- Overdue action item report
- Meeting readiness report
- Sales performance summary
- Weekly commitment report
- Meeting history report
- Audit report for authorized users

Export formats:

- Printable HTML
- PDF
- Microsoft Word
- Microsoft Excel where tabular data is appropriate

The generated management minutes must include:

- Company name
- Document title
- Meeting reference
- Meeting date
- Reporting cut-off date
- Attendance summary
- Agenda sections
- Discussion summaries
- Decisions
- Action items
- Owners
- Due dates
- Statuses
- Department updates
- Sales tables
- Approval information
- Version number
- Generated timestamp
- Confidentiality notice
- Page-friendly print formatting

Do not silently show live changed data in an already published export.
Use the approved meeting snapshot.

SEARCH AND FILTERING

Provide search and filters for:

- Meeting reference
- Meeting date
- Meeting status
- Agenda category
- Department
- Assigned user
- Action item status
- Priority
- Due date
- Overdue status
- Text content

Apply pagination.
Preserve filters during pagination.
Ensure authorization rules are applied to search results.

NOTIFICATIONS

Design an in-application notification system for:

- Department update reminders
- Returned submissions
- Meeting review requests
- Newly assigned action items
- Approaching due dates
- Overdue action items
- Approved minutes
- Published minutes

Create a notification service abstraction so email or Microsoft 365
integration can be added later.

Do not implement external email APIs unless explicitly configured.
The application must work using in-app notifications alone.

AUDIT LOGGING

Track:

- Record type
- Record identifier
- Action
- User
- Timestamp
- IP address where appropriate
- Previous values
- New values
- Reason
- Related meeting
- Request correlation ID if practical

Audit at least:

- Meeting creation
- Agenda changes
- Action-item assignments
- Status changes
- Due-date changes
- Meeting submission
- Return for correction
- Approval
- Publication
- Reopening
- Archiving
- User and permission changes

Do not expose sensitive audit details to ordinary users.

SECURITY REQUIREMENTS

Implement:

- Environment-based secrets
- CSRF protection
- Secure session settings
- Content Security Policy where practical
- Secure cookies in production
- HTTPS awareness
- Host validation
- Permission checks
- File type and size validation
- Safe uploaded-file naming
- Protection against object-level authorization failures
- Sanitization of rich-text input
- Login rate-limit integration point
- Password-policy documentation
- Security headers
- No secrets in the repository
- No DEBUG mode in production
- Custom 403, 404, and 500 pages

Uploaded files must not be executable.
Do not rely only on file extensions to validate uploads.

DATA PRIVACY

The system is an internal management system.

Apply:

- Least privilege
- Purpose limitation
- Data minimization
- Restricted access to confidential agenda items
- Auditability
- Configurable retention
- Secure deletion policy documentation
- No unnecessary sensitive personal information
- Redaction or exclusion of confidential items from ordinary exports

MODERN UI/UX

Use Bootstrap 5 and Bootstrap Icons.

The interface must be responsive and usable on:

- Laptop
- Desktop
- Tablet
- Mobile phone

Create:

- Responsive top navigation
- Collapsible desktop sidebar
- Off-canvas mobile navigation
- Dashboard cards
- Responsive tables
- Mobile card alternative for wide tables
- Accessible forms
- Status badges
- Progress bars
- Empty states
- Loading indicators
- Confirmation dialogs for destructive operations
- Toast messages
- Breadcrumbs
- Sticky action bar for long edit screens where practical

Design style:

- Professional enterprise intranet
- Clean spacing
- High readability
- Limited and consistent color palette
- Strong visual hierarchy
- Accessible contrast
- Large mobile touch targets
- No excessive animation
- No decorative UI that reduces readability

For financial tables:

- Right-align numeric values
- Use appropriate currency formatting
- Use parentheses or clear styles for negative values
- Keep table headers visible on long desktop tables if practical
- Allow horizontal scrolling on small screens
- Provide condensed mobile summaries

ACCESSIBILITY

Target WCAG 2.1 AA practices:

- Keyboard-accessible controls
- Visible focus states
- Form labels
- Helpful validation summaries
- ARIA attributes only when needed
- Sufficient contrast
- Do not communicate status through color alone
- Semantic headings
- Accessible tables

ADMINISTRATION

Configure Django Admin for controlled system administration.

Include:

- Search
- Filters
- Read-only audit fields
- Safe list displays
- Permission-aware admin actions
- Protection against accidental bulk deletion where practical

Do not use Django Admin as the primary user interface.

FUTURE APPLICATIONS

Prepare clean extension points for these future applications, but do not fully
implement them unless instructed:

1. warehouse
   - Delivery itinerary
   - Vehicle
   - Driver
   - Delivery schedule
   - Sales order
   - Customer
   - Delivery status
   - Delivery evidence

2. marketing
   - Vendor rebates
   - Incentive programs
   - Currency
   - Estimated amount
   - Approved amount
   - Claim period
   - Payment status
   - Remarks
   - Supporting documents

3. product_updates
   - Vendor
   - Brand
   - Product
   - Lifecycle notice
   - Price update
   - Promotion
   - Technical bulletin
   - Product Manager update

4. accounting
   - Accounts receivable aging
   - Over-75-day balance
   - On-process amount
   - For-collection amount
   - Collection owner
   - Commitment date
   - Collection status
   - Remarks

Create documented interfaces or reusable patterns so these applications can
contribute department sections to a meeting without creating direct circular
dependencies.

TESTING REQUIREMENTS

Create:

- Model tests
- Form-validation tests
- Permission tests
- Service-layer tests
- Workflow transition tests
- Calculation tests
- Export tests
- Carry-forward tests
- Snapshot tests
- View tests
- Basic responsive-template checks where practical

Critical tests:

1. Unauthorized users cannot edit meetings.
2. Contributors can edit only permitted department updates.
3. Published minutes cannot be silently changed.
4. Financial calculations use Decimal.
5. Invalid state transitions are rejected.
6. Carry-forward does not duplicate records if retried.
7. Closing an action item records required information.
8. Overdue calculation is correct.
9. Confidential agenda items are excluded from unauthorized views and exports.
10. Meeting cloning runs atomically.

SEED DATA

Create development fixtures or a management command with synthetic data for:

- Departments
- Roles
- Users
- One management meeting
- Agenda categories
- Agenda items
- Action items
- Sales teams
- Sales groups
- Targets
- Delivery performance
- Sales order performance
- Weekly commitments

Do not copy real employee names, customer names, financial figures, or
confidential details from any source document into seed data.
Use clearly labeled synthetic data.

DOCUMENTATION

Create:

- README.md
- docs/architecture.md
- docs/data-model.md
- docs/permissions.md
- docs/workflows.md
- docs/deployment.md
- docs/backup-restore.md
- docs/security.md
- docs/testing.md
- docs/future-modules.md

README must include:

- Prerequisites
- Installation
- Virtual environment
- Environment variables
- Database creation
- Migrations
- Seed data
- Running the development server
- Running tests
- Linting
- Creating a superuser
- Static-files collection
- Production deployment summary

DELIVERABLE RULES

Work in phases.

At the beginning of every phase:

1. Inspect the current repository.
2. Summarize what already exists.
3. State the exact files that will be created or modified.
4. State assumptions.
5. Avoid rewriting working files without a valid reason.

At the end of every phase:

1. Run Django system checks.
2. Run relevant tests.
3. Run linting.
4. Report files created and changed.
5. Report migrations created.
6. Report commands executed.
7. Report test results.
8. Report unresolved issues.
9. Update documentation.
10. Stop after completing the phase.

Do not generate placeholder code that falsely appears complete.

Do not leave blank pass statements, fake service implementations, sample-only
authorization, or TODO comments in critical workflows.

If a requirement is ambiguous, choose the most maintainable and secure
implementation, state the assumption, and continue.

Start with Phase 1 only.