import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO

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
    """Deep scan for brand identifiers. Includes specific Maison SKU patterns."""
    targets = {
        # Maison patterns: MAISON, MA_, and SKU starts JPP, CEB, PGN, VGA
        'Maison de l’Avenir': ['MAISON', 'MA_', 'JPP', 'CEB', 'PGN', 'VGA'],
        'Creation Lamis': ['LAMIS', 'CL_', 'CLP', 'CPL'],
        'Jean Paul Dupont': ['DUPONT', 'JPD'],
        'Paris Collection': ['PARIS COLLECTION', 'PC_', 'PCB', 'PCH'],
        'Dorall Collection': ['DORALL', 'DC_', 'DCL'],
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

st.title("🎯 Final Amazon master Audit")

st.sidebar.header("📁 Report Upload Center")
excel_types = ["csv", "xlsx", "xls", "xlsm", "xlsb"]
ad_file = st.sidebar.file_uploader("1. Ad Report", type=excel_types)
biz_file = st.sidebar.file_uploader("2. Business Report", type=excel_types)
inv_file = st.sidebar.file_uploader("3. Inventory Report (.txt)", type=["txt"])

if ad_file and biz_file and inv_file:
    with st.spinner('Pivoting inventory and mapping brands...'):
        df_ad = load_data(ad_file)
        df_biz = load_data(biz_file)
        df_inv = load_data(inv_file)

        # Standardize headers
        for df in [df_ad, df_biz, df_inv]: df.columns = [str(c).strip() for c in df.columns]

        # 1. Pivot Inventory by ASIN
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

        # 3. Clean Data
        df_biz[b_sales] = df_biz[b_sales].apply(clean_numeric)
        df_ad[a_total_sales] = df_ad[a_total_sales].apply(clean_numeric)
        df_ad[a_spend] = df_ad[a_spend].apply(clean_numeric)

        # 4. Aggregate Ad & Merging (Outer Join for 100% Stock Capture)
        ad_summary = df_ad.groupby(a_asin).agg({a_total_sales: 'sum', a_spend: 'sum', a_camp: 'first', a_sku: 'first'}).reset_index()
        ad_summary.columns = ['ASIN_KEY_AD', 'Ad_Sales', 'Ad_Spend', 'Camp', 'Ad_SKU']

        merged = pd.merge(df_biz, ad_summary, left_on=b_asin, right_on='ASIN_KEY_AD', how='outer')
        merged['Final_ASIN'] = merged[b_asin].fillna(merged['ASIN_KEY_AD'])
        merged = pd.merge(merged, inv_pivot, left_on='Final_ASIN', right_on='ASIN_KEY', how='outer').fillna(0)
        merged['Final_ASIN'] = merged['Final_ASIN'].fillna(merged['ASIN_KEY'])

        # 5. Mapping & Calculations
        merged['Brand'] = merged.apply(lambda r: get_brand_robust(r, b_title, b_sku, 'Camp'), axis=1)
        merged['ACOS'] = (merged['Ad_Spend'] / merged['Ad_Sales']).replace([np.inf, -np.inf], 0).fillna(0)
        merged['TACOS'] = (merged['Ad_Spend'] / merged[b_sales]).replace([np.inf, -np.inf], 0).fillna(0)
        merged['Organic Sales'] = merged[b_sales] - merged['Ad_Sales']

    # --- TABS ---
    tabs = st.tabs(["🌎 Global Portfolio"] + list(BRAND_MAP.values()))

    with tabs[0]:
        st.subheader("Global Stock & Sales Overview")
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Total Sales", f"AED {merged[b_sales].sum():,.2f}")
        m2.metric("Ad Sales", f"AED {merged['Ad_Sales'].sum():,.2f}")
        m3.metric("Global ACOS", f"{(merged['Ad_Spend'].sum()/merged['Ad_Sales'].sum() if merged['Ad_Sales'].sum() > 0 else 0):.2%}")
        m4.metric("Global TACOS", f"{(merged['Ad_Spend'].sum()/merged[b_sales].sum() if merged[b_sales].sum() > 0 else 0):.2%}")
        m5.metric("Sellable Stock", f"{merged['Stock'].sum():,.0f}")

        st.markdown("### Final Brand-Wise Stock Overview")
        brand_summary = merged.groupby('Brand').agg({b_sales: 'sum', 'Ad_Sales': 'sum', 'Ad_Spend': 'sum', 'Stock': 'sum'}).reset_index()
        st.dataframe(brand_summary.sort_values(by=b_sales, ascending=False).style.format({
            b_sales: '{:,.2f}', 'Ad_Sales': '{:,.2f}', 'Ad_Spend': '{:,.2f}', 'Stock': '{:,.0f}'
        }), use_container_width=True, hide_index=True)

    for idx, brand_name in enumerate(BRAND_MAP.values(), start=1):
        with tabs[idx]:
            b_data = merged[merged['Brand'] == brand_name]
            st.subheader(f"{brand_name} Stock & Performance")
            audit_cols = ['Final_ASIN', b_title, 'Stock', b_sales, 'Ad_Sales', 'Ad_Spend', 'ACOS', 'TACOS']
            st.dataframe(b_data[audit_cols].sort_values(by=b_sales, ascending=False), use_container_width=True, hide_index=True)

    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        brand_summary.to_excel(writer, sheet_name='Summary', index=False)
        merged.to_excel(writer, sheet_name='Audit', index=False)
    st.sidebar.download_button("📥 Download Master Report", data=output.getvalue(), file_name="Amazon_Master_Audit.xlsx")
else:
    st.info("Upload all three files to see the verified Maison inventory and global stock overview.")
