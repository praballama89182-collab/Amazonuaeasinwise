import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO

st.set_page_config(page_title="AMAZON MASTER BRAND AUDIT", page_icon="📊", layout="wide")

# 1. Configuration & Robust Mapping
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
    """Deep scan for brand identifiers in Title, SKU, and Campaign Name."""
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
    if camp_col and camp_col in row: text += " " + str(row[camp_col]).upper()
    
    for kw, brand in targets.items():
        if kw in text: return brand
    return "Unmapped"

def find_robust_col(df, keywords, exclude=None):
    for col in df.columns:
        col_clean = str(col).strip().lower()
        if any(kw.lower() in col_clean for kw in keywords):
            if exclude and any(ex.lower() in col_clean for ex in exclude): continue
            return col
    return None

st.title("📊 Amazon Master Brand & ASIN Audit")
st.markdown("---")

# File Uploaders
st.sidebar.header("📁 Report Uploads")
ad_file = st.sidebar.file_uploader("1. Ad Report (Spon. Products CSV)", type=["csv"])
biz_file = st.sidebar.file_uploader("2. Business Report (CSV/XLSX)", type=["csv", "xlsx"])
inv_file = st.sidebar.file_uploader("3. Inventory Report (.txt)", type=["txt"])

if ad_file and biz_file and inv_file:
    with st.spinner('Syncing reports...'):
        # Load Data
        ad_df = pd.read_csv(ad_file)
        biz_df = pd.read_csv(biz_file) if biz_file.name.endswith('.csv') else pd.read_excel(biz_file)
        inv_df = pd.read_csv(inv_file, sep='\t')

        # 1. Inventory Sync
        inv_df.columns = [c.strip().lower() for c in inv_df.columns]
        inv_summary = inv_df.groupby('asin')['quantity available'].sum().reset_index()
        inv_summary.columns = ['ASIN_KEY', 'Stock']

        # 2. Identify Columns (Robust to trailing spaces)
        b_asin = find_robust_col(biz_df, ['asin', 'child asin'])
        b_sales = find_robust_col(biz_df, ['ordered product sales', 'revenue'])
        b_title = find_robust_col(biz_df, ['title', 'item name'])
        b_sku = find_robust_col(biz_df, ['sku', 'seller-sku'])
        
        a_asin = find_robust_col(ad_df, ['advertised asin'])
        a_total_sales = find_robust_col(ad_df, ['7 Day Total Sales'])
        a_direct_sales = find_robust_col(ad_df, ['7 Day Advertised SKU Sales'])
        a_halo_sales = find_robust_col(ad_df, ['7 Day Other SKU Sales'])
        a_spend = find_robust_col(ad_df, ['spend'])
        a_sku = find_robust_col(ad_df, ['advertised sku'])
        a_camp = find_robust_col(ad_df, ['campaign name'])

        # 3. Data Cleaning
        biz_df[b_sales] = biz_df[b_sales].apply(clean_numeric)
        for col in [a_total_sales, a_direct_sales, a_halo_sales, a_spend]:
            if col: ad_df[col] = ad_df[col].apply(clean_numeric)

        # 4. Ad Aggregation
        ad_summary = ad_df.groupby(a_asin).agg({
            a_total_sales: 'sum', a_direct_sales: 'sum',
            a_halo_sales: 'sum', a_spend: 'sum',
            a_camp: 'first', a_sku: 'first'
        }).reset_index()

        # 5. Master Merge
        merged = pd.merge(biz_df, ad_summary, left_on=b_asin, right_on=a_asin, how='left').fillna(0)
        merged = pd.merge(merged, inv_summary, left_on=b_asin, right_on='ASIN_KEY', how='left').fillna(0)
        
        # 6. Apply Brand Mapping
        merged['Brand'] = merged.apply(lambda r: get_brand_robust(r, b_title, b_sku, a_camp), axis=1)
        
        # 7. Core Metrics
        merged['Organic Sales'] = merged[b_sales] - merged[a_total_sales]
        merged['TACOS'] = (merged[a_spend] / merged[b_sales]).replace([np.inf, -np.inf], 0).fillna(0)

    # --- TABS LAYOUT ---
    tab_list = ["🌎 Global Summary"] + list(BRAND_MAP.values())
    tabs = st.tabs(tab_list)

    # Global Summary
    with tabs[0]:
        st.subheader("Total Portfolio Performance")
        m1, m2, m3, m4 = st.columns(4)
        total_rev = merged[b_sales].sum()
        total_ad = merged[a_total_sales].sum()
        m1.metric("Total Sales", f"AED {total_rev:,.2f}")
        m2.metric("Ad Sales", f"AED {total_ad:,.2f}")
        m3.metric("Total Spend", f"AED {merged[a_spend].sum():,.2f}")
        m4.metric("Avg TACOS", f"{(merged[a_spend].sum()/total_rev):.2%}")

        st.markdown("### 📊 Performance by Brand")
        brand_perf = merged.groupby('Brand').agg({
            b_sales: 'sum', a_total_sales: 'sum', a_direct_sales: 'sum',
            a_halo_sales: 'sum', a_spend: 'sum', 'Stock': 'sum'
        }).reset_index().sort_values(by=b_sales, ascending=False)
        st.dataframe(brand_perf, use_container_width=True, hide_index=True)

    # Brand-Specific Tabs
    for idx, brand_name in enumerate(BRAND_MAP.values(), start=1):
        with tabs[idx]:
            b_data = merged[merged['Brand'] == brand_name]
            if not b_data.empty:
                st.subheader(f"{brand_name} Overview")
                k1, k2, k3, k4 = st.columns(4)
                k1.metric("Total Sales", f"AED {b_data[b_sales].sum():,.2f}")
                k2.metric("Ad Sales", f"AED {b_data[a_total_sales].sum():,.2f}")
                k3.metric("Spend", f"AED {b_data[a_spend].sum():,.2f}")
                k4.metric("Total Stock", f"{b_data['Stock'].sum():,.0f}")
                
                st.markdown("### 🎯 ASIN Performance Audit")
                audit_cols = [b_asin, b_title, 'Stock', b_sales, a_total_sales, a_direct_sales, a_halo_sales, a_spend, 'Organic Sales', 'TACOS']
                st.dataframe(b_data[audit_cols].sort_values(by=b_sales, ascending=False), use_container_width=True, hide_index=True)
            else:
                st.info(f"No products matched {brand_name}.")

    # Multi-Sheet Export
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        brand_perf.to_excel(writer, sheet_name='Brand_Breakdown', index=False)
        merged.to_excel(writer, sheet_name='Full_ASIN_Audit', index=False)
    st.sidebar.download_button("📥 Download Master Report", data=output.getvalue(), file_name="Amazon_Brand_Audit.xlsx")

else:
    st.info("Please upload all three reports in the sidebar to begin.")
