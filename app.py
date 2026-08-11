import io
import os
import re
from datetime import datetime

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(
    page_title="Activity Funnel Report",
    page_icon="📊",
    layout="wide",
)

# ── Custom CSS ─────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=DM+Sans:wght@300;400;500;600&display=swap');

    html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }

    .stApp { background: #f5f6fa; color: #1a1d27; }

    /* Metric cards */
    [data-testid="metric-container"] {
        background: #ffffff;
        border: 1px solid #e2e5ef;
        border-radius: 12px;
        padding: 20px 24px;
        box-shadow: 0 1px 4px rgba(0,0,0,.06);
    }
    [data-testid="metric-container"] label { color: #6b7390; font-size: 12px; letter-spacing: .08em; text-transform: uppercase; }
    [data-testid="metric-container"] [data-testid="stMetricValue"] { font-family: 'DM Mono', monospace; font-size: 2rem; color: #1a1d27; }
    [data-testid="metric-container"] [data-testid="stMetricDelta"] { font-size: 12px; }

    /* Funnel card */
    .funnel-card {
        background: #ffffff;
        border: 1px solid #e2e5ef;
        border-radius: 12px;
        padding: 28px;
        margin-bottom: 24px;
        box-shadow: 0 1px 4px rgba(0,0,0,.06);
    }
    .funnel-title {
        font-size: 11px;
        letter-spacing: .12em;
        text-transform: uppercase;
        color: #6b7390;
        margin-bottom: 20px;
        font-weight: 500;
    }
    .funnel-step {
        display: flex;
        align-items: center;
        margin-bottom: 10px;
        gap: 16px;
    }
    .funnel-bar-bg {
        flex: 1;
        background: #eef0f7;
        border-radius: 4px;
        height: 32px;
        position: relative;
        overflow: hidden;
    }
    .funnel-bar-fill {
        height: 100%;
        border-radius: 4px;
        transition: width .6s ease;
    }
    .funnel-label {
        font-family: 'DM Mono', monospace;
        font-size: 12px;
        color: #4a5068;
        min-width: 120px;
    }
    .funnel-count {
        font-family: 'DM Mono', monospace;
        font-size: 13px;
        color: #1a1d27;
        min-width: 60px;
        text-align: right;
    }
    .funnel-pct {
        font-family: 'DM Mono', monospace;
        font-size: 11px;
        color: #6b7390;
        min-width: 48px;
        text-align: right;
    }
    .drop-arrow {
        font-size: 11px;
        color: #e05252;
        font-family: 'DM Mono', monospace;
        padding-left: 136px;
        margin-bottom: 6px;
    }
    /* Sidebar */
    [data-testid="stSidebar"] {
        background: #ffffff;
        border-right: 1px solid #e2e5ef;
    }
    [data-testid="stSidebar"] .stSelectbox label,
    [data-testid="stSidebar"] .stMultiSelect label,
    [data-testid="stSidebar"] .stDateInput label { color: #6b7390; font-size: 12px; }

    /* Tabs */
    .stTabs [data-baseweb="tab-list"] { background: transparent; border-bottom: 1px solid #e2e5ef; }
    .stTabs [data-baseweb="tab"] { color: #6b7390; font-size: 13px; letter-spacing: .04em; padding: 8px 20px; }
    .stTabs [aria-selected="true"] { color: #1a1d27; border-bottom: 2px solid #4a7af6; }

    /* Section headers */
    .section-header {
        font-size: 11px;
        letter-spacing: .12em;
        text-transform: uppercase;
        color: #6b7390;
        font-weight: 500;
        margin: 32px 0 16px;
    }

    /* Divider */
    hr { border-color: #e2e5ef; }

    /* Dataframe */
    [data-testid="stDataFrame"] { border: 1px solid #e2e5ef; border-radius: 8px; overflow: hidden; }

    /* Download button */
    .stDownloadButton button {
        background: #5c8df6;
        color: #fff;
        border: none;
        border-radius: 8px;
        font-size: 13px;
        font-weight: 500;
        padding: 10px 24px;
    }
    .stDownloadButton button:hover { background: #4a7ae0; }

    /* Hide default streamlit branding */
    #MainMenu, footer { visibility: hidden; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ── Helpers ────────────────────────────────────────────────────────────────

def read_csv_file(path):
    encodings = ["utf-8", "utf-8-sig", "cp1252", "latin-1"]
    for enc in encodings:
        try:
            return pd.read_csv(path, encoding=enc)
        except Exception:
            continue
    return pd.read_csv(path)


def extract_user_id(value):
    if pd.isna(value):
        return None
    match = re.search(r"\((\d+)\)", str(value))
    return match.group(1) if match else None


def extract_user_ref(value):
    if pd.isna(value):
        return None
    match = re.search(r"User:([^(]+)", str(value))
    return match.group(1).strip() if match else None


def extract_status_to(message):
    if pd.isna(message):
        return None
    match = re.search(r"changed to\s+([A-Za-z _-]+)", str(message), flags=re.I)
    return match.group(1).strip() if match else None


def classify_event(row):
    actor = str(row.get("Admin", "")).strip()
    status_to = str(row.get("StatusTo", "")).lower()

    source = "System" if actor.lower() == "system" else ("Agent" if actor and actor.lower() != "nan" else "Unknown")

    if "approved" in status_to:
        event_type = "Approved"
    elif "pending" in status_to:
        event_type = "Pending"
    elif "review" in status_to:
        event_type = "Awaiting Review"
    elif "reject" in status_to or "declin" in status_to:
        event_type = "Rejected"
    elif "withdraw" in status_to or "cancel" in status_to:
        event_type = "Withdrawn"
    else:
        event_type = "Other"

    return pd.Series({"ActionSource": source, "EventType": event_type})


def process_files(files):
    frames = []
    for file in files:
        path = str(file)
        df = read_csv_file(path)
        df["SourceFile"] = os.path.basename(path)
        frames.append(df)

    if not frames:
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)

    date_col = next((c for c in ["Date", "Timestamp", "Created", "CreatedDate", "ActivityDate"] if c in df.columns), None)
    if date_col:
        df["RawDate"] = df[date_col]
        df["EventDateTime"] = pd.to_datetime(df[date_col], errors="coerce", dayfirst=True)
        df["EventDate"] = df["EventDateTime"].dt.date
        df["EventWeek"] = df["EventDateTime"].dt.to_period("W").apply(lambda p: p.start_time.date() if pd.notna(p) else None)
        df["EventMonth"] = df["EventDateTime"].dt.to_period("M").apply(lambda p: p.start_time.date() if pd.notna(p) else None)
    else:
        df["RawDate"] = df["EventDateTime"] = pd.NaT
        df["EventDate"] = df["EventWeek"] = df["EventMonth"] = None

    if "Date" in df.columns:
        df["UserID"] = df["Date"].apply(extract_user_id)
        df["UserRef"] = df["Date"].apply(extract_user_ref)
    else:
        df["UserID"] = df["UserRef"] = None

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
    df["IsRejected"] = df["EventType"].eq("Rejected")
    df["IsPending"] = df["EventType"].eq("Pending")
    df["IsWithdrawn"] = df["EventType"].eq("Withdrawn")

    return df


def build_funnel(df):
    """
    Build funnel metrics tracking each unique user through pipeline stages.

    For users who ultimately reach Approved status, multiple system-generated
    Pending events are collapsed to one — only their first pending event counts.
    This prevents re-pended approved users from inflating the Pending stage
    and distorting downstream conversion rates.
    """
    if df.empty:
        return {}

    all_users = df["UserID"].dropna().nunique()

    # Users whose final recorded outcome is Approved
    approved_user_ids = set(df.loc[df["IsApproval"], "UserID"].dropna().unique())

    # Deduplicated pending view:
    #   approved users -> keep only their earliest pending event (one per user)
    #   everyone else  -> keep as-is
    pending_rows = df.loc[df["IsSystemUpdate"] & df["IsPending"]].copy()
    approved_pending = (
        pending_rows[pending_rows["UserID"].isin(approved_user_ids)]
        .sort_values("EventDateTime")
        .drop_duplicates(subset=["UserID"], keep="first")
    )
    other_pending = pending_rows[~pending_rows["UserID"].isin(approved_user_ids)]
    deduped_pending = pd.concat([approved_pending, other_pending], ignore_index=True)

    # Stage 1 — entered the system
    entered = all_users

    # Stage 2 — system-flagged pending (approved users counted once each)
    pending_users = set(deduped_pending["UserID"].dropna().unique())
    pending_n = len(pending_users)

    # Stage 3 — agent touched the user at any point
    actioned_users = set(df.loc[df["IsManualAction"], "UserID"].dropna().unique())

    # Stage 4 — reviewed = pending AND actioned
    reviewed_ids = pending_users & actioned_users
    reviewed_n = len(reviewed_ids)

    # Stage 5 — approved
    approved_n = len(approved_user_ids)

    # Stage 6a — rejected
    rejected_n = df.loc[df["IsRejected"], "UserID"].dropna().nunique()

    # Stage 6b — withdrawn
    withdrawn_n = df.loc[df["IsWithdrawn"], "UserID"].dropna().nunique()

    # Awaiting review — pending but no agent action yet
    awaiting_n = len(pending_users - actioned_users)

    return {
        "entered": entered,
        "pending": pending_n,
        "reviewed": reviewed_n,
        "approved": approved_n,
        "rejected": rejected_n,
        "withdrawn": withdrawn_n,
        "awaiting": awaiting_n,
    }


def latest_user_summary(df):
    if df.empty:
        return pd.DataFrame()

    working = df.sort_values(["UserID", "EventDateTime"], na_position="last")
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
    grouped["Stage"] = grouped.apply(_assign_stage, axis=1)
    grouped["HasSystemAndAgent"] = (grouped["SystemUpdates"] > 0) & (grouped["ManualActions"] > 0)
    grouped["AwaitingReview"] = (grouped["SystemUpdates"] > 0) & (grouped["ManualActions"] == 0)
    return grouped


def _assign_stage(row):
    et = str(row.get("LatestEventType", "")).lower()
    if "approved" in et:
        return "✅ Approved"
    if "reject" in et or "declin" in et:
        return "❌ Rejected"
    if "withdraw" in et or "cancel" in et:
        return "↩️ Withdrawn"
    if row.get("ManualActions", 0) > 0:
        return "👤 Agent Actioned"
    if row.get("SystemUpdates", 0) > 0:
        return "⏳ Awaiting Review"
    return "🔵 Entered"


def to_excel_bytes(sheets):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for name, data in sheets.items():
            data.to_excel(writer, sheet_name=name[:31], index=False)
    return output.getvalue()


def pct(num, denom):
    return num / denom if denom else 0


# ── Render funnel HTML ─────────────────────────────────────────────────────

FUNNEL_COLORS = {
    "entered":   "#5c8df6",
    "pending":   "#a78bfa",
    "actioned":  "#38bdf8",
    "reviewed":  "#34d399",
    "approved":  "#4ade80",
    "rejected":  "#f87171",
    "withdrawn": "#fb923c",
    "awaiting":  "#fbbf24",
}

FUNNEL_STAGES = [
    ("entered",   "All Users Entered"),
    ("pending",   "System → Pending"),
    ("reviewed",  "Agent Reviewed"),
    ("approved",  "Approved"),
    ("rejected",  "Rejected"),
    ("withdrawn", "Withdrawn"),
    ("awaiting",  "Awaiting Review (no action yet)"),
]


def render_funnel_html(funnel: dict) -> str:
    top = max(funnel.get("entered", 1), 1)
    rows = []
    prev_key = None

    for key, label in FUNNEL_STAGES:
        val = funnel.get(key, 0)
        bar_pct = pct(val, top) * 100
        pct_str = f"{bar_pct:.1f}%"
        color = FUNNEL_COLORS.get(key, "#5c8df6")

        # Drop rate arrow vs previous main stage
        if prev_key and key not in ("rejected", "withdrawn", "awaiting"):
            prev_val = funnel.get(prev_key, 0)
            drop = prev_val - val
            drop_pct = pct(drop, prev_val) * 100 if prev_val else 0
            if drop > 0:
                rows.append(
                    f'<div class="drop-arrow">▼ {drop:,} dropped ({drop_pct:.1f}%)</div>'
                )

        rows.append(f"""
        <div class="funnel-step">
            <div class="funnel-label">{label}</div>
            <div class="funnel-bar-bg">
                <div class="funnel-bar-fill" style="width:{bar_pct:.1f}%;background:{color};opacity:.85;"></div>
            </div>
            <div class="funnel-count">{val:,}</div>
            <div class="funnel-pct">{pct_str}</div>
        </div>""")

        if key not in ("rejected", "withdrawn", "awaiting"):
            prev_key = key

    html = f"""
    <div class="funnel-card">
        {"".join(rows)}
    </div>"""
    return html


# ── Main ───────────────────────────────────────────────────────────────────

st.markdown('<h2 style="font-family:DM Mono,monospace;font-size:22px;color:#1a1d27;margin-bottom:4px;">Activity Funnel Report</h2>', unsafe_allow_html=True)
st.markdown('<p style="color:#6b7390;font-size:13px;margin-bottom:0;">System vs Agent pipeline — reads activity log CSVs from the <code>data/</code> folder.</p>', unsafe_allow_html=True)

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

if not os.path.isdir(DATA_DIR):
    st.error(f"Data directory not found: `{DATA_DIR}`. Create a `data/` folder next to `app.py` and place your CSV files there.")
    st.stop()

csv_files = sorted([
    os.path.join(DATA_DIR, f)
    for f in os.listdir(DATA_DIR)
    if f.lower().endswith(".csv")
])

if not csv_files:
    st.info(f"No CSV files found in `{DATA_DIR}`. Add activity log CSVs there and refresh.")
    st.stop()

df = process_files(csv_files)

if df.empty:
    st.error("No usable rows found in the uploaded files.")
    st.stop()

# ── Sidebar filters ────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown('<div style="font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:#6b7390;margin-bottom:16px;font-weight:500;">Filters</div>', unsafe_allow_html=True)

    if df["EventDate"].notna().any():
        min_date = df["EventDate"].dropna().min()
        max_date = df["EventDate"].dropna().max()
        date_range = st.date_input("Date range", value=(min_date, max_date))
    else:
        date_range = None

    granularity = st.selectbox("Time granularity", ["Day", "Week", "Month"], index=0)

    agents = sorted([x for x in df["Admin"].dropna().unique() if str(x).lower() not in ("system", "nan", "")])
    selected_agents = st.multiselect("Agents", agents)

    event_types = sorted(df["EventType"].dropna().unique())
    selected_event_types = st.multiselect("Event types", event_types)

    sources = sorted(df["ActionSource"].dropna().unique())
    selected_sources = st.multiselect("Action source", sources)

    st.divider()
    st.markdown('<div style="font-size:11px;color:#6b7390;">Files loaded</div>', unsafe_allow_html=True)
    for f in csv_files:
        st.markdown(f'<div style="font-size:12px;color:#4a5068;font-family:DM Mono,monospace;">📄 {os.path.basename(f)}</div>', unsafe_allow_html=True)

# ── Apply filters ──────────────────────────────────────────────────────────
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
if selected_sources:
    filtered = filtered[filtered["ActionSource"].isin(selected_sources)]

filtered_summary = latest_user_summary(filtered)
funnel = build_funnel(filtered)

# ── KPI row ────────────────────────────────────────────────────────────────
col1, col2, col3, col4, col5 = st.columns(5)

entered = funnel.get("entered", 0)
pending = funnel.get("pending", 0)
reviewed = funnel.get("reviewed", 0)
approved = funnel.get("approved", 0)
awaiting = funnel.get("awaiting", 0)

with col1:
    st.metric("Total Users", f"{entered:,}")
with col2:
    st.metric("System Flagged", f"{pending:,}", f"{pct(pending, entered):.0%} of total")
with col3:
    st.metric("Agent Reviewed", f"{reviewed:,}", f"{pct(reviewed, pending):.0%} of flagged")
with col4:
    st.metric("Approved", f"{approved:,}", f"{pct(approved, reviewed):.0%} of reviewed")
with col5:
    st.metric("Awaiting Review", f"{awaiting:,}", f"{pct(awaiting, pending):.0%} not actioned")

st.markdown("---")

# ── Funnel visualisation ───────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs(["📐 Funnel", "📈 Volume Over Time", "👤 Agent Activity", "🔍 User Lookup"])

with tab1:
    if True:
        # Sankey diagram
        node_labels = ["Entered", "Sys Pending", "Agent Reviewed", "Approved", "Rejected", "Withdrawn", "Awaiting Review"]
        node_colors = ["#5c8df6", "#a78bfa", "#38bdf8", "#4ade80", "#f87171", "#fb923c", "#fbbf24"]

        entered_n = funnel.get("entered", 0)
        pending_n = funnel.get("pending", 0)
        reviewed_n = funnel.get("reviewed", 0)
        approved_n = funnel.get("approved", 0)
        rejected_n = funnel.get("rejected", 0)
        withdrawn_n = funnel.get("withdrawn", 0)
        awaiting_n = funnel.get("awaiting", 0)
        not_pending = max(entered_n - pending_n, 0)

        sources_s = [0, 1, 2, 2, 2, 1]
        targets_s = [1, 2, 3, 4, 5, 6]
        values_s  = [
            max(pending_n, 0),
            max(reviewed_n, 0),
            max(approved_n, 0),
            max(rejected_n, 0),
            max(withdrawn_n, 0),
            max(awaiting_n, 0),
        ]
        link_colors = ["rgba(167,139,250,.35)", "rgba(56,189,248,.35)",
                       "rgba(74,222,128,.35)", "rgba(248,113,113,.35)",
                       "rgba(251,146,60,.35)", "rgba(251,191,36,.35)"]

        fig_sankey = go.Figure(go.Sankey(
            arrangement="snap",
            node=dict(
                pad=18, thickness=18,
                label=node_labels,
                color=node_colors,
                line=dict(color="#ffffff", width=1),
            ),
            link=dict(source=sources_s, target=targets_s, value=values_s, color=link_colors),
        ))
        fig_sankey.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(family="DM Mono", color="#4a5068", size=11),
            margin=dict(l=10, r=10, t=30, b=10),
            height=400,
            title=dict(text="Flow Diagram", font=dict(color="#6b7390", size=11), x=0),
        )
        st.plotly_chart(fig_sankey, width="stretch")

    # Stage distribution table
    st.markdown('<div class="section-header">Stage Distribution</div>', unsafe_allow_html=True)
    if not filtered_summary.empty:
        stage_dist = (
            filtered_summary.groupby("Stage")
            .size()
            .reset_index(name="Users")
            .sort_values("Users", ascending=False)
        )
        stage_dist["Share %"] = (stage_dist["Users"] / stage_dist["Users"].sum() * 100).round(1).astype(str) + "%"
        st.dataframe(stage_dist, width="stretch", hide_index=True)

    # Conversion rates summary
    st.markdown('<div class="section-header">Conversion Rates</div>', unsafe_allow_html=True)
    conv_data = {
        "Metric": [
            "System Flagged → Agent Reviewed",
            "Agent Reviewed → Approved",
            "Agent Reviewed → Rejected",
            "Agent Reviewed → Withdrawn",
            "System Flagged, No Action Yet",
        ],
        "Rate": [
            f"{pct(reviewed_n, pending_n):.1%}",
            f"{pct(approved_n, reviewed_n):.1%}",
            f"{pct(rejected_n, reviewed_n):.1%}",
            f"{pct(withdrawn_n, reviewed_n):.1%}",
            f"{pct(awaiting_n, pending_n):.1%}",
        ],
        "Numerator": [reviewed_n, approved_n, rejected_n, withdrawn_n, awaiting_n],
        "Denominator": [pending_n, reviewed_n, reviewed_n, reviewed_n, pending_n],
    }
    st.dataframe(pd.DataFrame(conv_data), width="stretch", hide_index=True)


with tab2:
    gran_col = {"Day": "EventDate", "Week": "EventWeek", "Month": "EventMonth"}[granularity]

    daily = (
        filtered.groupby([gran_col, "ActionSource", "EventType"], dropna=False)
        .size()
        .reset_index(name="Count")
    )

    if not daily.empty and daily[gran_col].notna().any():
        daily["Series"] = daily["ActionSource"] + " — " + daily["EventType"]

        fig_vol = px.bar(
            daily, x=gran_col, y="Count", color="Series", barmode="group",
            labels={gran_col: granularity, "Count": "Events"},
            color_discrete_sequence=["#5c8df6","#a78bfa","#38bdf8","#34d399","#f87171","#fb923c","#fbbf24"],
        )
        fig_vol.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(family="DM Mono", color="#4a5068", size=11),
            legend=dict(font=dict(color="#4a5068"), bgcolor="rgba(0,0,0,0)"),
            xaxis=dict(gridcolor="#e2e5ef"), yaxis=dict(gridcolor="#e2e5ef"),
            height=420, legend_title_text="",
        )
        st.plotly_chart(fig_vol, width="stretch")

        # Cumulative approved line
        approved_daily = (
            filtered[filtered["IsApproval"]]
            .groupby(gran_col, dropna=False)
            .size()
            .reset_index(name="Approvals")
            .dropna(subset=[gran_col])
            .sort_values(gran_col)
        )
        if not approved_daily.empty:
            approved_daily["Cumulative Approvals"] = approved_daily["Approvals"].cumsum()
            fig_cum = px.area(
                approved_daily, x=gran_col, y="Cumulative Approvals",
                labels={gran_col: granularity},
                color_discrete_sequence=["#4ade80"],
                title="Cumulative Approvals Over Time",
            )
            fig_cum.update_traces(line_color="#4ade80", fillcolor="rgba(74,222,128,.15)")
            fig_cum.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font=dict(family="DM Mono", color="#4a5068", size=11),
                xaxis=dict(gridcolor="#e2e5ef"), yaxis=dict(gridcolor="#e2e5ef"),
                height=320, title_font_color="#6b7390", title_font_size=11,
            )
            st.plotly_chart(fig_cum, width="stretch")
    else:
        st.warning("No valid dates found for time-series charting.")


with tab3:
    left_a, right_a = st.columns(2)

    with left_a:
        st.markdown('<div class="section-header">Agent Leaderboard</div>', unsafe_allow_html=True)
        agent_table = (
            filtered[filtered["IsManualAction"]]
            .groupby("Admin")
            .agg(
                TotalActions=("Admin", "size"),
                UniqueUsers=("UserID", "nunique"),
                Approvals=("IsApproval", "sum"),
                Rejections=("IsRejected", "sum"),
                PendingActions=("IsPending", "sum"),
            )
            .reset_index()
            .sort_values("TotalActions", ascending=False)
        )
        if not agent_table.empty:
            agent_table["Approval Rate"] = (agent_table["Approvals"] / agent_table["TotalActions"]).map("{:.0%}".format)
        st.dataframe(agent_table, width="stretch", hide_index=True)

    with right_a:
        st.markdown('<div class="section-header">Outcome Distribution</div>', unsafe_allow_html=True)
        outcome = filtered.groupby(["ActionSource", "EventType"]).size().reset_index(name="Count")
        if not outcome.empty:
            fig2 = px.bar(
                outcome, x="EventType", y="Count", color="ActionSource", barmode="group",
                color_discrete_map={"System": "#a78bfa", "Agent": "#38bdf8", "Unknown": "#7b8299"},
            )
            fig2.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font=dict(family="DM Mono", color="#4a5068", size=11),
                legend=dict(font=dict(color="#4a5068"), bgcolor="rgba(0,0,0,0)"),
                xaxis=dict(gridcolor="#e2e5ef"), yaxis=dict(gridcolor="#e2e5ef"),
                height=360, legend_title_text="",
            )
            st.plotly_chart(fig2, width="stretch")

    st.markdown('<div class="section-header">Full Cross-Reference</div>', unsafe_allow_html=True)
    st.dataframe(filtered_summary, width="stretch", hide_index=True)


with tab4:
    search_user = st.text_input("Search by User ID or reference", placeholder="e.g. 12345 or john.doe")
    if search_user:
        user_history = filtered[
            filtered["UserID"].astype(str).str.contains(search_user, case=False, na=False) |
            filtered["UserRef"].astype(str).str.contains(search_user, case=False, na=False)
        ].sort_values("EventDateTime")

        if user_history.empty:
            st.info("No matching users found.")
        else:
            uid = user_history["UserID"].iloc[0]
            uref = user_history["UserRef"].iloc[0]
            ustage = user_history.apply(lambda r: _assign_stage(r), axis=1).iloc[-1] if not user_history.empty else "—"

            m1, m2, m3 = st.columns(3)
            m1.metric("User ID", uid or "—")
            m2.metric("Reference", uref or "—")
            m3.metric("Current Stage", ustage)

            st.markdown('<div class="section-header">Event Timeline</div>', unsafe_allow_html=True)

            # Build a simple timeline
            timeline_rows = []
            for _, row in user_history.iterrows():
                timeline_rows.append({
                    "Date/Time": row.get("EventDateTime", ""),
                    "Actor": row.get("Admin", ""),
                    "Source": row.get("ActionSource", ""),
                    "Event": row.get("EventType", ""),
                    "Status": row.get("StatusTo", ""),
                    "File": row.get("SourceFile", ""),
                })
            st.dataframe(pd.DataFrame(timeline_rows), width="stretch", hide_index=True)

# ── Export ─────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown('<div class="section-header">Export</div>', unsafe_allow_html=True)

funnel_df = pd.DataFrame([
    {"Stage": label, "Users": funnel.get(key, 0), "% of Total": f"{pct(funnel.get(key,0), entered):.1%}"}
    for key, label in FUNNEL_STAGES
])

excel_bytes = to_excel_bytes({
    "Funnel Summary": funnel_df,
    "Conversion Rates": pd.DataFrame({
        "Metric": ["Flagged → Reviewed", "Reviewed → Approved", "Reviewed → Rejected", "Flagged Not Actioned"],
        "Rate": [
            f"{pct(reviewed_n, pending_n):.1%}",
            f"{pct(approved_n, reviewed_n):.1%}",
            f"{pct(rejected_n, reviewed_n):.1%}",
            f"{pct(awaiting_n, pending_n):.1%}",
        ],
    }),
    "Filtered Logs": filtered.drop(columns=["EventWeek", "EventMonth"], errors="ignore"),
    "Cross Reference": filtered_summary,
    "Agent Activity": agent_table if "agent_table" in locals() else pd.DataFrame(),
})

col_dl1, col_dl2 = st.columns([1, 4])
with col_dl1:
    st.download_button(
        label="⬇ Download Excel Report",
        data=excel_bytes,
        file_name=f"funnel_report_{datetime.today().strftime('%Y%m%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
