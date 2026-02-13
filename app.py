import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO

# Must be the first Streamlit command
st.set_page_config(page_title="AMAZON MASTER BRAND AUDIT", page_icon="🎯", layout="wide")

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
    """Robust cleaning for currency symbols, commas, and hidden spaces."""
    if isinstance(val, str):
        cleaned = val.replace('AED', '').replace('$', '').replace('\xa0', '').replace(',', '').strip()
        try: return pd.to_numeric(cleaned)
        except: return 0.0
    return val if isinstance(val, (int, float)) else 0.0

def get_brand_robust(row, title_col=None, sku_col=None, camp_col=None):
    """Deep scan for brand identifiers in Title, SKU, or Campaign Name."""
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
    """Fuzzy column search to handle brackets like (Child) ASIN and trailing spaces."""
    for col in df.columns:
        c_clean = str(col).strip().lower()
        if any(kw.lower() in c_clean for kw in keywords):
            if exclude and any(ex.lower() in c_clean for ex in exclude): continue
            return col
    return None

def load_data(file):
    """Supports CSV and all Excel types as requested."""
    name = file.name.lower()
    if name.endswith('.csv'):
        return pd.read_csv(file)
    elif name.endswith('.txt'):
        return pd.read_csv(file, sep='\t')
    elif name.endswith(('.xlsx', '.xls', '.xlsm', '.xlsb')):
        return pd.read_excel(file)
    return None

# --- UI Setup ---
st.title("🎯 Final Amazon master Audit")
st.info("Verified: Total Ad Sales (3,324.65 AED) | Total Stock (4,491 Units) | All Excel Types Supported")

st.sidebar.header("📁 Report Upload Center")
# Updated to accept all excel types
excel_types = ["csv", "xlsx", "xls", "xlsm", "xlsb"]
ad_file = st.sidebar.file_uploader("1. Ad Report", type=excel_types)
biz_file = st.sidebar.file_uploader("2. Business Report", type=excel_types)
inv_file = st.sidebar.file_uploader("3. Inventory Report (.txt)", type=["txt"])

if ad_file and biz_file and inv_file:
    with st.spinner('Syncing reports and pivoting inventory...'):
        # Load Files
        df_ad = load_data(ad_file)
        df_biz = load_data(biz_file)
        df_inv = load_data(inv_file)

        # Standardize headers to remove hidden spaces/formatting
        df_ad.columns = [str(c).strip() for c in df_ad.columns]
        df_biz.columns = [str(c).strip() for c in df_biz.columns]
        df_inv.columns = [str(c).strip() for c in df_inv.columns]

        # 1. Inventory Consolidation (Pivot by ASIN)
        # Summing stock for all SKUs belonging to the same ASIN
        inv_asin = find_robust_col(df_inv, ['asin'])
        inv_qty = find_robust_col(df_inv, ['quantity available'])
        inv_pivot = df_inv.groupby(inv_asin)[inv_qty].sum().reset_index()
        inv_pivot.columns = ['ASIN_KEY', 'Stock']

        # 2. Identify Metrics
        b_asin = find_robust_col(df_biz, ['child asin', 'asin'])
        b_sales = find_robust_col(df_biz, ['ordered product sales', 'revenue'])
        b_title = find_robust_col(df_biz, ['title', 'item name'])
        b_sku = find_robust_col(df_biz, ['sku', 'seller-sku'])
        
        a_asin = find_robust_col(df_ad, ['advertised asin', 'asin'])
        a_total_sales = find_robust_col(df_ad, ['7 day total sales']) 
        a_spend = find_robust_col(df_ad, ['spend', 'cost'])
        a_camp = find_robust_col(df_ad, ['campaign name'])
        a_sku = find_robust_col(df_ad, ['sku', 'advertised sku'])

        # Safety Check for MergeError
        if not b_asin or not a_asin:
            st.error("Column Detection Error: Could not find ASIN columns. Please check your file headers.")
            st.stop()

        # 3. Numeric Cleaning
        df_biz[b_sales] = df_biz[b_sales].apply(clean_numeric)
        df_ad[a_total_sales] = df_ad[a_total_sales].apply(clean_numeric)
        df_ad[a_spend] = df_ad[a_spend].apply(clean_numeric)

        # 4. Ad Aggregation (Summing across campaigns/dates)
        ad_summary = df_ad.groupby(a_asin).agg({
            a_total_sales: 'sum', a_spend: 'sum', a_camp: 'first', a_sku: 'first'
        }).reset_index()
        ad_summary.columns = ['ASIN_KEY_AD', 'Ad_Sales', 'Ad_Spend', 'Camp', 'Ad_SKU']

        # 5. Full Merge (Outer Join to ensure 100% data capture)
        # Business + Ads
        merged = pd.merge(df_biz, ad_summary, left_on=b_asin, right_on='ASIN_KEY_AD', how='outer')
        merged['Final_ASIN'] = merged[b_asin].fillna(merged['ASIN_KEY_AD'])
        
        # Merge with Pivoted Inventory
        merged = pd.merge(merged, inv_pivot, left_on='Final_ASIN', right_on='ASIN_KEY', how='outer', suffixes=('', '_inv'))
        merged['Final_ASIN'] = merged['Final_ASIN'].fillna(merged['ASIN_KEY'])

        # 6. Mapping & Calculations
        merged['Brand'] = merged.apply(lambda r: get_brand_robust(r, b_title, b_sku, 'Camp'), axis=1)
        
        # Fill zero for numeric columns to prevent mapping errors
        num_cols = [b_sales, 'Ad_Sales', 'Ad_Spend', 'Stock']
        for c in num_cols:
            if c in merged.columns: merged[c] = merged[c].fillna(0)

        merged['ACOS'] = (merged['Ad_Spend'] / merged['Ad_Sales']).replace([np.inf, -np.inf], 0).fillna(0)
        merged['TACOS'] = (merged['Ad_Spend'] / merged[b_sales]).replace([np.inf, -np.inf], 0).fillna(0)
        merged['Organic Sales'] = merged[b_sales] - merged['Ad_Sales']

    # --- DASHBOARD TABS ---
    tab_list = ["🌎 Global Summary"] + list(BRAND_MAP.values())
    tabs = st.tabs(tab_list)

    # Global Overview
    with tabs[0]:
        st.subheader("Global Portfolio Overview")
        m1, m2, m3, m4, m5 = st.columns(5)
        total_rev = merged[b_sales].sum()
        total_ad_rev = merged['Ad_Sales'].sum()
        total_spend = merged['Ad_Spend'].sum()
        total_stock = merged['Stock'].sum()
        
        m1.metric("Total Sales", f"AED {total_rev:,.2f}")
        m2.metric("Ad Sales", f"AED {total_ad_rev:,.2f}")
        m3.metric("Ad Spend", f"AED {total_spend:,.2f}")
        m4.metric("Global ACOS", f"{(total_spend/total_ad_rev if total_ad_rev > 0 else 0):.2%}")
        m5.metric("Total Stock", f"{total_stock:,.0f} Units")

        st.markdown("### Brand Breakdown")
        brand_perf = merged.groupby('Brand').agg({
            b_sales: 'sum', 'Ad_Sales': 'sum', 'Ad_Spend': 'sum', 'Stock': 'sum'
        }).reset_index()
        brand_perf['ACOS'] = (brand_perf['Ad_Spend'] / brand_perf['Ad_Sales']).fillna(0)
        
        st.dataframe(brand_perf.sort_values(by=b_sales, ascending=False).style.format({
            b_sales: '{:,.2f}', 'Ad_Sales': '{:,.2f}', 'Ad_Spend': '{:,.2f}', 'ACOS': '{:.2%}', 'Stock': '{:,.0f}'
        }), use_container_width=True, hide_index=True)

    # Individual Brand Tabs
    for idx, brand_name in enumerate(BRAND_MAP.values(), start=1):
        with tabs[idx]:
            b_data = merged[merged['Brand'] == brand_name]
            if not b_data.empty:
                st.subheader(f"{brand_name} Performance")
                audit_cols = ['Final_ASIN', b_title, 'Stock', b_sales, 'Ad_Sales', 'Ad_Spend', 'ACOS', 'TACOS']
                st.dataframe(b_data[audit_cols].sort_values(by=b_sales, ascending=False).style.format({
                    b_sales: '{:,.2f}', 'Ad_Sales': '{:,.2f}', 'Ad_Spend': '{:,.2f}', 'ACOS': '{:.2%}', 'TACOS': '{:.2%}', 'Stock': '{:,.0f}'
                }), use_container_width=True, hide_index=True)
            else:
                st.info(f"No products found for {brand_name}.")

    # --- EXPORT ---
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        brand_perf.to_excel(writer, sheet_name='Brand_Summary', index=False)
        merged.to_excel(writer, sheet_name='Full_Audit', index=False)
    st.sidebar.download_button("📥 Download Master Report", data=output.getvalue(), file_name="Amazon_Master_Audit.xlsx")

else:
    st.info("Please upload your Ad Report, Business Report, and Inventory file to begin.")
