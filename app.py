from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime, date
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

try:
    from streamlit_autorefresh import st_autorefresh
    AUTOREFRESH = True
except Exception:
    AUTOREFRESH = False

st.set_page_config(
    page_title="BGS Portal",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)

if AUTOREFRESH:
    st_autorefresh(interval=30_000, key="portal_refresh")

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

LINKS_FILE = DATA_DIR / "links.json"
TIMETABLE_FILE = DATA_DIR / "timetable.json"
HOMEWORK_FILE = DATA_DIR / "homework.json"
OVERRIDES_FILE = DATA_DIR / "schedule_overrides.json"

st.markdown("""
<style>
html, body, [class*="css"] {
    font-family: Inter, system-ui, sans-serif;
}
.stApp {
    background:
        radial-gradient(circle at top right, rgba(64,88,150,0.16), transparent 30%),
        linear-gradient(135deg, #0b1020 0%, #111827 45%, #0f172a 100%);
    color: #e5e7eb;
}
.block-container {
    padding-top: 1.2rem;
    padding-bottom: 2rem;
    max-width: 1400px;
}
.card {
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 18px;
    padding: 16px 18px;
    backdrop-filter: blur(14px);
    box-shadow: 0 10px 30px rgba(0,0,0,0.22);
    min-height: 118px;
}
.card h4 { margin: 0 0 8px 0; font-size: 0.92rem; color: #9ca3af; font-weight: 600; }
.card h2 { margin: 0; font-size: 1.6rem; color: #f8fafc; }
.subtle { color: #9ca3af; font-size: 0.95rem; }
.link-card {
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 16px;
    padding: 14px;
    margin-bottom: 12px;
}
.badge {
    display: inline-block;
    padding: 4px 10px;
    border-radius: 999px;
    background: rgba(59,130,246,0.18);
    border: 1px solid rgba(59,130,246,0.32);
    color: #dbeafe;
    font-size: 0.78rem;
    margin-bottom: 8px;
}
hr { border-color: rgba(255,255,255,0.08); }
</style>
""", unsafe_allow_html=True)

# -------------------------
# Helpers
# -------------------------
def load_json(path: Path, default):
    if not path.exists():
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default, f, indent=2)
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path: Path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def default_links():
    return [
        {"label": "MyGrammar", "url": "https://brisbanegrammarcom.sharepoint.com/sites/MyGrammar1/", "group": "School"},
        {"label": "Data Portal", "url": "https://app.powerbi.com/groups/me/reports/f76a3a6e-294d-4bf4-abcc-4fd467382e10/1cab637b75cb9267c7d5?chromeless=1&experience=power-bi", "group": "School"},
        {"label": "Edval Timetable", "url": "https://brisbanegrammar.edval.education/timetable", "group": "Timetable"},
        {"label": "BGS Website", "url": "https://www.brisbanegrammar.com", "group": "School"},
        {"label": "Parent Portal", "url": "https://parents.brisbanegrammar.com/welcome/", "group": "School"},
        {"label": "Lilley Centre", "url": "https://www.brisbanegrammar.com/lilley-centre", "group": "Library"},
        {"label": "Bookings", "url": "https://www.brisbanegrammar.com/page-modules/bookings", "group": "School"},
        {"label": "Student Email", "url": "", "group": "Internal"},
        {"label": "Canvas / LMS", "url": "", "group": "Internal"},
        {"label": "Student Notices", "url": "", "group": "Internal"},
    ]

def blank_week():
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    periods = [
        ("P1", "08:25", "09:10"),
        ("P2", "09:10", "09:55"),
        ("P3", "10:20", "11:05"),
        ("P4", "11:05", "11:50"),
        ("P5", "12:20", "13:05"),
        ("P6", "13:05", "13:50"),
    ]
    template = {}
    for d in days:
        template[d] = [
            {"period": p, "subject": "", "teacher": "", "room": "", "start": s, "end": e}
            for p, s, e in periods
        ]
    return template

def default_timetable():
    return {"A": blank_week(), "B": blank_week()}

def parse_time(t: str):
    return datetime.strptime(t, "%H:%M").time()

def get_now():
    return datetime.now()

def day_name():
    return get_now().strftime("%A")

def current_or_next(schedule, now_time):
    current = None
    upcoming = None
    for row in schedule:
        start_t = parse_time(row["start"])
        end_t = parse_time(row["end"])
        if start_t <= now_time <= end_t:
            current = row
        elif now_time < start_t and upcoming is None:
            upcoming = row
    return current, upcoming

def apply_overrides(schedule, overrides, week, day):
    changed = []
    output = [dict(row) for row in schedule]
    for ov in overrides:
        if ov.get("week") == week and ov.get("day") == day:
            for row in output:
                if row["period"] == ov.get("period"):
                    before = (row["start"], row["end"], row.get("room", ""))
                    row["start"] = ov.get("new_start", row["start"])
                    row["end"] = ov.get("new_end", row["end"])
                    row["room"] = ov.get("new_room", row.get("room", ""))
                    row["note"] = ov.get("note", "")
                    after = (row["start"], row["end"], row.get("room", ""))
                    if before != after:
                        changed.append(row)
    return output, changed

def homework_counts(items):
    today = date.today()
    open_items = [x for x in items if not x.get("done")]
    due_soon = 0
    for item in open_items:
        try:
            due = date.fromisoformat(item["due_date"])
            if due >= today and (due - today).days <= 2:
                due_soon += 1
        except Exception:
            pass
    return len(open_items), due_soon

# -------------------------
# Load data
# -------------------------
links = load_json(LINKS_FILE, default_links())
timetable = load_json(TIMETABLE_FILE, default_timetable())
homework = load_json(HOMEWORK_FILE, [])
overrides = load_json(OVERRIDES_FILE, [])

if "seen_alerts" not in st.session_state:
    st.session_state.seen_alerts = set()

# -------------------------
# Sidebar
# -------------------------
st.sidebar.title("BGS Portal")
selected_week = st.sidebar.selectbox("Week cycle", ["A", "B"], index=0)
valid_days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
default_day_idx = valid_days.index(day_name()) if day_name() in valid_days else 0
selected_day = st.sidebar.selectbox("View day", valid_days, index=default_day_idx)

st.sidebar.markdown("---")
st.sidebar.markdown("**Quick jump**")
st.sidebar.markdown("[MyGrammar](https://brisbanegrammarcom.sharepoint.com/sites/MyGrammar1/)")
st.sidebar.markdown("[Edval Timetable](https://brisbanegrammar.edval.education/timetable)")
st.sidebar.markdown("[Data Portal](https://app.powerbi.com/groups/me/reports/f76a3a6e-294d-4bf4-abcc-4fd467382e10/1cab637b75cb9267c7d5?chromeless=1&experience=power-bi)")

# -------------------------
# Header
# -------------------------
now = get_now()
today_name = now.strftime("%A")
today_date = now.strftime("%d %b %Y")
today_time = now.strftime("%I:%M %p")

base_today_schedule = timetable.get(selected_week, {}).get(today_name, [])
today_schedule, changed_rows = apply_overrides(base_today_schedule, overrides, selected_week, today_name)
current_class, next_class = current_or_next(today_schedule, now.time())
open_hw, due_soon = homework_counts(homework)

st.title("🎓 BGS Portal")
st.caption(f"Week {selected_week} · {today_date} · {today_time}")

c1, c2, c3, c4 = st.columns(4)

with c1:
    st.markdown(f"""
    <div class="card">
        <h4>Today</h4>
        <h2>{today_name}</h2>
        <div class="subtle">{today_date}</div>
    </div>""", unsafe_allow_html=True)

with c2:
    st.markdown(f"""
    <div class="card">
        <h4>Current time</h4>
        <h2>{today_time}</h2>
        <div class="subtle">Week {selected_week}</div>
    </div>""", unsafe_allow_html=True)

with c3:
    current_text = "Free period"
    current_subtle = "No class right now"
    if current_class and current_class.get("subject"):
        current_text = f'{current_class["period"]} · {current_class["subject"]}'
        current_subtle = f'{current_class["start"]}–{current_class["end"]} · {current_class.get("room","")}'
    st.markdown(f"""
    <div class="card">
        <h4>Current class</h4>
        <h2>{current_text}</h2>
        <div class="subtle">{current_subtle}</div>
    </div>""", unsafe_allow_html=True)

with c4:
    next_text = "No more classes"
    next_subtle = "Day complete"
    if next_class and next_class.get("subject"):
        next_text = f'{next_class["period"]} · {next_class["subject"]}'
        next_subtle = f'{next_class["start"]} · {next_class.get("room","")}'
    st.markdown(f"""
    <div class="card">
        <h4>Next up</h4>
        <h2>{next_text}</h2>
        <div class="subtle">{next_subtle}</div>
    </div>""", unsafe_allow_html=True)

# -------------------------
# Alerts
# -------------------------
if changed_rows:
    for row in changed_rows:
        alert_key = f"{selected_week}-{today_name}-{row['period']}-{row['start']}-{row['end']}"
        if alert_key not in st.session_state.seen_alerts:
            st.toast(f"⚠️ Schedule change: {row['period']} now {row['start']}–{row['end']}")
            st.session_state.seen_alerts.add(alert_key)
        note = f" — {row.get('note','')}" if row.get("note") else ""
        st.warning(f"**{row['period']} {row.get('subject','Class')}** changed to {row['start']}–{row['end']} in {row.get('room','TBA')}{note}")

# -------------------------
# Main layout
# -------------------------
left, right = st.columns([1.15, 0.85], gap="large")

with left:
    st.markdown("### Timetable")

    timetable_tabs = st.tabs(["Today", "Full Week", "Edval Live", "Edit", "Overrides"])

    with timetable_tabs[0]:
        day_schedule = timetable.get(selected_week, {}).get(selected_day, [])
        day_with_ov, _ = apply_overrides(day_schedule, overrides, selected_week, selected_day)
        df_day = pd.DataFrame(day_with_ov)
        st.dataframe(df_day, use_container_width=True, hide_index=True)

    with timetable_tabs[1]:
        for d in valid_days:
            st.markdown(f"**{d}**")
            df = pd.DataFrame(timetable.get(selected_week, {}).get(d, []))
            st.dataframe(df, use_container_width=True, hide_index=True)

    with timetable_tabs[2]:
        st.info("Edval may block embedding due to login requirements. Use the button below to open it directly.", icon="ℹ️")
        st.link_button("Open Edval Timetable ↗", "https://brisbanegrammar.edval.education/timetable", use_container_width=True)
        st.markdown("---")
        st.caption("Attempting embed — will show blank if Edval blocks iframes:")
        components.iframe("https://brisbanegrammar.edval.education/timetable", height=500, scrolling=True)

    with timetable_tabs[3]:
        edit_day = st.selectbox("Edit day", valid_days, key="edit_day")
        edit_df = pd.DataFrame(timetable[selected_week][edit_day])
        edited = st.data_editor(
            edit_df,
            use_container_width=True,
            num_rows="fixed",
            hide_index=True,
            key=f"editor_{selected_week}_{edit_day}"
        )
        if st.button("Save timetable changes"):
            timetable[selected_week][edit_day] = edited.fillna("").to_dict(orient="records")
            save_json(TIMETABLE_FILE, timetable)
            st.success("Saved.")
            st.rerun()

    with timetable_tabs[4]:
        with st.form("override_form", clear_on_submit=True):
            ov_day = st.selectbox("Day", valid_days)
            ov_period = st.selectbox("Period", ["P1", "P2", "P3", "P4", "P5", "P6"])
            ov_start = st.text_input("New start time", placeholder="08:35")
            ov_end = st.text_input("New end time", placeholder="09:20")
            ov_room = st.text_input("New room", placeholder="C205 / TBA")
            ov_note = st.text_input("Note", placeholder="Assembly / late start / room swap")
            if st.form_submit_button("Add override"):
                overrides.append({
                    "week": selected_week, "day": ov_day, "period": ov_period,
                    "new_start": ov_start, "new_end": ov_end,
                    "new_room": ov_room, "note": ov_note
                })
                save_json(OVERRIDES_FILE, overrides)
                st.success("Override added.")
                st.rerun()

        if overrides:
            ov_df = pd.DataFrame(overrides)
            st.dataframe(ov_df, use_container_width=True, hide_index=True)
            if st.button("Clear all overrides"):
                save_json(OVERRIDES_FILE, [])
                st.rerun()

with right:
    st.markdown("### Quick Links")
    groups = {}
    for item in links:
        groups.setdefault(item.get("group", "Other"), []).append(item)

    for group, items in groups.items():
        st.markdown(f"<div class='badge'>{group}</div>", unsafe_allow_html=True)
        cols = st.columns(2)
        for i, item in enumerate(items):
            url = item.get("url", "").strip()
            label = item.get("label", "Link")
            with cols[i % 2]:
                if url:
                    st.markdown(
                        f"<div class='link-card'><a href='{url}' target='_blank' style='color:#f8fafc;text-decoration:none;font-weight:600'>{label} ↗</a></div>",
                        unsafe_allow_html=True
                    )
                else:
                    st.markdown(
                        f"<div class='link-card'><div style='font-weight:600;color:#6b7280'>{label}</div><div class='subtle'>URL not set</div></div>",
                        unsafe_allow_html=True
                    )

    with st.expander("Edit links"):
        links_df = pd.DataFrame(links)
        new_links_df = st.data_editor(links_df, use_container_width=True, num_rows="dynamic", hide_index=True, key="links_editor")
        if st.button("Save links"):
            links = new_links_df.fillna("").to_dict(orient="records")
            save_json(LINKS_FILE, links)
            st.success("Links saved.")
            st.rerun()

    st.markdown("---")
    st.markdown("### Homework")
    hw_col1, hw_col2 = st.columns(2)
    hw_col1.metric("Open tasks", open_hw)
    hw_col2.metric("Due within 2 days", due_soon)

    with st.form("homework_form", clear_on_submit=True):
        subject = st.text_input("Subject")
        title = st.text_input("Task title")
        due_date_input = st.date_input("Due date")
        priority = st.selectbox("Priority", ["Low", "Medium", "High"])
        details = st.text_area("Details / how to complete")
        if st.form_submit_button("Add homework") and title.strip():
            homework.append({
                "subject": subject.strip(),
                "title": title.strip(),
                "due_date": due_date_input.isoformat(),
                "priority": priority,
                "details": details.strip(),
                "done": False,
                "created_at": datetime.now().isoformat(timespec="minutes")
            })
            save_json(HOMEWORK_FILE, homework)
            st.success("Added.")
            st.rerun()

    if homework:
        incomplete = sorted([x for x in homework if not x.get("done")], key=lambda x: x["due_date"])
        complete = [x for x in homework if x.get("done")]
        hw_tabs = st.tabs([f"To Do ({len(incomplete)})", f"Done ({len(complete)})"])

        with hw_tabs[0]:
            if not incomplete:
                st.info("No open homework.")
            for i, item in enumerate(incomplete):
                with st.container(border=True):
                    priority_color = {"High": "🔴", "Medium": "🟡", "Low": "🟢"}.get(item["priority"], "")
                    st.markdown(f"{priority_color} **{item['title']}**")
                    st.caption(f"{item['subject']} · Due {item['due_date']}")
                    if item["details"]:
                        st.write(item["details"])
                    c_done, c_del = st.columns(2)
                    with c_done:
                        if st.button("Mark done", key=f"done_{i}"):
                            homework[homework.index(item)]["done"] = True
                            save_json(HOMEWORK_FILE, homework)
                            st.rerun()
                    with c_del:
                        if st.button("Delete", key=f"del_{i}"):
                            homework.remove(item)
                            save_json(HOMEWORK_FILE, homework)
                            st.rerun()

        with hw_tabs[1]:
            if not complete:
                st.info("Nothing done yet.")
            for i, item in enumerate(complete):
                with st.container(border=True):
                    st.markdown(f"~~{item['title']}~~")
                    st.caption(f"{item['subject']} · {item['due_date']}")
                    if st.button("Remove", key=f"rm_{i}"):
                        homework.remove(item)
                        save_json(HOMEWORK_FILE, homework)
                        st.rerun()

st.markdown("---")
st.caption("BGS Portal · Fill in your timetable via Edit tab · Add more links via the link editor")
