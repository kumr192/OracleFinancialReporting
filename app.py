# app.py – Multi-Company Oracle ERP Dashboard with AI + Colored Charts
import streamlit as st
import pandas as pd
from datetime import datetime
import plotly.express as px
import requests

st.set_page_config(page_title="Oracle Financial Dashboard", page_icon="KumR", layout="wide")

# ───────────────────────────────────────── Sidebar ─────────────────────────────────────────
with st.sidebar:
    st.header("1️⃣ Upload TB File")
    uploaded_file = st.file_uploader("Upload Trial Balance Excel", type=[".xlsx", ".xls"])
    selected_sheet = None
    company_sheet_map = {}

    def extract_company_name(sheet_df):
        for row in sheet_df.itertuples(index=False):
            row_values = [str(x) for x in row if str(x) != 'nan']
            for i, val in enumerate(row_values):
                if "company" in val.lower() and i + 1 < len(row_values):
                    return row_values[i + 1].strip()
        return None

    if uploaded_file:
        xl_preview = pd.ExcelFile(uploaded_file)
        for sheet in xl_preview.sheet_names:
            try:
                df_sample = xl_preview.parse(sheet, header=None, nrows=20)
                company_name = extract_company_name(df_sample)
                if company_name:
                    company_sheet_map[company_name] = sheet
                else:
                    company_sheet_map[sheet] = sheet  # fallback to sheet name
            except Exception as e:
                company_sheet_map[sheet] = sheet

        display_names = list(company_sheet_map.keys())
        selected_display = st.selectbox("2️⃣ Select Company / Legal Entity", display_names)
        selected_sheet = company_sheet_map[selected_display]

    st.markdown("---")
    openai_api_key = st.text_input("🔐 OpenAI API Key", type="password", key="openai_key")

# ────────────────────────────── Load Trial Balance From Sheet ──────────────────────────────
def extract_trial_balance(sheet_df):
    for i in range(len(sheet_df)):
        row = sheet_df.iloc[i].astype(str).tolist()
        if any("account" in cell.lower() for cell in row) and any("description" in cell.lower() for cell in row):
            df = sheet_df.iloc[i:].copy()
            df.columns = df.iloc[0]
            df = df[1:].dropna(how='all')
            df.columns.name = None
            return df
    return pd.DataFrame()

def load_trial_balance_from_sheet(file, sheet):
    try:
        raw_df = pd.read_excel(file, sheet_name=sheet, header=None)
        df = extract_trial_balance(raw_df)

        if df.empty:
            st.warning("No trial balance found in selected sheet.")
            return None

        # Standardize column names
        col_map = {}
        for col in df.columns:
            cl = str(col).lower()
            if 'account' in cl and 'description' not in cl:
                col_map[col] = 'Account'
            elif 'description' in cl:
                col_map[col] = 'Description'
            elif 'beginning' in cl:
                col_map[col] = 'Beginning_Balance'
            elif 'ending' in cl:
                col_map[col] = 'Ending_Balance'
            elif 'debit' in cl:
                col_map[col] = 'Debits'
            elif 'credit' in cl:
                col_map[col] = 'Credits'
        df = df.rename(columns=col_map)

        if 'Account' not in df.columns:
            st.warning("No 'Account' column found.")
            return None

        df['Account'] = df['Account'].astype(str)
        df = df[df['Account'].str.match(r'^\d+$')]

        for col in ['Beginning_Balance', 'Ending_Balance', 'Debits', 'Credits']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

        return df

    except Exception as e:
        st.error(f"Error reading sheet: {e}")
        return None

# ──────────────────────────────── Classification Logic ────────────────────────────────
def classify_accounts(df):
    df['Category'] = ''
    df['Sub_Category'] = ''
    df['Account'] = df['Account'].astype(str)
    df.loc[df['Account'].str.startswith('1'), 'Category'] = 'Assets'
    df.loc[df['Account'].str.startswith('2'), 'Category'] = 'Liabilities'
    df.loc[df['Account'].str.startswith('3'), 'Category'] = 'Equity'
    df.loc[df['Account'].str.startswith(('10','11','12','13')), 'Sub_Category'] = 'Cash & Equivalents'
    df.loc[df['Account'].str.startswith(('14','15')), 'Sub_Category'] = 'Receivables'
    df.loc[df['Account'].str.startswith(('16')), 'Sub_Category'] = 'Inventory'
    df.loc[df['Account'].str.startswith(('17')), 'Sub_Category'] = 'Fixed Assets'
    df.loc[df['Account'].str.startswith(('18','19')), 'Sub_Category'] = 'Other Assets'
    df.loc[df['Account'].str.startswith(('20','21')), 'Sub_Category'] = 'Current Liabilities'
    df.loc[df['Account'].str.startswith(('22','23','24')), 'Sub_Category'] = 'Long-term Liabilities'
    df.loc[df['Category'] == 'Equity', 'Sub_Category'] = 'Stockholders Equity'
    return df

# ──────────────────────────────── AI FinBot ────────────────────────────────
def ask_ai_v1(df, api_key, key_suffix):
    st.markdown("<h2 style='color:#00bcd4'>💬 Financial FinBot</h2>", unsafe_allow_html=True)
    question = st.text_input("Ask a question about your trial balance", key=f"ai_question_{key_suffix}")
    if question:
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        context = df[['Account','Description','Category','Ending_Balance']].head(50).to_dict(orient='records')
        payload = {
            "model": "gpt-4",
            "messages": [
                {"role": "system", "content": "You're a CPA bot explaining Oracle Trial Balance anomalies."},
                {"role": "user", "content": f"Trial Balance Data: {context}"},
                {"role": "user", "content": question}
            ]
        }
        try:
            r = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
            if r.status_code == 200:
                answer = r.json()['choices'][0]['message']['content']
                st.success(answer)
            else:
                st.error(f"OpenAI error {r.status_code}")
        except Exception as e:
            st.error(str(e))

# ──────────────────────────────── Balance Sheet View ────────────────────────────────
def display_balance_sheet(df):
    st.header("📊 Balance Sheet")
    df_assets = df[df['Category'] == 'Assets']
    df_liab_eq = df[df['Category'].isin(['Liabilities', 'Equity'])]

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Assets")
        st.dataframe(df_assets[['Account', 'Description', 'Ending_Balance']], use_container_width=True)
        grp = df_assets.groupby('Sub_Category')['Ending_Balance'].sum().reset_index().nlargest(10, 'Ending_Balance')
        fig = px.bar(grp, x='Sub_Category', y='Ending_Balance', color='Sub_Category',
                     title='💰 Top Assets', color_discrete_sequence=px.colors.qualitative.Plotly)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Liabilities & Equity")
        st.dataframe(df_liab_eq[['Account', 'Description', 'Ending_Balance']], use_container_width=True)
        liab = df[df['Category'] == 'Liabilities'].groupby('Sub_Category')['Ending_Balance'].sum().reset_index()
        eq = df[df['Category'] == 'Equity'].groupby('Sub_Category')['Ending_Balance'].sum().reset_index()
        st.plotly_chart(px.bar(liab, x='Sub_Category', y='Ending_Balance', color='Sub_Category',
                               title='📕 Liabilities', color_discrete_sequence=px.colors.qualitative.Plotly), use_container_width=True)
        st.plotly_chart(px.bar(eq, x='Sub_Category', y='Ending_Balance', color='Sub_Category',
                               title='📗 Equity', color_discrete_sequence=px.colors.qualitative.Plotly), use_container_width=True)

# ──────────────────────────────── Income Statement ────────────────────────────────
def display_income_statement(df):
    st.header("📈 Income Statement")
    df_income = df[df['Account'].str.startswith(('4','5','6','7'))].copy()

    def classify(x):
        if x.startswith('4'): return 'Revenue'
        if x.startswith('5'): return 'COGS'
        if x.startswith('6'): return 'Operating Expense'
        return 'Other'

    df_income['Type'] = df_income['Account'].apply(classify)
    st.dataframe(df_income[['Account', 'Description', 'Ending_Balance', 'Type']], use_container_width=True)

    summary = df_income.groupby('Type')['Ending_Balance'].sum().reset_index()
    fig = px.bar(summary, x='Type', y='Ending_Balance', color='Type', title='Income Breakdown')
    st.plotly_chart(fig, use_container_width=True)

    revenue = summary.loc[summary['Type']=='Revenue', 'Ending_Balance'].sum()
    cogs = summary.loc[summary['Type']=='COGS', 'Ending_Balance'].sum()
    opex = summary.loc[summary['Type']=='Operating Expense', 'Ending_Balance'].sum()
    other = summary.loc[summary['Type']=='Other', 'Ending_Balance'].sum()
    ebitda = revenue - cogs - opex
    net_income = ebitda - other

    st.metric("EBITDA", f"${ebitda:,.2f}")
    st.metric("Net Income", f"${net_income:,.2f}")

# ──────────────────────────────── Cash Flow Placeholder ────────────────────────────────
def display_cash_flow():
    st.header("💸 Cash Flow Statement (WIP)")
    st.info("Upload multi-period TB to enable cash flow logic (direct/indirect).")

# ──────────────────────────────── Main Banner ────────────────────────────────
st.markdown("""
    <div style='padding: 20px; background: linear-gradient(to right, #1d2671, #c33764); border-radius: 10px;'>
        <h1 style='color: #ffffff;'>Financial Reports from Oracle Cloud Trial Balance</h1>
        <p style='color: #f0f0f0;'>May The Oracle Be With You</p>
    </div>
""", unsafe_allow_html=True)

st.markdown(f"#### Report Date: {datetime.now().strftime('%B %d, %Y')}")

# ──────────────────────────────── Main Execution ────────────────────────────────
if uploaded_file and selected_sheet:
    df_raw = load_trial_balance_from_sheet(uploaded_file, selected_sheet)
    if df_raw is not None:
        df_class = classify_accounts(df_raw)
        tabs = st.tabs(["Balance Sheet", "Income Statement", "Cash Flow"])

        with tabs[0]:
            display_balance_sheet(df_class)
            if openai_api_key:
                ask_ai_v1(df_class, openai_api_key, "bs")
            else:
                st.info("Enter OpenAI key in sidebar to use FinBot.")

        with tabs[1]:
            display_income_statement(df_class)
            if openai_api_key:
                ask_ai_v1(df_class, openai_api_key, "is")
            else:
                st.info("Enter OpenAI key in sidebar to use FinBot.")

        with tabs[2]:
            display_cash_flow()
else:
    st.info("📂 Please upload a Trial Balance file and select a company tab to continue.")
