import pandas as pd
import ast, json
import streamlit as st

def search_quotations_app():

    # Input for quotation number
    quotation_number = st.text_input("Enter Quotation Number", placeholder="e.g., 123456")

    if quotation_number:
        try:
            df = pd.read_excel(r"Logs/quotations.xlsx")

            # Filter rows matching the quotation number
            filtered_df = df[df['Agquote ID'].astype(str) == quotation_number]

            if filtered_df.empty:
                st.warning("⚠️ No records found for this quotation number.")
                return

            for _, row in filtered_df.iterrows():
                service_modes_list = ast.literal_eval(row['Service Modes'])
                result = ", ".join(service_modes_list)
                with st.expander(f"📍 FBA Code: {row['FBA Code']}({str(row['FBA Zip Code']).zfill(5)})"):
                    # Summary metrics
                    st.markdown(f"""**POL:** {row['POL']} | **POD:** {row['POD']} | **POD ZIP:** {str(row['POD Zip']).zfill(5)} """)
                    st.markdown(f"""**CBM:** {row['Total CBM']} | **Pallets:** {row['Total Pallets']} | **Weight:** {row['Total Weight']} """)
                    st.markdown(f"""**Pickup Charges:** {row['Pick-Up Charges']} | **P2P Charges:** {row['PER CBM P2P']} | **OCC:** {row['OCC']} | **DCC:** {row['DCC']} """)
                    st.markdown(f"""**Category:** {row['category']} | **Service Modes:** {result}""")

                    # Service Mode Rates Side by Side
                    cols = st.columns(4)
                    for idx, mode in enumerate(["LTL", "FTL", "FTL53", "Drayage"]):
                        value = row[mode]

                        # Skip NaN or None-like values
                        if pd.isna(value) or str(value).strip().lower() in ["none", "nan", ""]:
                            with cols[idx]:
                                st.markdown(f"#### {mode} Rates")
                                st.info("Not Available")
                            continue

                        # Parse string representation into dict if needed
                        if isinstance(value, str):
                            try:
                                value = ast.literal_eval(value)
                            except Exception:
                                try:
                                    value = json.loads(value)
                                except Exception:
                                    continue  # skip if can't parse

                        # Ensure we have a dict
                        if isinstance(value, dict) and value:
                            # Replace NaN with empty string
                            clean_dict = {k: ("" if pd.isna(v) else v) for k, v in value.items()}

                            with cols[idx]:
                                st.markdown(f"#### {mode} Rates")
                                st.dataframe(pd.DataFrame([clean_dict]), use_container_width=True)

                    # Lowest Rate
                    lowest_rate = row['Selected lm']
                    st.markdown("---")  # separator
                    st.subheader("🏆 Lowest Rate")
                    if pd.isna(lowest_rate) or str(lowest_rate).strip().lower() in ['none', 'nan', '']:
                        st.info("Not Available")
                    else:
                        if isinstance(lowest_rate, str):
                            try:
                                lowest_rate = ast.literal_eval(lowest_rate)
                            except Exception:
                                try:
                                    lowest_rate = json.loads(lowest_rate)
                                except Exception:
                                    continue  # skip if can't parse

                        if isinstance(lowest_rate, dict) and lowest_rate:
                            clean_dict = {k: ("" if pd.isna(v) else v) for k, v in lowest_rate.items()}
                            st.dataframe(pd.DataFrame([clean_dict]), use_container_width=True)

        except FileNotFoundError:
            st.error("`Logs/quotations.xlsx` not found.")
        except Exception as e:
            st.error(f"Error reading quotations: {e}")
