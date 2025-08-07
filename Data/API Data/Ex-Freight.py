#!/usr/bin/env python
# coding: utf-8

# In[2]:


import requests
import pandas as pd
from datetime import datetime, date
import os
from math import ceil
from tqdm import tqdm

LOG_FILE = r"D:\Ayyanagouda\Last Mile Rates\Logs\exfreight_api_log.xlsx"

def log_to_excel(log_data):
    log_df = pd.DataFrame([log_data])
    try:
        if os.path.exists(LOG_FILE):
            existing_df = pd.read_excel(LOG_FILE)
            final_df = pd.concat([existing_df, log_df], ignore_index=True)
        else:
            final_df = log_df
    except Exception as e:
        # Fall back to fresh file if read fails
        print(f"⚠️ Failed to read existing log file: {e}. Creating a new one.")
        final_df = log_df

    final_df.to_excel(LOG_FILE, index=False)



def exfreight_api(origin, destination, weight, qty):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_data = {
        "Timestamp": timestamp,
        "Origin": origin,
        "Destination": destination,
        "Weight (kg)": ceil(weight),
        "Quantity": qty,
        "Status": "",
        "Message": "",
        "Carrier Name": "",
        "Rate (USD)": ""
    }

    url = "https://exfreight.flipstone.com/api/v2/rating"

    headers = {
        "Authorization": "token 84fab4ca8d33fc1b",
        "Exfresso-Partner-Id": "20b81740-778e-43fd-8dfe-722c35179aab",
        "Content-Type": "application/json"
    }

    payload = {
        "username": "anshul.marele@agraga.com",
        "pickup": {"country": "US", "postal": origin},
        "delivery": {"country": "US", "postal": destination},
        "ship_day": date.today().strftime("%Y-%m-%d"),
        "ltl": {
            "accessorials": [
                {"category": "amazon_fba_delivery", "scope": "at_delivery"},
                {"category": "ocean_cfs_pickup", "scope": "at_pickup"}
            ],
            "freight_class": "85",
            "items": [
                {
                    "description": "GENERAL",
                    "dimensioned_pieces": {
                        "height": {"unit": "inch", "value": 72},
                        "length": {"unit": "inch", "value": 48},
                        "quantity": qty,
                        "width": {"unit": "inch", "value": 40}
                    },
                    "is_hazardous": False,
                    "total_weight": {"unit": "kilogram", "value": ceil(weight)}
                }
            ]
        },
        "product": "all",
        "result_filtering": None
    }

    try:
        response = requests.post(url, headers=headers, json=payload)

        if not response.ok:
            log_data["Status"] = "Error"
            log_data["Message"] = f"{response.status_code} - {response.text}"
            log_to_excel(log_data)
            return {"error": f"API error: {response.status_code}", "message": response.text}

        data = response.json()

        if "routes" not in data or not data["routes"]:
            log_data["Status"] = "Error"
            log_data["Message"] = "No routes returned by API"
            log_to_excel(log_data)
            return {"error": "No routes returned by API", "raw_response": data}

        rows = []
        for route in data['routes']:
            try:
                row = {
                    'Carrier Name': route['legs'][0]['carrier']['name'],
                    'SCAC': route['scac'],
                    'Quote Reference ID': route['bill_of_lading_details'].get('carrier_quote_reference_id'),
                    'Service Description': route['bill_of_lading_details'].get('carrier_service_description'),
                    'Pickup Date': route['legs'][0].get('scheduled_pickup_date'),
                    'Delivery Date': route['legs'][0].get('scheduled_delivery_date'),
                    'Transit Days': route.get('transit_days'),
                    'Total Charge (USD)': route['total_charge']['value'] / 100,
                    'Reliability (%)': route.get('overall_on_time_reliability'),
                    'Valid Until': route.get('valid_until'),
                    'Freight Charge': next((item['charge']['value'] / 100 for item in route['line_item_charges'] if 'Freight' in item['description']), 0),
                    'FBA Delivery Charge': next((item['charge']['value'] / 100 for item in route['line_item_charges'] if 'FBA Delivery' in item['description']), 0),
                }
                rows.append(row)
            except Exception as e:
                continue

        if not rows:
            log_data["Status"] = "Error"
            log_data["Message"] = "No valid rate rows parsed"
            log_to_excel(log_data)
            return {"error": "No valid rate rows parsed", "raw_response": data}

        df = pd.DataFrame(rows)
        best_rate = df.nsmallest(1, 'Total Charge (USD)').iloc[0]

        log_data["Status"] = "Success"
        log_data["Carrier Name"] = best_rate["Carrier Name"]
        log_data["Rate (USD)"] = best_rate["Total Charge (USD)"]
        log_data["Message"] = "Success"
        log_to_excel(log_data)

        return {
            "Lowest Rate": best_rate["Total Charge (USD)"],
            "Carrier Name": best_rate["Carrier Name"]
        }

    except Exception as e:
        log_data["Status"] = "Error"
        log_data["Message"] = str(e)
        log_to_excel(log_data)
        return {"error": "Exception occurred", "message": str(e)}

# Read the template
template = pd.read_excel(r"D:\Ayyanagouda\Last Mile Rates\Data\API Data\Template for last mile rates.xlsx")

response_rows = []

for i, rows in tqdm(template.iterrows(), total=len(template), desc="Origin-Destination Pairs"):
    fpod_zip = str(rows['Origin ZIP']).zfill(5)
    fpod_city = rows['Origin City']
    fpod_state_code = rows['Origin State Code']
    fba_code = rows['FBA Code']
    fba_zip = str(rows['FBA or Destination ZIP']).zfill(5)
    fba_city = rows['Destn City']
    fba_state_code = rows['Destn State Code']
    pallets = rows['Num Of Pallet']
    weight = pallets * 1000

    result = exfreight_api(fpod_zip, fba_zip, weight, pallets)

    # Handle response safely
    if "Lowest Rate" in result and "Carrier Name" in result:
        rate = result["Lowest Rate"]
        carrier = result["Carrier Name"]
    else:
        rate = None
        carrier = None

    response_rows.append({
        'FPOD ZIP': fpod_zip,
        'FPOD CITY': fpod_city,
        'FPOD STATE CODE': fpod_state_code,
        'FBA Code': fba_code,
        'FBA ZIP': fba_zip,
        'FBA CITY': fba_city,
        'FBA STATE CODE': fba_state_code,
        'Pallets': pallets,
        'Weight': weight,
        'Rate': rate,
        'Carrier Name': carrier
    })

# Convert to DataFrame
response = pd.DataFrame(response_rows)

response = pd.DataFrame(response_rows)
response.to_excel(r"D:\Ayyanagouda\Last Mile Rates\Data\API Data\exfreight_output.xlsx")


# In[3]:





# In[8]:





# In[ ]:




