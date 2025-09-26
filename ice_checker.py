# ice_checker_streamlit_supabase.py

import streamlit as st
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from concurrent.futures import ThreadPoolExecutor, as_completed
import datetime
import urllib.parse
import json
import time
from supabase import create_client, Client

# --- Supabase setup ---
SUPABASE_URL = "https://ynjhmsgccotfixsawslv.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inluamhtc2djY290Zml4c2F3c2x2Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTg4OTI5MzIsImV4cCI6MjA3NDQ2ODkzMn0.2qiBqYStes_4JWDQ8R4RUQfY95pCGF_yGIuVB7MZFjg"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- Config ---
MAX_BROWSERS = 5
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

# --- Fetch default facilities for Quick Defaults ---
def get_default_facility_descriptions():
    data = supabase.table("defaultFacilities").select("ExtID").execute()
    if not data.data:
        return []
    ext_ids = [item["ExtID"] for item in data.data]
    # Map ExtIDs to descriptions
    return [desc for desc, ext in FACILITIES.items() if ext in ext_ids]

# --- Selenium helpers ---
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
        f"&facilityCenterIds={','.join(facility_ids)}"
    )
    return url

def create_driver():
    # Set up Chrome options
    options = Options()
    options.add_argument("--headless=new")        # Headless mode
    options.add_argument("--no-sandbox")          # Required on Linux containers
    options.add_argument("--disable-dev-shm-usage")  # Avoid /dev/shm issues
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")

    # Path to Chromium and ChromeDriver on Streamlit Cloud
    options.binary_location = "/usr/bin/chromium"
    service = Service("/usr/bin/chromedriver")

    # Create and return driver
    driver = webdriver.Chrome(service=service, options=options)
    return driver

def check_availability(date_str, start_time, end_time, facility_ids):
    driver = create_driver()
    start_runtime = time.time()
    url = build_url_for_date(date_str, start_time, end_time, facility_ids)
    driver.get(url)
    wait = WebDriverWait(driver, 5)
    try:
        no_results_div = wait.until(
            EC.presence_of_element_located((By.CLASS_NAME, "card-section-actual__empty"))
        )
        status = False if "No results found" in no_results_div.text else True
    except:
        status = True
    runtime = time.time() - start_runtime
    driver.quit()
    return date_str, status, runtime, url

# --- Streamlit UI ---
st.title("🏒 Ice Time Availability Checker")
st.markdown("Currently only checks City of Ottawa last minute ice times.")
st.markdown("Note: City of Ottawa only shows LMI for 15 days from today.")

st.sidebar.header("Settings")
st.sidebar.markdown("---")

# Initialize session state
if "start_time_widget" not in st.session_state:
    st.session_state.start_time_widget = datetime.time(8,0)
if "end_time_widget" not in st.session_state:
    st.session_state.end_time_widget = datetime.time(21,0)
if "day_filter_widget" not in st.session_state:
    st.session_state.day_filter_widget = "Weekdays"
if "selected_facilities" not in st.session_state:
    st.session_state.selected_facilities = []

# --- Sidebar widgets ---

start_date = st.sidebar.date_input("Start Date", value=datetime.date.today())
num_days = st.sidebar.slider("Number of Days to Check", min_value=1, max_value=15, value=15)

start_time = st.sidebar.time_input("Start Time", key="start_time_widget")
end_time = st.sidebar.time_input("End Time", key="end_time_widget")

# Facility selection (no default param; controlled via session state)
selected_descriptions = st.sidebar.multiselect(
    "Select Facilities",
    options=FACILITY_DESCRIPTIONS,
    key="selected_facilities"
)
facility_ids = [FACILITIES[desc] for desc in selected_descriptions] if selected_descriptions else []

# Select All / Clear All
col1, col2 = st.sidebar.columns([1,1])

def select_all():
    st.session_state.selected_facilities = FACILITY_DESCRIPTIONS.copy()

def clear_all():
    st.session_state.selected_facilities = []

col1.button("Select All", on_click=select_all)
col2.button("Clear All", on_click=clear_all)

# Day Filter Radio
day_filter = st.sidebar.radio(
    "Filter Dates:",
    ["Weekdays", "Weekends", "Any Day"],
    key="day_filter_widget"
)

# Check Ice Times button
check_button = st.sidebar.button("Check Ice Times", help="Click to check ice time availability")
st.sidebar.markdown("---")

# Quick Defaults callbacks
def set_weekday_evening():
    st.session_state.start_time_widget = datetime.time(17,0)
    st.session_state.end_time_widget = datetime.time(21,0)
    st.session_state.day_filter_widget = "Weekdays"
    st.session_state.selected_facilities = get_default_facility_descriptions()

def set_weekend():
    st.session_state.start_time_widget = datetime.time(8,0)
    st.session_state.end_time_widget = datetime.time(21,0)
    st.session_state.day_filter_widget = "Weekends"
    st.session_state.selected_facilities = get_default_facility_descriptions()

st.sidebar.markdown("Quick Defaults")
st.sidebar.button("Weekday Evening", on_click=set_weekday_evening)
st.sidebar.button("Weekend", on_click=set_weekend)

# --- Generate target dates ---
all_dates = [start_date + datetime.timedelta(days=i) for i in range(num_days)]
if st.session_state.day_filter_widget == "Weekdays":
    TARGET_DATES = [d.isoformat() for d in all_dates if d.weekday() < 5]
elif st.session_state.day_filter_widget == "Weekends":
    TARGET_DATES = [d.isoformat() for d in all_dates if d.weekday() >= 5]
else:
    TARGET_DATES = [d.isoformat() for d in all_dates]

# --- Main Results Output ---
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
            with ThreadPoolExecutor(max_workers=MAX_BROWSERS) as executor:
                future_to_date = {
                    executor.submit(
                        check_availability,
                        date,
                        st.session_state.start_time_widget.strftime("%H:%M"),
                        st.session_state.end_time_widget.strftime("%H:%M"),
                        facility_ids
                    ): date for date in TARGET_DATES
                }
                for future in as_completed(future_to_date):
                    date_str, status, runtime, url = future.result()
                    results[date_str] = (status, runtime, url)

        st.subheader(f"City of Ottawa Last Minute Ice")
        st.markdown("---")
        st.subheader(f"{TARGET_DATES[0]} to {TARGET_DATES[-1]}")
        st.subheader(f"Earliest start {start_time} latest finish {end_time}")

        any_available = False
        any_notavailable = False
        for date_str in sorted(results.keys()):
            status, runtime, url = results[date_str]
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
