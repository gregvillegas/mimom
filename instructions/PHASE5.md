PHASE 5: SALES UPDATES AND COMMITMENTS

Implement the sales_updates application.

Models:

- ReportingPeriod
- SalesTeam
- SalesGroup
- SalesGroupMembership
- PerformanceTarget
- DeliveryPerformance
- SalesOrderPerformance
- WeeklyCommitment
- GroupPerformanceSnapshot

Required functions:

1. Manage reporting periods.
2. Manage sales teams and groups.
3. Enter targets.
4. Enter actual revenue and profit.
5. Enter delivery performance.
6. Enter sales-order performance.
7. Enter weekly commitments through related records.
8. Calculate:
   - percentage achieved
   - deficit
   - totals
   - monthly average where applicable
9. Present team subtotals.
10. Present overall totals.
11. Show target versus actual charts.
12. Show current reporting cut-off date.
13. Associate a reporting snapshot with a meeting.
14. Lock meeting snapshots at approval or publication.
15. Export performance tables to Excel.
16. Include sales tables in printable meeting minutes.

Rules:

- Use Decimal for all financial values.
- Do not use float.
- Do not hard-code four weekly commitment columns in the data model.
- Permit four-week and five-week reporting periods.
- Avoid storing calculated values unless a justified snapshot is required.
- Validate duplicate group-period records.
- Format Philippine peso and foreign currency correctly where applicable.
- Keep calculations in tested services or model properties.
- Show negative values consistently.
- Ensure wide tables are usable on mobile.

Create comprehensive calculation tests.
Update documentation and stop after Phase 5.