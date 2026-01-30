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
    """Clean currency and formatting for math."""
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

def find_robust_col(df, keywords, exclude=['acos', 'roas', 'cpc', 'ctr', 'rate', 'new-to-brand']):
    for col in df.columns:
        col_clean = str(col).strip().lower()
        if any(kw.lower() in col_clean for kw in keywords):
            if not any(ex.lower() in col_clean for ex in exclude):
                return col
    return None

st.title("🎯 Final Amazon ASIN Audit")
st.info("Verified Dashboard: 10+ KPIs, Campaign-First Mapping, and 30-Day DRR Velocity")

st.sidebar.header("Upload Reports")
ad_file = st.sidebar.file_uploader("1. Ad Report (CSV or Excel)", type=["csv", "xlsx", "xls"])
biz_file = st.sidebar.file_uploader("2. Business Report (CSV or Excel)", type=["csv", "xlsx", "xls"])

if ad_file and biz_file:
    def load_df(file):
        df = pd.read_csv(file) if file.name.endswith('.csv') else pd.read_excel(file)
        df.columns = [str(c).strip() for c in df.columns]
        return df

    ad_df_raw = load_df(ad_file)
    biz_df_raw = load_df(biz_file)

    # 1. Column Detection
    ad_asin_col = find_robust_col(ad_df_raw, ['Advertised ASIN', 'ASIN'])
    biz_asin_col = find_robust_col(biz_df_raw, ['(Child) ASIN', 'Child ASIN', 'ASIN'])
    biz_title_col = find_robust_col(biz_df_raw, ['Title', 'Item Name'])
    
    ad_sales_col = find_robust_col(ad_df_raw, ['Total Sales', 'Revenue'])
    ad_spend_col = find_robust_col(ad_df_raw, ['Spend', 'Cost'])
    ad_clicks_col = find_robust_col(ad_df_raw, ['Clicks'])
    ad_imps_col = find_robust_col(ad_df_raw, ['Impressions'])
    ad_orders_col = find_robust_col(ad_df_raw, ['Orders'])
    biz_sales_col = find_robust_col(biz_df_raw, ['Ordered Product Sales', 'Revenue'])

    # 2. Cleaning & Processing
    for c in [ad_spend_col, ad_sales_col, ad_clicks_col, ad_imps_col, ad_orders_col]:
        ad_df_raw[c] = ad_df_raw[c].apply(clean_numeric)
    
    biz_df = biz_df_raw.copy()
    biz_df[biz_sales_col] = biz_df[biz_sales_col].apply(clean_numeric)
    biz_df['Brand'] = biz_df[biz_title_col].apply(get_brand_robust)

    # 3. Aggregate Ad Data (Campaign + ASIN)
    ad_camp_summary = ad_df_raw.groupby(['Campaign Name', ad_asin_col]).agg({
        ad_spend_col: 'sum', ad_sales_col: 'sum', ad_clicks_col: 'sum', 
        ad_imps_col: 'sum', ad_orders_col: 'sum'
    }).reset_index()

    # Per-ASIN Ad Total for Organic isolation
    ad_asin_total = ad_df_raw.groupby(ad_asin_col).agg({ad_sales_col: 'sum', ad_spend_col: 'sum'}).rename(columns={ad_sales_col: 'ASIN_AD_SALES', ad_spend_col: 'ASIN_AD_SPEND'}).reset_index()

    # 4. Final Merge
    merged_df = pd.merge(biz_df, ad_camp_summary, left_on=biz_asin_col, right_on=ad_asin_col, how='left')
    merged_df = pd.merge(merged_df, ad_asin_total, on=ad_asin_col, how='left').fillna(0)
    merged_df['Campaign Name'] = merged_df['Campaign Name'].apply(lambda x: x if x != 0 and str(x).strip() != "" else "None")

    # Metrics Logic
    merged_df['Organic Sales'] = merged_df[biz_sales_col] - merged_df['ASIN_AD_SALES']
    merged_df['DRR'] = merged_df[biz_sales_col] / 30
    merged_df['Ad Contribution %'] = (merged_df['ASIN_AD_SALES'] / merged_df[biz_sales_col]).replace([np.inf, -np.inf], 0).fillna(0)
    merged_df['Organic Contribution %'] = (merged_df['Organic Sales'] / merged_df[biz_sales_col]).replace([np.inf, -np.inf], 0).fillna(0)
    
    # Ratios
    merged_df['ROAS'] = (merged_df[ad_sales_col] / merged_df[ad_spend_col]).replace([np.inf, -np.inf], 0).fillna(0)
    merged_df['ACOS'] = (merged_df[ad_spend_col] / merged_df[ad_sales_col]).replace([np.inf, -np.inf], 0).fillna(0)
    merged_df['TACOS'] = (merged_df[ad_spend_col] / merged_df[biz_sales_col]).replace([np.inf, -np.inf], 0).fillna(0)
    merged_df['CTR'] = (merged_df[ad_clicks_col] / merged_df[ad_imps_col]).replace([np.inf, -np.inf], 0).fillna(0)
    merged_df['CVR'] = (merged_df[ad_orders_col] / merged_df[ad_clicks_col]).replace([np.inf, -np.inf], 0).fillna(0)

    # Renaming for Table
    table_df = merged_df.rename(columns={
        'Campaign Name': 'Campaign', biz_asin_col: 'ASIN', biz_title_col: 'Item Name',
        biz_sales_col: 'Total Sales', ad_sales_col: 'Ad Sales (Campaign)', ad_spend_col: 'Spend',
        ad_imps_col: 'Impressions', ad_clicks_col: 'Clicks'
    })

    tabs = st.tabs(["🌍 Portfolio Overview"] + sorted(list(BRAND_MAP.values())))

    def display_metrics_dashboard(df_seg, is_global=False):
        """Unified 13-metric dashboard for overall and brands."""
        # Deduplicate to get accurate business sales
        unique_biz = df_seg.drop_duplicates(subset=['ASIN'])
        t_sales = unique_biz['Total Sales'].sum()
        a_sales = df_seg['Ad Sales (Campaign)'].sum()
        o_sales = t_sales - a_sales
        t_spend = df_seg['Spend'].sum()
        t_imps = df_seg['Impressions'].sum()
        t_clicks = df_seg['Clicks'].sum()
        t_orders = df_seg[ad_orders_col].sum() if ad_orders_col in df_seg.columns else 0

        # Ratios
        roas = a_sales / t_spend if t_spend > 0 else 0
        acos = t_spend / a_sales if a_sales > 0 else 0
        tacos = t_spend / t_sales if t_sales > 0 else 0
        ctr = t_clicks / t_imps if t_imps > 0 else 0
        cvr = t_orders / t_clicks if t_clicks > 0 else 0
        ad_cont = a_sales / t_sales if t_sales > 0 else 0
        org_cont = 1 - ad_cont

        st.markdown("#### 💰 Sales & Volume Metrics")
        c1, c2, c3, c4, c5, c6 = st.columns(6)
        c1.metric("Total Sales", f"{t_sales:,.2f}")
        c2.metric("Ad Sales", f"{a_sales:,.2f}")
        c3.metric("Organic Sales", f"{o_sales:,.2f}")
        c4.metric("Ad Spend", f"{t_spend:,.2f}")
        c5.metric("Impressions", f"{t_imps:,.0f}")
        c6.metric("Clicks", f"{t_clicks:,.0f}")

        st.markdown("#### ⚡ Efficiency & Contribution Metrics")
        e1, e2, e3, e4, e5, e6, e7 = st.columns(7)
        e1.metric("ROAS", f"{roas:.2f}")
        e2.metric("ACOS", f"{acos:.1%}")
        e3.metric("TACOS", f"{tacos:.1%}")
        e4.metric("CTR", f"{ctr:.2%}")
        e5.metric("CVR", f"{cvr:.2%}")
        e6.metric("Ad Contrib.", f"{ad_cont:.1%}")
        e7.metric("Org Contrib.", f"{org_cont:.1%}")

    with tabs[0]:
        st.subheader("Global Portfolio Dashboard")
        display_metrics_dashboard(table_df, is_global=True)
        st.divider()
        cols = ['Campaign', 'ASIN', 'Item Name', 'Total Sales', 'DRR', 'Ad Sales (Campaign)', 'Spend', 'Organic Sales', 'Ad Contribution %', 'ROAS', 'ACOS', 'TACOS', 'CTR', 'CVR', 'Impressions', 'Clicks']
        st.dataframe(table_df[cols].sort_values(by='Total Sales', ascending=False), hide_index=True, use_container_width=True)

    for i, brand in enumerate(sorted(BRAND_MAP.values())):
        with tabs[i+1]:
            b_data = table_df[table_df['Brand'] == brand]
            if not b_data.empty:
                st.subheader(f"{brand} Overview")
                display_metrics_dashboard(b_data)
                st.divider()
                st.dataframe(b_data[cols].sort_values(by='Total Sales', ascending=False), hide_index=True, use_container_width=True)
            else:
                st.warning(f"No products found for {brand}.")

    # Multi-Sheet Export
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        table_df[cols].to_excel(writer, sheet_name='OVERVIEW', index=False)
        for b_name in sorted(BRAND_MAP.values()):
            b_sheet = table_df[table_df['Brand'] == b_name]
            if not b_sheet.empty:
                b_sheet[cols].to_excel(writer, sheet_name=b_name[:31], index=False)
    st.sidebar.download_button("📥 Download Master Report", data=output.getvalue(), file_name="Amazon_ASIN_Audit_Master.xlsx", use_container_width=True)
else:
    st.info("Upload your Ad and Business reports to begin the audit.")
