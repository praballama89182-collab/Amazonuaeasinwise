import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO

st.set_page_config(page_title="AMAZON MASTER AUDIT", page_icon="📈", layout="wide")

# 1. Configuration & Mapping
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

def get_brand_robust(name):
    if pd.isna(name): return "Unmapped"
    n = str(name).upper().replace('’', "'").strip()
    for prefix, full_name in BRAND_MAP.items():
        fn = full_name.upper().replace('’', "'")
        if fn in n or any(n.startswith(f"{prefix}{sep}") for sep in ["_", " ", "-", " |"]):
            return full_name
    return "Unmapped"

def find_robust_col(df, keywords):
    for col in df.columns:
        col_clean = str(col).strip().lower()
        if any(kw.lower() in col_clean for kw in keywords):
            return col
    return None

# --- UI Setup ---
st.title("🚀 Amazon Master Performance Audit")
st.markdown("---")

st.sidebar.header("📁 Upload Center")
ad_file = st.sidebar.file_uploader("1. Ad Report (Spon. Products)", type=["csv", "xlsx"])
biz_file = st.sidebar.file_uploader("2. Business Report (Child ASIN)", type=["csv", "xlsx"])
inv_file = st.sidebar.file_uploader("3. Inventory Report (.txt)", type=["txt"])

if ad_file and biz_file and inv_file:
    # Load Data
    with st.spinner('Processing reports...'):
        ad_df = pd.read_csv(ad_file) if ad_file.name.endswith('.csv') else pd.read_excel(ad_file)
        biz_df = pd.read_csv(biz_file) if biz_file.name.endswith('.csv') else pd.read_excel(biz_file)
        inv_df = pd.read_csv(inv_file, sep='\t')

        # 1. Inventory Prep
        inv_df.columns = [c.strip().lower() for c in inv_df.columns]
        inv_summary = inv_df.groupby('asin')['quantity available'].sum().reset_index()
        inv_summary.columns = ['ASIN_KEY', 'Stock']

        # 2. Identify Columns
        biz_asin = find_robust_col(biz_df, ['asin', 'child asin'])
        biz_sales = find_robust_col(biz_df, ['ordered product sales', 'revenue'])
        biz_units = find_robust_col(biz_df, ['units ordered'])
        biz_title = find_robust_col(biz_df, ['title', 'item name'])
        
        ad_asin = find_robust_col(ad_df, ['advertised asin'])
        ad_sales = find_robust_col(ad_df, ['total sales', '7 day total sales'])
        ad_spend = find_robust_col(ad_df, ['spend'])

        # 3. Data Cleaning
        biz_df[biz_sales] = biz_df[biz_sales].apply(clean_numeric)
        ad_df[ad_sales] = ad_df[ad_sales].apply(clean_numeric)
        ad_df[ad_spend] = ad_df[ad_spend].apply(clean_numeric)

        # 4. Aggregation & Merge
        ad_summary = ad_df.groupby(ad_asin)[[ad_sales, ad_spend]].sum().reset_index()
        merged = pd.merge(biz_df, ad_summary, left_on=biz_asin, right_on=ad_asin, how='left').fillna(0)
        merged = pd.merge(merged, inv_summary, left_on=biz_asin, right_on='ASIN_KEY', how='left').fillna(0)
        
        merged['Brand'] = merged[biz_title].apply(get_brand_robust)
        merged['Organic Sales'] = merged[biz_sales] - merged[ad_sales]
        merged['TACOS'] = (merged[ad_spend] / merged[biz_sales]).replace([np.inf, -np.inf], 0).fillna(0)

    # --- TABS INTERFACE ---
    tab1, tab2, tab3 = st.tabs(["🌎 Global Summary", "🏷️ Brand Overview", "🎯 Detailed ASIN Audit"])

    with tab1:
        st.subheader("Account-Level Totals")
        total_rev = merged[biz_sales].sum()
        total_ad_rev = merged[ad_sales].sum()
        total_spend = merged[ad_spend].sum()
        avg_tacos = (total_spend / total_rev) if total_rev > 0 else 0

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Sales", f"{total_rev:,.2f}")
        c2.metric("Ad Sales", f"{total_ad_rev:,.2f}")
        c3.metric("Total Spend", f"{total_spend:,.2f}")
        c4.metric("Total TACOS", f"{avg_tacos:.2%}")

    with tab2:
        st.subheader("Performance by Brand")
        brand_summary = merged.groupby('Brand').agg({
            biz_sales: 'sum',
            ad_sales: 'sum',
            ad_spend: 'sum',
            'Stock': 'sum'
        }).reset_index()
        
        brand_summary['TACOS'] = (brand_summary[ad_spend] / brand_summary[biz_sales]).fillna(0)
        brand_summary['Organic Sales'] = brand_summary[biz_sales] - brand_summary[ad_sales]
        
        st.dataframe(
            brand_summary.sort_values(by=biz_sales, ascending=False).style.format({
                biz_sales: '{:,.2f}', ad_sales: '{:,.2f}', ad_spend: '{:,.2f}', 'TACOS': '{:.2%}'
            }), 
            use_container_width=True, hide_index=True
        )

    with tab3:
        st.subheader("Item-Level Audit")
        display_cols = ['Brand', biz_asin, biz_title, 'Stock', biz_sales, ad_sales, ad_spend, 'Organic Sales', 'TACOS']
        st.dataframe(
            merged[display_cols].sort_values(by=biz_sales, ascending=False).style.format({
                biz_sales: '{:,.2f}', ad_sales: '{:,.2f}', ad_spend: '{:,.2f}', 'TACOS': '{:.2%}'
            }), 
            use_container_width=True, hide_index=True
        )

    # --- EXPORT CENTER ---
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        brand_summary.to_excel(writer, sheet_name='Brand_Summary', index=False)
        merged[display_cols].to_excel(writer, sheet_name='ASIN_Audit', index=False)
    
    st.sidebar.markdown("---")
    st.sidebar.download_button(
        label="📥 Download Master Report (Excel)",
        data=output.getvalue(),
        file_name="Amazon_Performance_Master.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    # Mapping Health Check
    unmapped = merged[merged['Brand'] == 'Unmapped']
    if not unmapped.empty:
        st.sidebar.warning(f"Note: {len(unmapped)} ASINs were unmapped. Check naming consistency.")

else:
    st.info("Please upload the Advertising, Business, and Inventory files to begin.")
