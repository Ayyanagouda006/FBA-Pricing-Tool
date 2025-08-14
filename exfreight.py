import requests
import pandas as pd
from datetime import datetime, date
import os
from math import ceil

LOG_FILE = r"Logs/exfreight_api_log.xlsx"

def log_to_excel(log_data):
    # Create log DataFrame
    log_df = pd.DataFrame([log_data])

    if os.path.exists(LOG_FILE):
        existing_df = pd.read_excel(LOG_FILE)
        final_df = pd.concat([existing_df, log_df], ignore_index=True)
    else:
        final_df = log_df

    final_df.to_excel(LOG_FILE, index=False)


def api(origin, destination, weight, qty,quote_id):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_data = {
        "Quotation Number":quote_id,
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
            log_data['Source'] = ""
            log_to_excel(log_data)
            return {"error": f"API error: {response.status_code}", "message": response.text}

        data = response.json()

        if "routes" not in data or not data["routes"]:
            log_data["Status"] = "Error"
            log_data["Message"] = "No routes returned by API"
            log_data['Source'] = ""
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
            log_data['Source'] = ""
            log_to_excel(log_data)
            return {"error": "No valid rate rows parsed", "raw_response": data}

        df = pd.DataFrame(rows)
        best_rate = df.nsmallest(1, 'Total Charge (USD)').iloc[0]

        log_data["Status"] = "Success"
        log_data["Carrier Name"] = best_rate["Carrier Name"]
        log_data["Rate (USD)"] = best_rate["Total Charge (USD)"]
        log_data["Message"] = "Success"
        log_data['Source'] = "API"
        log_to_excel(log_data)

        return {
            "Lowest Rate": best_rate["Total Charge (USD)"],
            "Carrier Name": best_rate["Carrier Name"]
        }

    except Exception as e:
        log_data["Status"] = "Error"
        log_data["Message"] = str(e)
        log_data['Source'] = ""
        log_to_excel(log_data)
        return {"error": "Exception occurred", "message": str(e)}
    
def exfreight_api(origin, destination, weight, qty, quote_id):
    df = pd.read_excel(r"Data/API Data/exfreight_output.xlsx")
    origin = str(origin).zfill(5)
    destination = str(destination).zfill(5)
    df['FPOD ZIP'] = df['FPOD ZIP'].astype(str).str.zfill(5)
    df['FBA ZIP'] = df['FBA ZIP'].astype(str).str.zfill(5)
    # Filter matching rows
    match = df[
        (df['FPOD ZIP'] == origin) &
        (df['FBA ZIP'] == destination) &
        (df['Pallets'] == qty)
    ]
    # print(origin, destination, weight, qty)
    # print('Matching Rows lenght:',len(match))

    if not match.empty:
        valid_rows = match[
            match['Rate'].notna() & (match['Rate'] != '') &
            match['Carrier Name'].notna() & (match['Carrier Name'] != '')
        ]

        if not valid_rows.empty:
            row = valid_rows.iloc[0]
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_data = {
                "Quotation Number":quote_id,
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

            log_data["Status"] = "Success"
            log_data["Carrier Name"] = row["Carrier Name"]
            log_data["Rate (USD)"] = row["Rate"]
            log_data["Message"] = "Success"
            log_data['Source'] = "API"
            log_to_excel(log_data)
            return {
                "Lowest Rate": row["Rate"],
                "Carrier Name": row["Carrier Name"]
            }

    # Fallback to API
    return api(origin, destination, weight, qty, quote_id)

