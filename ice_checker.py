# ice_checker.py

import streamlit as st
import requests
import datetime
import urllib.parse
import json
import time
import os  # <-- for environment variables
from supabase import create_client, Client
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- Supabase setup ---
SUPABASE_URL = "https://ynjhmsgccotfixsawslv.supabase.co"
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")  # <-- get key from environment variable
if not SUPABASE_KEY:
    st.error("Supabase key not found. Set the SUPABASE_KEY environment variable.")
    st.stop()

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- Config ---
BASE_URL = "https://anc.ca.apm.activecommunities.com/ottawa/reservation/search"
PARAMS_TEMPLATE = {
    "locale": "en-US",
    "attendee": "15",
    "resourceType": "0",
    "equipmentQty": "1",
}

# --- Fetch facilities ---
def get_facilities():
    data = supabase.table("facilities").select("ExtID,Description").execute()
    if data.data:
        return {item["Description"]: item["ExtID"] for item in data.data}
    return {}

FACILITIES = get_facilities()
FACILITY_DESCRIPTIONS = list(FACILITIES.keys())

# --- Default facility descriptions ---
def get_default_facility_descriptions():
    data = supabase.table("defaultFacilities").select("ExtID").execute()
    if not data.data:
        return []
    ext_ids = [item["ExtID"] for item in data.data]
    return [desc for desc, ext in FACILITIES.items() if ext in ext_ids]

# --- Build URL and fetch availability ---
def build_url_for_date(date_str, start_time, end_time, facility_ids):
    event_json = {
        "fullDayBooking": False,
        "eventDates": [date_str],
        "startTime": start_time + ":00",
        "endTime": end_time + ":00",
        "hoursPerDay": 1,
        "isHoursPerDay": True
    }
    encoded_event = urllib.parse.quote(json.dumps(event_json))
    url = (
        f"{BASE_URL}?locale={PARAMS_TEMPLATE['locale']}"
        f"&attendee={PARAMS_TEMPLATE['attendee']}"
        f"&resourceType={PARAMS_TEMPLATE['resourceType']}"
        f"&equipmentQty={PARAMS_TEMPLATE['equipmentQty']}"
        f"&eventDateAndTime={encoded_event}"
        f"&facilityCenterIds={','.join(str(fac_id) for fac_id in facility_ids)}"
    )
    return url

def check_availability(date_str, start_time, end_time, facility_ids):
    url = build_url_for_date(date_str, start_time, end_time, facility_ids)
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            text = response.text
            status = "No results found" not in text
        else:
            status = False
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        status = False
    return date_str, status, url

# --- Streamlit UI ---
st.title("🏒 Ice Time Availability Checker")
st.markdown("Checks City of Ottawa last minute ice times (LMI for 15 days).")

st.sidebar.header("Settings")
st.sidebar.markdown("---")

# --- Session state initialization ---
if "start_time" not in st.session_state:
    st.session_state.start_time = datetime.time(8, 0)
if "end_time" not in st.session_state:
    st.session_state.end_time = datetime.time(21, 0)
if "day_filter" not in st.session_state:
    st.session_state.day_filter = "Weekdays"
if "selected_facilities" not in st.session_state:
    st.session_state.selected_facilities = []

# --- Sidebar widgets ---
start_date = st.sidebar.date_input("Start Date", value=datetime.date.today())
num_days = st.sidebar.slider("Number of Days to Check", 1, 15, 15)

# Only set `value` if the key isn't already in session_state
start_time = st.sidebar.time_input(
    "Start Time", 
    key="start_time"
)
end_time = st.sidebar.time_input(
    "End Time",
    key="end_time"
)

# Facility selection
selected_descriptions = st.sidebar.multiselect(
    "Select Facilities",
    options=FACILITY_DESCRIPTIONS,
    key="selected_facilities"
)
facility_ids = [FACILITIES[desc] for desc in selected_descriptions] if selected_descriptions else []

# Select All / Clear All buttons
def select_all_facilities():
    st.session_state.selected_facilities = FACILITY_DESCRIPTIONS.copy()

def clear_all_facilities():
    st.session_state.selected_facilities = []

col1, col2 = st.sidebar.columns([1,1])
col1.button("Select All", on_click=select_all_facilities)
col2.button("Clear All", on_click=clear_all_facilities)

# Day Filter
day_filter = st.sidebar.radio(
    "Filter Dates:",
    ["Weekdays","Weekends","Any Day"],
    index=["Weekdays","Weekends","Any Day"].index(st.session_state.day_filter),
    key="day_filter"
)

# Check Ice Times button
check_button = st.sidebar.button("Check Ice Times")
st.sidebar.markdown("---")  # line break before Quick Defaults

# --- Quick Defaults below Check Ice Times ---
def set_weekday_evening():
    st.session_state.start_time = datetime.time(17,0)
    st.session_state.end_time = datetime.time(21,0)
    st.session_state.day_filter = "Weekdays"
    st.session_state.selected_facilities = get_default_facility_descriptions()

def set_weekend():
    st.session_state.start_time = datetime.time(8,0)
    st.session_state.end_time = datetime.time(21,0)
    st.session_state.day_filter = "Weekends"
    st.session_state.selected_facilities = get_default_facility_descriptions()

st.sidebar.markdown("Quick Defaults")
st.sidebar.button("Weekday Evening", on_click=set_weekday_evening)
st.sidebar.button("Weekend", on_click=set_weekend)

# --- Generate target dates ---
all_dates = [start_date + datetime.timedelta(days=i) for i in range(num_days)]
if st.session_state.day_filter == "Weekdays":
    TARGET_DATES = [d.isoformat() for d in all_dates if d.weekday() < 5]
elif st.session_state.day_filter == "Weekends":
    TARGET_DATES = [d.isoformat() for d in all_dates if d.weekday() >= 5]
else:
    TARGET_DATES = [d.isoformat() for d in all_dates]

# --- Main Results ---
st.markdown("\n\n")
if check_button:
    if not facility_ids:
        st.warning("Please select at least one facility.")
    elif not TARGET_DATES:
        st.markdown("No ice times were found for the selected dates.")
    else:
        results = {}
        overall_start = time.time()
        with st.spinner("Checking ice time availability..."):
            with ThreadPoolExecutor(max_workers=5) as executor:
                future_to_date = {
                    executor.submit(
                        check_availability,
                        date,
                        st.session_state.start_time.strftime("%H:%M"),
                        st.session_state.end_time.strftime("%H:%M"),
                        facility_ids
                    ): date for date in TARGET_DATES
                }
                for future in as_completed(future_to_date):
                    date_str, status, url = future.result()
                    results[date_str] = (status, url)

        st.subheader(f"City of Ottawa Last Minute Ice")
        st.markdown("---")
        st.subheader(f"{TARGET_DATES[0]} to {TARGET_DATES[-1]}")
        st.subheader(f"Earliest start {st.session_state.start_time} latest finish {st.session_state.end_time}")

        any_available = False
        any_notavailable = False
        for date_str in sorted(results.keys()):
            status, url = results[date_str]
            if status:
                any_available = True
                st.markdown(f"**{date_str}**: ✅ Last Minute Ottawa ice times are available. ([View here]({url}))")
            else:
                any_notavailable = True

        if any_notavailable and not any_available:
            st.markdown("No ice times were found for the selected dates.")
        elif any_notavailable:
            st.markdown("No availability on other dates/times.")

        total_elapsed = time.time() - overall_start
        print(f"All dates checked in {total_elapsed:.2f}s")
