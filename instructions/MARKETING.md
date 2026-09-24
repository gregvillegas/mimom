FUTURE MODULE: MARKETING REBATE UPDATES

Create:

apps/marketing/

Models:

- Vendor
- RebateProgram
- RebateClaim
- RebateClaimUpdate
- RebateAttachment
- Currency
- ReportingPeriod

Fields should support:

- Program name
- Vendor
- Claim period
- Currency
- Estimated amount
- Submitted amount
- Approved amount
- Received amount
- Submission date
- Expected payment date
- Actual payment date
- Payment status
- Owner
- Remarks
- Supporting documents

Statuses:

- Draft
- For Submission
- Submitted
- Under Review
- Approved
- For Payment
- Partially Paid
- Paid
- Rejected
- Cancelled

Requirements:

- Do not combine different currencies into a total without an explicit
  exchange-rate record.
- Preserve original currency.
- Track update history.
- Record documentary evidence.
- Produce management summaries.
- Contribute an immutable marketing snapshot to a selected meeting.
- Add dashboard cards for pending, approved, and paid rebate claims.
`