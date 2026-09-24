PHASE 6: MINUTES PREPARATION, REVIEW, APPROVAL, AND PUBLISHING

Implement the structured minutes workflow.

Create:

1. Meeting preparation dashboard.
2. Department submission status.
3. Agenda completeness validation.
4. Structured minutes editor.
5. Discussion and decision editor.
6. Action-item creation during minutes editing.
7. Meeting preview.
8. Validation summary before submission.
9. Submit for review.
10. Return for correction with comments.
11. Resubmit for review.
12. Approve.
13. Publish.
14. Close.
15. Authorized reopen with reason.
16. Version history.
17. Immutable approved or published snapshot.

The meeting preparation dashboard must show:

- Department
- Contributor
- Required section
- Submission state
- Last update
- Submitted by
- Submitted timestamp
- Missing information
- Management remarks

The approved snapshot must include:

- Meeting metadata
- Attendance
- Agenda sections
- Discussions
- Decisions
- Action items
- Sales-performance data
- Approval metadata
- Version

Later edits to live records must not alter an approved snapshot.

Use transaction.atomic for approval and publication.
Prevent double publication.
Audit every workflow event.

Test approval and snapshot immutability.
Update documentation and stop after Phase 6.