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
    """Safely converts currency strings to numbers, removing AED and commas."""
    if isinstance(val, str):
        cleaned = val.replace('AED', '').replace('$', '').replace('\xa0', '').replace(',', '').strip()
        try: return pd.to_numeric(cleaned)
        except: return 0.0
    return val if isinstance(val, (int, float)) else 0.0

def get_brand_robust(name):
    """Maps items to core brands using title patterns."""
    if pd.isna(name): return "Unmapped"
    n = str(name).upper().replace('’', "'").strip()
    for prefix, full_name in BRAND_MAP.items():
        fn = full_name.upper().replace('’', "'")
        if fn in n or any(n.startswith(f"{prefix}{sep}") for sep in ["_", " ", "-", " |"]):
            return full_name
    return "Unmapped"

def find_robust_col(df, keywords, exclude=['acos', 'roas', 'cpc', 'ctr', 'rate']):
    """Finds exact metric columns while ignoring calculated ratios."""
    for col in df.columns:
        col_clean = str(col).strip().lower()
        if any(kw.lower() in col_clean for kw in keywords):
            # Ensure we don't pick up ratios or percentages when looking for absolute sales/spend
            if not any(ex.lower() in col_clean for ex in exclude):
                return col
    return None

st.title("🎯 ASIN-Wise Performance Audit")
st.info("Verified Audit: 30-Day Velocity, Organic Pull, and Paid Contribution")

st.sidebar.header("Upload Reports")
ad_file = st.sidebar.file_uploader("1. Advertised Product Report (Ads)", type=["csv", "xlsx"])
biz_file = st.sidebar.file_uploader("2. Business Report (30-Day Total Sales)", type=["csv", "xlsx"])

if ad_file and biz_file:
    def load_df(file):
        df = pd.read_csv(file) if file.name.endswith('.csv') else pd.read_excel(file)
        df.columns = [str(c).strip() for c in df.columns]
        return df

    ad_df_raw = load_df(ad_file)
    biz_df_raw = load_df(biz_file)
    
    # Header Mapping Logic (Updated for Business Report (Child) ASIN formats)
    ad_asin_col = find_robust_col(ad_df_raw, ['Advertised ASIN', 'ASIN'])
    biz_asin_col = find_robust_col(biz_df_raw, ['(Child) ASIN', 'Child ASIN', 'ASIN'])
    biz_title_col = find_robust_col(biz_df_raw, ['Title', 'Item Name'])
    
    # Detect Numeric Metric Columns
    ad_sales_col = find_robust_col(ad_df_raw, ['Total Sales', 'Revenue'])
    ad_spend_col = find_robust_col(ad_df_raw, ['Spend', 'Cost'])
    ad_clicks_col = find_robust_col(ad_df_raw, ['Clicks'])
    ad_imps_col = find_robust_col(ad_df_raw, ['Impressions'])
    ad_orders_col = find_robust_col(ad_df_raw, ['Total Orders', 'Orders'])
    biz_sales_col = find_robust_col(biz_df_raw, ['Ordered Product Sales', 'Revenue'])

    # Safety Check: Ensure all critical columns were found
    if not all([ad_asin_col, biz_asin_col, biz_sales_col, ad_sales_col]):
        st.error("Could not find all required columns. Please ensure you are uploading the standard Amazon Advertised Product and Business Reports.")
        st.write("Found Columns:", {"Ad ASIN": ad_asin_col, "Biz ASIN": biz_asin_col, "Biz Sales": biz_sales_col, "Ad Sales": ad_sales_col})
    else:
        # 1. Clean Business Data
        biz_df = biz_df_raw[[biz_asin_col, biz_title_col, biz_sales_col]].copy()
        biz_df[biz_sales_col] = biz_df[biz_sales_col].apply(clean_numeric)
        biz_df['Brand'] = biz_df[biz_title_col].apply(get_brand_robust)

        # 2. Clean Ad Data & Aggregate by ASIN
        for c in [ad_spend_col, ad_sales_col, ad_clicks_col, ad_imps_col, ad_orders_col]:
            ad_df_raw[c] = ad_df_raw[c].apply(clean_numeric)
            
        ad_summary = ad_df_raw.groupby(ad_asin_col).agg({
            ad_spend_col: 'sum', ad_sales_col: 'sum', ad_clicks_col: 'sum', ad_imps_col: 'sum', ad_orders_col: 'sum'
        }).reset_index()

        # 3. Final Merge & KPI Calculation
        final_df = pd.merge(biz_df, ad_summary, left_on=biz_asin_col, right_on=ad_asin_col, how='left').fillna(0)
        
        final_df['Organic Sales'] = final_df[biz_sales_col] - final_df[ad_sales_col]
        final_df['DRR'] = final_df[biz_sales_col] / 30
        final_df['Ad Contribution %'] = (final_df[ad_sales_col] / final_df[biz_sales_col]).replace([np.inf, -np.inf], 0).fillna(0)
        final_df['ROAS'] = (final_df[ad_sales_col] / final_df[ad_spend_col]).replace([np.inf, -np.inf], 0).fillna(0)
        final_df['CTR'] = (final_df[ad_clicks_col] / final_df[ad_imps_col]).replace([np.inf, -np.inf], 0).fillna(0)
        final_df['CVR'] = (final_df[ad_orders_col] / final_df[ad_clicks_col]).replace([np.inf, -np.inf], 0).fillna(0)

        # Standardize Names for UI
        final_df = final_df.rename(columns={
            biz_asin_col: 'ASIN', biz_title_col: 'Item Name', biz_sales_col: 'Total Sales', 
            ad_sales_col: 'Ad Sales', ad_spend_col: 'Ad Spend'
        })

        tabs = st.tabs(["🌍 Portfolio Overview"] + sorted(list(BRAND_MAP.values())))

        # Portfolio Tab
        with tabs[0]:
            st.subheader("Global Portfolio Summary (30 Days)")
            totals = final_df.select_dtypes(include=[np.number]).sum()
            
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("Total Sales", f"{totals['Total Sales']:,.2f}")
            c2.metric("Ad Sales", f"{totals['Ad Sales']:,.2f}")
            c3.metric("Organic Sales", f"{totals['Organic Sales']:,.2f}")
            c4.metric("Daily Run Rate (DRR)", f"{totals['DRR']:,.2f}")
            c5.metric("Paid Contrib %", f"{(totals['Ad Sales']/totals['Total Sales']):.1%}")
            
            st.divider()
            st.dataframe(final_df.sort_values(by='Total Sales', ascending=False), hide_index=True, use_container_width=True)

        # Brand Tabs
        for i, brand in enumerate(sorted(BRAND_MAP.values())):
            with tabs[i+1]:
                b_data = final_df[final_df['Brand'] == brand]
                if not b_data.empty:
                    st.subheader(f"{brand} - ASIN Velocity & Contribution")
                    # Display metrics with DRR included
                    st.dataframe(b_data[['ASIN', 'Item Name', 'Total Sales', 'DRR', 'Ad Sales', 'Organic Sales', 'Ad Contribution %', 'ROAS', 'CTR', 'CVR']].sort_values(by='Total Sales', ascending=False), hide_index=True, use_container_width=True)
                else:
                    st.warning(f"No active data found for {brand} in these reports.")

        # Multi-Sheet Excel Export
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            final_df.to_excel(writer, sheet_name='OVERVIEW_AUDIT', index=False)
            for brand_name in sorted(BRAND_MAP.values()):
                brand_sheet = final_df[final_df['Brand'] == brand_name]
                if not brand_sheet.empty:
                    brand_sheet.to_excel(writer, sheet_name=brand_name[:31], index=False)
        st.sidebar.download_button("📥 Download ASIN Audit Report", data=output.getvalue(), file_name="Amazon_ASIN_Contribution_Audit.xlsx", use_container_width=True)

else:
    st.info("Upload your 30-day reports to generate the ASIN Performance Audit.")
