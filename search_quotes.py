import pandas as pd
import ast, json
import streamlit as st
from io import BytesIO

def search_quotations_app():
    quotation_number = st.text_input("Enter Quotation Number", placeholder="e.g., 123456")

    if quotation_number:
        try:
            df = pd.read_excel(r"Logs/quotations.xlsx")

            # Load booking logs from both sheets
            summary_df = pd.read_excel(r"Logs/bookings_log.xlsx", sheet_name="Summary")
            breakdown_df = pd.read_excel(r"Logs/bookings_log.xlsx", sheet_name="Breakdown")

            filtered_df = df[df['Agquote ID'].astype(str) == quotation_number]

            if filtered_df.empty:
                st.warning("⚠️ No records found for this quotation number.")
                return

            # ---------------- Show Destinations ----------------
            for _, row in filtered_df.iterrows():
                service_modes_list = ast.literal_eval(row['Service Modes'])
                result = ", ".join(service_modes_list)

                with st.expander(f"📍 FBA Code: {row['FBA Code']} ({str(row['FBA Zip Code']).zfill(5)})"):
                    st.markdown(f"""**POL:** {row['POL']} | **POD:** {row['POD']} | **POD ZIP:** {str(row['POD Zip']).zfill(5)} """)
                    st.markdown(f"""**CBM:** {row['Total CBM']} | **Pallets:** {row['Total Pallets']} | **Weight:** {row['Total Weight']} """)
                    st.markdown(f"""**Pickup Charges:** {row['Pick-Up Charges']} | **P2P Charges:** {row['PER CBM P2P']} | **OCC:** {row['OCC']} | **DCC:** {row['DCC']} """)
                    st.markdown(f"""**Category:** {row['category']} | **Service Modes:** {result}""")

                    cols = st.columns(4)
                    for idx, mode in enumerate(["LTL", "FTL", "FTL53", "Drayage"]):
                        value = row[mode]
                        if pd.isna(value) or str(value).strip().lower() in ["none", "nan", ""]:
                            with cols[idx]:
                                st.markdown(f"#### {mode} Rates")
                                st.info("Not Available")
                            continue
                        if isinstance(value, str):
                            try:
                                value = ast.literal_eval(value)
                            except:
                                try:
                                    value = json.loads(value)
                                except:
                                    continue
                        if isinstance(value, dict) and value:
                            clean_dict = {k: ("" if pd.isna(v) else v) for k, v in value.items()}
                            with cols[idx]:
                                st.markdown(f"#### {mode} Rates")
                                st.dataframe(pd.DataFrame([clean_dict]), use_container_width=True)

                    lowest_rate = row['Selected lm']
                    st.markdown("---")
                    st.subheader("🏆 Lowest Rate")
                    if pd.isna(lowest_rate) or str(lowest_rate).strip().lower() in ['none', 'nan', '']:
                        st.info("Not Available")
                    else:
                        if isinstance(lowest_rate, str):
                            try:
                                lowest_rate = ast.literal_eval(lowest_rate)
                            except:
                                try:
                                    lowest_rate = json.loads(lowest_rate)
                                except:
                                    continue
                        if isinstance(lowest_rate, dict) and lowest_rate:
                            clean_dict = {k: ("" if pd.isna(v) else v) for k, v in lowest_rate.items()}
                            st.dataframe(pd.DataFrame([clean_dict]), use_container_width=True)

            # ---------------- After All Destinations ----------------
            bookings_for_quote = summary_df[summary_df['Quotation Number'].astype(str) == quotation_number]
            
            booking_count = len(list(bookings_for_quote['Booking ID'].unique()))

            if booking_count > 0:
                st.markdown("---")
                st.markdown(f"**📦 Number of Bookings for this Quotation:** `{booking_count}`")

                # Direct single-click download
                buffer = BytesIO()
                with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                    # ✅ Loop over unique booking IDs so we capture multiple rows for each
                    for booking_id in bookings_for_quote['Booking ID'].unique():
                        booking_num = booking_id.split(" ")[1]

                        # ✅ Get all matching summary rows for this booking
                        booking_summary = bookings_for_quote[
                            (bookings_for_quote['Booking ID'] == booking_id) &
                            (bookings_for_quote['Quotation Number'] == quotation_number)
                        ]

                        # ✅ Get all matching breakdown rows
                        booking_breakdown = breakdown_df[
                            (breakdown_df['Booking ID'] == booking_id) &
                            (breakdown_df['Quotation Number'] == quotation_number)
                        ]

                        # Write summary table
                        booking_summary.to_excel(writer, sheet_name=f"{booking_id}", index=False, startrow=1)

                        # Write breakdown below summary
                        start_row = len(booking_summary) + 4
                        booking_breakdown.to_excel(writer, sheet_name=f"{booking_id}", index=False, startrow=start_row)

                        # Add headers
                        ws = writer.sheets[f"{booking_id}"]
                        ws.cell(row=1, column=1).value = "📦 Summary Table"
                        ws.cell(row=start_row, column=1).value = "📊 Detailed Breakdown"

                # Finalize Excel data
                buffer.seek(0)

                st.download_button(
                    label="📤 Export All Bookings to Excel",
                    data=buffer,
                    file_name=f"Bookings_{quotation_number}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )


        except FileNotFoundError:
            st.error("`Logs/quotations.xlsx` or `Logs/booking_logs.xlsx` not found.")
        except Exception as e:
            st.error(f"Error reading data: {e}")
