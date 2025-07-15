import streamlit as st
import os
import pandas as pd
import fitz
import re
from datetime import date
from view import display_overall_summary,favorite_stores, plot_net_spend, plot_linear_spending
from general_pdf_extrract import extract_transactions_dynamically

def upload_pdf():
    # single uploader that shows built-in list + delete
    uploaded = st.file_uploader(
        label = "Upload PDF(s)", 
        type=["pdf"], 
        accept_multiple_files=True, 
        key="pdf_uploader"
    )
    if uploaded:
        for file in uploaded:
            # process each newly added PDF only once
            if file.name not in st.session_state.uploaded_pdfs:
                # 1) save
                os.makedirs("uploads", exist_ok=True)
                path = os.path.join("uploads", file.name)
                with open(path, "wb") as f:
                    f.write(file.read())
                st.success(f"Processed {file.name}")
                st.session_state.uploaded_pdfs.append(file.name)    
                
def show_csv():
    # extract & cache
    for file in st.session_state.uploaded_pdfs:
        path = os.path.join("uploads", file)
        doc = fitz.open(path)
        full_text = "".join(page.get_text() for page in doc)
        lines = [line.strip() for line in full_text.split('\n') if line.strip()]

        df = extract_transactions_dynamically(lines)
        start_date = pd.to_datetime(df['Date'].iloc[0]).date()
        end_date = pd.to_datetime(df['Date'].iloc[-1]).date()
        domain = f"{start_date}_to_{end_date}"
        st.session_state.pdf_dfs[domain] = df

    # List uploaded Excel/spreadsheets
    excel_list = st.session_state.pdf_dfs
    if excel_list:
        for domain, df in excel_list.items():
            col1, col2 = st.columns([4, 1])
            with col1:
                st.write(f"{domain}.csv")
            with col2:
                st.download_button(
                    label="📥", 
                    data=df.to_csv(index=False),
                    file_name=f"{domain}.csv",
                    mime="text/csv",
                    key=f"download_{domain}"
                )
    else:
        st.write("No spreadsheets uploaded yet.")
        
def choose_period():
    if "temp_date_range" not in st.session_state:
        st.session_state.temp_date_range = (st.session_state.start_date, st.session_state.end_date)
    if "confirmed_date_range" not in st.session_state:
        st.session_state.confirmed_date_range = pd.DataFrame()

    # 2. date picker
    date_range = st.date_input(
        "Choose period",
        value=st.session_state.temp_date_range,
    )

    # 3. confirm button
    if st.button("✅ Confirm date range"):
        if isinstance(date_range, tuple) and len(date_range) == 2:
            start, end = date_range
            st.session_state.confirmed_date_range = date_range
            st.session_state.start_date, st.session_state.end_date = date_range
            st.success(f"✔️ Confirmed date range: {start} to {end}")
        else:
            st.warning("⚠️ Please select a complete date range")     
            return pd.DataFrame() 
    return merge_dfs_in_period(st.session_state.pdf_dfs, st.session_state.start_date, st.session_state.end_date)

def find_year_near_period_keyword(lines, window=5, year_min=2000, year_max=2100):
    """
    Find the year near the period keyword in the 4 lines
    """
    for idx, line in enumerate(lines):
        if ('period' or 'Period') in line.lower():
            start = max(0, idx - window)
            end = min(len(lines), idx + window + 1)
            for i in range(start, end):
                years = re.findall(r'\b(20\d{2}|19\d{2})\b', lines[i])
                for y in years:
                    y_int = int(y)
                    if year_min <= y_int <= year_max:
                        return y_int  
    return None

def generate_excel_from_pdf(pdf_path):
    # Step 1: Read all text content from the PDF
    doc = fitz.open(pdf_path)
    full_text = ""
    for page in doc:
        full_text += page.get_text()

    # Step 2: Split the content into non-empty lines
    lines = [line.strip() for line in full_text.split('\n') if line.strip()]
    year = find_year_near_period_keyword(lines)
    
    #Step 3:
    transactions = []
    i = 0
    while i < len(lines) - 3:
        # Check if the line starts with a date (e.g., "Jun 5")
        if re.match(r'^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}$', lines[i]):
            trans_date = lines[i]
            post_date = lines[i+1] if re.match(r'^(Jan|Feb|Mar|...)\s+\d{1,2}$', lines[i+1]) else ""
            merchant_lines = []
            amount = None

            j = i + 2
            while j < len(lines):
                amt_match = re.match(r'^-?\$?-?\d{1,4}(,\d{3})*\.\d{2}$', lines[j])
                if amt_match:
                    amount = float(lines[j].replace('$', '').replace(',', ''))
                    break
                else:
                    merchant_lines.append(lines[j])
                j += 1

            merchant = ' '.join(merchant_lines)
            i = j + 1
            
            if "THANK" in merchant:
                continue
            date_str = trans_date.split()[0] + ' ' + trans_date.split()[1] + ' ' + str(year)
            transactions.append({
                "Date": pd.to_datetime(date_str, format="%b %d %Y", errors="coerce"),
                "Merchant": merchant,
                "Amount": amount
            })
            
        else:
            i += 1

    df = pd.DataFrame(transactions)
    return df

def merge_dfs_in_period(pdf_dfs, start_date, end_date):
    in_period_dfs = []
    if pdf_dfs:  
        for df in pdf_dfs.values():
            mask = (df['Date'] >= pd.to_datetime(start_date)) & (df['Date'] <= pd.to_datetime(end_date))
            in_period_dfs.append(df[mask])
        if not len(in_period_dfs):
            st.error("No spreadsheets in the selected period.")
            return pd.DataFrame()
        return  pd.concat(in_period_dfs, ignore_index=True)
    else:
        st.error("No spreadsheets uploaded yet.") 
        return pd.DataFrame()

def summary_by_unit(df, unit):
    spend_list = []
    spend_date_list = []
    df_list = []
    
    df_copy = df.copy()
    if unit == 'Year':
        unique_values = sorted(df_copy['Date'].dt.year.dropna().unique())
        for value in unique_values:
            sub_df = df_copy[df_copy['Date'].dt.year == value]
            spend_list.append(sub_df['Amount'].sum())
            spend_date_list.append(value)
            df_list.append(sub_df)
    elif unit == 'Month':
        df_copy['YearMonth'] = df_copy['Date'].dt.year.astype(str) + '-' + df_copy['Date'].dt.month.astype(str).str.zfill(2)
        unique_values = sorted(df_copy['YearMonth'].dropna().unique())
        for value in unique_values:
            sub_df = df_copy[df_copy['YearMonth'] == value]
            spend_list.append(sub_df['Amount'].sum())
            spend_date_list.append(value)    
            df_list.append(sub_df)
    elif unit == 'Week':
        week_index = df_copy['Date'].dt.isocalendar().week
        year_index = df_copy['Date'].dt.isocalendar().year
        year_week = year_index.astype(str) + '-W' + week_index.astype(str).str.zfill(2)
        unique_values = sorted(year_week.dropna().unique())
        for value in unique_values:
            mask = (year_week == value)
            sub_df = df_copy[mask]
            spend_list.append(sub_df['Amount'].sum())
            spend_date_list.append(value)    
            df_list.append(sub_df)
    return  spend_list, spend_date_list, df_list

class Canvas:
    """
    HomePage controls the layout of the Streamlit dashboard.
    """
    def __init__(self):
        self.filtered_df = pd.DataFrame()

        # Ensure uploads directory exists
        os.makedirs('uploads', exist_ok=True)
        # Initialize session state only once
        if 'uploaded_pdfs' not in st.session_state:
            st.session_state.uploaded_pdfs = []
        if 'uploaded_excels' not in st.session_state:
            st.session_state.pdf_dfs = {}
        if 'view' not in st.session_state:
            st.session_state.view = 'Month'
            
        today = date.today()
        one_year_ago = date(today.year - 10, today.month, today.day)
        if 'start_date' not in st.session_state:
            st.session_state.start_date = one_year_ago
        if 'end_date' not in st.session_state:
            st.session_state.end_date = today

    def render(self):
        # Set wide layout
        st.set_page_config(page_title="Bank Dashboard", layout="wide")
        left_col, right_col = st.columns([1, 5])

        with left_col:
            self.render_sidebar()

        with right_col:
            self.render_period_selector()
            self.render_content()

    def render_sidebar(self):
        st.header("📁 File Manager")
        st.write("Drag and drop or select PDFs files below:")
        upload_pdf()
        st.subheader("Available Spreadsheets")
        show_csv()
         
    def render_period_selector(self):
        self.filtered_df = choose_period()

    def render_content(self):
        tabs = st.tabs(["Summary", "Favorite Stores", "Line Chart", "Net Spend Table"])
        with tabs[0]:
            self.render_summary()
        with tabs[1]:
            self.render_favorite_stores()
        with tabs[2]:
            self.render_dimension_selector("plot")
            self.render_plot_unit_spending()
        with tabs[3]:
            self.render_dimension_selector("net")
            self.render_net_spend_by_category()

    def render_summary(self):
        st.subheader(f"Summary")
        display_overall_summary(self.filtered_df)

    def render_favorite_stores(self):
        favorite_stores(self.filtered_df)

    def render_plot_unit_spending(self):
        if  not self.filtered_df.empty and st.session_state.view:
            spend_list, spend_date_list, df_list_in_unit = summary_by_unit(self.filtered_df, st.session_state.view)
            plot_linear_spending(spend_date_list, spend_list)

    def render_net_spend_by_category(self):
        if  not self.filtered_df.empty and st.session_state.view:
            spend_list, spend_date_list, df_list_in_unit = summary_by_unit(self.filtered_df, st.session_state.view)
            plot_net_spend(df_list_in_unit)
            
    def render_dimension_selector(self, key_prefix):
        """Renders the Year/Month/Week analysis dimension buttons."""
        st.subheader("📊 Analysis Dimension")
        c1, c2, c3 = st.columns(3)
        if c1.button("📅 Year", key=f"{key_prefix}_year"):
            st.session_state.view = 'Year'
        if c2.button("🗓️ Month", key=f"{key_prefix}_month"):
            st.session_state.view = 'Month'
        if c3.button("📆 Week", key=f"{key_prefix}_week"):
            st.session_state.view = 'Week'
        
        unit = st.session_state.view
        if not(unit == 'Year' or unit == 'Month' or unit == 'Week'):
            st.info('Please select a valid analysis dimension') 
        
# main.py usage:
if __name__ == '__main__':
    app = Canvas()
    app.render()
