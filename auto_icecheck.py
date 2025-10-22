# auto_check.py

import datetime
import os
import smtplib
from email.mime.text import MIMEText
from supabase import create_client, Client
import requests
import urllib.parse
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- Supabase setup ---
SUPABASE_URL = "https://ynjhmsgccotfixsawslv.supabase.co"
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

BASE_SEARCH_URL = "https://anc.ca.apm.activecommunities.com/ottawa/reservation/search"
BASE_API_URL = "https://anc.ca.apm.activecommunities.com/ottawa/rest/reservation/resource"

def get_facilities():
    data = supabase.table("facilities").select("ExtID,Description").execute()
    return {item["Description"]: item["ExtID"] for item in data.data}

def get_default_facility_descriptions():
    facilities = get_facilities()
    data = supabase.table("defaultFacilities").select("ExtID").execute()
    ext_ids = [item["ExtID"] for item in data.data]
    return [desc for desc, ext in facilities.items() if ext in ext_ids]

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
    return (
        f"{BASE_SEARCH_URL}?locale=en-US&attendee=15&resourceType=0&equipmentQty=1"
        f"&eventDateAndTime={encoded_event}&facilityCenterIds={','.join(str(f) for f in facility_ids)}"
    )

def check_availability(date_str, start_time, end_time, facility_ids):
    payload = {
        "name": "",
        "attendee": 15,
        "date_times": [],
        "center_ids": facility_ids,
        "date_time_length": {
            "dates": [date_str],
            "start_time": start_time + ":00",
            "end_time": end_time + ":00",
            "hours_per_day": 1
        },
        "full_day_booking": False,
        "resource_type": 0,
        "search_client_id": "auto-" + str(time.time()),
        "start_index": 0
    }
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    url_ref = build_url_for_date(date_str, start_time, end_time, facility_ids)
    try:
        r = requests.post(BASE_API_URL, headers=headers, json=payload, timeout=10)
        if r.status_code == 200:
            data = r.json()
            available = any(i.get("availability", "").lower() == "available" for i in data['body']['items'])
            return date_str, available, url_ref
    except Exception as e:
        print(f"Error: {e}")
    return date_str, False, url_ref

def run_check(start_time, end_time, day_filter, label):
    facilities = get_facilities()
    selected = get_default_facility_descriptions()
    facility_ids = [facilities[desc] for desc in selected]
    today = datetime.date.today()
    all_dates = [today + datetime.timedelta(days=i) for i in range(16)]
    if day_filter == "Weekdays":
        target_dates = [d.isoformat() for d in all_dates if d.weekday() < 5]
    elif day_filter == "Weekends":
        target_dates = [d.isoformat() for d in all_dates if d.weekday() >= 5]
    else:
        target_dates = [d.isoformat() for d in all_dates]

    results = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [
            executor.submit(check_availability, date, start_time.strftime("%H:%M"), end_time.strftime("%H:%M"), facility_ids)
            for date in target_dates
        ]
        for f in as_completed(futures):
            date_str, status, url = f.result()
            if status:
                results.append((date_str, url))
    if results:
        send_email(results, label)

def send_email(results, label):
    sender = "your_email@gmail.com"
    recipient = "your_email@gmail.com"
    app_password = os.environ.get("EMAIL_APP_PASSWORD")

    body = f"Ice available for {label}:\n\n"
    for date_str, url in results:
        body += f"{date_str}: {url}\n"

    msg = MIMEText(body)
    msg["Subject"] = f"🏒 Ice Available - {label}"
    msg["From"] = sender
    msg["To"] = recipient

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(sender, app_password)
        server.send_message(msg)

# --- Run both checks ---
if __name__ == "__main__":
    print("Running weekday evening check...")
    run_check(datetime.time(17,0), datetime.time(21,0), "Weekdays", "Weekday Evening")

    print("Running weekend check...")
    run_check(datetime.time(8,0), datetime.time(21,0), "Weekends", "Weekend")
