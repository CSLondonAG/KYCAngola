
import io
import re
from datetime import datetime

import pandas as pd
import plotly.express as px
import streamlit as st


st.set_page_config(
    page_title="System vs Agent Activity Reporting",
    page_icon="📊",
    layout="wide",
)


def read_uploaded_csv(file):
    """Read uploaded CSV with a few common encoding fallbacks."""
    encodings = ["utf-8", "utf-8-sig", "cp1252", "latin-1"]
    for enc in encodings:
        try:
            file.seek(0)
            return pd.read_csv(file, encoding=enc)
        except Exception:
            continue
    file.seek(0)
    return pd.read_csv(file)


def extract_user_id(value):
    if pd.isna(value):
        return None
    text = str(value)
    match = re.search(r"\((\d+)\)", text)
    return match.group(1) if match else None


def extract_user_ref(value):
    if pd.isna(value):
        return None
    text = str(value)
    match = re.search(r"User:([^(]+)", text)
    return match.group(1).strip() if match else None


def extract_status_to(message):
    if pd.isna(message):
        return None
    text = str(message)
    match = re.search(r"changed to\s+([A-Za-z _-]+)", text, flags=re.I)
    if match:
        return match.group(1).strip()
    return None


def classify_event(row):
    actor = str(row.get("Admin", "")).strip()
    status_to = str(row.get("StatusTo", "")).lower()

    if actor.lower() == "system":
        source = "System"
    elif actor and actor.lower() != "nan":
        source = "Agent"
    else:
        source = "Unknown"

    if "approved" in status_to:
        event_type = "Approved"
    elif "pending" in status_to:
        event_type = "Pending"
    elif "review" in status_to:
        event_type = "Awaiting review"
    elif "reject" in status_to or "declin" in status_to:
        event_type = "Rejected"
    else:
        event_type = "Other"

    return pd.Series({"ActionSource": source, "EventType": event_type})


def process_files(files):
    frames = []

    for file in files:
        df = read_uploaded_csv(file)
        df["SourceFile"] = file.name
        frames.append(df)

    if not frames:
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)

    # Flexible date parsing
    date_col = None
    for candidate in ["Date", "Timestamp", "Created", "CreatedDate", "ActivityDate"]:
        if candidate in df.columns:
            date_col = candidate
            break

    if date_col:
        df["RawDate"] = df[date_col]
        df["EventDateTime"] = pd.to_datetime(df[date_col], errors="coerce", dayfirst=True)
        df["EventDate"] = df["EventDateTime"].dt.date
    else:
        df["RawDate"] = None
        df["EventDateTime"] = pd.NaT
        df["EventDate"] = None

    if "Date" in df.columns:
        df["UserID"] = df["Date"].apply(extract_user_id)
        df["UserRef"] = df["Date"].apply(extract_user_ref)
    else:
        df["UserID"] = None
        df["UserRef"] = None

    if "Message" in df.columns:
        df["StatusTo"] = df["Message"].apply(extract_status_to)
    else:
        df["StatusTo"] = None

    if "Admin" not in df.columns:
        df["Admin"] = "Unknown"

    classified = df.apply(classify_event, axis=1)
    df = pd.concat([df, classified], axis=1)

    df["IsSystemUpdate"] = df["ActionSource"].eq("System")
    df["IsManualAction"] = df["ActionSource"].eq("Agent")
    df["IsApproval"] = df["EventType"].eq("Approved")
    df["IsPending"] = df["EventType"].eq("Pending")

    return df


def latest_user_summary(df):
    if df.empty:
        return pd.DataFrame()

    working = df.copy()
    working = working.sort_values(["UserID", "EventDateTime"], na_position="last")

    grouped = (
        working.groupby("UserID", dropna=False)
        .agg(
            UserRef=("UserRef", "last"),
            FirstEvent=("EventDateTime", "min"),
            LastEvent=("EventDateTime", "max"),
            TotalEvents=("UserID", "size"),
            SystemUpdates=("IsSystemUpdate", "sum"),
            ManualActions=("IsManualAction", "sum"),
            LatestStatus=("StatusTo", "last"),
            LatestEventType=("EventType", "last"),
            LastActor=("Admin", "last"),
        )
        .reset_index()
    )

    grouped["HasSystemAndAgent"] = (grouped["SystemUpdates"] > 0) & (grouped["ManualActions"] > 0)
    grouped["AwaitingReview"] = (grouped["SystemUpdates"] > 0) & (grouped["ManualActions"] == 0)
    return grouped


def to_excel_bytes(sheets):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for name, data in sheets.items():
            safe_name = name[:31]
            data.to_excel(writer, sheet_name=safe_name, index=False)
    return output.getvalue()


st.title("System vs Agent Activity Reporting")
st.caption("Upload activity log CSVs, cross-reference system updates with manual agent actions, and export operational reports.")

uploaded_files = st.file_uploader(
    "Upload one or more activity log CSV files",
    type=["csv"],
    accept_multiple_files=True,
)

if not uploaded_files:
    st.info("Upload CSV exports to generate the dashboard.")
    st.stop()

df = process_files(uploaded_files)

if df.empty:
    st.error("No usable rows found in the uploaded files.")
    st.stop()

summary = latest_user_summary(df)

with st.sidebar:
    st.header("Filters")

    if df["EventDate"].notna().any():
        min_date = df["EventDate"].dropna().min()
        max_date = df["EventDate"].dropna().max()
        date_range = st.date_input("Date range", value=(min_date, max_date))
    else:
        date_range = None

    agents = sorted([x for x in df["Admin"].dropna().unique() if str(x).lower() != "system"])
    selected_agents = st.multiselect("Agents", agents)

    event_types = sorted(df["EventType"].dropna().unique())
    selected_event_types = st.multiselect("Event types", event_types)

filtered = df.copy()

if date_range and isinstance(date_range, tuple) and len(date_range) == 2:
    start, end = date_range
    filtered = filtered[
        (pd.to_datetime(filtered["EventDate"], errors="coerce") >= pd.to_datetime(start)) &
        (pd.to_datetime(filtered["EventDate"], errors="coerce") <= pd.to_datetime(end))
    ]

if selected_agents:
    filtered = filtered[filtered["Admin"].isin(selected_agents)]

if selected_event_types:
    filtered = filtered[filtered["EventType"].isin(selected_event_types)]

filtered_summary = latest_user_summary(filtered)

set_pending_by_system = filtered.loc[
    filtered["IsSystemUpdate"] & filtered["EventType"].eq("Pending"), "UserID"
].nunique()

manual_actioned = filtered.loc[filtered["IsManualAction"], "UserID"].nunique()
approved = filtered.loc[filtered["IsManualAction"] & filtered["EventType"].eq("Approved"), "UserID"].nunique()

awaiting_review = filtered_summary["AwaitingReview"].sum() if not filtered_summary.empty else 0

total_system_pending = max(set_pending_by_system, 1)
manual_pct = manual_actioned / total_system_pending
approved_pct = approved / max(manual_actioned, 1)
awaiting_pct = awaiting_review / total_system_pending

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("Set Pending by system", f"{set_pending_by_system:,}", "unique users")

with col2:
    st.metric("Manually actioned", f"{manual_actioned:,}", f"{manual_pct:.0%} of system pending")

with col3:
    st.metric("Approved", f"{approved:,}", f"{approved_pct:.0%} of actioned")

with col4:
    st.metric("Awaiting review", f"{awaiting_review:,}", f"{awaiting_pct:.0%} not yet actioned")

st.divider()

st.subheader("Daily Volume — System Flags vs Manual Resolutions")

daily = (
    filtered.groupby(["EventDate", "ActionSource", "EventType"], dropna=False)
    .size()
    .reset_index(name="Count")
)

if not daily.empty and daily["EventDate"].notna().any():
    daily["Series"] = daily["ActionSource"] + " — " + daily["EventType"]
    fig = px.bar(
        daily,
        x="EventDate",
        y="Count",
        color="Series",
        barmode="group",
        labels={"EventDate": "Date", "Count": "Volume"},
    )
    fig.update_layout(legend_title_text="", height=420)
    st.plotly_chart(fig, use_container_width=True)
else:
    st.warning("No valid dates found for daily charting.")

left, right = st.columns(2)

with left:
    st.subheader("Agent Activity")
    agent_table = (
        filtered[filtered["IsManualAction"]]
        .groupby("Admin")
        .agg(
            TotalActions=("Admin", "size"),
            UniqueUsers=("UserID", "nunique"),
            Approvals=("IsApproval", "sum"),
            PendingActions=("IsPending", "sum"),
        )
        .reset_index()
        .sort_values("TotalActions", ascending=False)
    )
    st.dataframe(agent_table, use_container_width=True, hide_index=True)

with right:
    st.subheader("Outcome Distribution")
    outcome = filtered.groupby(["ActionSource", "EventType"]).size().reset_index(name="Count")
    if not outcome.empty:
        fig2 = px.bar(
            outcome,
            x="EventType",
            y="Count",
            color="ActionSource",
            barmode="group",
        )
        fig2.update_layout(height=360, legend_title_text="")
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("No outcome data available.")

st.subheader("Cross-Reference Summary")
st.dataframe(filtered_summary, use_container_width=True, hide_index=True)

st.subheader("Search User History")
search_user = st.text_input("Enter User ID or reference")
if search_user:
    user_history = filtered[
        filtered["UserID"].astype(str).str.contains(search_user, case=False, na=False) |
        filtered["UserRef"].astype(str).str.contains(search_user, case=False, na=False)
    ].sort_values("EventDateTime")
    st.dataframe(user_history, use_container_width=True, hide_index=True)

st.divider()

excel_bytes = to_excel_bytes(
    {
        "Filtered Logs": filtered,
        "Cross Reference": filtered_summary,
        "Agent Activity": agent_table if "agent_table" in locals() else pd.DataFrame(),
    }
)

st.download_button(
    label="Download Excel Report",
    data=excel_bytes,
    file_name="system_agent_activity_report.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)
