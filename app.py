import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO

st.set_page_config(page_title="AMAZON MASTER BRAND AUDIT", page_icon="📊", layout="wide")

# Brand Configuration
BRAND_MAP = {
    'MA': 'Maison de l’Avenir',
    'CL': 'Creation Lamis',
    'JPD': 'Jean Paul Dupont',
    'PC': 'Paris Collection',
    'DC': 'Dorall Collection',
    'CPT': 'CP Trendies'
}

def clean_numeric(val):
    if isinstance(val, str):
        cleaned = val.replace('AED', '').replace('$', '').replace('\xa0', '').replace(',', '').strip()
        try: return pd.to_numeric(cleaned)
        except: return 0.0
    return val if isinstance(val, (int, float)) else 0.0

def get_brand_robust(row, title_col=None, sku_col=None, camp_col=None):
    targets = {
        'MAISON': 'Maison de l’Avenir', 'MA_': 'Maison de l’Avenir',
        'LAMIS': 'Creation Lamis', 'CL ': 'Creation Lamis', 'CL_': 'Creation Lamis',
        'DUPONT': 'Jean Paul Dupont', 'JPD ': 'Jean Paul Dupont', 'JPD_': 'Jean Paul Dupont',
        'PARIS COLLECTION': 'Paris Collection', 'PC ': 'Paris Collection', 'PC_': 'Paris Collection',
        'DORALL': 'Dorall Collection', 'DC ': 'Dorall Collection', 'DC_': 'Dorall Collection',
        'TRENDIES': 'CP Trendies', 'CPT': 'CP Trendies', 'CP_': 'CP Trendies', 'CPMK': 'CP Trendies'
    }
    text = ""
    if title_col and title_col in row: text += " " + str(row[title_col]).upper()
    if sku_col and sku_col in row: text += " " + str(row[sku_col]).upper()
    if camp_col and camp_col in row and pd.notna(row[camp_col]): text += " " + str(row[camp_col]).upper()
    for kw, brand in targets.items():
        if kw in text: return brand
    return "Unmapped"

def find_robust_col(df, keywords):
    for col in df.columns:
        col_clean = str(col).strip().lower()
        if any(kw.lower() in col_clean for kw in keywords):
            return col
    return None

st.title("🚀 Amazon Master Brand & ASIN Audit")

st.sidebar.header("📁 Report Upload Center")
ad_file = st.sidebar.file_uploader("1. Ad Report (CSV/Excel)", type=["csv", "xlsx"])
biz_file = st.sidebar.file_uploader("2. Business Report (CSV/Excel)", type=["csv", "xlsx"])
inv_file = st.sidebar.file_uploader("3. Inventory Report (.txt)", type=["txt"])

if ad_file and biz_file and inv_file:
    # Load Data
    ad_df = pd.read_csv(ad_file) if ad_file.name.endswith('.csv') else pd.read_excel(ad_file)
    biz_df = pd.read_csv(biz_file) if biz_file.name.endswith('.csv') else pd.read_excel(biz_file)
    inv_df = pd.read_csv(inv_file, sep='\t')

    # Standardize Headers
    ad_df.columns = [c.strip() for c in ad_df.columns]
    biz_df.columns = [c.strip() for c in biz_df.columns]
    inv_df.columns = [c.strip().lower() for c in inv_df.columns]

    # 1. Inventory Sync (Aggregated by ASIN)
    inv_summary = inv_df.groupby('asin')['quantity available'].sum().reset_index()
    inv_summary.columns = ['ASIN_KEY', 'Stock']

    # 2. Map Columns
    b_asin = find_robust_col(biz_df, ['asin', 'child asin'])
    b_sales = find_robust_col(biz_df, ['ordered product sales', 'revenue'])
    b_title = find_robust_col(biz_df, ['title', 'item name'])
    b_sku = find_robust_col(biz_df, ['sku', 'seller-sku'])
    
    a_asin = find_robust_col(ad_df, ['advertised asin'])
    a_total_sales = find_robust_col(ad_df, ['7 Day Total Sales'])
    a_spend = find_robust_col(ad_df, ['spend'])
    a_camp = find_robust_col(ad_df, ['campaign name'])

    # 3. Clean & Merge
    biz_df[b_sales] = biz_df[b_sales].apply(clean_numeric)
    ad_df[a_total_sales] = ad_df[a_total_sales].apply(clean_numeric)
    ad_df[a_spend] = ad_df[a_spend].apply(clean_numeric)

    ad_summary = ad_df.groupby(a_asin).agg({a_total_sales: 'sum', a_spend: 'sum', a_camp: 'first'}).reset_index()
    merged = pd.merge(biz_df, ad_summary, left_on=b_asin, right_on=a_asin, how='left').fillna(0)
    merged = pd.merge(merged, inv_summary, left_on=b_asin, right_on='ASIN_KEY', how='left').fillna(0)
    
    merged['Brand'] = merged.apply(lambda r: get_brand_robust(r, b_title, b_sku, a_camp), axis=1)
    merged['Organic Sales'] = merged[b_sales] - merged[a_total_sales]
    merged['TACOS'] = (merged[a_spend] / merged[b_sales]).replace([np.inf, -np.inf], 0).fillna(0)

    # --- TABS ---
    tabs = st.tabs(["🌎 Global Summary"] + list(BRAND_MAP.values()))

    with tabs[0]:
        st.subheader("Account Performance Summary")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Sales", f"AED {merged[b_sales].sum():,.2f}")
        m2.metric("Ad Sales", f"AED {merged[a_total_sales].sum():,.2f}")
        m3.metric("Total Spend", f"AED {merged[a_spend].sum():,.2f}")
        m4.metric("Avg TACOS", f"{(merged[a_spend].sum() / merged[b_sales].sum() if merged[b_sales].sum() > 0 else 0):.2%}")
        
        brand_perf = merged.groupby('Brand').agg({b_sales: 'sum', a_total_sales: 'sum', a_spend: 'sum', 'Stock': 'sum'}).reset_index()
        st.dataframe(brand_perf.sort_values(by=b_sales, ascending=False), use_container_width=True, hide_index=True)

    for idx, brand_name in enumerate(BRAND_MAP.values(), start=1):
        with tabs[idx]:
            b_data = merged[merged['Brand'] == brand_name]
            st.subheader(f"{brand_name} ASIN Audit")
            cols = [b_asin, b_title, 'Stock', b_sales, a_total_sales, a_spend, 'Organic Sales', 'TACOS']
            st.dataframe(b_data[cols].sort_values(by=b_sales, ascending=False), use_container_width=True, hide_index=True)

    # Export
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        merged.to_excel(writer, sheet_name='Full_Audit', index=False)
    st.sidebar.download_button("📥 Download Excel Report", data=output.getvalue(), file_name="Amazon_Audit_Master.xlsx")
