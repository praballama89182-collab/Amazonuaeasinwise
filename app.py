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
    for col in df.columns:
        c_low = str(col).strip().lower()
        if any(kw.lower() in c_low for kw in keywords):
            if exclude and any(ex.lower() in c_low for ex in exclude): continue
            return col
    return None

st.title("🎯 Final Amazon Master Audit")

# Sidebar
st.sidebar.header("📁 Upload Reports")
file_types = ["csv", "xlsx", "xls", "xlsm", "xlsb"]
ad_f = st.sidebar.file_uploader("1. Ad Report", type=file_types)
biz_f = st.sidebar.file_uploader("2. Business Report", type=file_types)
inv_f = st.sidebar.file_uploader("3. Inventory Report (.txt)", type=["txt"])

if ad_f and biz_f and inv_f:
    with st.spinner('Syncing data and filtering sellable stock...'):
        # Load
        df_ad = pd.read_csv(ad_f) if ad_f.name.endswith('.csv') else pd.read_excel(ad_f)
        df_biz = pd.read_csv(biz_f) if biz_f.name.endswith('.csv') else pd.read_excel(biz_f)
        df_inv = pd.read_csv(inv_f, sep='\t')

        # Clean Headers
        df_ad.columns = [str(c).strip() for c in df_ad.columns]
        df_biz.columns = [str(c).strip() for c in df_biz.columns]
        df_inv.columns = [str(c).strip() for c in df_inv.columns]

        # 1. Inventory: Aggregating SELLABLE ASINs only
        i_asin = find_col(df_inv, ['asin'])
        i_qty = find_col(df_inv, ['quantity available'])
        i_cond = find_col(df_inv, ['warehouse-condition-code'])
        
        # Filter for SELLABLE
        df_inv_sell = df_inv[df_inv[i_cond].astype(str).str.strip().str.upper() == 'SELLABLE']
        inv_pivot = df_inv_sell.groupby(i_asin)[i_qty].sum().reset_index()
        inv_pivot.columns = ['ASIN_KEY_INV', 'Stock']

        # 2. Metrics Detection
        b_asin = find_col(df_biz, ['child asin', 'asin'])
        b_sales = find_col(df_biz, ['ordered product sales', 'revenue'])
        b_title = find_col(df_biz, ['title', 'item name'])
        a_asin = find_col(df_ad, ['advertised asin'])
        a_sales = find_col(df_ad, ['7 day total sales']) 
        a_spend = find_col(df_ad, ['spend'])
        a_camp = find_col(df_ad, ['campaign name'])

        # 3. Clean
        df_biz[b_sales] = df_biz[b_sales].apply(clean_numeric)
        df_ad[a_sales] = df_ad[a_sales].apply(clean_numeric)
        df_ad[a_spend] = df_ad[a_spend].apply(clean_numeric)

        # 4. Three-Way Outer Merge (Ensure 100% Stock Capture)
        ad_agg = df_ad.groupby(a_asin).agg({a_sales: 'sum', a_spend: 'sum', a_camp: 'first'}).reset_index()
        
        # Merge Biz + Ads
        merged = pd.merge(df_biz, ad_agg, left_on=b_asin, right_on=a_asin, how='outer')
        merged['Master_ASIN'] = merged[b_asin].fillna(merged[a_asin])
        
        # Merge with Inventory
        merged = pd.merge(merged, inv_pivot, left_on='Master_ASIN', right_on='ASIN_KEY_INV', how='outer', suffixes=('', '_inv'))
        merged['Final_ASIN'] = merged['Master_ASIN'].fillna(merged['ASIN_KEY_INV'])

        # 5. Mapping & Calculations
        merged['Brand'] = merged.apply(lambda r: get_brand_robust(r, b_title, None, a_camp), axis=1)
        merged['ACOS'] = (merged[a_spend] / merged[a_sales]).replace([np.inf, -np.inf], 0).fillna(0)
        merged['TACOS'] = (merged[a_spend] / merged[b_sales]).replace([np.inf, -np.inf], 0).fillna(0)
        
        # Fill numeric NaNs
        for c in [b_sales, a_sales, a_spend, 'Stock']:
            merged[c] = merged[c].fillna(0)

    # --- TABS ---
    tabs = st.tabs(["🌎 Global Portfolio"] + list(BRAND_MAP.values()))

    with tabs[0]:
        st.subheader("Global Sellable Stock & Performance")
        m1, m2, m3, m4, m5 = st.columns(5)
        t_rev, t_ad, t_spend = merged[b_sales].sum(), merged[a_sales].sum(), merged[a_spend].sum()
        m1.metric("Total Sales", f"AED {t_rev:,.2f}")
        m2.metric("Ad Sales", f"AED {t_ad:,.2f}")
        m3.metric("Global ACOS", f"{(t_spend/t_ad if t_ad > 0 else 0):.2%}")
        m4.metric("Global TACOS", f"{(t_spend/t_rev if t_rev > 0 else 0):.2%}")
        m5.metric("Sellable Stock", f"{merged['Stock'].sum():,.0f} Units")
        
        brand_summary = merged.groupby('Brand').agg({b_sales: 'sum', a_sales: 'sum', a_spend: 'sum', 'Stock': 'sum'}).reset_index()
        st.dataframe(brand_summary.sort_values(by=b_sales, ascending=False).style.format({
            b_sales: '{:,.2f}', a_sales: '{:,.2f}', a_spend: '{:,.2f}', 'Stock': '{:,.0f}'
        }), use_container_width=True, hide_index=True)

    for idx, brand_name in enumerate(BRAND_MAP.values(), start=1):
        with tabs[idx]:
            b_data = merged[merged['Brand'] == brand_name]
            st.subheader(f"{brand_name} Metrics")
            k1, k2, k3, k4, k5 = st.columns(5)
            br_rev, br_ad, br_sp = b_data[b_sales].sum(), b_data[a_sales].sum(), b_data[a_spend].sum()
            k1.metric("Total Sales", f"AED {br_rev:,.2f}")
            k2.metric("Ad Sales", f"AED {br_ad:,.2f}")
            k3.metric("ACOS", f"{(br_sp/br_ad if br_ad > 0 else 0):.2%}")
            k4.metric("TACOS", f"{(br_sp/br_rev if br_rev > 0 else 0):.2%}")
            k5.metric("Sellable Stock", f"{b_data['Stock'].sum():,.0f}")
            
            st.dataframe(b_data[['Final_ASIN', b_title, 'Stock', b_sales, a_sales, a_spend, 'ACOS', 'TACOS']], use_container_width=True, hide_index=True)

    # Export
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        merged.to_excel(writer, sheet_name='Audit', index=False)
    st.sidebar.download_button("📥 Download Final Audit", data=output.getvalue(), file_name="Amazon_Performance_Master.xlsx")

else:
    st.info("Upload your reports to generate the dashboard with SELLABLE inventory only.")
