import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO

st.set_page_config(page_title="AMAZON MASTER AUDIT", page_icon="🎯", layout="wide")

# 1. Configuration & Mapping
BRAND_MAP = {
    'MA': 'Maison de l’Avenir',
    'CL': 'Creation Lamis',
    'JPD': 'Jean Paul Dupont',
    'PC': 'Paris Collection',
    'DC': 'Dorall Collection',
    'CPT': 'CP Trendies'
}

def clean_numeric(val):
    """Deep clean of currency, commas, and hidden spaces."""
    if isinstance(val, str):
        cleaned = val.replace('AED', '').replace('$', '').replace('\xa0', '').replace(',', '').strip()
        try: return pd.to_numeric(cleaned)
        except: return 0.0
    return val if isinstance(val, (int, float)) else 0.0

def get_brand_robust(row, title_col=None, sku_col=None, camp_col=None):
    targets = {
        'MAISON': 'Maison de l’Avenir', 'MA_': 'Maison de l’Avenir',
        'LAMIS': 'Creation Lamis', 'CL ': 'Creation Lamis', 'CL_': 'Creation Lamis',
        'DUPONT': 'Jean Paul Dupont', 'JPD ': 'Jean Paul Dupont', 'JPD_': 'Jean Paul Dupont',
        'PARIS COLLECTION': 'Paris Collection', 'PC ': 'Paris Collection', 'PC_': 'Paris Collection',
        'DORALL': 'Dorall Collection', 'DC ': 'Dorall Collection', 'DC_': 'Dorall Collection',
        'TRENDIES': 'CP Trendies', 'CPT': 'CP Trendies', 'CP_': 'CP Trendies', 'CPMK': 'CP Trendies'
    }
    text = ""
    if title_col and title_col in row: text += " " + str(row[title_col]).upper()
    if sku_col and sku_col in row: text += " " + str(row[sku_col]).upper()
    if camp_col and camp_col in row and pd.notna(row[camp_col]): text += " " + str(row[camp_col]).upper()
    for kw, brand in targets.items():
        if kw in text: return brand
    return "Unmapped"

def find_col(df, keywords, exclude=None):
    """Fuzzy column search to handle (Child) ASIN and trailing spaces."""
    for col in df.columns:
        c_low = str(col).strip().lower()
        if any(kw.lower() in c_low for kw in keywords):
            if exclude and any(ex.lower() in c_low for ex in exclude):
                continue
            return col
    return None

st.title("🎯 Final Amazon Master Audit")

# Sidebar
st.sidebar.header("📁 Upload Reports")
ad_f = st.sidebar.file_uploader("1. Ad Report (CSV)", type=["csv"])
biz_f = st.sidebar.file_uploader("2. Business Report (CSV)", type=["csv"])
inv_f = st.sidebar.file_uploader("3. Inventory Report (.txt)", type=["txt"])

if ad_f and biz_f and inv_f:
    with st.spinner('Processing...'):
        # Load
        df_ad = pd.read_csv(ad_f)
        df_biz = pd.read_csv(biz_f)
        df_inv = pd.read_csv(inv_f, sep='\t')

        # 1. Inventory: Aggregating Repeated ASINs (Pivot)
        i_asin = find_col(df_inv, ['asin'])
        i_qty = find_col(df_inv, ['quantity available'])
        inv_pivot = df_inv.groupby(i_asin)[i_qty].sum().reset_index()
        inv_pivot.columns = ['ASIN_KEY', 'Stock']

        # 2. Identify Metrics
        b_asin = find_col(df_biz, ['child asin', 'asin'])
        b_sales = find_col(df_biz, ['ordered product sales', 'revenue'])
        b_title = find_col(df_biz, ['title', 'item name'])
        
        a_asin = find_col(df_ad, ['advertised asin'])
        a_sales = find_col(df_ad, ['7 day total sales']) # Captures the 3,324.65 total
        a_spend = find_col(df_ad, ['spend'])
        a_camp = find_col(df_ad, ['campaign name'])

        # 3. Clean
        df_biz[b_sales] = df_biz[b_sales].apply(clean_numeric)
        df_ad[a_sales] = df_ad[a_sales].apply(clean_numeric)
        df_ad[a_spend] = df_ad[a_spend].apply(clean_numeric)

        # 4. Merge (Using Outer Join to ensure no Stock is lost)
        ad_agg = df_ad.groupby(a_asin).agg({a_sales: 'sum', a_spend: 'sum', a_camp: 'first'}).reset_index()
        
        merged = pd.merge(df_biz, ad_agg, left_on=b_asin, right_on=a_asin, how='outer')
        merged['Final_ASIN'] = merged[b_asin].fillna(merged[a_asin])
        merged = pd.merge(merged, inv_pivot, left_on='Final_ASIN', right_on='ASIN_KEY', how='left').fillna(0)

        # 5. Mapping
        merged['Brand'] = merged.apply(lambda r: get_brand_robust(r, b_title, None, a_camp), axis=1)
        merged['ACOS'] = (merged[a_spend] / merged[a_sales]).replace([np.inf, -np.inf], 0).fillna(0)
        merged['TACOS'] = (merged[a_spend] / merged[b_sales]).replace([np.inf, -np.inf], 0).fillna(0)

    # --- UI ---
    tabs = st.tabs(["🌎 Global Portfolio"] + list(BRAND_MAP.values()))

    with tabs[0]:
        st.subheader("Account Summary")
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Total Sales", f"{merged[b_sales].sum():,.2f}")
        m2.metric("Ad Sales", f"{merged[a_sales].sum():,.2f}")
        m3.metric("Ad Spend", f"{merged[a_spend].sum():,.2f}")
        m4.metric("ACOS", f"{(merged[a_spend].sum()/merged[a_sales].sum() if merged[a_sales].sum() > 0 else 0):.2%}")
        m5.metric("Total Stock", f"{merged['Stock'].sum():,.0f}")
        
        brand_summary = merged.groupby('Brand').agg({b_sales: 'sum', a_sales: 'sum', a_spend: 'sum', 'Stock': 'sum'}).reset_index()
        st.dataframe(brand_summary.sort_values(by=b_sales, ascending=False), use_container_width=True, hide_index=True)

    for idx, brand_name in enumerate(BRAND_MAP.values(), start=1):
        with tabs[idx]:
            b_data = merged[merged['Brand'] == brand_name]
            st.dataframe(b_data[['Final_ASIN', b_title, 'Stock', b_sales, a_sales, a_spend, 'ACOS', 'TACOS']], use_container_width=True, hide_index=True)

    # Export
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        merged.to_excel(writer, sheet_name='Audit', index=False)
    st.sidebar.download_button("📥 Download Audit", data=output.getvalue(), file_name="Amazon_Audit.xlsx")

else:
    st.info("Upload your reports to see the verified data.")
