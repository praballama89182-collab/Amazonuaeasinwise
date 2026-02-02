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
        if any(kw.lower() == col_clean or kw.lower() in col_clean for kw in keywords):
            if not any(ex.lower() in col_clean for ex in exclude):
                return col
    return None

st.title("🎯 FINAL AMAZON ASIN WISE")
st.info("Verified Framework: Optimized for .txt Inventory Reports (ASIN/SKU Mapping)")

st.sidebar.header("Upload Reports")
ad_file = st.sidebar.file_uploader("1. Ad Report (CSV or Excel)", type=["csv", "xlsx", "xls"])
biz_file = st.sidebar.file_uploader("2. Business Report (CSV or Excel)", type=["csv", "xlsx", "xls"])
inv_file = st.sidebar.file_uploader("3. Inventory Report (.txt or CSV)", type=["txt", "csv"])

if ad_file and biz_file:
    def load_df(file):
        if file.name.endswith('.csv'):
            return pd.read_csv(file)
        elif file.name.endswith('.txt'):
            # Standard Amazon .txt reports are Tab-Separated
            return pd.read_csv(file, sep='\t')
        else:
            return pd.read_excel(file)

    ad_df_raw = load_df(ad_file)
    biz_df_raw = load_df(biz_file)
    inv_df_raw = load_df(inv_file) if inv_file else None

    # Standardize column cleaning
    ad_df_raw.columns = [str(c).strip() for c in ad_df_raw.columns]
    biz_df_raw.columns = [str(c).strip() for c in biz_df_raw.columns]

    # 1. Column Detection
    ad_asin_col = find_robust_col(ad_df_raw, ['Advertised ASIN', 'ASIN'])
    biz_asin_col = find_robust_col(biz_df_raw, ['(Child) ASIN', 'Child ASIN', 'ASIN'])
    biz_title_col = find_robust_col(biz_df_raw, ['Title', 'Item Name'])
    
    ad_sales_col = find_robust_col(ad_df_raw, ['Total Sales', 'Revenue', '7 Day Total Sales'])
    ad_spend_col = find_robust_col(ad_df_raw, ['Spend', 'Cost'])
    biz_sales_col = find_robust_col(biz_df_raw, ['Ordered Product Sales', 'Revenue'])

    # 2. Advanced Inventory Processing
    inv_summary = None
    if inv_df_raw is not None:
        inv_df_raw.columns = [str(c).strip().lower() for c in inv_df_raw.columns]
        # Match ASIN if available, fallback to SKU
        inv_id_col = find_robust_col(inv_df_raw, ['asin', 'sku', 'seller-sku'])
        inv_qty_col = find_robust_col(inv_df_raw, ['quantity', 'qty', 'available'])
        
        if inv_id_col and inv_qty_col:
            # Aggregate by ASIN/SKU and handle missing quantities (NaN -> 0)
            inv_summary = inv_df_raw.groupby(inv_id_col)[inv_qty_col].sum().fillna(0).reset_index()
            inv_summary.columns = ['INV_KEY', 'Available_Inventory']

    # 3. Clean Metrics
    if ad_sales_col: ad_df_raw[ad_sales_col] = ad_df_raw[ad_sales_col].apply(clean_numeric)
    if ad_spend_col: ad_df_raw[ad_spend_col] = ad_df_raw[ad_spend_col].apply(clean_numeric)
    if biz_sales_col: biz_df_raw[biz_sales_col] = biz_df_raw[biz_sales_col].apply(clean_numeric)
    biz_df_raw['Brand'] = biz_df_raw[biz_title_col].apply(get_brand_robust) if biz_title_col else "Unmapped"

    # 4. Aggregation
    ad_asin_total = ad_df_raw.groupby(ad_asin_col).agg({
        ad_sales_col: 'sum', ad_spend_col: 'sum'
    }).reset_index()

    # 5. Merge Strategy
    merged_df = pd.merge(biz_df_raw, ad_asin_total, left_on=biz_asin_col, right_on=ad_asin_col, how='left').fillna(0)
    
    if inv_summary is not None:
        # We join inventory to the business report's ASIN
        merged_df = pd.merge(merged_df, inv_summary, left_on=biz_asin_col, right_on='INV_KEY', how='left')
        # If ASIN didn't match, we try SKU as a fallback if 'sku' column exists in business report
        biz_sku_col = find_robust_col(biz_df_raw, ['sku', 'seller-sku'])
        if biz_sku_col and merged_df['Available_Inventory'].isna().any():
            sku_map = inv_summary.set_index('INV_KEY')['Available_Inventory']
            merged_df['Available_Inventory'] = merged_df['Available_Inventory'].fillna(merged_df[biz_sku_col].map(sku_map))
        
        merged_df['Available_Inventory'] = merged_df['Available_Inventory'].fillna(0)
    else:
        merged_df['Available_Inventory'] = "No File"

    # 6. Final Calculations
    merged_df['Organic Sales'] = merged_df[biz_sales_col] - merged_df[ad_sales_col]
    merged_df['DRR'] = merged_df[biz_sales_col] / 30
    merged_df['Ad Contribution %'] = (merged_df[ad_sales_col] / merged_df[biz_sales_col]).replace([np.inf, -np.inf], 0).fillna(0)
    merged_df['TACOS'] = (merged_df[ad_spend_col] / merged_df[biz_sales_col]).replace([np.inf, -np.inf], 0).fillna(0)

    # 7. UI Display
    table_df = merged_df.rename(columns={
        biz_asin_col: 'ASIN', biz_title_col: 'Item Name', biz_sales_col: 'Total Sales',
        ad_sales_col: 'Ad Sales', ad_spend_col: 'Ad Spend', 'Available_Inventory': 'Stock'
    })

    cols = ['ASIN', 'Item Name', 'Stock', 'Total Sales', 'DRR', 'Ad Sales', 'Ad Spend', 'Organic Sales', 'Ad Contribution %', 'TACOS']
    
    st.subheader("Final ASIN Audit")
    st.dataframe(table_df[cols].sort_values(by='Total Sales', ascending=False), use_container_width=True, hide_index=True)

    # Export
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        table_df[cols].to_excel(writer, sheet_name='Audit', index=False)
    st.sidebar.download_button("📥 Download Master Report", data=output.getvalue(), file_name="Amazon_ASIN_Audit.xlsx")

else:
    st.warning("Please upload the Ad Report, Business Report, and the .txt Inventory Report.")
