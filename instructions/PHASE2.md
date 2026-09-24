PHASE 2: ACCOUNTS, ORGANIZATION, AND ROLE-BASED ACCESS

Inspect Phase 1 before changing files.

Implement:

1. Custom user model if not already created safely.
2. User profile.
3. Department.
4. Position.
5. Management team or working group.
6. Department membership.
7. Active and inactive organizational assignments.
8. Django Groups and Permissions.
9. Seed groups:
   - System Administrator
   - Management Administrator
   - Meeting Chairperson
   - Minutes Secretary
   - Department Contributor
   - Viewer
10. Reusable permission mixins and decorators.
11. Template permission helpers.
12. User-management pages for authorized administrators.
13. Department assignment interface.
14. Profile page.
15. Password-change flow.
16. Audit hooks for user, group, and permission changes.

Business requirements:

- A user may belong to several groups.
- A user may be assigned to more than one department.
- Department Contributor access must be limited to assigned departments.
- Inactive users must not receive new assignments.
- Do not infer a user’s department from job title.
- Do not rely only on template hiding for security.

Testing:

- Permission matrix tests.
- Object-level authorization tests.
- Department access tests.
- Inactive-user tests.
- Admin access tests.

Update documentation and stop after Phase 2.