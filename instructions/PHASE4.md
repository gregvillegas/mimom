PHASE 4: ACTION ITEM TRACKING

Implement the reusable action_items application.

Models:

- ActionItem
- ActionItemAssignee or supporting-user relationship
- ActionItemUpdate
- ActionItemAttachment
- ActionItemStatusHistory
- ActionItemCarryForwardLink

Implement:

1. Action-item creation from an agenda item.
2. Standalone action-item creation when authorized.
3. Assignment to user and department.
4. Supporting users.
5. Due dates.
6. Priorities.
7. Statuses.
8. Progress percentage.
9. Update history.
10. Blockers and next steps.
11. Supporting evidence.
12. Completion workflow.
13. Reopen workflow with mandatory reason.
14. Overdue calculation.
15. Filters and search.
16. My Action Items page.
17. Department Action Items page.
18. Overdue Action Items page.
19. Action-item dashboard widgets.
20. Carry-forward preview and execution.

Carry-forward must:

- Link the new record to the original.
- Preserve history.
- Avoid copying completed or cancelled items by default.
- Be idempotent.
- Run in a database transaction.
- Record an audit event.

Test:

- Overdue logic.
- Completion requirements.
- Reopening.
- Object-level permissions.
- Carry-forward.
- Duplicate prevention.
- Progress validation.

Update documentation and stop after Phase 4.