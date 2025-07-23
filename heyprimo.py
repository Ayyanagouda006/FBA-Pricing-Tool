import requests
import json
import pandas as pd
from datetime import datetime

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
        return None

    rates = api_response["data"]["results"]["rates"]
    if not rates:
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
        return None

    best_rate = filtered_df.nsmallest(1, 'Total Cost').iloc[0]

    return {"Lowest Rate": best_rate["Total Cost"], "Carrier Name": best_rate["Carrier"]}