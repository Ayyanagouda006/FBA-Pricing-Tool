import requests
import json
import pandas as pd
from datetime import datetime
import os

LOG_FILE = r"Logs/heyprimo_api_tracking.xlsx"

# ----------------- Logging Function -----------------
def log_heyprimo_result(ori_city, ori_state, ori_zip, dest_city, dest_state, dest_zip, qty, status, message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = {
        "Timestamp": timestamp,
        "Origin City": ori_city,
        "Origin State Code": ori_state,
        "Origin ZIP": ori_zip,
        "Destination City": dest_city,
        "Destination State Code": dest_state,
        "Destination ZIP": dest_zip,
        "Pallet Count": qty,
        "Status": status,
        "Message": message
    }

    if os.path.exists(LOG_FILE):
        df = pd.read_excel(LOG_FILE)
    else:
        df = pd.DataFrame(columns=list(log_entry.keys()))

    df = pd.concat([df, pd.DataFrame([log_entry])], ignore_index=True)
    df.to_excel(LOG_FILE, index=False)

# ----------------- Get API Token -----------------
def get_access_token(username: str, password: str) -> str:
    login_url = "https://heyprimo-api.shipprimus.com/api/v1/login"
    login_data = {"username": username, "password": password}
    headers = {"accept": "application/json", "Content-Type": "application/json"}

    response = requests.post(login_url, json=login_data, headers=headers)
    if response.status_code == 200:
        token = response.json().get("data", {}).get("accessToken")
        if token:
            return token
        else:
            raise ValueError("Access token not found in response.")
    else:
        raise ValueError(f"Login failed: {response.status_code} - {response.text}")

# ----------------- Fetch Rates -----------------
def fetch_shipping_rates(token: str, query_params: dict) -> dict:
    url = "https://heyprimo-api.shipprimus.com/applet/v1/rate/multiple"
    headers = {"Authorization": f"Bearer {token}", "accept": "application/json"}

    response = requests.get(url, headers=headers, params=query_params)
    try:
        return response.json()
    except json.JSONDecodeError:
        return None

# ----------------- Process Single Row -----------------
def heyprimo_api(row: dict):
    try:
        ori_city = row['Origin City'].strip().upper()
        ori_state = row['Origin State Code'].strip().upper()
        ori_zip = str(row['Origin ZIP']).zfill(5)
        dest_city = row['Destn City'].strip().upper()
        dest_state = row['Destn State Code'].strip().upper()
        dest_zip = str(row['FBA or Destination ZIP']).zfill(5)
        qty = int(row['Num Of Pallet'])

        query_params = {
            "destinationCity": dest_city,
            "destinationCountry": "US",
            "destinationState": dest_state,
            "destinationZipcode": dest_zip,
            "originCity": ori_city,
            "originCountry": "US",
            "originState": ori_state,
            "originZipcode": ori_zip,
            "rateTypesList[]": ["LTL", "Guaranteed"],
            "uom": "METRIC",
            "accessorialsList[]": ["APD", "CTO"],
            "vendorIdList[]": [],
            "pickupDate": datetime.today().strftime("%Y-%m-%d"),
            "freightInfo": json.dumps([{
                "qty": qty,
                "weight": 660,
                "weightType": "each",
                "length": 48,
                "width": 40,
                "height": 72,
                "dimType": "PLT",
                "stack": False
            }])
        }

        username = "anoop.raghavan@agraga.com"
        password = "agraga24"

        token = get_access_token(username, password)
        api_response = fetch_shipping_rates(token, query_params)

        if not api_response or "data" not in api_response or "results" not in api_response["data"]:
            log_heyprimo_result(ori_city, ori_state, ori_zip, dest_city, dest_state, dest_zip, qty, "Failed", "No response or missing data/results")
            return None

        rates = api_response["data"]["results"]["rates"]
        if not rates:
            log_heyprimo_result(ori_city, ori_state, ori_zip, dest_city, dest_state, dest_zip, qty, "Failed", "Empty rates list")
            return None

        data_list = []
        for rate in rates:
            freight_charge = next((item["total"] for item in rate["rateBreakdown"] if item["name"] == "FREIGHT CHARGE"), 0)
            appointment_charge = next((item["total"] for item in rate["rateBreakdown"] if item["name"] == "APPOINTMENT AT DESTINATION"), 0)

            data_list.append({
                "Carrier": rate["name"],
                "SCAC": rate["SCAC"],
                "Service Level": rate["serviceLevel"],
                "Transit Days": rate["transitDays"],
                "Rate Type": rate["rateType"],
                "Total Cost": rate["total"],
                "Freight Charge": freight_charge,
                "Appointment Charge": appointment_charge
            })

        df = pd.DataFrame(data_list)
        filtered_df = df[df['SCAC'].isin(['CNWY', 'UPGF', 'EXLA', 'ABFS'])]

        if filtered_df.empty:
            log_heyprimo_result(ori_city, ori_state, ori_zip, dest_city, dest_state, dest_zip, qty, "Failed", "No rates matched preferred SCAC list")
            return None

        best_rate = filtered_df.nsmallest(1, 'Total Cost').iloc[0]
        result = {
            "Lowest Rate": best_rate["Total Cost"],
            "Carrier Name": best_rate["Carrier"]
        }

        log_heyprimo_result(ori_city, ori_state, ori_zip, dest_city, dest_state, dest_zip, qty, "Success", f"Rate: {result['Lowest Rate']}, Carrier: {result['Carrier Name']}")
        return result

    except Exception as e:
        log_heyprimo_result(row.get('Origin City', ''), row.get('Origin State Code', ''), row.get("Origin ZIP", ""), 
                            row.get('Destn City',''), row.get('Destn State Code', ''), row.get("FBA or Destination ZIP", ""), 
                            row.get("Num Of Pallet", ""), "Failed", f"Exception: {str(e)}")
        return None
