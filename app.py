import streamlit as st
import sqlite3
import smtplib
from email.mime.text import MIMEText
import streamlit.components.v1 as components
from datetime import datetime, timedelta

# 1. Page Configuration
st.set_page_config(page_title="Essen Haus & CBI Roster Pro", page_icon="🍺", layout="wide")

DB_FILE = "scheduler.db"

# --- GLOBAL CONFIGURATION ---
ROLE_WAGES = {
    "Server": 6.00,
    "Bartender": 8.00,
    "Host": 14.00,
    "Expo": 14.00,
    "VB Ref": 80.00,
    "Manager": 22.00
}

CLOCK_TIMES = ["Off", "11:00 AM", "11:30 AM", "12:00 PM", "2:00 PM", "3:30 PM", "4:00 PM", "4:30 PM", "5:00 PM", "5:30 PM", "6:00 PM", "8:00 PM"]

# --- OUTBOUND EMAIL SMTP DETAILS ---
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = st.secrets.get("sender_email", "your-restaurant-email@gmail.com")
SENDER_PASSWORD = st.secrets.get("sender_password", "your-gmail-app-password")

def inject_native_styles():
    st.markdown("""
        <style>
        div.stButton > button {
            width: 100% !important;
            white-space: normal !important;
            word-wrap: break-word !important;
            padding: 0.6rem 0.2rem !important;
            font-size: 13px !important;
            font-weight: 600 !important;
            line-height: 1.3 !important;
            height: auto !important;
            min-height: 55px !important;
            border-radius: 8px !important;
            transition: all 0.15s ease-in-out !important;
        }
        div.stButton > button p { color: #ffffff !important; font-weight: 700 !important; }
        div.stButton > button:hover { filter: brightness(1.15) !important; transform: translateY(-2px) !important; }
        
        .roster-section {
            background-color: #1e293b;
            border-radius: 8px;
            padding: 16px;
            margin-bottom: 16px;
            border: 1px solid #334155;
        }
        .roster-role-header {
            font-size: 16px;
            font-weight: 700;
            color: #f8fafc;
            border-bottom: 2px solid #475569;
            padding-bottom: 6px;
            margin-bottom: 12px;
        }
        .roster-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 6px 0;
            border-bottom: 1px solid #334155;
        }
        .roster-row:last-child {
            border-bottom: none;
        }
        .roster-emp-name {
            font-size: 14px;
            color: #3b82f6;
            font-weight: 500;
        }
        .roster-time {
            font-size: 14px;
            color: #94a3b8;
        }
        .roster-pending-tag {
            font-size: 12px;
            color: #f59e0b;
            font-weight: 600;
            font-style: italic;
            margin-left: 6px;
        }
        .roster-links a {
            font-size: 12px;
            color: #94a3b8 !important;
            text-decoration: none;
            margin-left: 8px;
        }
        .roster-links a:hover {
            color: #f8fafc !important;
        }
        </style>
    """, unsafe_allow_html=True)

def inject_color_scripts():
    components.html("""
    <script>
    function colorizeButtons() {
        const buttons = window.parent.document.querySelectorAll('div.stButton > button');
        buttons.forEach(btn => {
            const text = btn.innerText;
            if (text.includes('Server')) { btn.style.backgroundColor = '#10b981'; btn.style.borderColor = '#10b981'; }
            else if (text.includes('Bartender')) { btn.style.backgroundColor = '#3b82f6'; btn.style.borderColor = '#3b82f6'; }
            else if (text.includes('Host') || text.includes('Ref')) { btn.style.backgroundColor = '#a855f7'; btn.style.borderColor = '#a855f7'; }
            else if (text.includes('Expo')) { btn.style.backgroundColor = '#f59e0b'; btn.style.borderColor = '#f59e0b'; }
            else if (text.includes('Manager')) { btn.style.backgroundColor = '#475569'; btn.style.borderColor = '#475569'; }
            else if (text.includes('+')) { btn.style.backgroundColor = '#1e293b'; btn.style.borderColor = '#334155'; btn.style.borderStyle = 'dashed'; }
        });
    }
    colorizeButtons();
    new MutationObserver(colorizeButtons).observe(window.parent.document.body, { childList: true, subtree: true });
    </script>
    """, height=0, width=0)

def get_monday_of_week(date_obj):
    return date_obj - timedelta(days=date_obj.weekday())

def init_db():
    conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS schedule (week_start TEXT, employee TEXT, day TEXT, role TEXT, type TEXT, hours REAL, location TEXT DEFAULT "Essen Haus", PRIMARY KEY (week_start, employee, day))')
    cursor.execute('CREATE TABLE IF NOT EXISTS availability (employee TEXT, day TEXT, request_type TEXT, PRIMARY KEY (employee, day))')
    cursor.execute('CREATE TABLE IF NOT EXISTS trade_board (id INTEGER PRIMARY KEY AUTOINCREMENT, week_start TEXT, employee TEXT, day TEXT, details TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS week_status (week_start TEXT PRIMARY KEY, published INTEGER DEFAULT 0)')
    cursor.execute('CREATE TABLE IF NOT EXISTS users (employee TEXT PRIMARY KEY, pin TEXT, is_manager INTEGER DEFAULT 0, wage REAL DEFAULT 20.00, phone TEXT DEFAULT "", email TEXT DEFAULT "")')
    
    # Pre-seed initial employees if table is empty
    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] == 0:
        # Inserting default employees. Standard users have 1234, Tim (Manager) has 4321
        cursor.execute("INSERT INTO users VALUES (?,?,?,?,?,?)", ("Grace", "1234", 0, 6.00, "123-456-7890", "grace@example.com"))
        cursor.execute("INSERT INTO users VALUES (?,?,?,?,?,?)", ("Gracie", "1234", 0, 14.00, "123-456-7891", "gracie@example.com"))
        cursor.execute("INSERT INTO users VALUES (?,?,?,?,?,?)", ("Tim", "4321", 1, 22.00, "123-456-7892", "tim@example.com"))
    
    conn.commit(); conn.close()

# --- CACHED READS FOR HIGH PERFORMANCE ---
@st.cache_data(ttl=60)
def get_all_employees_with_wages():
    conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
    cursor.execute("SELECT employee, wage, is_manager, phone, email FROM users")
    rows = cursor.fetchall(); conn.close()
    return {r[0]: {"wage": r[1], "is_manager": bool(r[2]), "phone": r[3] or "", "email": r[4] or ""} for r in rows}

@st.cache_data(ttl=10)
def is_week_published(week_str):
    conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
    cursor.execute("SELECT published FROM week_status WHERE week_start=?", (week_str,))
    res = cursor.fetchone(); conn.close()
    return bool(res[0]) if res else False

@st.cache_data(ttl=5)
def load_week_data(week_str, employees_list_tuple):
    conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    cursor.execute("SELECT employee, day, role, type, hours, location FROM schedule WHERE week_start=?", (week_str,))
    rows = cursor.fetchall()
    
    schedule_dict = {emp: {day: {"role": "None", "type": "Off", "hours": 0.0, "location": "Essen Haus"} for day in days} for emp in employees_list_tuple}
    for emp, day, role, shift_time, hours, loc in rows:
        if emp in schedule_dict and day in schedule_dict[emp]:
            schedule_dict[emp][day] = {"role": role, "type": shift_time, "hours": hours, "location": loc or "Essen Haus"}
            
    cursor.execute("SELECT employee, day, request_type FROM availability")
    avail_dict = {emp: {} for emp in employees_list_tuple}
    for emp, day, req in cursor.fetchall():
        if emp in avail_dict: avail_dict[emp][day] = req
            
    cursor.execute("SELECT id, employee, day, details FROM trade_board WHERE week_start=?", (week_str,))
    trade_list = [{"id": r[0], "employee": r[1], "day": r[2], "details": r[3]} for r in cursor.fetchall()]
    conn.close()
    return schedule_dict, avail_dict, trade_list

def clear_app_caches():
    st.cache_data.clear()

def set_week_publication(week_str, status_int):
    conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO week_status VALUES (?, ?)", (week_str, status_int))
    conn.commit(); conn.close()
    clear_app_caches()

def email_out_weekly_schedule(week_str, schedule_data, employee_meta):
    if not SENDER_EMAIL or SENDER_PASSWORD == "your-gmail-app-password":
        st.warning("SMTP email credentials not configured. Outbound emails skipped.")
        return
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    success_count = 0
    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls(); server.login(SENDER_EMAIL, SENDER_PASSWORD)
        for emp, shifts in schedule_data.items():
            email_addr = employee_meta.get(emp, {}).get("email")
            if not email_addr or "@" not in email_addr: continue
            shift_list_text = ""
            total_hours = 0.0
            for d in days:
                s = shifts[d]
                if s["type"] != "Off":
                    shift_list_text += f"- {d}: {s['location']} - {s['role']} @ {s['type']} ({s['hours']} hrs)\n"
                    total_hours += s["hours"]
                else: shift_list_text += f"- {d}: Off\n"
            body = f"Hello {emp},\n\nYour weekly schedule has been published for {week_str}.\n\n{shift_list_text}\nTotal Hours: {total_hours} hrs\n\nManagement Team"
            msg = MIMEText(body); msg["Subject"] = f"New Schedule - Week of {week_str}"; msg["From"] = SENDER_EMAIL; msg["To"] = email_addr
            server.sendmail(SENDER_EMAIL, email_addr, msg.as_string()); success_count += 1
        server.quit(); st.success(f"Schedule emails dispatched to {success_count} employees.")
    except Exception as e: st.error(f"Failed to dispatch emails: {e}")

@st.dialog("Confirm Shift Drop")
def confirm_drop_dialog(week_string, employee, day, role, shift_time, location):
    st.write(f"Are you sure you want to request to drop your **{location} — {role} @ {shift_time}** shift on **{day}**?")
    st.caption("Your team members will see this shift on the trade pool board, but you remain responsible for covering it until claimed.")
    c1, c2 = st.columns(2)
    if c1.button("Yes, List Shift", type="primary", use_container_width=True):
        conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM trade_board WHERE week_start=? AND employee=? AND day=?", (week_string, employee, day))
        if cursor.fetchone()[0] == 0:
            cursor.execute("INSERT INTO trade_board (week_start, employee, day, details) VALUES (?,?,?,?)", (week_string, employee, day, f"[{location}] {role} @ {shift_time}"))
            conn.commit()
            st.toast("Shift successfully listed on Trade Board.")
        conn.close()
        clear_app_caches()
        st.rerun()
    if c2.button("Cancel", use_container_width=True): st.rerun()

# Run database setup & make sure our core team is registered
init_db()

st.sidebar.title("Security Access")
if "authenticated" not in st.session_state:
    st.session_state.authenticated, st.session_state.user_profile, st.session_state.is_manager = False, None, False

employee_directory = get_all_employees_with_wages()
current_db_employees = list(employee_directory.keys())
current_db_employees_tuple = tuple(current_db_employees)

if not st.session_state.authenticated:
    login_user = st.sidebar.selectbox("Select Your Profile:", current_db_employees)
    login_pin = st.sidebar.text_input("Enter PIN:", type="password")
    if st.sidebar.button("Log In", type="primary"):
        conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
        cursor.execute("SELECT is_manager FROM users WHERE employee=? AND pin=?", (login_user, login_pin))
        res = cursor.fetchone(); conn.close()
        if res:
            st.session_state.authenticated, st.session_state.user_profile, st.session_state.is_manager = True, login_user, bool(res[0])
            clear_app_caches()
            st.rerun()
        else: st.sidebar.error("Invalid PIN")
else:
    inject_native_styles(); inject_color_scripts()
    st.sidebar.write(f"Logged in: **{st.session_state.user_profile}**")
    if st.sidebar.button("Log Out"): st.session_state.authenticated = False; clear_app_caches(); st.rerun()
    
    chosen_date = st.sidebar.date_input("Calendar Week:", datetime.today())
    monday_date = get_monday_of_week(chosen_date)
    week_string = monday_date.strftime("%Y-%m-%d")
    
    st.session_state.schedule, st.session_state.availability_db, st.session_state.up_for_grabs = load_week_data(week_string, current_db_employees_tuple)
    week_is_live = is_week_published(week_string)
    
    nav_options = ["Server Portal"]
    if st.session_state.is_manager: nav_options.append("Manager Hub")
    app_mode = st.sidebar.radio("Go To View:", nav_options)

    # --- SERVER PORTAL ---
    if app_mode == "Server Portal":
        u = st.session_state.user_profile
        st.title(f"Team Portal: {u}")
        tab1, tab2, tab3 = st.tabs(["Schedule View", "Request Time Off", "Shift Trade Board"])
        
        with tab1:
            if not week_is_live and not st.session_state.is_manager:
                st.info("The manager hasn't published this schedule yet.")
            else:
                view_mode = st.radio("Display Filter:", ["Show Full Team Floor Plan", "Show Just My Personal Schedule"], horizontal=True)
                
                if view_mode == "Show Just My Personal Schedule":
                    st.write("### Your Shifts for the Week")
                    cols = st.columns(7)
                    for idx, d_day in enumerate(["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]):
                        with cols[idx]:
                            st.markdown(f"##### {d_day[:3]}")
                            s = st.session_state.schedule[u][d_day]
                            is_dropped = any(t['employee'] == u and t['day'] == d_day for t in st.session_state.up_for_grabs)
                            
                            if s["type"] != "Off":
                                drop_suffix = " (Pending Trade)" if is_dropped else ""
                                st.success(f"**{s['location']}**\n\n{s['role']}\n\nShift: {s['type']}{drop_suffix}")
                                if not is_dropped:
                                    if st.button("Drop Shift", key=f"p_drop_{d_day}"):
                                        confirm_drop_dialog(week_string, u, d_day, s['role'], s['type'], s['location'])
                                else:
                                    st.caption("Listed on Trade Board")
                            else: st.markdown("<p style='color:gray; font-size:13px;'>Off</p>", unsafe_allow_html=True)
                else:
                    view_day = st.selectbox("Select Day to View Floor Map:", ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"])
                    st.write(f"### Floor Configuration for {view_day}")
                    
                    day_shifts = []
                    for emp in current_db_employees:
                        s = st.session_state.schedule[emp][view_day]
                        if s["type"] != "Off":
                            meta = employee_directory.get(emp, {})
                            is_dropped = any(t['employee'] == emp and t['day'] == view_day for t in st.session_state.up_for_grabs)
                            day_shifts.append({
                                "emp": emp,
                                "role": s["role"],
                                "time": s["type"],
                                "location": s["location"],
                                "phone": meta.get("phone", ""),
                                "email": meta.get("email", ""),
                                "is_dropped": is_dropped
                            })
                    
                    col_eh, col_cbi = st.columns(2)
                    
                    def render_roster_column(venue_name, current_shifts):
                        st.markdown(f"#### {venue_name}")
                        venue_shifts = [x for x in current_shifts if x["location"] == venue_name]
                        
                        if not venue_shifts:
                            st.caption(f"No floor shifts logged for {venue_name}.")
                            return
                            
                        roles_present = sorted(list(set([x["role"] for x in venue_shifts])))
                        for role in roles_present:
                            role_shifts = [x for x in venue_shifts if x["role"] == role]
                            role_shifts.sort(key=lambda x: CLOCK_TIMES.index(x["time"]) if x["time"] in CLOCK_TIMES else 99)
                            
                            html_buffer = f"<div class='roster-section'><div class='roster-role-header'>{role} ({len(role_shifts)})</div>"
                            for s in role_shifts:
                                pending_text = "<span class='roster-pending-tag'>(Pending Trade)</span>" if s["is_dropped"] else ""
                                
                                contact_links = ""
                                if s["emp"] != u:
                                    if s["phone"]: contact_links += f"<a href='sms:{s['phone']}'>Text</a>"
                                    if s["email"]: contact_links += f" | <a href='mailto:{s['email']}'>Mail</a>"
                                else:
                                    contact_links += "<span style='font-size:12px; color:#e2e8f0;'>Your Shift</span>"
                                    
                                html_buffer += f"""
                                <div class='roster-row'>
                                    <div>
                                        <span class='roster-emp-name'>{s['emp']}</span>
                                        <span class='roster-time'> {s['time']}</span>
                                        {pending_text}
                                    </div>
                                    <div class='roster-links'>
                                        {contact_links}
                                    </div>
                                </div>
                                """
                            html_buffer += "</div>"
                            st.markdown(html_buffer, unsafe_allow_html=True)
                            
                            for s in role_shifts:
                                if s["emp"] == u and not s["is_dropped"]:
                                    if st.button(f"Request Drop for My {role} Shift", key=f"inline_drop_{venue_name}_{role}"):
                                        confirm_drop_dialog(week_string, u, view_day, s['role'], s['time'], venue_name)

                    with col_eh:
                        render_roster_column("Essen Haus", day_shifts)
                    with col_cbi:
                        render_roster_column("CBI Side", day_shifts)

        with tab2:
            st.subheader("Submit Availability Adjustment / Time-Off")
            c1, c2 = st.columns(2)
            req_day = c1.selectbox("Target Day:", ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"])
            duration_type = c2.selectbox("Request Type Duration:", ["Permanent (Recurring Rule)", "Temporary (Single Date Shift)"])
            
            final_status_string = ""
            if duration_type == "Permanent (Recurring Rule)":
                st.info("This alerts management that you are globally unavailable on this specific day every week.")
                final_status_string = "Permanent Block"
            else:
                shift_window = st.radio("Unavailable For Window:", ["Morning Shift", "Evening Shift"], horizontal=True)
                final_status_string = f"Temp: {shift_window}"
                
            if st.button("Submit Time-Off Request", type="primary"):
                conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
                cursor.execute("INSERT OR REPLACE INTO availability VALUES (?, ?, ?)", (u, req_day, final_status_string))
                conn.commit(); conn.close()
                clear_app_caches()
                st.success("Availability updated successfully!"); st.rerun()

        with tab3:
            st.subheader("Available Trades Pool")
            trades = st.session_state.up_for_grabs
            open_trades = [t for t in trades if t["employee"] != u]
            if open_trades:
                for t in open_trades:
                    with st.container(border=True):
                        c_text, c_act = st.columns([4, 1])
                        c_text.write(f"Employee: **{t['employee']}** wants to drop **{t['day']}** | Context: `{t['details']}`")
                        if c_act.button("Claim Shift", key=f"claim_{t['id']}", type="primary"):
                            conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
                            cursor.execute("SELECT role, type, hours, location FROM schedule WHERE week_start=? AND employee=? AND day=?", (week_string, t["employee"], t["day"]))
                            info = cursor.fetchone()
                            if info:
                                cursor.execute("INSERT OR REPLACE INTO schedule VALUES (?,?,?,?,?,?,?)", (week_string, u, t["day"], info[0], info[1], info[2], info[3]))
                                cursor.execute("INSERT OR REPLACE INTO schedule VALUES (?,?,?,?,?,?,?)", (week_string, t["employee"], t["day"], "None", "Off", 0.0, "Essen Haus"))
                                cursor.execute("DELETE FROM trade_board WHERE id=?", (t["id"],))
                                conn.commit()
                            conn.close()
                            clear_app_caches()
                            st.success("Shift claimed!"); st.rerun()
            else: st.caption("No shifts on the board.")

    # --- MANAGER HUB ---
    elif app_mode == "Manager Hub":
        m_tab1, m_tab2 = st.tabs(["Roster Grid Engine", "Staff Directory"])
        with m_tab1:
            tool_c1, tool_c2, tool_c3 = st.columns([2, 2, 3])
            if week_is_live:
                tool_c2.markdown("<h3 style='color:#10b981; margin:0;'>Published</h3>", unsafe_allow_html=True)
                if tool_c3.button("Unpublish Schedule"): set_week_publication(week_string, 0); st.rerun()
            else:
                tool_c2.markdown("<h3 style='color:#f59e0b; margin:0;'>Draft Mode</h3>", unsafe_allow_html=True)
                if tool_c3.button("Publish Schedule to Team", type="primary"):
                    set_week_publication(week_string, 1)
                    email_out_weekly_schedule(week_string, st.session_state.schedule, employee_directory)
                    st.rerun()
            
            st.divider()
            header_cols = st.columns([2.2] + [1.4] * 7 + [1.6])
            header_cols[0].write("**Employee**")
            for i, d in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]): header_cols[i+1].write(f"**{d}**")
            header_cols[-1].write("**Total**")

            for emp in current_db_employees:
                row_cols = st.columns([2.2] + [1.4] * 7 + [1.6])
                row_cols[0].markdown(f"**{emp}**")
                tot_hours = 0.0
                for i, d in enumerate(["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]):
                    s = st.session_state.schedule[emp][d]
                    has_request = st.session_state.availability_db.get(emp, {}).get(d)
                    is_dropped = any(t['employee'] == emp and t['day'] == d for t in st.session_state.up_for_grabs)
                    
                    if has_request: 
                        if "Permanent" in has_request: label = "PERM\nBLOCK"
                        else: label = f"Conflict: {has_request.replace('Temp: ', '')}"
                    elif s["type"] != "Off":
                        pfx = "EH" if s["location"] == "Essen Haus" else "CBI"
                        label = f"[{pfx}] {s['role']}\nShift: {s['type']}"
                        if is_dropped: label += "\nDROP REQ"
                    else: label = "+"
                    
                    if row_cols[i+1].button(label, key=f"m_{emp}_{d}"):
                        st.session_state.sel = {"emp": emp, "day": d}
                        st.rerun()
                    tot_hours += s["hours"]
                row_cols[-1].metric("", f"{tot_hours}h", label_visibility="collapsed")

            if "sel" in st.session_state:
                e, d = st.session_state.sel["emp"], st.session_state.sel["day"]
                st.divider(); st.subheader(f"Shift Editor: {e} on {d}")
                c1, c2, c3, c4 = st.columns(4)
                loc_choice = c1.selectbox("Venue Location", ["Essen Haus", "CBI Side"])
                r = c2.selectbox("Role", ["Server", "Bartender", "Host", "Expo", "Manager"])
                t = c3.selectbox("Start Time", CLOCK_TIMES)
                h = c4.number_input("Calculated Shift Hours", value=6.0 if t != "Off" else 0.0, step=0.5)
                
                col_save, col_close = st.columns([1, 5])
                if col_save.button("Save Assignment", type="primary"):
                    conn = sqlite3.connect(DB_FILE); cur = conn.cursor()
                    cur.execute("INSERT OR REPLACE INTO schedule VALUES (?,?,?,?,?,?,?)", (week_string, e, d, r if t != "Off" else "None", t, h, loc_choice))
                    cur.execute("DELETE FROM trade_board WHERE week_start=? AND employee=? AND day=?", (week_string, e, d))
                    conn.commit(); cur.close()
                    clear_app_caches()
                    del st.session_state.sel; st.rerun()
                if col_close.button("Cancel"): del st.session_state.sel; st.rerun()

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
                        conn = sqlite3.connect(DB_FILE); cur = conn.cursor()
                        cur.execute("INSERT INTO users VALUES (?,?,?,20.00,?,?)", (n, p, 1 if m else 0, ph, em))
                        conn.commit(); conn.close()
                        clear_app_caches()
                        st.success("Employee hired successfully."); st.rerun()
