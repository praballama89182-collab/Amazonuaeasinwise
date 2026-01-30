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
    """Safely strips currency symbols and formatting to return floats."""
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
st.info("Verified Ad Metrics: Campaign-First View, Brand Overviews, and ASIN-level DRR")

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

    # 1. Column Identification
    ad_asin_col = find_robust_col(ad_df_raw, ['Advertised ASIN', 'ASIN'])
    biz_asin_col = find_robust_col(biz_df_raw, ['(Child) ASIN', 'Child ASIN', 'ASIN'])
    biz_title_col = find_robust_col(biz_df_raw, ['Title', 'Item Name'])
    
    # Ad Metrics
    ad_sales_col = find_robust_col(ad_df_raw, ['Total Sales', 'Revenue'])
    ad_spend_col = find_robust_col(ad_df_raw, ['Spend', 'Cost'])
    ad_clicks_col = find_robust_col(ad_df_raw, ['Clicks'])
    ad_imps_col = find_robust_col(ad_df_raw, ['Impressions'])
    ad_orders_col = find_robust_col(ad_df_raw, ['Orders'])
    biz_sales_col = find_robust_col(biz_df_raw, ['Ordered Product Sales', 'Revenue'])

    # 2. Process Business Data (ASIN Level Source of Truth)
    biz_df = biz_df_raw.copy()
    biz_df[biz_sales_col] = biz_df[biz_sales_col].apply(clean_numeric)
    biz_df['Brand'] = biz_df[biz_title_col].apply(get_brand_robust)
    
    # 3. Process Ad Data
    for c in [ad_spend_col, ad_sales_col, ad_clicks_col, ad_imps_col, ad_orders_col]:
        ad_df_raw[c] = ad_df_raw[c].apply(clean_numeric)
    
    # Group by Campaign and ASIN
    ad_camp_summary = ad_df_raw.groupby(['Campaign Name', ad_asin_col]).agg({
        ad_spend_col: 'sum', ad_sales_col: 'sum', ad_clicks_col: 'sum', 
        ad_imps_col: 'sum', ad_orders_col: 'sum'
    }).reset_index()

    # Total Ad Sales per ASIN for Organic calculation
    ad_asin_total = ad_df_raw.groupby(ad_asin_col).agg({ad_sales_col: 'sum'}).rename(columns={ad_sales_col: 'ASIN_AD_TOTAL'}).reset_index()

    # 4. Final Merge & Logic
    merged_df = pd.merge(biz_df, ad_camp_summary, left_on=biz_asin_col, right_on=ad_asin_col, how='left')
    merged_df = pd.merge(merged_df, ad_asin_total, on=ad_asin_col, how='left').fillna(0)

    merged_df['Campaign Name'] = merged_df['Campaign Name'].apply(lambda x: x if x != 0 and str(x).strip() != "" else "None")

    # Calculations
    merged_df['Organic Sales'] = merged_df[biz_sales_col] - merged_df['ASIN_AD_TOTAL']
    merged_df['DRR'] = merged_df[biz_sales_col] / 30
    merged_df['Ad Contribution %'] = (merged_df['ASIN_AD_TOTAL'] / merged_df[biz_sales_col]).replace([np.inf, -np.inf], 0).fillna(0)
    merged_df['Organic Contribution %'] = (merged_df['Organic Sales'] / merged_df[biz_sales_col]).replace([np.inf, -np.inf], 0).fillna(0)
    
    # Efficiency
    merged_df['ROAS'] = (merged_df[ad_sales_col] / merged_df[ad_spend_col]).replace([np.inf, -np.inf], 0).fillna(0)
    merged_df['ACOS'] = (merged_df[ad_spend_col] / merged_df[ad_sales_col]).replace([np.inf, -np.inf], 0).fillna(0)
    merged_df['CTR'] = (merged_df[ad_clicks_col] / merged_df[ad_imps_col]).replace([np.inf, -np.inf], 0).fillna(0)
    merged_df['CVR'] = (merged_df[ad_orders_col] / merged_df[ad_clicks_col]).replace([np.inf, -np.inf], 0).fillna(0)

    # Renaming for display
    display_df = merged_df.rename(columns={
        'Campaign Name': 'Campaign', biz_asin_col: 'ASIN', biz_title_col: 'Item Name',
        biz_sales_col: 'Total Sales', ad_sales_col: 'Ad Sales (Campaign)'
    })

    tabs = st.tabs(["🌍 Portfolio Overview"] + sorted(list(BRAND_MAP.values())))

    def show_metrics_header(df_segment):
        """Standardized Overview Header for each tab."""
        t_sales = df_segment.drop_duplicates(subset=['ASIN'])['Total Sales'].sum()
        a_sales = df_segment['Ad Sales (Campaign)'].sum()
        o_sales = t_sales - a_sales
        a_spend = df_segment['Ad Spend'].sum() if 'Ad Spend' in df_segment.columns else df_segment[ad_spend_col].sum()
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Sales", f"{t_sales:,.2f}")
        c2.metric("Organic Sales", f"{o_sales:,.2f}")
        c3.metric("Ad Sales", f"{a_sales:,.2f}")
        c4.metric("Ad Contribution", f"{(a_sales/t_sales):.1%}" if t_sales > 0 else "0%")

    with tabs[0]:
        st.subheader("Global Portfolio Overview")
        show_metrics_header(display_df)
        st.divider()
        cols_to_show = ['Campaign', 'ASIN', 'Item Name', 'Total Sales', 'DRR', 'Ad Sales (Campaign)', 'Organic Sales', 'Ad Contribution %', 'Organic Contribution %', 'ROAS', 'ACOS', 'CTR', 'CVR']
        st.dataframe(display_df[cols_to_show].sort_values(by='Total Sales', ascending=False), hide_index=True, use_container_width=True)

    for i, brand in enumerate(sorted(BRAND_MAP.values())):
        with tabs[i+1]:
            b_data = display_df[display_df['Brand'] == brand]
            if not b_data.empty:
                st.subheader(f"{brand} Overview")
                show_metrics_header(b_data)
                st.divider()
                st.dataframe(b_data[cols_to_show].sort_values(by='Total Sales', ascending=False), hide_index=True, use_container_width=True)
            else:
                st.warning(f"No active data for {brand}.")

    # Export
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        display_df[cols_to_show].to_excel(writer, sheet_name='PORTFOLIO_AUDIT', index=False)
        for b_name in sorted(BRAND_MAP.values()):
            b_sheet = display_df[display_df['Brand'] == b_name]
            if not b_sheet.empty:
                b_sheet[cols_to_show].to_excel(writer, sheet_name=b_name[:31], index=False)
    st.sidebar.download_button("📥 Download ASIN Audit", data=output.getvalue(), file_name="Amazon_ASIN_Audit.xlsx", use_container_width=True)
else:
    st.info("Upload your reports (CSV/Excel) to proceed.")
