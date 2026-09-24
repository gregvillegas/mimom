FUTURE MODULE: ACCOUNTING ACCOUNTS RECEIVABLE UPDATES

Create:

apps/accounting/

Models:

- CustomerAccount
- Receivable
- ReceivableAgingSnapshot
- CollectionUpdate
- CollectionCommitment
- ReceivableAttachment

Fields:

- Customer
- Invoice reference
- Sales order reference
- Team
- Account executive
- Invoice date
- Due date
- Original amount
- Open amount
- Aging days
- Aging bucket
- Collection status
- On-process amount
- For-collection amount
- Commitment date
- Collection owner
- Latest update
- Dispute status
- Remarks

Requirements:

- Use Decimal for amounts.
- Calculate aging from an explicit snapshot date.
- Preserve historical aging snapshots.
- Restrict sensitive financial records by permission.
- Create team summaries.
- Create over-75-day summaries.
- Create collection commitment reports.
- Contribute an immutable AR summary to a management meeting.
- Do not expose unnecessary customer financial details to ordinary viewers.FUTURE MODULE: ACCOUNTING ACCOUNTS RECEIVABLE UPDATES

Create:

apps/accounting/

Models:

- CustomerAccount
- Receivable
- ReceivableAgingSnapshot
- CollectionUpdate
- CollectionCommitment
- ReceivableAttachment

Fields:

- Customer
- Invoice reference
- Sales order reference
- Team
- Account executive
- Invoice date
- Due date
- Original amount
- Open amount
- Aging days
- Aging bucket
- Collection status
- On-process amount
- For-collection amount
- Commitment date
- Collection owner
- Latest update
- Dispute status
- Remarks

Requirements:

- Use Decimal for amounts.
- Calculate aging from an explicit snapshot date.
- Preserve historical aging snapshots.
- Restrict sensitive financial records by permission.
- Create team summaries.
- Create over-75-day summaries.
- Create collection commitment reports.
- Contribute an immutable AR summary to a management meeting.
- Do not expose unnecessary customer financial details to ordinary viewers.