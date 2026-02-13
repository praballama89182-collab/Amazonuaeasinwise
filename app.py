import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO

st.set_page_config(page_title="AMAZON MASTER AUDIT", page_icon="🎯", layout="wide")

# 1. Configuration
BRAND_MAP = {
    'MA': 'Maison de l’Avenir',
    'CL': 'Creation Lamis',
    'JPD': 'Jean Paul Dupont',
    'PC': 'Paris Collection',
    'DC': 'Dorall Collection',
    'CPT': 'CP Trendies'
}

def clean_numeric(val):
    """Robust cleaning for currency, commas, and trailing spaces."""
    if isinstance(val, str):
        cleaned = val.replace('AED', '').replace('$', '').replace('\xa0', '').replace(',', '').strip()
        try: return pd.to_numeric(cleaned)
        except: return 0.0
    return val if isinstance(val, (int, float)) else 0.0

def get_brand_robust(row, title_col=None, sku_col=None, camp_col=None):
    """Reinforced mapping logic using SKU prefixes and Title keywords."""
    targets = {
        'Maison de l’Avenir': ['MAISON', 'MA_', 'JPP', 'CEB', 'PGN', 'VGA'],
        'Creation Lamis': ['LAMIS', 'CL_', 'CL |', 'CLP', 'CPL', '3DM'],
        'Jean Paul Dupont': ['DUPONT', 'JPD'],
        'Paris Collection': ['PARIS COLLECTION', 'PC_', 'PC |', 'PCB', 'PCH', 'PCBC'],
        'Dorall Collection': ['DORALL', 'DC_', 'DC |', 'DCL'],
        'CP Trendies': ['TRENDIES', 'CPT', 'CP_', 'CPMK', 'CPM', 'CPN', 'TGJ']
    }
    
    text = ""
    if title_col and title_col in row: text += " " + str(row[title_col]).upper()
    if sku_col and sku_col in row: text += " " + str(row[sku_col]).upper()
    if camp_col and camp_col in row and pd.notna(row[camp_col]): text += " " + str(row[camp_col]).upper()
    
    for brand_name, keywords in targets.items():
        if any(kw in text for kw in keywords):
            return brand_name
    return "Unmapped"

def find_robust_col(df, keywords, exclude=None):
    """Fuzzy column search."""
    for col in df.columns:
        c_clean = str(col).strip().lower()
        if any(kw.lower() in c_clean for kw in keywords):
            if exclude and any(ex.lower() in c_clean for ex in exclude): continue
            return col
    return None

def load_data(file):
    name = file.name.lower()
    if name.endswith('.csv'): return pd.read_csv(file)
    elif name.endswith('.txt'): return pd.read_csv(file, sep='\t')
    elif name.endswith(('.xlsx', '.xls', '.xlsm', '.xlsb')): return pd.read_excel(file)
    return None

# --- UI Setup ---
st.title("🎯 Final Amazon Master Audit")
st.info("Verified Maison Mapping (JPP, CEB, PGN, VGA) | Sellable Stock Only | Purchase % Removed")

st.sidebar.header("📁 Report Upload Center")
excel_types = ["csv", "xlsx", "xls", "xlsm", "xlsb"]
ad_file = st.sidebar.file_uploader("1. Ad Report", type=excel_types)
biz_file = st.sidebar.file_uploader("2. Business Report", type=excel_types)
inv_file = st.sidebar.file_uploader("3. Inventory Report (.txt)", type=["txt"])

if ad_file and biz_file and inv_file:
    with st.spinner('Syncing reports and calculating metrics...'):
        df_ad = load_data(ad_file)
        df_biz = load_data(biz_file)
        df_inv = load_data(inv_file)

        for df in [df_ad, df_biz, df_inv]: df.columns = [str(c).strip() for c in df.columns]

        # 1. Map Brands to Inventory FIRST
        i_asin = find_robust_col(df_inv, ['asin'])
        i_qty = find_robust_col(df_inv, ['quantity available'])
        i_cond = find_robust_col(df_inv, ['warehouse-condition-code'])
        i_sku = find_robust_col(df_inv, ['seller-sku'])
        
        df_inv['Brand'] = df_inv.apply(lambda r: get_brand_robust(r, sku_col=i_sku), axis=1)
        
        # 2. Pivot Inventory by Brand & ASIN (Sellable Only)
        df_inv_sell = df_inv[df_inv[i_cond].astype(str).str.strip().str.upper() == 'SELLABLE']
        inv_summary = df_inv_sell.groupby([i_asin, 'Brand'])[i_qty].sum().reset_index()
        inv_summary.columns = ['Final_ASIN', 'Brand', 'Stock']

        # 3. Identify Sales Metrics
        b_asin = find_robust_col(df_biz, ['child asin', 'asin'])
        b_sales = find_robust_col(df_biz, ['ordered product sales', 'revenue'])
        b_title = find_robust_col(df_biz, ['title', 'item name'])
        b_sku = find_robust_col(df_biz, ['sku', 'seller-sku'])
        df_biz[b_sales] = df_biz[b_sales].apply(clean_numeric)

        a_asin = find_robust_col(df_ad, ['advertised asin', 'asin'])
        a_sales = find_robust_col(df_ad, ['7 day total sales']) 
        a_spend = find_robust_col(df_ad, ['spend', 'cost'])
        a_camp = find_robust_col(df_ad, ['campaign name'])
        df_ad[a_sales] = df_ad[a_sales].apply(clean_numeric)
        df_ad[a_spend] = df_ad[a_spend].apply(clean_numeric)

        # 4. Aggregate & Final Merge
        ad_summary = df_ad.groupby(a_asin).agg({a_sales: 'sum', a_spend: 'sum', a_camp: 'first'}).reset_index()
        ad_summary.columns = ['ASIN', 'Ad_Sales', 'Ad_Spend', 'Camp']

        # Start with Inventory to ensure all stock is captured even if no sales exist
        master = pd.merge(inv_summary, df_biz, left_on='Final_ASIN', right_on=b_asin, how='outer', suffixes=('', '_biz'))
        master['Final_ASIN'] = master['Final_ASIN'].fillna(master[b_asin])
        
        # Merge Ad Data
        master = pd.merge(master, ad_summary, left_on='Final_ASIN', right_on='ASIN', how='outer')
        master['Final_ASIN'] = master['Final_ASIN'].fillna(master['ASIN'])

        # Final Brand Mapping Cleanup
        master['Brand'] = master.apply(lambda r: get_brand_robust(r, b_title, b_sku, 'Camp') if pd.isna(r['Brand']) or r['Brand']=='Unmapped' else r['Brand'], axis=1)

        # Calculations
        master['ACOS'] = (master['Ad_Spend'] / master['Ad_Sales']).replace([np.inf, -np.inf], 0).fillna(0)
        master['TACOS'] = (master['Ad_Spend'] / master[b_sales]).replace([np.inf, -np.inf], 0).fillna(0)
        
        num_cols = [b_sales, 'Ad_Sales', 'Ad_Spend', 'Stock']
        for c in num_cols:
            if c in master.columns: master[c] = master[c].fillna(0)

    # --- DASHBOARD ---
    tabs = st.tabs(["🌎 Global Summary"] + list(BRAND_MAP.values()))

    with tabs[0]:
        st.subheader("Global Stock & Sales Overview")
        m1, m2, m3, m4, m5 = st.columns(5)
        total_rev = master[b_sales].sum()
        total_ad = master['Ad_Sales'].sum()
        total_sp = master['Ad_Spend'].sum()
        
        m1.metric("Total Sales", f"AED {total_rev:,.2f}")
        m2.metric("Ad Sales", f"AED {total_ad:,.2f}")
        m3.metric("Ad Spend", f"AED {total_sp:,.2f}")
        m4.metric("Global ACOS", f"{(total_sp/total_ad if total_ad > 0 else 0):.2%}")
        m5.metric("Sellable Stock", f"{master['Stock'].sum():,.0f}")

        st.markdown("### Brand-Wise Breakdown")
        brand_perf = master.groupby('Brand').agg({b_sales: 'sum', 'Ad_Sales': 'sum', 'Ad_Spend': 'sum', 'Stock': 'sum'}).reset_index()
        brand_perf['ACOS'] = (brand_perf['Ad_Spend'] / brand_perf['Ad_Sales']).fillna(0)
        brand_perf['TACOS'] = (brand_perf['Ad_Spend'] / brand_perf[b_sales]).fillna(0)
        
        st.dataframe(brand_perf.sort_values(by=b_sales, ascending=False).style.format({
            b_sales: '{:,.2f}', 'Ad_Sales': '{:,.2f}', 'Ad_Spend': '{:,.2f}', 'Stock': '{:,.0f}', 'ACOS': '{:.2%}', 'TACOS': '{:.2%}'
        }), use_container_width=True, hide_index=True)

    for idx, brand_name in enumerate(BRAND_MAP.values(), start=1):
        with tabs[idx]:
            b_data = master[master['Brand'] == brand_name]
            st.subheader(f"{brand_name} Performance")
            audit_cols = ['Final_ASIN', b_title, 'Stock', b_sales, 'Ad_Sales', 'Ad_Spend', 'ACOS', 'TACOS']
            st.dataframe(b_data[audit_cols].sort_values(by=b_sales, ascending=False).style.format({
                b_sales: '{:,.2f}', 'Ad_Sales': '{:,.2f}', 'Ad_Spend': '{:,.2f}', 'ACOS': '{:.2%}', 'TACOS': '{:.2%}', 'Stock': '{:,.0f}'
            }), use_container_width=True, hide_index=True)

    # Export
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        master.to_excel(writer, sheet_name='Audit', index=False)
    st.sidebar.download_button("📥 Download Final Report", data=output.getvalue(), file_name="Amazon_Master_Audit.xlsx")

else:
    st.info("Please upload your Ad, Business, and Inventory reports to generate the dashboard.")
