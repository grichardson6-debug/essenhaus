import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, timedelta

# 1. Page Configuration
st.set_page_config(page_title="Essen Haus & CBI Roster Pro", page_icon="🍺", layout="wide")

# --- CRASH PROTECTION: CHECK FOR SECRETS ---
if "public_gsheet_url" not in st.secrets:
    st.error("🚨 **Database Link Missing!**")
    st.warning("Please go to your Streamlit Cloud Dashboard -> Settings -> Secrets, and add your `public_gsheet_url = '...'`")
    st.stop()

# --- GLOBAL CONFIGURATION ---
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

# Establish Google Sheets Connection
conn = st.connection("gsheets", type=GSheetsConnection)

def get_monday_of_week(date_obj):
    return date_obj - timedelta(days=date_obj.weekday())

# --- GOOGLE SHEETS DATA READ/WRITE LOGIC ---
@st.cache_data(ttl=10)
def load_all_sheets_data():
    try:
        url = st.secrets["public_gsheet_url"]
        users_df = conn.read(spreadsheet=url, worksheet="users", ttl="10s")
        sched_df = conn.read(spreadsheet=url, worksheet="schedule", ttl="5s")
        avail_df = conn.read(spreadsheet=url, worksheet="availability", ttl="10s")
        trade_df = conn.read(spreadsheet=url, worksheet="trade_board", ttl="5s")
        status_df = conn.read(spreadsheet=url, worksheet="week_status", ttl="10s")
        return users_df, sched_df, avail_df, trade_df, status_df
    except Exception:
        u = pd.DataFrame(columns=["employee", "pin", "is_manager", "wage", "phone", "email"])
        s = pd.DataFrame(columns=["week_start", "employee", "day", "role", "type", "hours", "location"])
        a = pd.DataFrame(columns=["employee", "day", "request_type"])
        t = pd.DataFrame(columns=["id", "week_start", "employee", "day", "details"])
        st_df = pd.DataFrame(columns=["week_start", "published"])
        return u, s, a, t, st_df

def write_sheet_data(worksheet_name, updated_df):
    url = st.secrets["public_gsheet_url"]
    conn.update(spreadsheet=url, worksheet=worksheet_name, data=updated_df)
    st.cache_data.clear()

def init_gsheet_tables():
    u_df, s_df, a_df, t_df, st_df = load_all_sheets_data()
    if u_df.empty:
        base_users = [
            {"employee": "Tim", "pin": "4321", "is_manager": 1, "wage": 22.00, "phone": "", "email": "tim@example.com"},
            {"employee": "Grace", "pin": "1234", "is_manager": 0, "wage": 6.00, "phone": "", "email": ""},
            {"employee": "Gracie", "pin": "1234", "is_manager": 0, "wage": 14.00, "phone": "", "email": ""}
        ]
        u_df = pd.DataFrame(base_users)
        write_sheet_data("users", u_df)

init_gsheet_tables()

# Hydrate views
users_df, sched_df, avail_df, trade_df, status_df = load_all_sheets_data()

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
            st.cache_data.clear()
            st.rerun()
        else: st.sidebar.error("Invalid PIN")
else:
    st.sidebar.write(f"Logged in: **{st.session_state.user_profile}**")
    if st.sidebar.button("Log Out"): st.session_state.authenticated = False; st.cache_data.clear(); st.rerun()
    
    chosen_date = st.sidebar.date_input("Calendar Week:", datetime.today())
    monday_date = get_monday_of_week(chosen_date)
    week_string = monday_date.strftime("%Y-%m-%d")
    
    week_is_live = False
    if not status_df.empty and "week_start" in status_df.columns:
        match = status_df[status_df["week_start"] == week_string]
        if not match.empty:
            week_is_live = bool(int(match.iloc[0]["published"]))
            
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
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
        for _, a_row in avail_df.iterrows():
            emp_name = str(a_row["employee"])
            if emp_name in availability_matrix:
                availability_matrix[emp_name][str(a_row["day"])] = str(a_row["request_type"])
                
    up_for_grabs = []
    if not trade_df.empty:
        filtered_trade = trade_df[trade_df["week_start"] == week_string]
        for _, t_row in filtered_trade.iterrows():
            up_for_grabs.append({
                "id": str(t_row["id"]), "employee": str(t_row["employee"]), "day": str(t_row["day"]), "details": str(t_row["details"])
            })

    nav_options = ["Server Portal"]
    if st.session_state.is_manager: nav_options.append("Manager Hub")
    app_mode = st.sidebar.radio("Go To View:", nav_options)

    # --- SERVER PORTAL ---
    if app_mode == "Server Portal":
        u = st.session_state.user_profile
        tab1, tab2, tab3 = st.tabs(["Schedule View", "Request Time Off", "Shift Trade Board"])
        
        with tab1:
            if not week_is_live and not st.session_state.is_manager:
                st.info("The manager hasn't published this schedule yet.")
            else:
                view_mode = st.radio("Display Filter:", ["Show Full Team Floor Plan", "Show Just My Personal Schedule"], horizontal=True)
                
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
                                        new_id = str(len(trade_df) + 1)
                                        new_row = pd.DataFrame([{"id": new_id, "week_start": week_string, "employee": u, "day": d_day, "details": f"[{s['location']}] {s['role']} @ {s['type']}"}])
                                        trade_df = pd.concat([trade_df, new_row], ignore_index=True)
                                        write_sheet_data("trade_board", trade_df)
                                        st.toast("Shift listed on Cloud Board.")
                                        st.rerun()
                                else: st.caption("Listed on Trade Board")
                            else: st.markdown("<p style='color:gray; font-size:13px;'>Off</p>", unsafe_allow_html=True)
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
                            
                        # Sort by time, then role
                        venue_shifts.sort(key=lambda x: CLOCK_TIMES.index(x["time"]) if x["time"] in CLOCK_TIMES else 99)
                        
                        for s in venue_shifts:
                            # Render exact blue info box style from screenshot
                            st.info(f"**{s['role']}** - {s['emp']} @ {s['time']}")
                            
                            contact_links = []
                            if s["phone"]: contact_links.append(f"📞 💬 [Text](sms:{s['phone']})")
                            if s["email"]: contact_links.append(f"📧 [Mail](mailto:{s['email']})")
                            
                            if s["emp"] != u:
                                if contact_links:
                                    st.markdown(" | ".join(contact_links))
                            else:
                                if not s["is_dropped"]:
                                    if st.button(f"🔴 Drop My Shift: {s['role']} - {s['emp']} @ {s['time']}", key=f"inline_drop_{venue_name}_{s['role']}_{s['emp']}"):
                                        new_id = str(len(trade_df) + 1)
                                        new_row = pd.DataFrame([{"id": new_id, "week_start": week_string, "employee": u, "day": view_day, "details": f"[{s['location']}] {s['role']} @ {s['time']}"}])
                                        trade_df = pd.concat([trade_df, new_row], ignore_index=True)
                                        write_sheet_data("trade_board", trade_df)
                                        st.toast("Shift listed on Cloud Board.")
                                        st.rerun()
                                else:
                                    st.warning("Shift drop pending...")

                    with col_eh: render_roster_column("Essen Haus", "🏰", day_shifts)
                    with col_cbi: render_roster_column("CBI Side", "🌭", day_shifts)

        with tab2:
            st.subheader("Submit Availability / Time-Off")
            c1, c2 = st.columns(2)
            req_day = c1.selectbox("Target Day:", days)
            duration_type = c2.selectbox("Duration Style:", ["Permanent (Recurring Rule)", "Temporary (Single Date Shift)"])
            
            final_status_string = "Permanent Block" if duration_type == "Permanent (Recurring Rule)" else f"Temp: {st.radio('Window:', ['Morning Shift', 'Evening Shift'], horizontal=True)}"
                
            if st.button("Submit Request", type="primary"):
                if not avail_df.empty:
                    avail_df = avail_df[~((avail_df["employee"] == u) & (avail_df["day"] == req_day))]
                new_avail_row = pd.DataFrame([{"employee": u, "day": req_day, "request_type": final_status_string}])
                avail_df = pd.concat([avail_df, new_avail_row], ignore_index=True)
                write_sheet_data("availability", avail_df)
                st.success("Cloud availability saved!"); st.rerun()

        with tab3:
            st.subheader("Available Trades Pool")
            open_trades = [t for t in up_for_grabs if t["employee"] != u]
            if open_trades:
                for t in open_trades:
                    with st.container(border=True):
                        c_text, c_act = st.columns([4, 1])
                        c_text.write(f"Employee: **{t['employee']}** wishes to drop **{t['day']}** | Context: `{t['details']}`")
                        if c_act.button("Claim Shift", key=f"claim_{t['id']}", type="primary"):
                            match_idx = sched_df[(sched_df["week_start"] == week_string) & (sched_df["employee"] == t["employee"]) & (sched_df["day"] == t["day"])].index
                            if not match_idx.empty:
                                orig_row = sched_df.loc[match_idx[0]].copy()
                                sched_df.loc[match_idx[0], ["role", "type", "hours"]] = ["None", "Off", 0.0]
                                
                                sched_df = sched_df[~((sched_df["week_start"] == week_string) & (sched_df["employee"] == u) & (sched_df["day"] == t["day"]))]
                                new_shift = pd.DataFrame([{"week_start": week_string, "employee": u, "day": t["day"], "role": orig_row["role"], "type": orig_row["type"], "hours": orig_row["hours"], "location": orig_row["location"]}])
                                sched_df = pd.concat([sched_df, new_shift], ignore_index=True)
                                
                                trade_df = trade_df[trade_df["id"] != t["id"]]
                                write_sheet_data("schedule", sched_df)
                                write_sheet_data("trade_board", trade_df)
                                st.success("Shift claimed!"); st.rerun()
            else: st.caption("No open drops currently on the board.")

    # --- MANAGER HUB ---
    elif app_mode == "Manager Hub":
        m_tab1, m_tab2 = st.tabs(["Roster Grid Engine", "Staff Directory"])
        with m_tab1:
            tool_c1, tool_c2, tool_c3 = st.columns([2, 2, 3])
            if week_is_live:
                tool_c2.markdown("<h3 style='color:#10b981; margin:0;'>Published</h3>", unsafe_allow_html=True)
                if tool_c3.button("Unpublish Schedule"):
                    status_df = status_df[status_df["week_start"] != week_string]
                    new_status = pd.DataFrame([{"week_start": week_string, "published": 0}])
                    status_df = pd.concat([status_df, new_status], ignore_index=True)
                    write_sheet_data("week_status", status_df)
                    st.rerun()
            else:
                tool_c2.markdown("<h3 style='color:#f59e0b; margin:0;'>Draft Mode</h3>", unsafe_allow_html=True)
                if tool_c3.button("Publish Schedule to Team", type="primary"):
                    status_df = status_df[status_df["week_start"] != week_string]
                    new_status = pd.DataFrame([{"week_start": week_string, "published": 1}])
                    status_df = pd.concat([status_df, new_status], ignore_index=True)
                    write_sheet_data("week_status", status_df)
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
                for i, d in enumerate(days):
                    s = schedule_matrix[emp][d]
                    has_request = availability_matrix.get(emp, {}).get(d)
                    is_dropped = any(t['employee'] == emp and t['day'] == d for t in up_for_grabs)
                    
                    if has_request: label = "PERM\nBLOCK" if "Permanent" in has_request else f"Conflict: {has_request.replace('Temp: ', '')}"
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
                r = c2.selectbox("Role", ["Server", "Bartender", "Host", "Expo", "CBI CL Server", "Manager"])
                t = c3.selectbox("Start Time", CLOCK_TIMES)
                h = c4.number_input("Hours", value=6.0 if t != "Off" else 0.0, step=0.5)
                
                col_save, col_close = st.columns([1, 5])
                if col_save.button("Save Assignment", type="primary"):
                    sched_df = sched_df[~((sched_df["week_start"] == week_string) & (sched_df["employee"] == e) & (sched_df["day"] == d))]
                    new_assign = pd.DataFrame([{"week_start": week_string, "employee": e, "day": d, "role": r if t != "Off" else "None", "type": t, "hours": h, "location": loc_choice}])
                    sched_df = pd.concat([sched_df, new_assign], ignore_index=True)
                    
                    trade_df = trade_df[~((trade_df["week_start"] == week_string) & (trade_df["employee"] == e) & (trade_df["day"] == d))]
                    
                    write_sheet_data("schedule", sched_df)
                    write_sheet_data("trade_board", trade_df)
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
                        new_user = pd.DataFrame([{"employee": n, "pin": p, "is_manager": 1 if m else 0, "wage": 20.00, "phone": ph, "email": em}])
                        users_df = pd.concat([users_df, new_user], ignore_index=True)
                        write_sheet_data("users", users_df)
                        st.success("Employee hired!"); st.rerun()
