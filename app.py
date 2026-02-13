import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO

st.set_page_config(page_title="AMAZON FINAL MASTER AUDIT", page_icon="🎯", layout="wide")

# 1. Configuration & Robust Brand Mapping
BRAND_MAP = {
    'MA': 'Maison de l’Avenir',
    'CL': 'Creation Lamis',
    'JPD': 'Jean Paul Dupont',
    'PC': 'Paris Collection',
    'DC': 'Dorall Collection',
    'CPT': 'CP Trendies'
}

def clean_numeric(val):
    """Handles currency symbols, commas, and hidden spaces."""
    if isinstance(val, str):
        cleaned = val.replace('AED', '').replace('$', '').replace('\xa0', '').replace(',', '').strip()
        try: return pd.to_numeric(cleaned)
        except: return 0.0
    return val if isinstance(val, (int, float)) else 0.0

def get_brand_robust(row, title_col=None, sku_col=None, camp_col=None):
    """Categorizes rows into brands by scanning Title, SKU, and Campaign Name."""
    targets = {
        'MAISON': 'Maison de l’Avenir', 'MA_': 'Maison de l’Avenir',
        'LAMIS': 'Creation Lamis', 'CL ': 'Creation Lamis', 'CL_': 'Creation Lamis', 'CL |': 'Creation Lamis',
        'DUPONT': 'Jean Paul Dupont', 'JPD ': 'Jean Paul Dupont', 'JPD_': 'Jean Paul Dupont', 'JPD |': 'Jean Paul Dupont',
        'PARIS COLLECTION': 'Paris Collection', 'PC ': 'Paris Collection', 'PC_': 'Paris Collection', 'PC |': 'Paris Collection',
        'DORALL': 'Dorall Collection', 'DC ': 'Dorall Collection', 'DC_': 'Dorall Collection', 'DC |': 'Dorall Collection',
        'TRENDIES': 'CP Trendies', 'CPT': 'CP Trendies', 'CP_': 'CP Trendies', 'CPMK': 'CP Trendies'
    }
    text = ""
    if title_col and title_col in row: text += " " + str(row[title_col]).upper()
    if sku_col and sku_col in row: text += " " + str(row[sku_col]).upper()
    if camp_col and camp_col in row and pd.notna(row[camp_col]): text += " " + str(row[camp_col]).upper()
    
    for kw, brand in targets.items():
        if kw in text: return brand
    return "Unmapped"

def find_robust_col(df, keywords, exclude=None):
    """Aggressively finds column names and returns the first match."""
    for col in df.columns:
        col_clean = str(col).strip().lower()
        if any(kw.lower() in col_clean for kw in keywords):
            if exclude and any(ex.lower() in col_clean for ex in exclude): continue
            return col
    return None

def load_data(file):
    if file.name.endswith('.csv'):
        return pd.read_csv(file)
    elif file.name.endswith('.txt'):
        return pd.read_csv(file, sep='\t')
    else:
        return pd.read_excel(file)

st.title("🚀 Amazon Master Brand & ASIN Audit")

# Sidebar Uploads
st.sidebar.header("📁 Report Upload Center")
ad_file = st.sidebar.file_uploader("1. Ad Report (CSV or Excel)", type=["csv", "xlsx"])
biz_file = st.sidebar.file_uploader("2. Business Report (CSV or Excel)", type=["csv", "xlsx"])
inv_file = st.sidebar.file_uploader("3. Inventory Report (.txt)", type=["txt"])

if ad_file and biz_file and inv_file:
    with st.spinner('Processing reports...'):
        # Load Data
        df_ad = load_data(ad_file)
        df_biz = load_data(biz_file)
        df_inv = load_data(inv_file)

        # Standardize headers
        df_ad.columns = [str(c).strip() for c in df_ad.columns]
        df_biz.columns = [str(c).strip() for c in df_biz.columns]
        df_inv.columns = [str(c).strip() for c in df_inv.columns]

        # 1. Aggregated Inventory (Pivoted by ASIN)
        # Your file uses 'asin' and 'Quantity Available'
        inv_asin = find_robust_col(df_inv, ['asin'])
        inv_qty = find_robust_col(df_inv, ['quantity available'])
        inv_summary = df_inv.groupby(inv_asin)[inv_qty].sum().reset_index()
        inv_summary.columns = ['ASIN_KEY', 'Stock']

        # 2. Identify Ad & Biz Columns
        # FIXED: Specific keywords to match '(Child) ASIN' and '7 Day Total Sales '
        b_asin = find_robust_col(df_biz, ['child asin', 'asin'])
        b_sales = find_robust_col(df_biz, ['ordered product sales', 'revenue'])
        b_title = find_robust_col(df_biz, ['title', 'item name'])
        b_sku = find_robust_col(df_biz, ['sku', 'seller-sku'])
        
        a_asin = find_robust_col(df_ad, ['advertised asin', 'asin'])
        a_total_sales = find_robust_col(df_ad, ['7 day total sales']) 
        a_spend = find_robust_col(df_ad, ['spend', 'cost'])
        a_camp = find_robust_col(df_ad, ['campaign name'])

        # Safety Check: Prevent MergeError if columns are not found
        if not b_asin or not a_asin:
            st.error(f"Mapping Error: Could not find ASIN column. Business: {b_asin}, Ad: {a_asin}")
            st.stop()

        # 3. Numeric Cleaning
        df_biz[b_sales] = df_biz[b_sales].apply(clean_numeric)
        df_ad[a_total_sales] = df_ad[a_total_sales].apply(clean_numeric)
        df_ad[a_spend] = df_ad[a_spend].apply(clean_numeric)

        # 4. Ad Aggregation
        ad_summary = df_ad.groupby(a_asin).agg({a_total_sales: 'sum', a_spend: 'sum', a_camp: 'first'}).reset_index()

        # 5. Master Data Merge
        merged = pd.merge(df_biz, ad_summary, left_on=b_asin, right_on=a_asin, how='left').fillna(0)
        merged = pd.merge(merged, inv_summary, left_on=b_asin, right_on='ASIN_KEY', how='left').fillna(0)
        
        # 6. Final Calculations
        merged['Brand'] = merged.apply(lambda r: get_brand_robust(r, b_title, b_sku, a_camp), axis=1)
        merged['ACOS'] = (merged[a_spend] / merged[a_total_sales]).replace([np.inf, -np.inf], 0).fillna(0)
        merged['TACOS'] = (merged[a_spend] / merged[b_sales]).replace([np.inf, -np.inf], 0).fillna(0)
        merged['Organic Sales'] = merged[b_sales] - merged[a_total_sales]

    # --- UI Tabs ---
    tabs = st.tabs(["🌎 Global Portfolio"] + list(BRAND_MAP.values()))

    with tabs[0]:
        st.subheader("Global Stock & Sales Overview")
        m1, m2, m3, m4, m5 = st.columns(5)
        t_rev, t_ad = merged[b_sales].sum(), merged[a_total_sales].sum()
        t_spend, t_stock = merged[a_spend].sum(), merged['Stock'].sum()
        
        m1.metric("Total Sales", f"AED {t_rev:,.2f}")
        m2.metric("Ad Sales", f"AED {t_ad:,.2f}")
        m3.metric("Ad Spend", f"AED {t_spend:,.2f}")
        m4.metric("ACOS", f"{(t_spend/t_ad if t_ad > 0 else 0):.2%}")
        m5.metric("Total Stock", f"{t_stock:,.0f}")

        brand_perf = merged.groupby('Brand').agg({b_sales: 'sum', a_total_sales: 'sum', a_spend: 'sum', 'Stock': 'sum'}).reset_index()
        st.dataframe(brand_perf.sort_values(by=b_sales, ascending=False), use_container_width=True, hide_index=True)

    for idx, brand_name in enumerate(BRAND_MAP.values(), start=1):
        with tabs[idx]:
            b_data = merged[merged['Brand'] == brand_name]
            st.dataframe(b_data[[b_asin, b_title, 'Stock', b_sales, a_total_sales, a_spend, 'ACOS', 'TACOS']], use_container_width=True, hide_index=True)

    # Export
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        merged.to_excel(writer, sheet_name='Audit', index=False)
    st.sidebar.download_button("📥 Download Master Report", data=output.getvalue(), file_name="Amazon_Performance_Master.xlsx")
