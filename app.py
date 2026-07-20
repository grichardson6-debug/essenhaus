import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import os
import smtplib
from email.message import EmailMessage

# 1. Page Configuration
st.set_page_config(page_title="Essen Haus & CBI Roster Pro", page_icon="🍺", layout="wide")

# --- GLOBAL CONFIGURATION ---
DB_PATH = "essenhaus.db"

ROLE_WAGES = {
    "Server": 6.00,
    "Bartender": 8.00,
    "Host": 14.00,
    "Expo": 14.00,
    "CBI CL Server": 7.00,
    "VB Ref": 80.00,
    "Manager": 22.00
}

CLOCK_TIMES = ["Off", "11:00 AM", "11:30 AM", "12:00 PM", "2:00 PM", "3:30 PM", "4:00 PM", "4:30 PM", "5:00 PM", "5:30 PM", "6:00 PM", "8:00 PM"]

days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def get_monday_of_week(date_obj):
    return date_obj - timedelta(days=date_obj.weekday())


# --- DATABASE SETUP ---
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            employee TEXT PRIMARY KEY,
            pin TEXT,
            is_manager INTEGER,
            wage REAL,
            phone TEXT,
            email TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS schedule (
            week_start TEXT,
            employee TEXT,
            day TEXT,
            role TEXT,
            type TEXT,
            hours REAL,
            location TEXT,
            PRIMARY KEY (week_start, employee, day)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS availability (
            employee TEXT,
            day TEXT,
            request_type TEXT,
            specific_date TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS trade_board (
            id TEXT PRIMARY KEY,
            week_start TEXT,
            employee TEXT,
            day TEXT,
            details TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS week_status (
            week_start TEXT PRIMARY KEY,
            published INTEGER
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee TEXT,
            timestamp TEXT,
            message TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS trade_comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_id TEXT,
            employee TEXT,
            timestamp TEXT,
            comment TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    conn.commit()

    # Seed base users only if table is empty
    c.execute("SELECT COUNT(*) FROM users")
    if c.fetchone()[0] == 0:
        base_users = [
            ("Tim", "4321", 1, 22.00, "", "tim@example.com"),
            ("Grace", "1234", 0, 6.00, "", ""),
            ("Gracie", "1234", 0, 14.00, "", "")
        ]
        c.executemany("INSERT INTO users (employee, pin, is_manager, wage, phone, email) VALUES (?, ?, ?, ?, ?, ?)", base_users)
        conn.commit()
    conn.close()


init_db()


# --- DATA READ/WRITE HELPERS ---
def read_table(table_name):
    conn = get_conn()
    df = pd.read_sql_query(f"SELECT * FROM {table_name}", conn)
    conn.close()
    return df


def load_all_data():
    return (read_table("users"), read_table("schedule"), read_table("availability"), read_table("trade_board"),
            read_table("week_status"), read_table("messages"), read_table("trade_comments"))


def upsert_schedule_row(week_start, employee, day, role, type_, hours, location):
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM schedule WHERE week_start=? AND employee=? AND day=?", (week_start, employee, day))
    c.execute("INSERT INTO schedule (week_start, employee, day, role, type, hours, location) VALUES (?, ?, ?, ?, ?, ?, ?)",
              (week_start, employee, day, role, type_, hours, location))
    conn.commit()
    conn.close()


def delete_schedule_row(week_start, employee, day):
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM schedule WHERE week_start=? AND employee=? AND day=?", (week_start, employee, day))
    conn.commit()
    conn.close()


def add_availability_row(employee, day, request_type, specific_date):
    conn = get_conn()
    c = conn.cursor()
    if specific_date:
        c.execute("DELETE FROM availability WHERE employee=? AND specific_date=?", (employee, specific_date))
    else:
        c.execute("DELETE FROM availability WHERE employee=? AND day=? AND (specific_date IS NULL OR specific_date='')", (employee, day))
    c.execute("INSERT INTO availability (employee, day, request_type, specific_date) VALUES (?, ?, ?, ?)",
              (employee, day, request_type, specific_date))
    conn.commit()
    conn.close()


def add_trade_row(new_id, week_start, employee, day, details):
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT INTO trade_board (id, week_start, employee, day, details) VALUES (?, ?, ?, ?, ?)",
              (new_id, week_start, employee, day, details))
    conn.commit()
    conn.close()


def remove_trade_row(trade_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM trade_board WHERE id=?", (trade_id,))
    c.execute("DELETE FROM trade_comments WHERE trade_id=?", (trade_id,))
    conn.commit()
    conn.close()


def set_week_status(week_start, published):
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM week_status WHERE week_start=?", (week_start,))
    c.execute("INSERT INTO week_status (week_start, published) VALUES (?, ?)", (week_start, published))
    conn.commit()
    conn.close()


def add_new_employee(name, pin, is_manager, wage, phone, email):
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO users (employee, pin, is_manager, wage, phone, email) VALUES (?, ?, ?, ?, ?, ?)",
              (name, pin, 1 if is_manager else 0, wage, phone, email))
    conn.commit()
    conn.close()


def add_message(employee, message):
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT INTO messages (employee, timestamp, message) VALUES (?, ?, ?)",
              (employee, datetime.now().strftime("%Y-%m-%d %I:%M %p"), message))
    conn.commit()
    conn.close()


def add_trade_comment(trade_id, employee, comment):
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT INTO trade_comments (trade_id, employee, timestamp, comment) VALUES (?, ?, ?, ?)",
              (trade_id, employee, datetime.now().strftime("%Y-%m-%d %I:%M %p"), comment))
    conn.commit()
    conn.close()


def get_settings():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT key, value FROM settings")
    rows = c.fetchall()
    conn.close()
    return {r["key"]: r["value"] for r in rows}


def save_setting(key, value):
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()


def send_schedule_emails(week_string, schedule_matrix, employee_directory):
    settings = get_settings()
    server = settings.get("smtp_server", "").strip()
    port = settings.get("smtp_port", "").strip()
    user = settings.get("smtp_user", "").strip()
    password = settings.get("smtp_password", "")
    from_name = settings.get("from_name", "Essen Haus Scheduling").strip() or "Essen Haus Scheduling"

    if not (server and port and user and password):
        return 0, ["Email settings are not configured. Go to Manager Hub > Email Settings."]

    try:
        smtp_conn = smtplib.SMTP(server, int(port), timeout=15)
        smtp_conn.starttls()
        smtp_conn.login(user, password)
    except Exception as e:
        return 0, [f"Could not connect to email server: {e}"]

    sent = 0
    failed = []
    for emp, meta in employee_directory.items():
        to_email = meta.get("email", "").strip()
        if not to_email:
            continue

        lines = [f"Hi {emp}, your schedule for the week of {week_string} is now live:", ""]
        has_shift = False
        for d in days:
            s = schedule_matrix.get(emp, {}).get(d)
            if s and s["type"] != "Off":
                has_shift = True
                lines.append(f"  {d}: {s['role']} @ {s['type']} ({s['location']})")
        if not has_shift:
            lines.append("  You are not scheduled to work this week.")
        body = "\n".join(lines)

        msg = EmailMessage()
        msg["Subject"] = f"Your Schedule: Week of {week_string}"
        msg["From"] = f"{from_name} <{user}>"
        msg["To"] = to_email
        msg.set_content(body)

        try:
            smtp_conn.send_message(msg)
            sent += 1
        except Exception as e:
            failed.append(f"{emp}: {e}")

    smtp_conn.quit()
    return sent, failed


# Hydrate views
users_df, sched_df, avail_df, trade_df, status_df, messages_df, trade_comments_df = load_all_data()


def normalize_pin(raw_pin):
    if pd.isna(raw_pin):
        return ""
    if isinstance(raw_pin, float):
        return str(int(raw_pin))
    return str(raw_pin).strip()


employee_directory = {}
for _, row in users_df.iterrows():
    employee_directory[str(row["employee"])] = {
        "pin": normalize_pin(row["pin"]),
        "is_manager": bool(int(row["is_manager"])),
        "wage": float(row["wage"]),
        "phone": str(row["phone"]) if pd.notna(row["phone"]) else "",
        "email": str(row["email"]) if pd.notna(row["email"]) else ""
    }
current_db_employees = list(employee_directory.keys())

st.sidebar.title("Security Access")
if "authenticated" not in st.session_state:
    st.session_state.authenticated, st.session_state.user_profile, st.session_state.is_manager = False, None, False

if not st.session_state.authenticated:
    login_user = st.sidebar.selectbox("Select Your Profile:", current_db_employees)
    login_pin = st.sidebar.text_input("Enter PIN:", type="password")
    if st.sidebar.button("Log In", type="primary"):
        meta = employee_directory.get(login_user, {})
        if meta and meta["pin"] == login_pin.strip():
            st.session_state.authenticated, st.session_state.user_profile, st.session_state.is_manager = True, login_user, meta["is_manager"]
            st.rerun()
        else:
            st.sidebar.error("Invalid PIN")
else:
    st.sidebar.write(f"Logged in: **{st.session_state.user_profile}**")
    if st.sidebar.button("Log Out"):
        st.session_state.authenticated = False
        st.rerun()

    chosen_date = st.sidebar.date_input("Calendar Week:", datetime.today())
    monday_date = get_monday_of_week(chosen_date)
    week_string = monday_date.strftime("%Y-%m-%d")

    week_is_live = False
    if not status_df.empty and "week_start" in status_df.columns:
        match = status_df[status_df["week_start"] == week_string]
        if not match.empty:
            week_is_live = bool(int(match.iloc[0]["published"]))

    schedule_matrix = {emp: {day: {"role": "None", "type": "Off", "hours": 0.0, "location": "Essen Haus"} for day in days} for emp in current_db_employees}

    if not sched_df.empty:
        filtered_sched = sched_df[sched_df["week_start"] == week_string]
        for _, r_row in filtered_sched.iterrows():
            emp_name = str(r_row["employee"])
            d_name = str(r_row["day"])
            if emp_name in schedule_matrix and d_name in schedule_matrix[emp_name]:
                schedule_matrix[emp_name][d_name] = {
                    "role": str(r_row["role"]),
                    "type": str(r_row["type"]),
                    "hours": float(r_row["hours"]),
                    "location": str(r_row["location"]) if pd.notna(r_row["location"]) else "Essen Haus"
                }

    availability_matrix = {emp: {} for emp in current_db_employees}
    if not avail_df.empty:
        week_end_date = monday_date + timedelta(days=6)
        for _, a_row in avail_df.iterrows():
            emp_name = str(a_row["employee"])
            if emp_name not in availability_matrix:
                continue
            req_type = str(a_row["request_type"])
            specific_date_str = str(a_row.get("specific_date", "")).strip()
            if specific_date_str and specific_date_str.lower() != "nan" and specific_date_str.lower() != "none":
                try:
                    req_date = datetime.strptime(specific_date_str, "%Y-%m-%d").date()
                except ValueError:
                    continue
                if monday_date <= req_date <= week_end_date:
                    availability_matrix[emp_name][str(a_row["day"])] = req_type
            else:
                availability_matrix[emp_name][str(a_row["day"])] = req_type

    up_for_grabs = []
    if not trade_df.empty:
        filtered_trade = trade_df[trade_df["week_start"] == week_string]
        for _, t_row in filtered_trade.iterrows():
            up_for_grabs.append({
                "id": str(t_row["id"]), "employee": str(t_row["employee"]), "day": str(t_row["day"]), "details": str(t_row["details"])
            })

    nav_options = ["Server Portal"]
    if st.session_state.is_manager:
        nav_options.append("Manager Hub")
    app_mode = st.sidebar.radio("Go To View:", nav_options)

    # --- SERVER PORTAL ---
    if app_mode == "Server Portal":
        u = st.session_state.user_profile
        tab1, tab_directory, tab_messages, tab2, tab3 = st.tabs(
            ["Schedule View", "Team Directory", "Message Board", "Request Time Off", "Shift Trade Board"]
        )

        with tab1:
            if not week_is_live and not st.session_state.is_manager:
                st.info("The manager hasn't published this schedule yet.")
            else:
                view_mode = st.radio("Display Filter:", ["Show Just My Personal Schedule", "Show Full Team Floor Plan"], horizontal=True)

                if view_mode == "Show Just My Personal Schedule":
                    st.write("### Your Shifts for the Week")
                    cols = st.columns(7)
                    for idx, d_day in enumerate(days):
                        with cols[idx]:
                            st.markdown(f"##### {d_day[:3]}")
                            s = schedule_matrix[u][d_day]
                            is_dropped = any(t['employee'] == u and t['day'] == d_day for t in up_for_grabs)

                            if s["type"] != "Off":
                                drop_suffix = " (Pending Trade)" if is_dropped else ""
                                st.success(f"**{s['location']}**\n\n{s['role']}\n\nShift: {s['type']}{drop_suffix}")
                                if not is_dropped:
                                    if st.button("Drop Shift", key=f"p_drop_{d_day}"):
                                        new_id = f"{week_string}_{u}_{d_day}_{datetime.now().timestamp()}"
                                        add_trade_row(new_id, week_string, u, d_day, f"[{s['location']}] {s['role']} @ {s['type']}")
                                        st.toast("Shift listed on Trade Board.")
                                        st.rerun()
                                else:
                                    st.caption("Listed on Trade Board")
                                    my_trade = next((t for t in up_for_grabs if t['employee'] == u and t['day'] == d_day), None)
                                    if my_trade and st.button("Cancel Drop", key=f"p_cancel_{d_day}"):
                                        remove_trade_row(my_trade["id"])
                                        st.toast("Drop cancelled — shift is back on your schedule.")
                                        st.rerun()
                            else:
                                st.markdown("<p style='color:gray; font-size:13px;'>Off</p>", unsafe_allow_html=True)
                else:
                    view_day = st.selectbox("Select Day to View Floor Map:", days)
                    st.write(f"### 📋 Floor Configuration for {view_day}")

                    day_shifts = []
                    for emp in current_db_employees:
                        s = schedule_matrix[emp][view_day]
                        if s["type"] != "Off":
                            meta = employee_directory.get(emp, {})
                            is_dropped = any(t['employee'] == emp and t['day'] == view_day for t in up_for_grabs)
                            day_shifts.append({
                                "emp": emp, "role": s["role"], "time": s["type"], "location": s["location"],
                                "phone": meta.get("phone", ""), "email": meta.get("email", ""), "is_dropped": is_dropped
                            })

                    col_eh, col_cbi = st.columns(2)

                    def render_roster_column(venue_name, icon, current_shifts):
                        st.markdown(f"#### {icon} {venue_name}")
                        venue_shifts = [x for x in current_shifts if x["location"] == venue_name]
                        if not venue_shifts:
                            st.caption(f"No floor shifts logged for {venue_name.split(' ')[0]}.")
                            return

                        venue_shifts.sort(key=lambda x: CLOCK_TIMES.index(x["time"]) if x["time"] in CLOCK_TIMES else 99)

                        for s in venue_shifts:
                            st.info(f"**{s['role']}** - {s['emp']} @ {s['time']}")

                            contact_links = []
                            if s["phone"]:
                                contact_links.append(f"📞 💬 [Text](sms:{s['phone']})")
                            if s["email"]:
                                contact_links.append(f"📧 [Mail](mailto:{s['email']})")

                            if s["emp"] != u:
                                if contact_links:
                                    st.markdown(" | ".join(contact_links))
                            else:
                                if not s["is_dropped"]:
                                    if st.button(f"🔴 Drop My Shift: {s['role']} - {s['emp']} @ {s['time']}", key=f"inline_drop_{venue_name}_{s['role']}_{s['emp']}"):
                                        new_id = f"{week_string}_{u}_{view_day}_{datetime.now().timestamp()}"
                                        add_trade_row(new_id, week_string, u, view_day, f"[{s['location']}] {s['role']} @ {s['time']}")
                                        st.toast("Shift listed on Trade Board.")
                                        st.rerun()
                                else:
                                    st.warning("Shift drop pending...")
                                    my_trade = next((t for t in up_for_grabs if t['employee'] == s['emp'] and t['day'] == view_day), None)
                                    if my_trade and st.button("Cancel Drop", key=f"inline_cancel_{venue_name}_{s['role']}_{s['emp']}"):
                                        remove_trade_row(my_trade["id"])
                                        st.toast("Drop cancelled — shift is back on your schedule.")
                                        st.rerun()

                    with col_eh:
                        render_roster_column("Essen Haus", "🏰", day_shifts)
                    with col_cbi:
                        render_roster_column("CBI Side", "🌭", day_shifts)

        with tab_directory:
            st.subheader("Team Directory")
            st.caption("Contact info for the whole crew.")
            for emp in current_db_employees:
                meta = employee_directory.get(emp, {})
                with st.container(border=True):
                    c1, c2 = st.columns([2, 3])
                    c1.markdown(f"**{emp}**" + (" 👑" if meta.get("is_manager") else ""))
                    contacts = []
                    if meta.get("phone"):
                        contacts.append(f"📞 [{meta['phone']}](tel:{meta['phone']})")
                    if meta.get("email"):
                        contacts.append(f"📧 [{meta['email']}](mailto:{meta['email']})")
                    c2.markdown(" &nbsp;|&nbsp; ".join(contacts) if contacts else "_No contact info on file_")

        with tab_messages:
            st.subheader("Team Message Board")
            with st.form("new_message_form", clear_on_submit=True):
                msg_text = st.text_area("Post a message to the team:", height=80)
                if st.form_submit_button("Post Message", type="primary"):
                    if msg_text.strip():
                        add_message(u, msg_text.strip())
                        st.rerun()
            st.divider()
            if not messages_df.empty:
                for _, m in messages_df.sort_values("id", ascending=False).iterrows():
                    with st.container(border=True):
                        st.markdown(f"**{m['employee']}** · _{m['timestamp']}_")
                        st.write(m["message"])
            else:
                st.caption("No messages yet. Be the first to post!")

        with tab2:
            st.subheader("Submit Availability / Time-Off")
            duration_type = st.radio("Duration Style:", ["Permanent (Recurring Rule)", "Temporary (Single Date)"], horizontal=True)

            if duration_type == "Permanent (Recurring Rule)":
                st.write("Select the day(s) you're permanently unavailable:")
                checked_days = []
                cols = st.columns(7)
                for i, d in enumerate(days):
                    if cols[i].checkbox(d[:3], key=f"perm_{d}"):
                        checked_days.append(d)

                perm_window = st.radio("Which shift(s) on those days?", ["Morning", "Evening", "Full Day"], horizontal=True)

                if st.button("Submit Request", type="primary"):
                    if not checked_days:
                        st.warning("Select at least one day.")
                    else:
                        for d in checked_days:
                            add_availability_row(u, d, f"Permanent Block: {perm_window}", "")
                        st.success("Availability saved!")
                        st.rerun()

            else:
                req_date = st.date_input("Select the specific date:", datetime.today())
                window = st.radio("Window:", ["Morning Shift", "Evening Shift", "Full Day"], horizontal=True)
                req_day = req_date.strftime("%A")
                st.caption(f"This falls on a **{req_day}**.")

                if st.button("Submit Request", type="primary"):
                    date_str = req_date.strftime("%Y-%m-%d")
                    add_availability_row(u, req_day, f"Temp: {window}", date_str)
                    st.success("Availability saved!")
                    st.rerun()

        with tab3:
            st.subheader("Shift Trade Board")

            def render_trade_comments(trade_id):
                comments = trade_comments_df[trade_comments_df["trade_id"] == trade_id] if not trade_comments_df.empty else pd.DataFrame()
                for _, cm in comments.iterrows():
                    st.caption(f"💬 **{cm['employee']}** ({cm['timestamp']}): {cm['comment']}")
                cc1, cc2 = st.columns([4, 1])
                new_comment = cc1.text_input("Add a comment", key=f"comment_{trade_id}", label_visibility="collapsed", placeholder="Add a comment...")
                if cc2.button("Comment", key=f"comment_btn_{trade_id}"):
                    if new_comment.strip():
                        add_trade_comment(trade_id, u, new_comment.strip())
                        st.rerun()

            st.markdown("#### Your Posted Shifts")
            my_trades = [t for t in up_for_grabs if t["employee"] == u]
            if my_trades:
                for t in my_trades:
                    with st.container(border=True):
                        st.write(f"You listed **{t['day']}**: `{t['details']}`")
                        render_trade_comments(t["id"])
                        if st.button("↩️ Cancel Drop (Keep My Shift)", key=f"cancel_{t['id']}", type="primary"):
                            remove_trade_row(t["id"])
                            st.toast("Drop cancelled — shift is back on your schedule.")
                            st.rerun()
            else:
                st.caption("You haven't listed any shifts on the board.")

            st.divider()
            st.markdown("#### Available From Others")
            open_trades = [t for t in up_for_grabs if t["employee"] != u]
            if open_trades:
                for t in open_trades:
                    with st.container(border=True):
                        c_text, c_act = st.columns([4, 1])
                        c_text.write(f"Employee: **{t['employee']}** wishes to drop **{t['day']}** | Context: `{t['details']}`")
                        render_trade_comments(t["id"])
                        if c_act.button("Claim Shift", key=f"claim_{t['id']}", type="primary"):
                            match = sched_df[(sched_df["week_start"] == week_string) & (sched_df["employee"] == t["employee"]) & (sched_df["day"] == t["day"])]
                            if not match.empty:
                                orig_row = match.iloc[0]
                                delete_schedule_row(week_string, t["employee"], t["day"])
                                delete_schedule_row(week_string, u, t["day"])
                                upsert_schedule_row(week_string, u, t["day"], orig_row["role"], orig_row["type"], orig_row["hours"], orig_row["location"])
                                remove_trade_row(t["id"])
                                st.success("Shift claimed!")
                                st.rerun()
            else:
                st.caption("No open drops currently on the board.")

    # --- MANAGER HUB ---
    elif app_mode == "Manager Hub":
        m_tab1, m_tab2, m_tab3 = st.tabs(["Roster Grid Engine", "Staff Directory", "Email Settings"])
        with m_tab1:
            if "last_email_report" in st.session_state:
                rep = st.session_state.last_email_report
                with st.expander(f"📧 Last Email Send Report — {rep['sent']} sent, {len(rep['failed'])} failed", expanded=bool(rep["failed"])):
                    if rep["failed"]:
                        for f in rep["failed"]:
                            st.error(f)
                    else:
                        st.success("All emails delivered successfully.")

            tool_c1, tool_c2, tool_c3 = st.columns([2, 2, 3])
            notify_team = tool_c1.checkbox("📧 Email team on publish", value=True)
            if week_is_live:
                tool_c2.markdown("<h3 style='color:#10b981; margin:0;'>Published</h3>", unsafe_allow_html=True)
                if tool_c3.button("Unpublish Schedule"):
                    set_week_status(week_string, 0)
                    st.rerun()
            else:
                tool_c2.markdown("<h3 style='color:#f59e0b; margin:0;'>Draft Mode</h3>", unsafe_allow_html=True)
                if tool_c3.button("Publish Schedule to Team", type="primary"):
                    set_week_status(week_string, 1)
                    if notify_team:
                        sent, fail_list = send_schedule_emails(week_string, schedule_matrix, employee_directory)
                        st.session_state.last_email_report = {"sent": sent, "failed": fail_list}
                        st.toast(f"Published! Emails: {sent} sent" + (f", {len(fail_list)} failed." if fail_list else "."))
                    st.rerun()

            st.divider()
            st.markdown(
                "<div style='font-size:13px; color:gray;'>🟢 Scheduled &nbsp;|&nbsp; 🔴 Permanent Block &nbsp;|&nbsp; "
                "🟠 Temp Conflict &nbsp;|&nbsp; 🔵 Drop Pending &nbsp;|&nbsp; ⚪ Open</div>",
                unsafe_allow_html=True
            )
            header_cols = st.columns([2.2] + [1.4] * 7 + [1.6])
            header_cols[0].write("**Employee**")
            for i, d in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]):
                header_cols[i + 1].write(f"**{d}**")
            header_cols[-1].write("**Total**")

            for emp in current_db_employees:
                row_cols = st.columns([2.2] + [1.4] * 7 + [1.6])
                row_cols[0].markdown(f"**{emp}**")
                tot_hours = 0.0
                for i, d in enumerate(days):
                    s = schedule_matrix[emp][d]
                    has_request = availability_matrix.get(emp, {}).get(d)
                    is_dropped = any(t['employee'] == emp and t['day'] == d for t in up_for_grabs)
                    btn_type = "secondary"

                    if has_request:
                        if "Permanent" in has_request:
                            window = has_request.split(":")[-1].strip() if ":" in has_request else "Full Day"
                            tag = {"Morning": "AM", "Evening": "PM"}.get(window, "ALL")
                            label = f"🔴 PERM-{tag}"
                        else:
                            label = f"🟠 {has_request.replace('Temp: ', '')}"
                    elif s["type"] != "Off":
                        pfx = "EH" if s["location"] == "Essen Haus" else "CBI"
                        dot = "🔵" if is_dropped else "🟢"
                        label = f"{dot} [{pfx}] {s['role']}\nShift: {s['type']}"
                        if is_dropped:
                            label += "\nDROP REQ"
                        btn_type = "primary"
                    else:
                        label = "⚪ +"

                    if row_cols[i + 1].button(label, key=f"m_{emp}_{d}", type=btn_type):
                        st.session_state.sel = {"emp": emp, "day": d}
                        st.rerun()
                    tot_hours += s["hours"]
                row_cols[-1].metric("", f"{tot_hours}h", label_visibility="collapsed")

            if "sel" in st.session_state:
                e, d = st.session_state.sel["emp"], st.session_state.sel["day"]
                st.divider()
                st.subheader(f"Shift Editor: {e} on {d}")
                conflict = availability_matrix.get(e, {}).get(d)
                if conflict:
                    st.warning(f"⚠️ {e} has a time-off request for {d}: **{conflict}**")
                c1, c2, c3, c4 = st.columns(4)
                loc_choice = c1.selectbox("Venue Location", ["Essen Haus", "CBI Side"])
                r = c2.selectbox("Role", ["Server", "Bartender", "Host", "Expo", "CBI CL Server", "Manager"])
                t = c3.selectbox("Start Time", CLOCK_TIMES)
                h = c4.number_input("Hours", value=6.0 if t != "Off" else 0.0, step=0.5)

                col_save, col_close = st.columns([1, 5])
                if col_save.button("Save Assignment", type="primary"):
                    upsert_schedule_row(week_string, e, d, r if t != "Off" else "None", t, h, loc_choice)
                    conn = get_conn()
                    c = conn.cursor()
                    c.execute("DELETE FROM trade_board WHERE week_start=? AND employee=? AND day=?", (week_string, e, d))
                    conn.commit()
                    conn.close()
                    del st.session_state.sel
                    st.rerun()
                if col_close.button("Cancel"):
                    del st.session_state.sel
                    st.rerun()

        with m_tab2:
            st.subheader("Staff Directory")
            with st.form("new_emp"):
                n = st.text_input("Name")
                p = st.text_input("4-Digit PIN", max_chars=4)
                ph = st.text_input("Phone Number")
                em = st.text_input("Email Address")
                m = st.checkbox("Grant Manager Privileges?")
                if st.form_submit_button("Hire Team Member"):
                    if n and p:
                        add_new_employee(n, p, m, 20.00, ph, em)
                        st.success("Employee hired!")
                        st.rerun()

        with m_tab3:
            st.subheader("Email Notification Settings")
            st.caption(
                "Configure the outgoing email account used to send published schedules to the team. "
                "For Gmail, use an App Password (not your normal password) generated at myaccount.google.com/apppasswords."
            )
            current_settings = get_settings()
            with st.form("email_settings_form"):
                s_server = st.text_input("SMTP Server", value=current_settings.get("smtp_server", "smtp.gmail.com"))
                s_port = st.text_input("SMTP Port", value=current_settings.get("smtp_port", "587"))
                s_user = st.text_input("Sender Email Address", value=current_settings.get("smtp_user", ""))
                s_pass = st.text_input("Sender Password / App Password", value=current_settings.get("smtp_password", ""), type="password")
                s_name = st.text_input("Display Name", value=current_settings.get("from_name", "Essen Haus Scheduling"))
                if st.form_submit_button("Save Email Settings", type="primary"):
                    save_setting("smtp_server", s_server.strip())
                    save_setting("smtp_port", s_port.strip())
                    save_setting("smtp_user", s_user.strip())
                    save_setting("smtp_password", s_pass)
                    save_setting("from_name", s_name.strip())
                    st.success("Email settings saved.")
                    st.rerun()
