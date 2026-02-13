import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO

st.set_page_config(page_title="AMAZON MASTER BRAND AUDIT", page_icon="📊", layout="wide")

# 1. Definitive Brand Mapping Configuration
BRAND_MAP = {
    'MA': 'Maison de l’Avenir',
    'CL': 'Creation Lamis',
    'JPD': 'Jean Paul Dupont',
    'PC': 'Paris Collection',
    'DC': 'Dorall Collection',
    'CPT': 'CP Trendies'
}

def clean_numeric(val):
    """Handles currency symbols, commas, and non-breaking spaces."""
    if isinstance(val, str):
        cleaned = val.replace('AED', '').replace('$', '').replace('\xa0', '').replace(',', '').strip()
        try: return pd.to_numeric(cleaned)
        except: return 0.0
    return val if isinstance(val, (int, float)) else 0.0

def get_brand_robust(row, title_col=None, sku_col=None, camp_col=None):
    """Categorizes rows into brands by scanning Title, SKU, and Campaign Name."""
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
    """Finds columns matching keywords, handling trailing spaces and exclusions."""
    for col in df.columns:
        col_clean = str(col).strip().lower()
        if any(kw.lower() in col_clean for kw in keywords):
            if exclude and any(ex.lower() in col_clean for ex in exclude): continue
            return col
    return None

def load_data(file):
    """Utility to load CSV or Excel files."""
    if file.name.endswith('.csv'):
        return pd.read_csv(file)
    else:
        return pd.read_excel(file)

# --- UI Setup ---
st.title("📊 Amazon Master Brand & ASIN Audit")
st.markdown("---")

st.sidebar.header("📁 Report Upload Center")
ad_file = st.sidebar.file_uploader("1. Ad Report (CSV or Excel)", type=["csv", "xlsx", "xls"])
biz_file = st.sidebar.file_uploader("2. Business Report (CSV or Excel)", type=["csv", "xlsx", "xls"])
inv_file = st.sidebar.file_uploader("3. Inventory Report (.txt)", type=["txt"])

if ad_file and biz_file and inv_file:
    with st.spinner('Syncing reports and cross-checking data...'):
        # Load Data
        ad_df_raw = load_data(ad_file)
        biz_df_raw = load_data(biz_file)
        inv_df_raw = pd.read_csv(inv_file, sep='\t')

        # Standardize headers
        ad_df_raw.columns = [c.strip() for c in ad_df_raw.columns]
        biz_df_raw.columns = [c.strip() for c in biz_df_raw.columns]
        inv_df_raw.columns = [c.strip().lower() for c in inv_df_raw.columns]

        # 1. Inventory Consolidation (by ASIN)
        inv_summary = inv_df_raw.groupby('asin')['quantity available'].sum().reset_index()
        inv_summary.columns = ['ASIN_KEY', 'Stock']

        # 2. Column Identification
        b_asin = find_robust_col(biz_df_raw, ['asin', 'child asin'])
        b_sales = find_robust_col(biz_df_raw, ['ordered product sales', 'revenue'])
        b_title = find_robust_col(biz_df_raw, ['title', 'item name'])
        b_sku = find_robust_col(biz_df_raw, ['sku', 'seller-sku'])
        
        a_asin = find_robust_col(ad_df_raw, ['advertised asin'])
        a_total_sales = find_robust_col(ad_df_raw, ['7 Day Total Sales']) # Corrected for full sales
        a_direct_sales = find_robust_col(ad_df_raw, ['7 Day Advertised SKU Sales'])
        a_halo_sales = find_robust_col(ad_df_raw, ['7 Day Other SKU Sales'])
        a_spend = find_robust_col(ad_df_raw, ['spend'])
        a_sku = find_robust_col(ad_df_raw, ['advertised sku'])
        a_camp = find_robust_col(ad_df_raw, ['campaign name'])

        # 3. Numeric Cleaning
        biz_df_raw[b_sales] = biz_df_raw[b_sales].apply(clean_numeric)
        for col in [a_total_sales, a_direct_sales, a_halo_sales, a_spend]:
            if col: ad_df_raw[col] = ad_df_raw[col].apply(clean_numeric)

        # 4. Ad Data Aggregation
        ad_summary = ad_df_raw.groupby(a_asin).agg({
            a_total_sales: 'sum', a_direct_sales: 'sum',
            a_halo_sales: 'sum', a_spend: 'sum',
            a_camp: 'first', a_sku: 'first'
        }).reset_index()

        # 5. Master Data Merge
        merged = pd.merge(biz_df_raw, ad_summary, left_on=b_asin, right_on=a_asin, how='left').fillna(0)
        merged = pd.merge(merged, inv_summary, left_on=b_asin, right_on='ASIN_KEY', how='left').fillna(0)
        
        # 6. Final Mapping & Calcs
        merged['Brand'] = merged.apply(lambda r: get_brand_robust(r, b_title, b_sku, a_camp), axis=1)
        merged['Organic Sales'] = merged[b_sales] - merged[a_total_sales]
        merged['TACOS'] = (merged[a_spend] / merged[b_sales]).replace([np.inf, -np.inf], 0).fillna(0)

    # --- TABBED INTERFACE ---
    tab_list = ["🌎 Global Summary"] + list(BRAND_MAP.values())
    tabs = st.tabs(tab_list)

    # Global Summary Tab
    with tabs[0]:
        st.subheader("Account Portfolio Summary")
        m1, m2, m3, m4 = st.columns(4)
        total_rev = merged[b_sales].sum()
        total_ad = merged[a_total_sales].sum()
        m1.metric("Total Sales", f"AED {total_rev:,.2f}")
        m2.metric("Ad Sales", f"AED {total_ad:,.2f}")
        m3.metric("Total Spend", f"AED {merged[a_spend].sum():,.2f}")
        m4.metric("Total TACOS", f"{(merged[a_spend].sum()/total_rev if total_rev > 0 else 0):.2%}")

        st.markdown("### 📊 Brand Breakdown")
        brand_perf = merged.groupby('Brand').agg({
            b_sales: 'sum', a_total_sales: 'sum', a_spend: 'sum', 'Stock': 'sum'
        }).reset_index().sort_values(by=b_sales, ascending=False)
        st.dataframe(brand_perf, use_container_width=True, hide_index=True)

    # Individual Brand Tabs
    for idx, brand_name in enumerate(BRAND_MAP.values(), start=1):
        with tabs[idx]:
            b_data = merged[merged['Brand'] == brand_name]
            if not b_data.empty:
                st.subheader(f"{brand_name} Summary")
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Total Sales", f"AED {b_data[b_sales].sum():,.2f}")
                c2.metric("Ad Sales", f"AED {b_data[a_total_sales].sum():,.2f}")
                c3.metric("Spend", f"AED {b_data[a_spend].sum():,.2f}")
                c4.metric("Stock", f"{b_data['Stock'].sum():,.0f}")
                
                st.markdown(f"### 🎯 {brand_name} ASIN Audit")
                audit_cols = [b_asin, b_title, 'Stock', b_sales, a_total_sales, a_direct_sales, a_halo_sales, a_spend, 'Organic Sales', 'TACOS']
                st.dataframe(b_data[audit_cols].sort_values(by=b_sales, ascending=False), use_container_width=True, hide_index=True)
            else:
                st.info(f"No active data found for {brand_name} in these reports.")

    # --- EXPORT ---
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        brand_perf.to_excel(writer, sheet_name='Global_Summary', index=False)
        for name in BRAND_MAP.values():
            sheet_name = name[:30] # Excel limit
            merged[merged['Brand'] == name].to_excel(writer, sheet_name=sheet_name, index=False)
    
    st.sidebar.markdown("---")
    st.sidebar.download_button("📥 Download Excel Master Report", data=output.getvalue(), file_name="Amazon_Performance_Audit.xlsx")

else:
    st.info("Please upload the Advertising, Business, and Inventory files to begin.")
