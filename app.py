import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO

st.set_page_config(page_title="ASIN Performance Audit", page_icon="🎯", layout="wide")

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
    """Safely converts currency and formatted strings to numbers, removing AED and commas."""
    if isinstance(val, str):
        cleaned = val.replace('AED', '').replace('$', '').replace('\xa0', '').replace(',', '').strip()
        try: return pd.to_numeric(cleaned)
        except: return 0.0
    return val if isinstance(val, (int, float)) else 0.0

def get_brand_robust(name):
    """Maps items to core brands using title patterns and prefixes."""
    if pd.isna(name): return "Unmapped"
    n = str(name).upper().replace('’', "'").strip()
    for prefix, full_name in BRAND_MAP.items():
        fn = full_name.upper().replace('’', "'")
        if fn in n or any(n.startswith(f"{prefix}{sep}") for sep in ["_", " ", "-", " |"]):
            return full_name
    return "Unmapped"

def find_robust_col(df, keywords, exclude=['acos', 'roas', 'cpc', 'ctr', 'rate', '(']):
    """Finds exact metric columns (Total Sales, Spend) avoiding derived ratios."""
    for col in df.columns:
        col_clean = str(col).strip().lower()
        if any(kw.lower() in col_clean for kw in keywords):
            if not any(ex.lower() in col_clean for ex in exclude):
                return col
    return None

st.title("🎯 ASIN-Wise Performance Audit")
st.info("Verified Audit: Mapping ASIN Data between Ads and Business Reports")

st.sidebar.header("Upload Files")
ad_file = st.sidebar.file_uploader("1. Advertised Product Report (Ads)", type=["csv", "xlsx"])
biz_file = st.sidebar.file_uploader("2. Business Report (Total Sales)", type=["csv", "xlsx"])

if ad_file and biz_file:
    def load_df(file):
        df = pd.read_csv(file) if file.name.endswith('.csv') else pd.read_excel(file)
        df.columns = [str(c).strip() for c in df.columns]
        return df

    # Load and map columns
    ad_df_raw, biz_df_raw = load_df(ad_file), load_df(biz_file)
    
    # Header Mapping (Verified with test run)
    ad_asin_col = find_robust_col(ad_df_raw, ['Advertised ASIN', 'ASIN'])
    biz_asin_col = find_robust_col(biz_df_raw, ['Child ASIN', 'ASIN'])
    biz_title_col = find_robust_col(biz_df_raw, ['Title', 'Item Name'])
    
    # Metric Columns (Handles hidden spaces)
    ad_sales_col = find_robust_col(ad_df_raw, ['Total Sales'])
    ad_spend_col = find_robust_col(ad_df_raw, ['Spend', 'Cost'])
    ad_clicks_col = find_robust_col(ad_df_raw, ['Clicks'])
    ad_imps_col = find_robust_col(ad_df_raw, ['Impressions'])
    ad_orders_col = find_robust_col(ad_df_raw, ['Total Orders'])
    biz_sales_col = find_robust_col(biz_df_raw, ['Ordered Product Sales', 'Revenue'])

    # 1. Clean Business Data
    biz_df = biz_df_raw[[biz_asin_col, biz_title_col, biz_sales_col]].copy()
    biz_df[biz_sales_col] = biz_df[biz_sales_col].apply(clean_numeric)
    biz_df['Brand'] = biz_df[biz_title_col].apply(get_brand_robust)

    # 2. Aggregate Ad Metrics by ASIN
    # Forces numeric cleaning before sum to avoid aggregation errors
    for c in [ad_spend_col, ad_sales_col, ad_clicks_col, ad_imps_col, ad_orders_col]:
        ad_df_raw[c] = ad_df_raw[c].apply(clean_numeric)
        
    ad_summary = ad_df_raw.groupby(ad_asin_col).agg({
        ad_spend_col: 'sum', ad_sales_col: 'sum', ad_clicks_col: 'sum', ad_imps_col: 'sum', ad_orders_col: 'sum'
    }).reset_index()

    # 3. Final Merge and Calculation
    final_df = pd.merge(biz_df, ad_summary, left_on=biz_asin_col, right_on=ad_asin_col, how='left').fillna(0)
    
    final_df['Organic Sales'] = final_df[biz_sales_col] - final_df[ad_sales_col]
    final_df['Ad Contribution %'] = (final_df[ad_sales_col] / final_df[biz_sales_col]).replace([np.inf, -np.inf], 0).fillna(0)
    final_df['ROAS'] = (final_df[ad_sales_col] / final_df[ad_spend_col]).replace([np.inf, -np.inf], 0).fillna(0)
    final_df['CTR'] = (final_df[ad_clicks_col] / final_df[ad_imps_col]).replace([np.inf, -np.inf], 0).fillna(0)
    final_df['CVR'] = (final_df[ad_orders_col] / final_df[ad_clicks_col]).replace([np.inf, -np.inf], 0).fillna(0)

    # Standardize column names for UI
    final_df = final_df.rename(columns={
        biz_asin_col: 'ASIN', biz_title_col: 'Item Name', biz_sales_col: 'Total Sales', 
        ad_sales_col: 'Ad Sales', ad_spend_col: 'Ad Spend', ad_clicks_col: 'Clicks',
        ad_imps_col: 'Impressions', ad_orders_col: 'Orders'
    })

    tabs = st.tabs(["🌍 Portfolio Overview"] + sorted(list(BRAND_MAP.values())))

    with tabs[0]:
        st.subheader("Global ASIN Performance Overview")
        totals = final_df.select_dtypes(include=[np.number]).sum()
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Overall Sales", f"{totals['Total Sales']:,.2f}")
        c2.metric("Overall Ad Sales", f"{totals['Ad Sales']:,.2f}")
        c3.metric("Overall Organic Sales", f"{totals['Organic Sales']:,.2f}")
        c4.metric("Portfolio Ad Contribution", f"{(totals['Ad Sales']/totals['Total Sales']):.1%}")
        
        st.divider()
        st.dataframe(final_df.sort_values(by='Total Sales', ascending=False), hide_index=True, use_container_width=True)

    for i, brand in enumerate(sorted(BRAND_MAP.values())):
        with tabs[i+1]:
            b_data = final_df[final_df['Brand'] == brand]
            if not b_data.empty:
                st.subheader(f"ASIN Breakdown: {brand}")
                # Re-sorting by highest total sales
                st.dataframe(b_data[['ASIN', 'Item Name', 'Total Sales', 'Ad Sales', 'Organic Sales', 'Ad Contribution %', 'ROAS', 'CTR', 'CVR']].sort_values(by='Total Sales', ascending=False), hide_index=True, use_container_width=True)
            else:
                st.warning(f"No products detected for {brand} in current reports.")

    # Excel Export (Single File, Multi-Sheet)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        final_df.to_excel(writer, sheet_name='PORTFOLIO_OVERVIEW', index=False)
        for brand_name in sorted(BRAND_MAP.values()):
            brand_sheet = final_df[final_df['Brand'] == brand_name]
            if not brand_sheet.empty:
                brand_sheet.to_excel(writer, sheet_name=brand_name[:31], index=False)
    st.sidebar.download_button("📥 Download Audit Excel", data=output.getvalue(), file_name="Amazon_ASIN_Audit.xlsx", use_container_width=True)
else:
    st.info("Upload the Advertised Product (Ads) and Business (Sales) reports to view the contribution audit.")
