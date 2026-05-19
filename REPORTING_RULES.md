# Reporting Rules - V1

## Classification

### System update
A row is treated as a system update when:

```text
Admin = System
```

### Manual agent activity
A row is treated as manual activity when:

```text
Admin is not System
```

### Event type
The app reads the status text from the activity message.

Example:

```text
Status changed to Approved
```

Then it classifies the event as:

- Approved
- Pending
- Awaiting review
- Rejected
- Other

## Funnel logic

### Set Pending by system
Unique users where the system changed the status to Pending.

### Manually actioned
Unique users where a non-system admin/agent performed any action.

### Approved
Unique users where a manual agent action changed the status to Approved.

### Awaiting review
Unique users with system updates but no manual agent action in the filtered data.

## Key point

The dashboard is currently event-based, with user-level summary reporting layered on top.

This can be changed later if the true reporting unit should be case ID/account ID rather than user ID.