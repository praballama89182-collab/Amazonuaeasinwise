import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO

st.set_page_config(page_title="AMAZON FINAL MASTER AUDIT", page_icon="🎯", layout="wide")

# 1. Definitive Brand Mapping
BRAND_MAP = {
    'MA': 'Maison de l’Avenir',
    'CL': 'Creation Lamis',
    'JPD': 'Jean Paul Dupont',
    'PC': 'Paris Collection',
    'DC': 'Dorall Collection',
    'CPT': 'CP Trendies'
}

def clean_numeric(val):
    """Robust cleaning for currency symbols, commas, and hidden spaces."""
    if isinstance(val, str):
        cleaned = val.replace('AED', '').replace('$', '').replace('\xa0', '').replace(',', '').strip()
        try: return pd.to_numeric(cleaned)
        except: return 0.0
    return val if isinstance(val, (int, float)) else 0.0

def get_brand_robust(row, title_col=None, sku_col=None, camp_col=None):
    """Categorizes rows by scanning Title, SKU, and Campaign Name."""
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
    """Finds columns using partial matching to ignore trailing/leading spaces."""
    for col in df.columns:
        col_clean = str(col).strip().lower()
        if any(kw.lower() in col_clean for kw in keywords):
            if exclude and any(ex.lower() in col_clean for ex in exclude): continue
            return col
    return None

# --- Main App ---
st.title("🎯 Final Amazon Master Audit")
st.markdown("---")

# Sidebar Uploads
st.sidebar.header("📁 Report Uploads")
ad_file = st.sidebar.file_uploader("1. Ad Report (CSV/Excel)", type=["csv", "xlsx"])
biz_file = st.sidebar.file_uploader("2. Business Report (CSV/Excel)", type=["csv", "xlsx"])
inv_file = st.sidebar.file_uploader("3. Inventory Report (.txt)", type=["txt"])

if ad_file and biz_file and inv_file:
    with st.spinner('Calculating final metrics...'):
        # Load Files
        df_ad = pd.read_csv(ad_file) if ad_file.name.endswith('.csv') else pd.read_excel(ad_file)
        df_biz = pd.read_csv(biz_file) if biz_file.name.endswith('.csv') else pd.read_excel(biz_file)
        df_inv = pd.read_csv(inv_file, sep='\t')

        # Clean Column Headers
        df_ad.columns = [str(c).strip() for c in df_ad.columns]
        df_biz.columns = [str(c).strip() for c in df_biz.columns]
        df_inv.columns = [str(c).strip() for c in df_inv.columns]

        # 1. Inventory: Aggregate by ASIN (Summing all SKUs)
        inv_asin = find_robust_col(df_inv, ['asin'])
        inv_qty = find_robust_col(df_inv, ['quantity available'])
        inv_summary = df_inv.groupby(inv_asin)[inv_qty].sum().reset_index()
        inv_summary.columns = ['ASIN_KEY', 'Stock']

        # 2. Identify Ad Metrics (Total Sales vs Direct Sales)
        a_asin = find_robust_col(df_ad, ['advertised asin'])
        a_total_sales = find_robust_col(df_ad, ['7 day total sales']) 
        a_spend = find_robust_col(df_ad, ['spend'])
        a_camp = find_robust_col(df_ad, ['campaign name'])

        # 3. Identify Business Metrics
        b_asin = find_robust_col(df_biz, ['(child) asin', 'child asin'])
        b_sales = find_robust_col(df_biz, ['ordered product sales', 'revenue'])
        b_title = find_robust_col(df_biz, ['title', 'item name'])
        b_sku = find_robust_col(df_biz, ['sku', 'seller-sku'])

        # 4. Clean Data
        df_ad[a_total_sales] = df_ad[a_total_sales].apply(clean_numeric)
        df_ad[a_spend] = df_ad[a_spend].apply(clean_numeric)
        df_biz[b_sales] = df_biz[b_sales].apply(clean_numeric)

        # 5. Aggregate Ad Data by ASIN
        ad_summary = df_ad.groupby(a_asin).agg({
            a_total_sales: 'sum', a_spend: 'sum', a_camp: 'first'
        }).reset_index()

        # 6. Master Merge
        merged = pd.merge(df_biz, ad_summary, left_on=b_asin, right_on=a_asin, how='left').fillna(0)
        merged = pd.merge(merged, inv_summary, left_on=b_asin, right_on='ASIN_KEY', how='left').fillna(0)
        
        # 7. Final Brands & Calculations
        merged['Brand'] = merged.apply(lambda r: get_brand_robust(r, b_title, b_sku, a_camp), axis=1)
        merged['Organic Sales'] = merged[b_sales] - merged[a_total_sales]
        merged['TACOS'] = (merged[a_spend] / merged[b_sales]).replace([np.inf, -np.inf], 0).fillna(0)

    # --- TABS INTERFACE ---
    tabs = st.tabs(["🌎 Global Portfolio"] + list(BRAND_MAP.values()))

    # Global Summary
    with tabs[0]:
        st.subheader("Account Performance Summary")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Sales", f"AED {merged[b_sales].sum():,.2f}")
        m2.metric("Ad Sales (Total)", f"AED {merged[a_total_sales].sum():,.2f}")
        m3.metric("Ad Spend", f"AED {merged[a_spend].sum():,.2f}")
        m4.metric("Avg TACOS", f"{(merged[a_spend].sum()/merged[b_sales].sum()):.2%}")

        st.markdown("### Brand Breakdown")
        brand_perf = merged.groupby('Brand').agg({
            b_sales: 'sum', a_total_sales: 'sum', a_spend: 'sum', 'Stock': 'sum'
        }).reset_index().sort_values(by=b_sales, ascending=False)
        st.dataframe(brand_perf, use_container_width=True, hide_index=True)

    # Brand Tabs
    for idx, brand_name in enumerate(BRAND_MAP.values(), start=1):
        with tabs[idx]:
            b_data = merged[merged['Brand'] == brand_name]
            if not b_data.empty:
                st.subheader(f"{brand_name} Metrics")
                k1, k2, k3, k4 = st.columns(4)
                k1.metric("Total Sales", f"AED {b_data[b_sales].sum():,.2f}")
                k2.metric("Ad Sales", f"AED {b_data[a_total_sales].sum():,.2f}")
                k3.metric("Spend", f"AED {b_data[a_spend].sum():,.2f}")
                k4.metric("Total Stock", f"{b_data['Stock'].sum():,.0f}")
                
                st.markdown("### ASIN Performance Audit")
                cols = [b_asin, b_title, 'Stock', b_sales, a_total_sales, a_spend, 'Organic Sales', 'TACOS']
                st.dataframe(b_data[cols].sort_values(by=b_sales, ascending=False), use_container_width=True, hide_index=True)
            else:
                st.info(f"No products found for {brand_name}.")

    # --- EXCEL EXPORT ---
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        brand_perf.to_excel(writer, sheet_name='Global_Brand_Summary', index=False)
        merged.to_excel(writer, sheet_name='Full_ASIN_Audit', index=False)
    st.sidebar.download_button("📥 Download Final Report", data=output.getvalue(), file_name="Amazon_Master_Audit.xlsx")

else:
    st.info("Upload all three files to generate your finalized dashboard.")
