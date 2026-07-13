import streamlit as st
import sqlite3
import streamlit.components.v1 as components
from datetime import datetime, timedelta

# 1. Page Configuration
st.set_page_config(page_title="Essen Haus & CBI Roster Pro", page_icon="🍺", layout="wide")

DB_FILE = "scheduler.db"

# --- GLOBAL MATRICES YOU MIGHT EDIT ON THE FLY ---
ROLE_WAGES = {
    "Server": 6.00,
    "Bartender": 8.00,
    "Host": 14.00,
    "Expo": 14.00,
    "VB Ref": 80.00,
    "Manager": 22.00
}

CLOCK_TIMES = ["Off", "11:00 AM", "11:30 AM", "12:00 PM", "2:00 PM", "3:30 PM", "4:00 PM", "4:30 PM", "5:00 PM", "5:30 PM", "6:00 PM", "8:00 PM"]

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
            else if (text.includes('➕')) { btn.style.backgroundColor = '#1e293b'; btn.style.borderColor = '#334155'; btn.style.borderStyle = 'dashed'; }
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
    cursor.execute('CREATE TABLE IF NOT EXISTS users (employee TEXT PRIMARY KEY, pin TEXT, is_manager INTEGER DEFAULT 0, wage REAL DEFAULT 20.00)')
    cursor.execute('CREATE TABLE IF NOT EXISTS week_status (week_start TEXT PRIMARY KEY, published INTEGER DEFAULT 0)')
    conn.commit()
    
    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT OR REPLACE INTO users VALUES ('Grace', '1111', 0, 20.00)")
        cursor.execute("INSERT OR REPLACE INTO users VALUES ('Gracie', '2222', 0, 20.00)")
        cursor.execute("INSERT OR REPLACE INTO users VALUES ('Nealle', '9999', 1, 25.00)")
        conn.commit()
    conn.close()

def get_all_employees_with_wages():
    conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
    cursor.execute("SELECT employee, wage, is_manager FROM users")
    rows = cursor.fetchall(); conn.close()
    return {r[0]: {"wage": r[1], "is_manager": bool(r[2])} for r in rows}

def is_week_published(week_str):
    conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
    cursor.execute("SELECT published FROM week_status WHERE week_start=?", (week_str,))
    res = cursor.fetchone(); conn.close()
    return bool(res[0]) if res else False

def set_week_publication(week_str, status_int):
    conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO week_status VALUES (?, ?)", (week_str, status_int))
    conn.commit(); conn.close()

def load_week_data(week_str, employees_list):
    conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    cursor.execute("SELECT employee, day, role, type, hours, location FROM schedule WHERE week_start=?", (week_str,))
    rows = cursor.fetchall()
    
    schedule_dict = {emp: {day: {"role": "None", "type": "Off", "hours": 0.0, "location": "Essen Haus"} for day in days} for emp in employees_list}
    for emp, day, role, shift_time, hours, loc in rows:
        if emp in schedule_dict and day in schedule_dict[emp]:
            schedule_dict[emp][day] = {"role": role, "type": shift_time, "hours": hours, "location": loc or "Essen Haus"}
            
    cursor.execute("SELECT employee, day, request_type FROM availability")
    avail_dict = {emp: {} for emp in employees_list}
    for emp, day, req in cursor.fetchall():
        if emp in avail_dict: avail_dict[emp][day] = req
            
    cursor.execute("SELECT id, employee, day, details FROM trade_board WHERE week_start=?", (week_str,))
    trade_list = [{"id": r[0], "employee": r[1], "day": r[2], "details": r[3]} for r in cursor.fetchall()]
    conn.close()
    return schedule_dict, avail_dict, trade_list

@st.dialog("🔄 Confirm Shift Drop")
def confirm_drop_dialog(week_string, employee, day, role, shift_time, location):
    st.write(f"Are you sure you want to drop your **{location} — {role} @ {shift_time}** shift on **{day}**?")
    c1, c2 = st.columns(2)
    if c1.button("Yes, Drop It", type="primary", use_container_width=True):
        conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM trade_board WHERE week_start=? AND employee=? AND day=?", (week_string, employee, day))
        if cursor.fetchone()[0] == 0:
            cursor.execute("INSERT INTO trade_board (week_start, employee, day, details) VALUES (?,?,?,?)", (week_string, employee, day, f"[{location}] {role} @ {shift_time}"))
            conn.commit()
            st.toast("🚀 Shift successfully posted to Trade Board!")
        conn.close(); st.rerun()
    if c2.button("Cancel", use_container_width=True): st.rerun()

init_db()

st.sidebar.title("🔒 Security Access")
if "authenticated" not in st.session_state:
    st.session_state.authenticated, st.session_state.user_profile, st.session_state.is_manager = False, None, False

employee_directory = get_all_employees_with_wages()
current_db_employees = list(employee_directory.keys())

if not st.session_state.authenticated:
    login_user = st.sidebar.selectbox("Select Your Profile:", current_db_employees)
    login_pin = st.sidebar.text_input("Enter PIN:", type="password")
    if st.sidebar.button("Log In", type="primary"):
        conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
        cursor.execute("SELECT is_manager FROM users WHERE employee=? AND pin=?", (login_user, login_pin))
        res = cursor.fetchone(); conn.close()
        if res:
            st.session_state.authenticated, st.session_state.user_profile, st.session_state.is_manager = True, login_user, bool(res[0])
            st.rerun()
        else: st.sidebar.error("❌ Invalid PIN")
else:
    inject_native_styles()
    inject_color_scripts()
    
    st.sidebar.write(f"Logged in: **{st.session_state.user_profile}**")
    if st.sidebar.button("Log Out"): st.session_state.authenticated = False; st.rerun()
    
    chosen_date = st.sidebar.date_input("Calendar Week:", datetime.today())
    monday_date = get_monday_of_week(chosen_date)
    week_string = monday_date.strftime("%Y-%m-%d")
    
    st.session_state.schedule, st.session_state.availability_db, st.session_state.up_for_grabs = load_week_data(week_string, current_db_employees)
    week_is_live = is_week_published(week_string)
    
    nav_options = ["Server Portal"]
    if st.session_state.is_manager: nav_options.append("Manager Hub")
    app_mode = st.sidebar.radio("Go To View:", nav_options)

    # --- SERVER PORTAL ---
    if app_mode == "Server Portal":
        u = st.session_state.user_profile
        st.title(f"Team Portal: {u}")
        tab1, tab2, tab3 = st.tabs(["📅 Schedule View", "🏖️ Request Time Off", "🔄 Shift Trade Board"])
        
        with tab1:
            if not week_is_live and not st.session_state.is_manager:
                st.info("🚧 The manager hasn't published this schedule yet.")
            else:
                # --- NEW VIEW MODE FILTER TOGGLE ---
                view_mode = st.radio("Display Filter:", ["Show Full Team Floor Plan", "Show Just My Personal Schedule"], horizontal=True)
                
                if view_mode == "Show Just My Personal Schedule":
                    st.write("### 📅 Your Shifts for the Week")
                    cols = st.columns(7)
                    days_list = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
                    
                    for idx, d_day in enumerate(days_list):
                        with cols[idx]:
                            st.markdown(f"##### {d_day[:3]}")
                            s = st.session_state.schedule[u][d_day]
                            if s["type"] != "Off":
                                st.success(f"**{s['location']}**\n\n{s['role']}\n\n⏱️ {s['type']}")
                                if st.button("Drop Shift", key=f"p_drop_{d_day}"):
                                    confirm_drop_dialog(week_string, u, d_day, s['role'], s['type'], s['location'])
                            else:
                                st.markdown("<p style='color:gray; font-size:13px;'>🟢 Off</p>", unsafe_allow_html=True)
                
                else:
                    # Original Master Floor Plan View
                    view_day = st.selectbox("Select Day to View Floor Map:", ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"])
                    st.write(f"### 📋 Floor Configuration for {view_day}")
                    
                    eh_shifts = []
                    cbi_shifts = []
                    for emp in current_db_employees:
                        s = st.session_state.schedule[emp][view_day]
                        if s["type"] != "Off":
                            shift_data = {"emp": emp, "role": s["role"], "time": s["type"]}
                            if s["location"] == "Essen Haus": eh_shifts.append(shift_data)
                            else: cbi_shifts.append(shift_data)
                    
                    eh_shifts.sort(key=lambda x: CLOCK_TIMES.index(x["time"]) if x["time"] in CLOCK_TIMES else 99)
                    cbi_shifts.sort(key=lambda x: CLOCK_TIMES.index(x["time"]) if x["time"] in CLOCK_TIMES else 99)
                    
                    col_eh, col_cbi = st.columns(2)
                    
                    with col_eh:
                        st.markdown("#### 🏰 Essen Haus Floor Plan")
                        if eh_shifts:
                            for s in eh_shifts:
                                card_label = f"**{s['role']}** - {s['emp']} @ {s['time']}"
                                if s['emp'] == u:
                                    if st.button(f"🔴 Drop My Shift: {card_label}", key=f"drop_eh_{s['emp']}"):
                                        confirm_drop_dialog(week_string, u, view_day, s['role'], s['time'], "Essen Haus")
                                else: st.info(card_label)
                        else: st.caption("No floor shifts logged for Essen Haus.")
                        
                    with col_cbi:
                        st.markdown("#### 🌭 Come Back In (CBI) Side")
                        if cbi_shifts:
                            for s in cbi_shifts:
                                card_label = f"**{s['role']}** - {s['emp']} @ {s['time']}"
                                if s['emp'] == u:
                                    if st.button(f"🔴 Drop My Shift: {card_label}", key=f"drop_cbi_{s['emp']}"):
                                        confirm_drop_dialog(week_string, u, view_day, s['role'], s['time'], "CBI Side")
                                else: st.info(card_label)
                        else: st.caption("No floor shifts logged for CBI.")

        with tab2:
            st.subheader("Submit Time-Off Request")
            c1, c2 = st.columns(2)
            req_day = c1.selectbox("Select Day:", ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"])
            req_type = c2.selectbox("Reason:", ["Vacation", "Medical / Doc", "Personal Day", "Childcare"])
            if st.button("Submit Request", type="primary"):
                conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
                cursor.execute("INSERT OR REPLACE INTO availability VALUES (?, ?, ?)", (u, req_day, req_type))
                conn.commit(); conn.close(); st.success("Submitted!"); st.rerun()

        with tab3:
            st.subheader("Available Trades Pool")
            trades = st.session_state.up_for_grabs
            open_trades = [t for t in trades if t["employee"] != u]
            if open_trades:
                for t in open_trades:
                    with st.container(border=True):
                        c_text, c_act = st.columns([4, 1])
                        c_text.write(f"👤 **{t['employee']}** wants to drop **{t['day']}** | Context: `{t['details']}`")
                        if c_act.button("Claim Shift", key=f"claim_{t['id']}", type="primary"):
                            conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
                            cursor.execute("SELECT role, type, hours, location FROM schedule WHERE week_start=? AND employee=? AND day=?", (week_string, t["employee"], t["day"]))
                            info = cursor.fetchone()
                            if info:
                                cursor.execute("INSERT OR REPLACE INTO schedule VALUES (?,?,?,?,?,?,?)", (week_string, u, t["day"], info[0], info[1], info[2], info[3]))
                                cursor.execute("INSERT OR REPLACE INTO schedule VALUES (?,?,?,?,?,?,?)", (week_string, t["employee"], t["day"], "None", "Off", 0.0, "Essen Haus"))
                                cursor.execute("DELETE FROM trade_board WHERE id=?", (t["id"],))
                                conn.commit()
                            conn.close(); st.success("Shift claimed!"); st.rerun()
            else: st.caption("No shifts on the board.")

    # --- MANAGER HUB ---
    elif app_mode == "Manager Hub":
        m_tab1, m_tab2 = st.tabs(["📅 Roster Grid Engine", "👤 Staff Directory"])
        
        with m_tab1:
            tool_c1, tool_c2, tool_c3 = st.columns([2, 2, 3])
            if week_is_live:
                tool_c2.markdown("<h3 style='color:#10b981; margin:0;'>📢 Published</h3>", unsafe_allow_html=True)
                if tool_c3.button("Unpublish Schedule"): set_week_publication(week_string, 0); st.rerun()
            else:
                tool_c2.markdown("<h3 style='color:#f59e0b; margin:0;'>📝 Draft Mode</h3>", unsafe_allow_html=True)
                if tool_c3.button("Publish Schedule to Team", type="primary"): set_week_publication(week_string, 1); st.rerun()
            
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
                    
                    if has_request: label = f"⚠️ Request\n({emp[:4]})"
                    elif s["type"] != "Off":
                        pfx = "EH" if s["location"] == "Essen Haus" else "CBI"
                        label = f"[{pfx}] {s['role']}\n⏱️ {s['type']}"
                        if is_dropped: label += "\n🔄 DROP REQ"
                    else: label = "➕"
                    
                    if row_cols[i+1].button(label, key=f"m_{emp}_{d}"):
                        st.session_state.sel = {"emp": emp, "day": d}
                        st.rerun()
                    tot_hours += s["hours"]
                row_cols[-1].metric("", f"{tot_hours}h", label_visibility="collapsed")

            if "sel" in st.session_state:
                e, d = st.session_state.sel["emp"], st.session_state.sel["day"]
                st.divider()
                st.subheader(f"Shift Editor: {e} on {d}")
                
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
                    conn.commit(); cur.close(); del st.session_state.sel; st.rerun()
                if col_close.button("Cancel"): del st.session_state.sel; st.rerun()

        with m_tab2:
            st.subheader("Hire Team Member")
            with st.form("new_emp"):
                n = st.text_input("Name")
                p = st.text_input("4-Digit PIN", max_chars=4)
                m = st.checkbox("Grant Manager Privileges?")
                if st.form_submit_button("Hire Team Member"):
                    if n and p:
                        conn = sqlite3.connect(DB_FILE); cur = conn.cursor()
                        cur.execute("INSERT INTO users VALUES (?,?,?,20.00)", (n, p, 1 if m else 0))
                        conn.commit(); conn.close(); st.success("Hired!"); st.rerun()