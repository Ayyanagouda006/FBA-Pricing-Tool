import re
import pandas as pd
from heyprimo import heyprimo_api
from exfreight import exfreight_api
from jbhunt import jbhunt_api
from math import ceil

def ltl_rate(fpod_city, fpod_st_code, fpod_zip, fba_city, fba_st_code, fba_zip, qty, weight):
    # Read offline last mile rates
    lm = pd.read_excel(r"Data/Last Mile Rates (no api).xlsx", "Last Mile Rates (no api)")
    lm = lm[lm['Delivery Type'] == "LTL"]

    # Step 1: Get API results
    hp_result = heyprimo_api({
        "Origin City": fpod_city,
        "Origin State Code": fpod_st_code,
        "Origin ZIP": fpod_zip,
        "Destn City": fba_city,
        "Destn State Code": fba_st_code,
        "FBA or Destination ZIP": fba_zip,
        "Num Of Pallet": qty
    })

    ef_result = exfreight_api(fpod_zip, fba_zip, weight, qty)

    # Step 2: Parse rates from API safely
    candidates = []

    if isinstance(hp_result, dict) and "Lowest Rate" in hp_result:
        candidates.append({
            "Rate": round(float(hp_result["Lowest Rate"]), 2),
            "Carrier Name": hp_result["Carrier Name"],
            "Service Provider": "HeyPrimo"
        })

    if isinstance(ef_result, dict) and "Lowest Rate" in ef_result:
        candidates.append({
            "Rate": round(float(ef_result["Lowest Rate"]), 2),
            "Carrier Name": ef_result["Carrier Name"],
            "Service Provider": "Ex-Freight"
        })

    # Step 3: Find offline Excel rates (exact match by zip + pallet count)
    try:
        offline_match = lm[
            (lm['FPOD ZIP'].astype(str).str.zfill(5) == str(fpod_zip).zfill(5)) &
            (lm['FBA ZIP'].astype(str).str.zfill(5) == str(fba_zip).zfill(5)) &
            (lm['No. of pallets'] == qty)
        ]

        for _, row in offline_match.iterrows():
            candidates.append({
                "Rate": round(float(row['Rate']), 2),
                "Carrier Name": row['Carrier Name'],
                "Service Provider": row["Broker"]
            })
    except Exception as e:
        print("Error matching offline Excel rate:", e)

    # Step 4: Pick the lowest rate
    if candidates:
        return min(candidates, key=lambda x: x["Rate"])
    else:
        return None
    
def ftl_rate(fpod_zip, fba_zip, qty):
    lm = pd.read_excel(r"Data/Last Mile Rates (no api).xlsx", "Last Mile Rates (no api)")
    
    # Separate FTL and FTL53 sheets
    lm_ftl = lm[lm['Delivery Type'] == "FTL"]
    lm_ftl53 = lm[lm['Delivery Type'] == "FTL53"]

    ftl_cand = []
    ftl_match = lm_ftl[
        (lm_ftl['FPOD ZIP'].astype(str).str.zfill(5) == str(fpod_zip).zfill(5)) &
        (lm_ftl['FBA ZIP'].astype(str).str.zfill(5) == str(fba_zip).zfill(5))
    ]

    for _, row in ftl_match.iterrows():
        ftl_cand.append({
            "Rate": round(float(row['Rate']), 2),
            "Carrier Name": row['Carrier Name'],
            "Service Provider": row["Broker"]
        })

    ftl53_cand = []
    ftl53_match = lm_ftl53[
        (lm_ftl53['FPOD ZIP'].astype(str).str.zfill(5) == str(fpod_zip).zfill(5)) &
        (lm_ftl53['FBA ZIP'].astype(str).str.zfill(5) == str(fba_zip).zfill(5))
    ]

    for _, row in ftl53_match.iterrows():
        ftl53_cand.append({
            "Rate": round(float(row['Rate']), 2),
            "Carrier Name": row['Carrier Name'],
            "Service Provider": row["Broker"]
        })

    # Safely return min if any rates were found, else None
    best_ftl = min(ftl_cand, key=lambda x: x["Rate"]) if ftl_cand else None
    best_ftl53 = min(ftl53_cand, key=lambda x: x["Rate"]) if ftl53_cand else None

    return best_ftl, best_ftl53

def rates_comparison(fpod_city, fpod_st_code, fpod_zip, fba_city, fba_st_code, fba_zip, total_pallet_count, weight, service_modes):
        # Your external rate functions
    ltl = ltl_rate(fpod_city, fpod_st_code, fpod_zip, fba_city, fba_st_code, fba_zip, total_pallet_count, weight)
    ftl, ftl53 = ftl_rate(fpod_zip, fba_zip, total_pallet_count)
    drayage = jbhunt_api(fpod_zip, fba_zip, weight)
    # Step 1: Associate each rate with a label
    rate_dicts = {
        "LTL": ltl,
        "FTL": ftl,
        "FTL53": ftl53,
        "Drayage": drayage
    }

    # Step 2: Filter out None or invalid entries (non-dict or missing/invalid Rate)
    valid_rates = {
        k: v for k, v in rate_dicts.items()
        if isinstance(v, dict) and isinstance(v.get("Rate"), (int, float)) and v["Rate"] > 0
    }

    # Step 3: Determine the lowest valid rate
    if valid_rates:
        min_type = min(valid_rates, key=lambda k: valid_rates[k]["Rate"])
        min_data = valid_rates[min_type]
        lowest = {
            "Rate Type": min_type,
            "Rate": min_data["Rate"],
            "Carrier Name": min_data.get("Carrier Name", ""),
            "Service Provider": min_data.get("Service Provider", "")
        }
    else:
        lowest = {
            "Rate Type": "N/A",
            "Rate": 0.0,
            "Carrier Name": "",
            "Service Provider": ""
        }

    service_valid_rates = {
        rate_type: rate_data
        for rate_type, rate_data in rate_dicts.items()
        if rate_type in service_modes and isinstance(rate_data, dict)
        and isinstance(rate_data.get("Rate"), (int, float)) and rate_data["Rate"] > 0
    }

    # Step 3: Find the lowest valid rate among available services
    if service_valid_rates:
        min_type = min(service_valid_rates, key=lambda k: service_valid_rates[k]["Rate"])
        min_data = service_valid_rates[min_type]
        selected_lowest = {
            "Rate Type": min_type,
            "Rate": min_data["Rate"],
            "Carrier Name": min_data.get("Carrier Name", ""),
            "Service Provider": min_data.get("Service Provider", "")
        }
    else:
        selected_lowest = {
            "Rate Type": "N/A",
            "Rate": 0.0,
            "Carrier Name": "",
            "Service Provider": ""
        }

    return ltl,ftl,ftl53,drayage,lowest,selected_lowest

def classify_fba_code(fba_locations: pd.DataFrame, fba_code: str, quote_cbm: float) -> str:
    """
    Classifies the FBA code into HOT, WARM, or COLD based on activity and quote CBM.

    Args:
        fba_locations (pd.DataFrame): DataFrame with FBA location data.
        fba_code (str): The FBA code to classify.
        quote_cbm (float): The CBM value from the quote.

    Returns:
        str: "HOT", "WARM", or "COLD"
    """
    # Filter the DataFrame to the relevant FBA code
    sub_df = fba_locations[fba_locations["FBA Code"] == fba_code]

    if sub_df.empty:
        return "COLD"  # Default if FBA code not found

    last_10_weeks = sub_df["Last 10 weeks"].values[0]
    last_1_week = sub_df["Last 1 Week"].values[0]

    if (
        last_10_weeks > 500
        or (last_10_weeks < 500 and quote_cbm > 35)
        or last_1_week > 65
    ):
        return "HOT"
    elif quote_cbm > 15 or last_1_week > 25:
        return "WARM"
    else:
        return "COLD"
    
def console_lmservice(category, fpod, des_val, pallets, quote_cbm):
    fpod = fpod.upper()
    category = category.upper()
    des_val = des_val.lower()

    # Condition 1
    if fpod in ["USNYC", "USCHS"] and des_val == "single":
        return "condition1", "Own Console", ["Drayage"]

    # Condition 2
    if fpod in ["USNYC", "USCHS"] and des_val == "multiple":
        if pallets > 12:
            return "condition2", "Own Console", ["FTL53"]
        else:
            return "condition2", "Own Console", ["FTL", "FTL53", "LTL"]

    # Condition 3
    if fpod not in ["USNYC", "USCHS"] and category == "HOT" and des_val == "single":
        return "condition3", "Own Console", ["Drayage"]

    # Condition 4
    if fpod not in ["USNYC", "USCHS"] and des_val == "multiple" and quote_cbm > 25:
        if pallets > 12:
            return "condition4", "Own Console", ["FTL53"]
        else:
            return "condition4", "Own Console", ["FTL", "FTL53", "LTL"]

    # Condition 5
    if fpod not in ["USNYC", "USCHS"] and category == "WARM":
        if pallets > 12:
            return "condition5", "Coload", ["FTL53"]
        else:
            return "condition5", "Own Console", ["FTL", "FTL53"]

    # Condition 6
    if fpod not in ["USNYC", "USCHS"] and category == "COLD":
        return "condition6", "Coload", ["FTL", "LTL"]

    # Default fallback
    return "", "not selected", []


def rates(origin, cleaned_data, console_type, is_occ, is_dcc, des_val, service_modes, shipment_scope, pickup_charges):
    if shipment_scope == "Door-to-Door":
        if pickup_charges in [0.0, "0.0", "", None]:
            return {}, ["Pickup charges are required for Door-to-Door shipment scope."]

    # Load Excel sheets
    try:
        fba_locations = pd.read_excel(r"Data/FBA Rates.xlsx", 'FBA Locations')
        p2p = pd.read_excel(r"Data/FBA Rates.xlsx", 'P2P')
        accessorials = pd.read_excel(r"Data/FBA Rates.xlsx", 'Accessorials')
        palletization = pd.read_excel(r"Data/FBA Rates.xlsx", 'Palletization')
    except Exception as e:
        return {}, [f"❌ Failed to load one or more Excel sheets: {e}"]

    results = {}
    errors = []

    for dest in cleaned_data:
        destination_name = dest.get("destination", "")
        cargo_details = dest.get("cargoDetails", [])

        qty = 0
        weight = 0.0
        pallets = 0
        loose_cbm = 0.0
        total_cbm = 0.0

        for item in cargo_details:
            try:
                package = item.get("packageType", "")
                item_qty = int(item.get("numPackages", 0))
                item_weight = float(item.get("totalWeight", 0.0))
                item_cbm = float(item.get("totalVolume", 0.0))

                qty += item_qty
                weight += item_weight
                total_cbm += item_cbm

                if package.lower() == "pallet":
                    pallets += item_qty
                else:
                    loose_cbm += item_cbm
            except Exception as e:
                errors.append(f"❌ Error parsing cargo for {destination_name}: {e}")
                continue

        loose_as_pallets = ceil(loose_cbm / 1.8)
        total_pallet_count = pallets + loose_as_pallets

        fba_code = destination_name.split(" ")[0]
        sub_fba_locations = fba_locations[fba_locations['FBA Code'] == fba_code]

        if sub_fba_locations.empty:
            errors.append(f"⚠️ FBA Code {fba_code} not found in FBA Locations sheet.")
            continue

        try:
            category = classify_fba_code(fba_locations, fba_code, total_cbm)
        except Exception as e:
            category = "Unknown"
            errors.append(f"⚠️ Error classifying FBA code {fba_code}: {e}")

        for i, row in sub_fba_locations.iterrows():
            fpod_zip = str(row['FPOD ZIP']).zfill(5)
            fpod_city = row['FPOD CITY']
            fpod_unloc = row['FPOD UNLOC']
            fpod_st_code = row['FPOD STATE CODE']
            fba_zip = str(row['FBA ZIP']).zfill(5)
            fba_city = row['FBA CITY']
            fba_st_code = row['FBA STATE CODE']

            condition, console, service_mode = console_lmservice(
                category, fpod_unloc, des_val, total_pallet_count, total_cbm
            )

            if console_type == "not selected" and console_type != "both selected":
                console_type = console
            if service_modes == []:
                service_modes = service_mode

            try:
                ltl, ftl, ftl53, drayage, lowest, selected_lowest = rates_comparison(
                    fpod_city, fpod_st_code, fpod_zip,
                    fba_city, fba_st_code, fba_zip,
                    total_pallet_count, weight, service_modes
                )
            except Exception as e:
                errors.append(f"❌ Rate comparison failed for {destination_name} (FBA {fba_code}): {e}")
                continue

            if console_type.lower() == "both selected":
                sub_p2p = p2p[p2p['FPOD UNLOC'] == fpod_unloc]
            else:
                sub_p2p = p2p[
                    (p2p['FPOD UNLOC'] == fpod_unloc) &
                    (p2p['P2P Type'].str.lower() == console_type.lower())
                ]

            if sub_p2p.empty:
                errors.append(f"⚠️ No P2P match found for FPOD {fpod_unloc}, console type: {console_type}")
                continue


            for j, prow in sub_p2p.iterrows():
                try:
                    pol = prow['POL Name']
                    pol_unloc = prow['POR/POL']
                    percbm_p2p = prow['Per CBM(USD)']
                    total_p2p = percbm_p2p * total_cbm
                    console = prow['P2P Type']

                    if shipment_scope == "Port-to-Door":
                        try:
                            origin_unloc = re.search(r'\((.*?)\)', origin).group(1)
                        except Exception as e:
                            errors.append(f"⚠️ Failed to parse POL from origin string '{origin}': {e}")
                            continue

                        if pol_unloc != origin_unloc:
                            continue

                    try:
                        pod_doc = accessorials[
                            (accessorials['Location Unloc'] == fpod_unloc) & 
                            (accessorials['Charge Head'] == 'Documentation')
                        ]['Amount'].values[0]
                    except IndexError:
                        errors.append(f"⚠️ Documentation charge missing for {fpod_unloc}")
                        pod_doc = 0

                    try:
                        occ = accessorials[
                            (accessorials['Location Unloc'] == pol_unloc) & 
                            (accessorials['Charge Head'] == 'OCC')
                        ]['Amount'].values[0] if is_occ else 0
                    except IndexError:
                        if is_occ:
                            errors.append(f"⚠️ OCC charge missing for {pol_unloc}")
                        occ = 0

                    try:
                        dcc = accessorials[
                            (accessorials['Location Unloc'] == fpod_unloc) & 
                            (accessorials['Charge Head'] == 'DCC')
                        ]['Amount'].values[0] if is_dcc else 0
                    except IndexError:
                        if is_dcc:
                            errors.append(f"⚠️ DCC charge missing for {fpod_unloc}")
                        dcc = 0

                    try:
                        pal_cost = palletization[
                            (palletization['FPOD UNLOC'] == fpod_unloc) &
                            (palletization['Service Type'] == 'Palletization cost Per Pallet')
                        ]['Amount'].values[0]
                        palletization_cost = float(pal_cost) * total_pallet_count
                    except IndexError:
                        errors.append(f"⚠️ Palletization Cost missing for {fpod_unloc}")
                        palletization_cost = 0.0

                    if destination_name not in results:
                        results[destination_name] = {}

                    if shipment_scope == "Door-to-Door":
                        gtotal = float(selected_lowest["Rate"]) + float(total_p2p) + float(pod_doc) + float(occ) + float(dcc) + float(pickup_charges) + float(palletization_cost)
                    else:
                        gtotal = float(selected_lowest["Rate"]) + float(total_p2p) + float(pod_doc) + float(occ) + float(dcc) + float(palletization_cost)

                    tot_pcbm = gtotal / total_cbm if total_cbm else 0

                    results[destination_name][console] = {
                        "Shipment Scope":shipment_scope,
                        "Origin": origin,
                        "POL": pol,
                        "POD": fpod_city,
                        "POD Zip": fpod_zip,
                        "FBA Code": fba_code,
                        "FBA Zip Code": fba_zip,
                        "Qty": qty,
                        "Total Weight": weight,
                        "Total CBM": total_cbm,
                        "Total Pallets": total_pallet_count,
                        "category": category,
                        "Service Modes": service_modes,
                        "condition": condition,
                        "LTL": ltl,
                        "FTL": ftl,
                        "FTL53": ftl53,
                        "Drayage": drayage,
                        'lowest lm': lowest,
                        'Selected lm': selected_lowest,
                        "Pick-Up Charges": pickup_charges,
                        "PER CBM P2P": percbm_p2p,
                        "P2P Charge": total_p2p,
                        "Destination Doc": float(pod_doc),
                        "OCC": float(occ),
                        "DCC": float(dcc),
                        "Documentation": float(pod_doc),
                        "Palletization Cost": + float(palletization_cost),
                        "Last Mile Rate": selected_lowest["Rate"],
                        "Total Cost": gtotal,
                        "Total per cbm": tot_pcbm
                    }
                except Exception as e:
                    errors.append(f"❌ Error processing P2P row for {destination_name}: {e}")

    return results, errors
