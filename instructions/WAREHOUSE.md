FUTURE MODULE: WAREHOUSE DELIVERY ITINERARY

Create a new Django application:

apps/warehouse/

Do not tightly couple it to the meetings application.

Models should support:

- DeliveryItinerary
- DeliveryStop
- SalesOrderReference
- Customer
- DeliveryAddress
- Vehicle
- Driver
- DeliveryAssistant
- ScheduledDate
- DeliveryWindow
- DeliveryPriority
- DeliveryStatus
- ProofOfDelivery
- DeliveryIssue
- Remarks

Required statuses:

- Planned
- Confirmed
- For Loading
- In Transit
- Arrived
- Delivered
- Partially Delivered
- Failed
- Rescheduled
- Cancelled

Functions:

- Daily itinerary
- Weekly itinerary
- Driver view
- Mobile delivery view
- Delivery status updates
- Proof-of-delivery upload
- Delivery issue recording
- Search and filtering
- Printable itinerary
- Excel export
- Management summary contribution to a meeting
- Pending-delivery count and value interfaces
- Audit history

Create a provider or service interface through which warehouse can contribute
a structured department update to a management meeting snapshot.

Do not make meetings depend directly on warehouse model internals.