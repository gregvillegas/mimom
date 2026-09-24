PHASE 3: MEETING AND AGENDA MANAGEMENT

Implement the meeting-management domain.

Models:

- MeetingType
- Meeting
- MeetingStatusHistory
- MeetingAttendance
- AgendaCategory
- AgendaItem
- AgendaItemAttachment
- MeetingAttachment

Meeting statuses:

- Draft
- Open for Department Updates
- Agenda Finalized
- Meeting In Progress
- For Review
- Returned for Correction
- Approved
- Published
- Closed
- Archived

Implement:

1. Meeting list, detail, create, update, and permitted delete or archive.
2. Human-readable meeting reference generation.
3. Attendance management.
4. Agenda category management.
5. Agenda item creation and editing.
6. Agenda ordering.
7. Discussion, decision, status, owner, department, and confidentiality fields.
8. Supporting attachments.
9. Meeting workflow transitions.
10. Transition validation.
11. Meeting status history.
12. Draft locking and publishing controls.
13. Meeting calendar and list views.
14. Mobile-friendly meeting pages.
15. Management dashboard shell.

Business rules:

- Approved and published meetings must not be directly editable.
- Reopening requires authorization and a reason.
- Meeting references must be unique.
- Agenda items may be carried forward.
- Attendance must distinguish invitation from actual attendance.
- Confidential agenda items must be permission-controlled.

Create services for workflow transitions.
Use database transactions where appropriate.

Test all workflow transitions and permissions.
Update documentation and stop after Phase 3.