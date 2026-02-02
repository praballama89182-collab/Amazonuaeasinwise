import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO

st.set_page_config(page_title="FINAL AMAZON ASIN WISE", page_icon="🎯", layout="wide")

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
    """Deep clean of currency, commas, and non-breaking spaces."""
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
    """Strips hidden spaces from headers to ensure matching."""
    for col in df.columns:
        col_clean = str(col).strip().lower()
        if any(kw.lower() in col_clean for kw in keywords):
            if not any(ex.lower() in col_clean for ex in exclude):
                return col
    return None

st.title("🎯 FINAL AMAZON ASIN WISE")
st.info("Verified Framework: Campaign-First View, Absolute Totals, Inventory Integration, and 30-Day DRR Velocity")

st.sidebar.header("Upload Reports")
ad_file = st.sidebar.file_uploader("1. Ad Report (CSV or Excel)", type=["csv", "xlsx", "xls"])
biz_file = st.sidebar.file_uploader("2. Business Report (CSV or Excel)", type=["csv", "xlsx", "xls"])
inv_file = st.sidebar.file_uploader("3. Inventory Report (.txt or CSV)", type=["txt", "csv"])

if ad_file and biz_file:
    def load_df(file):
        if file.name.endswith('.csv'):
            df = pd.read_csv(file)
        elif file.name.endswith('.txt'):
            df = pd.read_csv(file, sep='\t')
        else:
            df = pd.read_excel(file)
        df.columns = [str(c).strip() for c in df.columns]
        return df

    ad_df_raw = load_df(ad_file)
    biz_df_raw = load_df(biz_file)
    inv_df_raw = load_df(inv_file) if inv_file else None

    # 1. Column Detection
    ad_asin_col = find_robust_col(ad_df_raw, ['Advertised ASIN', 'ASIN'])
    biz_asin_col = find_robust_col(biz_df_raw, ['(Child) ASIN', 'Child ASIN', 'ASIN'])
    biz_title_col = find_robust_col(biz_df_raw, ['Title', 'Item Name'])
    
    ad_sales_col = find_robust_col(ad_df_raw, ['Total Sales', 'Revenue', '7 Day Total Sales'])
    ad_spend_col = find_robust_col(ad_df_raw, ['Spend', 'Cost'])
    ad_clicks_col = find_robust_col(ad_df_raw, ['Clicks'])
    ad_imps_col = find_robust_col(ad_df_raw, ['Impressions'])
    ad_orders_col = find_robust_col(ad_df_raw, ['Total Orders', 'Orders'])
    biz_sales_col = find_robust_col(biz_df_raw, ['Ordered Product Sales', 'Revenue'])

    # DEBUG: Column Verification
    with st.expander("🔍 Column Mapping Debug"):
        st.write("**Ad Report ASIN Column:**", ad_asin_col)
        st.write("**Business Report ASIN Column:**", biz_asin_col)
        if not ad_asin_col or not biz_asin_col:
            st.error("Critical Columns missing! Ensure your Ad Report is an 'Advertised Product' report.")

    # 2. VALIDATION GATE: Stop execution if columns aren't found
    if not ad_asin_col or not biz_asin_col:
        st.warning("Missing required ASIN columns. Please check your file headers.")
        st.stop()

    # 3. Clean Metric Values
    cols_to_clean = [ad_spend_col, ad_sales_col, ad_clicks_col, ad_imps_col, ad_orders_col]
    for c in [col for col in cols_to_clean if col is not None]:
        ad_df_raw[c] = ad_df_raw[c].apply(clean_numeric)
    
    biz_df_raw[biz_sales_col] = biz_df_raw[biz_sales_col].apply(clean_numeric)
    biz_df_raw['Brand'] = biz_df_raw[biz_title_col].apply(get_brand_robust)

    # 4. Process Inventory Data
    inv_summary = None
    if inv_df_raw is not None:
        inv_asin_col = find_robust_col(inv_df_raw, ['asin', 'seller-sku'])
        inv_qty_col = find_robust_col(inv_df_raw, ['Quantity Available', 'Available', 'Quantity', 'afn-fulfillable-quantity'])
        if inv_asin_col and inv_qty_col:
            inv_summary = inv_df_raw.groupby(inv_asin_col)[inv_qty_col].sum().reset_index()
            inv_summary.columns = ['ASIN_INV', 'Available_Inventory']

    # 5. Aggregation Logic
    # We group by Campaign + ASIN. Ensure 'Campaign Name' exists or use a placeholder.
    camp_col = 'Campaign Name' if 'Campaign Name' in ad_df_raw.columns else ad_df_raw.columns[0]
    
    ad_camp_summary = ad_df_raw.groupby([camp_col, ad_asin_col]).agg({
        ad_sales_col: 'sum', ad_spend_col: 'sum', ad_clicks_col: 'sum', 
        ad_imps_col: 'sum', ad_orders_col: 'sum'
    }).reset_index()

    ad_asin_total = ad_df_raw.groupby(ad_asin_col).agg({ad_sales_col: 'sum'}).rename(columns={ad_sales_col: 'ASIN_AD_TOTAL'}).reset_index()

    # 6. Final Merge
    merged_df = pd.merge(biz_df_raw, ad_camp_summary, left_on=biz_asin_col, right_on=ad_asin_col, how='left')
    merged_df = pd.merge(merged_df, ad_asin_total, left_on=biz_asin_col, right_on=ad_asin_col, how='left').fillna(0)
    
    if inv_summary is not None:
        merged_df = pd.merge(merged_df, inv_summary, left_on=biz_asin_col, right_on='ASIN_INV', how='left').fillna(0)
    else:
        merged_df['Available_Inventory'] = "No File"

    merged_df[camp_col] = merged_df[camp_col].replace(0, "None").replace("", "None")

    # 7. Calculation Logic
    merged_df['Organic Sales'] = merged_df[biz_sales_col] - merged_df['ASIN_AD_TOTAL']
    merged_df['DRR'] = merged_df[biz_sales_col] / 30
    merged_df['Ad Contribution %'] = (merged_df['ASIN_AD_TOTAL'] / merged_df[biz_sales_col]).replace([np.inf, -np.inf], 0).fillna(0)
    
    merged_df['ROAS'] = (merged_df[ad_sales_col] / merged_df[ad_spend_col]).replace([np.inf, -np.inf], 0).fillna(0)
    merged_df['ACOS'] = (merged_df[ad_spend_col] / merged_df[ad_sales_col]).replace([np.inf, -np.inf], 0).fillna(0)
    merged_df['TACOS'] = (merged_df[ad_spend_col] / merged_df[biz_sales_col]).replace([np.inf, -np.inf], 0).fillna(0)
    merged_df['CTR'] = (merged_df[ad_clicks_col] / merged_df[ad_imps_col]).replace([np.inf, -np.inf], 0).fillna(0)
    merged_df['CVR'] = (merged_df[ad_orders_col] / merged_df[ad_clicks_col]).replace([np.inf, -np.inf], 0).fillna(0)

    # UI Formatting
    table_df = merged_df.rename(columns={
        camp_col: 'Campaign', biz_asin_col: 'ASIN', biz_title_col: 'Item Name',
        biz_sales_col: 'Total Sales', ad_sales_col: 'Ad Sales (Campaign)', ad_spend_col: 'Spend',
        ad_imps_col: 'Impressions', ad_clicks_col: 'Clicks', 'Available_Inventory': 'Inventory'
    })

    # Dashboard Logic
    tabs = st.tabs(["🌍 Portfolio Overview"] + sorted(list(BRAND_MAP.values())))

    def display_metrics_dashboard(raw_ad_seg, raw_biz_seg):
        t_sales = raw_biz_seg[biz_sales_col].sum()
        a_sales = raw_ad_seg[ad_sales_col].sum()
        o_sales = t_sales - a_sales
        t_spend = raw_ad_seg[ad_spend_col].sum()
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Sales", f"{t_sales:,.2f}")
        c2.metric("Ad Sales", f"{a_sales:,.2f}")
        c3.metric("Organic Sales", f"{o_sales:,.2f}")
        c4.metric("Ad Spend", f"{t_spend:,.2f}")
        
        e1, e2, e3, e4 = st.columns(4)
        e1.metric("ROAS", f"{a_sales/t_spend:.2f}" if t_spend > 0 else "0.00")
        e2.metric("TACOS", f"{(t_spend/t_sales):.1%}" if t_sales > 0 else "0.0%")
        e3.metric("Ad Contrib.", f"{(a_sales/t_sales):.1%}" if t_sales > 0 else "0.0%")
        e4.metric("ACOS", f"{(t_spend/a_sales):.1%}" if a_sales > 0 else "0.0%")

    cols_to_show = ['Campaign', 'ASIN', 'Item Name', 'Inventory', 'Total Sales', 'DRR', 'Ad Sales (Campaign)', 'Spend', 'Organic Sales', 'Ad Contribution %', 'ROAS', 'ACOS', 'TACOS']

    with tabs[0]:
        display_metrics_dashboard(ad_df_raw, biz_df_raw)
        st.dataframe(table_df[cols_to_show].sort_values(by='Total Sales', ascending=False), hide_index=True, use_container_width=True)

    for i, brand in enumerate(sorted(BRAND_MAP.values())):
        with tabs[i+1]:
            b_data = table_df[table_df['Brand'] == brand]
            if not b_data.empty:
                # Filter raw data for accurate dashboard metrics
                brand_asins = b_data['ASIN'].unique()
                raw_ad_b = ad_df_raw[ad_df_raw[ad_asin_col].isin(brand_asins)]
                raw_biz_b = biz_df_raw[biz_df_raw[biz_asin_col].isin(brand_asins)]
                
                display_metrics_dashboard(raw_ad_b, raw_biz_b)
                st.dataframe(b_data[cols_to_show].sort_values(by='Total Sales', ascending=False), hide_index=True, use_container_width=True)
            else:
                st.warning(f"No products found for {brand}.")

    # Export
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        table_df[cols_to_show].to_excel(writer, sheet_name='OVERVIEW', index=False)
    st.sidebar.download_button("📥 Download Master Report", data=output.getvalue(), file_name="Amazon_Audit.xlsx", use_container_width=True)

else:
    st.info("Please upload Ad and Business reports to generate the audit.")
