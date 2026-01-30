import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO

st.set_page_config(page_title="Final ASIN Audit", page_icon="🎯", layout="wide")

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
    """Strips currency symbols and formatting to return floats."""
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

def find_robust_col(df, keywords, exclude=['acos', 'roas', 'cpc', 'ctr', 'rate', 'new-to-brand']):
    """Finds primary metric columns in Amazon's variable headers."""
    for col in df.columns:
        col_clean = str(col).strip().lower()
        if any(kw.lower() in col_clean for kw in keywords):
            if not any(ex.lower() in col_clean for ex in exclude):
                return col
    return None

st.title("🎯 Final Amazon ASIN Audit")
st.info("Verified Ad Metrics: Campaign Mapping, Velocity (DRR), and Organic Contribution")

st.sidebar.header("Upload Reports")
ad_file = st.sidebar.file_uploader("1. Ad Report (CSV or Excel)", type=["csv", "xlsx", "xls"])
biz_file = st.sidebar.file_uploader("2. Business Report (CSV or Excel)", type=["csv", "xlsx", "xls"])

if ad_file and biz_file:
    def load_flexible_df(file):
        if file.name.endswith('.csv'):
            df = pd.read_csv(file)
        else:
            df = pd.read_excel(file)
        df.columns = [str(c).strip() for c in df.columns]
        return df

    ad_df_raw = load_flexible_df(ad_file)
    biz_df_raw = load_flexible_df(biz_file)

    # Column Mapping
    ad_asin_col = find_robust_col(ad_df_raw, ['Advertised ASIN', 'ASIN'])
    biz_asin_col = find_robust_col(biz_df_raw, ['(Child) ASIN', 'Child ASIN', 'ASIN'])
    biz_title_col = find_robust_col(biz_df_raw, ['Title', 'Item Name'])
    
    # Metrics Mapping
    ad_sales_col = find_robust_col(ad_df_raw, ['Total Sales', 'Revenue'])
    ad_spend_col = find_robust_col(ad_df_raw, ['Spend', 'Cost'])
    ad_clicks_col = find_robust_col(ad_df_raw, ['Clicks'])
    ad_imps_col = find_robust_col(ad_df_raw, ['Impressions'])
    ad_orders_col = find_robust_col(ad_df_raw, ['Orders'])
    biz_sales_col = find_robust_col(biz_df_raw, ['Ordered Product Sales', 'Revenue'])

    # 1. Process Business Data (Source of Truth)
    biz_df = biz_df_raw[[biz_asin_col, biz_title_col, biz_sales_col]].copy()
    biz_df[biz_sales_col] = biz_df[biz_sales_col].apply(clean_numeric)
    biz_df['Brand'] = biz_df[biz_title_col].apply(get_brand_robust)

    # 2. Process Ad Data
    for c in [ad_spend_col, ad_sales_col, ad_clicks_col, ad_imps_col, ad_orders_col]:
        ad_df_raw[c] = ad_df_raw[c].apply(clean_numeric)
        
    ad_summary = ad_df_raw.groupby(ad_asin_col).agg({
        ad_spend_col: 'sum', 
        ad_sales_col: 'sum', 
        ad_clicks_col: 'sum', 
        ad_imps_col: 'sum', 
        ad_orders_col: 'sum',
        'Campaign Name': lambda x: ", ".join(sorted(set(str(v) for v in x if pd.notna(v))))
    }).reset_index()

    # 3. Final Merge (Renaming only to ASIN)
    final_df = pd.merge(biz_df, ad_summary, left_on=biz_asin_col, right_on=ad_asin_col, how='left').fillna(0)
    
    # Rename standardized columns immediately
    final_df = final_df.rename(columns={
        biz_asin_col: 'ASIN', 
        biz_title_col: 'Item Name', 
        biz_sales_col: 'Total Sales', 
        ad_sales_col: 'Ad Sales', 
        ad_spend_col: 'Ad Spend',
        ad_orders_col: 'Orders',
        ad_clicks_col: 'Clicks',
        ad_imps_col: 'Impressions',
        'Campaign Name': 'Associated Campaigns'
    })

    # Remove the redundant mapped ad ASIN column if it exists
    if ad_asin_col in final_df.columns and ad_asin_col != 'ASIN':
        final_df = final_df.drop(columns=[ad_asin_col])

    # 4. Calculation Logic
    final_df['Organic Sales'] = final_df['Total Sales'] - final_df['Ad Sales']
    final_df['DRR'] = final_df['Total Sales'] / 30
    final_df['Ad Contribution %'] = (final_df['Ad Sales'] / final_df['Total Sales']).replace([np.inf, -np.inf], 0).fillna(0)
    final_df['Organic Contribution %'] = (final_df['Organic Sales'] / final_df['Total Sales']).replace([np.inf, -np.inf], 0).fillna(0)
    final_df['ROAS'] = (final_df['Ad Sales'] / final_df['Ad Spend']).replace([np.inf, -np.inf], 0).fillna(0)
    final_df['ACOS'] = (final_df['Ad Spend'] / final_df['Ad Sales']).replace([np.inf, -np.inf], 0).fillna(0)
    final_df['CTR'] = (final_df['Clicks'] / final_df['Impressions']).replace([np.inf, -np.inf], 0).fillna(0)
    final_df['CVR'] = (final_df['Orders'] / final_df['Clicks']).replace([np.inf, -np.inf], 0).fillna(0)

    # UI LAYOUT
    tabs = st.tabs(["🌍 Portfolio Overview"] + sorted(list(BRAND_MAP.values())))

    with tabs[0]:
        st.subheader("Global Portfolio Metrics (30 Days)")
        totals = final_df.select_dtypes(include=[np.number]).sum()
        
        # Aggregated Efficiencies
        p_roas = totals['Ad Sales'] / totals['Ad Spend'] if totals['Ad Spend'] > 0 else 0
        p_acos = totals['Ad Spend'] / totals['Ad Sales'] if totals['Ad Sales'] > 0 else 0
        p_ctr = totals['Clicks'] / totals['Impressions'] if totals['Impressions'] > 0 else 0
        p_cvr = totals['Orders'] / totals['Clicks'] if totals['Clicks'] > 0 else 0
        p_ad_cont = totals['Ad Sales'] / totals['Total Sales'] if totals['Total Sales'] > 0 else 0
        p_org_cont = totals['Organic Sales'] / totals['Total Sales'] if totals['Total Sales'] > 0 else 0

        # Row 1: Primary Contribution
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Sales", f"{totals['Total Sales']:,.2f}")
        c2.metric("Organic Sales", f"{totals['Organic Sales']:,.2f}")
        c3.metric("Ad Sales", f"{totals['Ad Sales']:,.2f}")
        c4.metric("Daily Run Rate (DRR)", f"{totals['DRR']:,.2f}")

        # Row 2: Contribution % & Efficiency
        e1, e2, e3, e4, e5, e6 = st.columns(6)
        e1.metric("Organic Contribution", f"{p_org_cont:.1%}")
        e2.metric("Ad Contribution", f"{p_ad_cont:.1%}")
        e3.metric("ROAS", f"{p_roas:.2f}")
        e4.metric("ACOS", f"{p_acos:.1%}")
        e5.metric("CTR", f"{p_ctr:.2%}")
        e6.metric("CVR", f"{p_cvr:.2%}")
        
        st.divider()
        st.dataframe(final_df.sort_values(by='Total Sales', ascending=False), hide_index=True, use_container_width=True)

    for i, brand in enumerate(sorted(BRAND_MAP.values())):
        with tabs[i+1]:
            b_data = final_df[final_df['Brand'] == brand]
            if not b_data.empty:
                st.subheader(f"{brand} ASIN Velocity & Contribution")
                cols = ['ASIN', 'Item Name', 'Total Sales', 'DRR', 'Ad Sales', 'Organic Sales', 'Organic Contribution %', 'Ad Contribution %', 'ROAS', 'ACOS', 'CTR', 'CVR', 'Associated Campaigns']
                st.dataframe(b_data[cols].sort_values(by='Total Sales', ascending=False), hide_index=True, use_container_width=True)
            else:
                st.warning(f"No active data for {brand}.")

    # Multi-Sheet Export
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        final_df.to_excel(writer, sheet_name='OVERVIEW', index=False)
        for b_name in sorted(BRAND_MAP.values()):
            b_sheet = final_df[final_df['Brand'] == b_name]
            if not b_sheet.empty:
                b_sheet.to_excel(writer, sheet_name=b_name[:31], index=False)
    st.sidebar.download_button("📥 Download ASIN Audit Report", data=output.getvalue(), file_name="Amazon_ASIN_Audit.xlsx", use_container_width=True)

else:
    st.info("Upload your reports (CSV/Excel) to generate the verified ASIN audit.")
