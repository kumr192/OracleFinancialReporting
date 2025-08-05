# app.py – Enhanced Oracle ERP Financial Dashboard (Geckoboard-Style with Gen AI)
import streamlit as st
import pandas as pd
from datetime import datetime
import plotly.express as px
import plotly.graph_objects as go
import io
import xlsxwriter
import json
import requests

st.set_page_config(page_title="Oracle Financial Dashboard", page_icon="KumR", layout="wide")

# Sidebar
with st.sidebar:
    st.header("TB Upload & Open AI Credentials")
    uploaded_file = st.file_uploader("Upload Trial Balance Excel", type=[".xlsx", ".xls"])
    show_details = True
    st.markdown("---")
    openai_api_key = st.text_input("Enter OpenAI API Key", type="password", key="openai_key")

# Load Trial Balance

def load_trial_balance(uploaded_file):
    try:
        xl = pd.ExcelFile(uploaded_file)
        for sheet in xl.sheet_names:
            temp = xl.parse(sheet, header=None)
            for idx, row in temp.iterrows():
                if row.astype(str).str.contains('Account', case=False, na=False).any():
                    df = xl.parse(sheet, header=idx)
                    df = df.dropna(how='all')
                    break
        col_map = {}
        for col in df.columns:
            cl = str(col).lower()
            if 'account' in cl and 'description' not in cl:
                col_map[col] = 'Account'
            elif 'description' in cl:
                col_map[col] = 'Description'
            elif 'beginning' in cl and 'balance' in cl:
                col_map[col] = 'Beginning_Balance'
            elif 'ending' in cl and 'balance' in cl:
                col_map[col] = 'Ending_Balance'
            elif 'debit' in cl:
                col_map[col] = 'Debits'
            elif 'credit' in cl:
                col_map[col] = 'Credits'
        df = df.rename(columns=col_map)
        df = df[df['Account'].notna() & df['Account'].astype(str).str.match(r'^\d+$')]
        for col in ['Beginning_Balance', 'Ending_Balance', 'Debits', 'Credits']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        return df
    except Exception as e:
        st.error(f"Error loading TB: {e}")
        return None

# Classify Accounts

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

# GenAI FinBot using OpenAI v1 API
def ask_ai_v1(df, api_key, key_suffix):
    st.markdown("<h2 style='color:#00bcd4'>Financial FinBot</h2>", unsafe_allow_html=True)
    question = st.text_input("Ask a question about your trial balance", key=f"ai_question_{key_suffix}")
    if question:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
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
            response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
            if response.status_code == 200:
                answer = response.json()['choices'][0]['message']['content']
                st.success(answer)
            elif response.status_code >= 500:
                st.error("OpenAI server error. Please try again shortly.")
            else:
                st.error(f"API Error {response.status_code}: {response.text}")
        except Exception as e:
            st.error(str(e))

# Balance Sheet

def display_balance_sheet(df):
    st.header("Balance Sheet")
    df_assets = df[df['Category'] == 'Assets']
    df_liabilities_equity = df[df['Category'].isin(['Liabilities', 'Equity'])]

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Assets Table")
        st.dataframe(df_assets[['Account', 'Description', 'Ending_Balance']], use_container_width=True)
        df_assets_grouped = df_assets.groupby('Sub_Category')['Ending_Balance'].sum().reset_index().nlargest(10, 'Ending_Balance')
        fig1 = px.bar(df_assets_grouped, x='Sub_Category', y='Ending_Balance', color='Sub_Category', title='💰 Top 10 Assets Breakdown')
        st.plotly_chart(fig1, use_container_width=True)

    with col2:
        st.subheader("Liabilities & Equity Table")
        st.dataframe(df_liabilities_equity[['Account', 'Description', 'Ending_Balance']], use_container_width=True)
        df_liab = df[df['Category'] == 'Liabilities'].groupby('Sub_Category')['Ending_Balance'].sum().reset_index().nlargest(10, 'Ending_Balance')
        df_liab['Ending_Balance'] = df_liab['Ending_Balance'].abs()
        df_eq = df[df['Category'] == 'Equity'].groupby('Sub_Category')['Ending_Balance'].sum().reset_index().nlargest(10, 'Ending_Balance')
        df_eq['Ending_Balance'] = df_eq['Ending_Balance'].abs()
        fig2 = px.bar(df_liab, x='Sub_Category', y='Ending_Balance', color='Sub_Category', title='🧾 Top 10 Liabilities Breakdown')
        st.plotly_chart(fig2, use_container_width=True)
        st.plotly_chart(px.bar(df_eq, x='Sub_Category', y='Ending_Balance', color='Sub_Category', title='📊 Equity Composition'), use_container_width=True)

# Income Statement

def display_income_statement(df):
    st.header("Income Statement")
    income_df = df[df['Account'].str.startswith(('4','5','6','7'))].copy()
    def classify_type(x):
        if x.startswith('4'): return 'Revenue'
        if x.startswith('5'): return 'COGS'
        if x.startswith('6'): return 'Operating Expense'
        if x.startswith('7'): return 'Other'
        return 'Other'
    income_df['Type'] = income_df['Account'].apply(classify_type)
    st.dataframe(income_df[['Account', 'Description', 'Ending_Balance', 'Type']], use_container_width=True)

    summary = income_df.groupby('Type')['Ending_Balance'].sum().reset_index()
    fig = px.bar(summary, x='Type', y='Ending_Balance', color='Type', title='Top Level Income Summary')
    st.plotly_chart(fig, use_container_width=True)

    revenue = summary[summary['Type']=='Revenue']['Ending_Balance'].sum()
    cogs = summary[summary['Type']=='COGS']['Ending_Balance'].sum()
    opex = summary[summary['Type']=='Operating Expense']['Ending_Balance'].sum()
    other = summary[summary['Type']=='Other']['Ending_Balance'].sum()
    ebitda = revenue - cogs - opex
    net_income = ebitda - other

    st.metric("EBITDA", f"${ebitda:,.2f}")
    st.metric("Net Income", f"${net_income:,.2f}")

# Cash Flow

def display_cash_flow():
    st.header("Cash Flow Statement-WIP")
    st.info("This is a placeholder for cash flow logic. Direct or indirect method can be implemented with multi-period TB.")

# Main

st.markdown("""
    <div style='padding: 20px; background: linear-gradient(to right, #1d2671, #c33764); border-radius: 10px;'>
        <h1 style='color: #ffffff;'>Financial Reports from Oracle Cloud Trial Balance </h1>
        <p style='color: #f0f0f0;'>May The Oracle Be With You</p>
    </div>
""", unsafe_allow_html=True)

st.markdown(f"#### Report Date: {datetime.now().strftime('%B %d, %Y')}")

if uploaded_file:
    df_raw = load_trial_balance(uploaded_file)
    if df_raw is not None:
        df_class = classify_accounts(df_raw)
        tabs = st.tabs(["Balance Sheet", "Income Statement", "Cash Flow-WIP"])

        with tabs[0]:
            display_balance_sheet(df_class)
            if openai_api_key: ask_ai_v1(df_class, openai_api_key, "bs")
            else: st.info("Enter OpenAI API key in sidebar to use AI FinBot.")

        with tabs[1]:
            display_income_statement(df_class)
            if openai_api_key: ask_ai_v1(df_class, openai_api_key, "is")
            else: st.info("Enter OpenAI API key in sidebar to use AI FinBot.")

        with tabs[2]:
            display_cash_flow()
else:
    st.info("Please upload a Trial Balance Excel file to begin.")
