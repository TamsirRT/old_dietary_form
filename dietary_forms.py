# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "pandas",
#     "google-api-python-client",
#     "google-auth",
#     "google-auth-oauthlib",
# ]
# ///
import os.path
import re
from datetime import datetime, timedelta

import pandas as pd
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

sheet_id = "1N6E1zMAghSGGxwaS1hPb8_ijDmNsJzOMVgx2Ro41ug8"
sheet_name = "Sheet1"
url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet={sheet_name}"


def expand_bld(start, end, bld, default_headcount=None):
    start_date = datetime.strptime(start, "%m/%d/%Y")
    end_date = datetime.strptime(end, "%m/%d/%Y")

    day_meals = [x.strip().upper() for x in str(bld).split(",")]
    num_days = (end_date - start_date).days + 1
    dates = [start_date + timedelta(days=i) for i in range(num_days)]

    if len(day_meals) != num_days:
        print(f"  WARNING: {num_days} days but {len(day_meals)} meal codes in '{bld}' "
              f"- only {min(num_days, len(day_meals))} days will be used")

    prefixed = {
        "OB": "Outdoor Breakfast",
        "OL": "Outdoor Lunch",
        "OD": "Outdoor Dinner",
        "UB": "Upgraded Breakfast",
        "UL": "Upgraded Lunch",
        "UD": "Upgraded Dinner",
    }
    meal_map = {"B": "Breakfast", "L": "Lunch", "D": "Dinner"}

    expanded = []
    for date, code in zip(dates, day_meals):
        meals, headcounts = [], []

        # e.g. BL(30)D(25)UB(10) -> {'L': 30, 'D': 25, 'UB': 10}
        # Optional O/U prefix + exactly one meal letter, so "BL(30)" is read as L=30.
        variations = {m.group(1): int(m.group(2))
                      for m in re.finditer(r'([OU]?[BLD])\((\d+)\)', code)}

        code = re.sub(r'\(\d+\)', '', code)

        for key, label in prefixed.items():
            if key in code:
                meals.append(label)
                headcounts.append(variations.get(key, default_headcount))

        for key, label in meal_map.items():
            if key in code and not any(x in code for x in [f"O{key}", f"U{key}"]):
                meals.append(label)
                headcounts.append(variations.get(key, default_headcount))

        expanded.append({
            "date": date.strftime("%m/%d/%Y"),
            "meals": meals,
            "headcounts": headcounts,
        })

    return expanded


SCOPES = [
    "https://www.googleapis.com/auth/forms",
    "https://www.googleapis.com/auth/drive",
]

SCRIPT_ID = "1VvPeSxF50TbI7vi4JW7DbiX971X9gcaG9WW_CuWNy7Mnw9cG03uOr6jx"


def main():
    # Resolve token/credential files next to this script, not wherever you ran it from
    here = os.path.dirname(os.path.abspath(__file__))
    token_path = os.path.join(here, "token.json")
    secrets_path = os.path.join(here, "desktop_credentials.json")

    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(secrets_path, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, "w") as token:
            token.write(creds.to_json())

    service = build("script", "v1", credentials=creds)

    groups_df = pd.read_csv(url)
    df = groups_df[["group_name", "headcount", "start", "end", "bld", "contact", "start_a", "end_a"]]

    for _, row in df.iterrows():
        start_dt = datetime.strptime(row["start"], "%Y-%m-%d")
        end_dt = datetime.strptime(row["end"], "%Y-%m-%d")
        form_name = f"{row['group_name']} ({start_dt.strftime('%b %d, %Y')}) Dietary Form"
        start_date = start_dt.strftime("%m/%d/%Y")
        end_date = end_dt.strftime("%m/%d/%Y")
        # pandas gives numpy.int64, which the API client can't JSON-serialize -> plain int
        headcount = int(row["headcount"])
        bld_data = expand_bld(start_date, end_date, row["bld"], default_headcount=headcount)

        request = {
            "function": "create_dietary_form",
            "parameters": [form_name, start_date, end_date, headcount, bld_data],
            "devMode": True,
        }

        print(f"Calling the Apps Script API for {form_name}...")
        response = service.scripts().run(scriptId=SCRIPT_ID, body=request).execute()
        print(response)

        if "error" in response:
            error = response["error"]["details"][0]
            print(f"Script error message: {error['errorMessage']}")
            print(f"Script error stacktrace: {error.get('scriptStackTraceElements')}")
        else:
            print("Function executed successfully!")


if __name__ == "__main__":
    main()
