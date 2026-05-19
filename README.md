# System vs Agent Activity Reporting App

This is a Streamlit dashboard for uploading activity log CSV exports and cross-referencing system-generated updates against manual agent activity.

## What it does

- Upload multiple CSV exports
- Merge logs into one dataset
- Classify events as System / Agent / Unknown
- Classify outcomes such as Pending, Approved, Awaiting Review, Rejected, Other
- Produce KPI funnel cards
- Show daily activity charts
- Show agent activity summaries
- Show user-level cross-reference reporting
- Export filtered reports to Excel

## How to run locally

1. Install Python 3.10+
2. Open a terminal in this folder
3. Run:

```bash
pip install -r requirements.txt
streamlit run app.py
```

## V1 assumptions

The first version assumes the exported logs include columns similar to:

- Date
- Admin
- Message

Current rules:

- `Admin = System` means system-generated update
- Any other `Admin` value means manual agent action
- User ID is extracted from brackets in the Date field
- Status is extracted from messages containing `changed to ...`

These rules can be adjusted once the final operational definitions are agreed.