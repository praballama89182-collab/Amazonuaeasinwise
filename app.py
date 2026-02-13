import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO

# 1. Page Configuration
st.set_page_config(page_title="AMAZON MASTER AUDIT", page_icon="🎯", layout="wide")

# 2. Maison Fragrance Name Reference
MAISON_REF = {
    'B0DGLJHCJJ': 'Oud Opulence', 'B0DGLJKQHN': 'Nova Noir', 'B0DGLLBR1R': 'Majestic Millennium',
    'B0DG919KGY': 'Jardin De Jade', 'B0DGLJJZX8': 'Opulent Odyssey', 'B0DGLHZCNX': 'Aurora Opulence',
    'B0DGLHTX18': 'Oud Intense', 'B0DGLHTYB2': 'Midnight Solstice', 'B0DGLM8XYD': 'Vortex Echo',
    'B0DGLJYGKW': 'Avenir Triumph', 'B0DZX2RL6P': 'Noir Intense', 'B0DGLKQJBY': 'Nebula Nectar',
    'B0DGLHHJFZ': 'Electra Elixir', 'B0DGLM918B': 'Ethereal Embrace', 'B0DGLLSH43': 'Eternal Oud'
}

BRAND_MAP = {
    'MA': 'Maison de l’Avenir', 'CL': 'Creation Lamis', 'JPD': 'Jean Paul Dupont', 
    'PC': 'Paris Collection', 'DC': 'Dorall Collection', 'CPT': 'CP Trendies'
}

def clean_numeric(val):
    if isinstance(val, str):
        cleaned = val.replace('AED', '').replace('$', '').replace('\xa0', '').replace(',', '').strip()
        try: return pd.to_numeric(cleaned)
        except: return 0.0
    return val if isinstance(val, (int, float)) else 0.0

def get_brand_robust(row, title_col=None, sku_col=None, camp_col=None):
    """Backtrack mapping using every identified SKU pattern and keyword."""
    targets = {
        'Maison de l’Avenir': ['MAISON', 'MA_', 'JPP', 'CEB', 'PGN', 'VGA'],
        'Creation Lamis': ['LAMIS', 'CL_', 'CL |', 'CLP', 'CPL', '3DM', 'CLAM'],
        'Jean Paul Dupont': ['DUPONT', 'JPD'],
        'Paris Collection': ['PARIS COLLECTION', 'PC_', 'PC |', 'PCB', 'PCH', 'PCBC', 'PCF', 'PCK', 'PCL'],
        'Dorall Collection': ['DORALL', 'DC_', 'DC |', 'DCL'],
        'CP Trendies': ['TRENDIES', 'CPT', 'CP_', 'CPMK', 'CPM', 'CPN', 'TGJ', 'COCP']
    }
    text = ""
    if title_col and title_col in row: text += " " + str(row[title_col]).upper()
    if sku_col and sku_col in row: text += " " + str(row[sku_col]).upper()
    if camp_col and camp_col in row and pd.notna(row[camp_col]): text += " " + str(row[camp_col]).upper()
    
    for brand_name, keywords in targets.items():
        if any(kw in text for kw in keywords): return brand_name
    return "Unmapped"

def find_col(df, keywords, exclude=None):
    for col in df.columns:
        c_low = str(col).strip().lower()
        if any(kw.lower() in c_low for kw in keywords):
            if exclude and any(ex.lower() in c_low for ex in exclude): continue
            return col
    return None

st.title("🚀 Amazon Master Brand & Inventory Audit")

# Sidebar Uploads
st.sidebar.header("📁 Report Upload Center")
file_types = ["csv", "xlsx", "xls", "xlsm", "xlsb"]
ad_f = st.sidebar.file_uploader("1. Ad Report", type=file_types)
biz_f = st.sidebar.file_uploader("2. Business Report", type=file_types)
inv_f = st.sidebar.file_uploader("3. Inventory Report (.txt)", type=["txt"])

if ad_f and biz_f and inv_f:
    with st.spinner('Performing deep SKU mapping...'):
        df_ad = pd.read_csv(ad_f) if ad_f.name.endswith('.csv') else pd.read_excel(ad_f)
        df_biz = pd.read_csv(biz_f) if biz_f.name.endswith('.csv') else pd.read_excel(biz_f)
        df_inv = pd.read_csv(inv_f, sep='\t')

        for df in [df_ad, df_biz, df_inv]: df.columns = [str(c).strip() for c in df.columns]

        # 1. Inventory: Pivot Sellable Stock & Map Brands
        i_asin, i_qty, i_cond, i_sku = find_col(df_inv, ['asin']), find_col(df_inv, ['quantity available']), find_col(df_inv, ['warehouse-condition-code']), find_col(df_inv, ['seller-sku'])
        df_inv_sell = df_inv[df_inv[i_cond].astype(str).str.strip().str.upper() == 'SELLABLE'].copy()
        df_inv_sell['Mapped_Brand'] = df_inv_sell.apply(lambda r: get_brand_robust(r, sku_col=i_sku), axis=1)
        
        inv_pivot = df_inv_sell.groupby([i_asin, 'Mapped_Brand'])[i_qty].sum().reset_index()
        inv_pivot.columns = ['Final_ASIN', 'Brand', 'Stock']

        # 2. Sales & Ad Metrics
        b_asin, b_sales, b_title = find_col(df_biz, ['child asin', 'asin']), find_col(df_biz, ['ordered product sales']), find_col(df_biz, ['title', 'item name'])
        a_asin, a_sales, a_spend, a_camp = find_col(df_ad, ['advertised asin']), find_col(df_ad, ['7 day total sales']), find_col(df_ad, ['spend']), find_col(df_ad, ['campaign name'])

        df_biz[b_sales] = df_biz[b_sales].apply(clean_numeric)
        df_ad[a_sales], df_ad[a_spend] = df_ad[a_sales].apply(clean_numeric), df_ad[a_spend].apply(clean_numeric)

        # 3. Final Merge (Outer Join to capture all Stock)
        ad_agg = df_ad.groupby(a_asin).agg({a_sales: 'sum', a_spend: 'sum', a_camp: 'first'}).reset_index()
        
        master = pd.merge(inv_pivot, df_biz[[b_asin, b_title, b_sales]], left_on='Final_ASIN', right_on=b_asin, how='outer')
        master['Final_ASIN'] = master['Final_ASIN'].fillna(master[b_asin])
        master = pd.merge(master, ad_agg, left_on='Final_ASIN', right_on=a_asin, how='outer', suffixes=('', '_ad')).fillna(0)

        # 4. Final Name & Brand Resolution
        master['Item Name'] = master.apply(lambda r: MAISON_REF.get(r['Final_ASIN'], r[b_title] if pd.notna(r[b_title]) and r[b_title] != 0 else "N/A"), axis=1)
        master['Brand'] = master.apply(lambda r: r['Brand'] if r['Brand'] != 0 and r['Brand'] != "Unmapped" else get_brand_robust(r, b_title, None, a_camp), axis=1)
        
        master['ACOS'] = (master[a_spend] / master[a_sales]).replace([np.inf, -np.inf], 0).fillna(0)
        master['TACOS'] = (master[a_spend] / master[b_sales]).replace([np.inf, -np.inf], 0).fillna(0)

    # --- UI LAYOUT ---
    st.subheader("🌎 Global Portfolio Overview")
    ov1, ov2, ov3, ov4 = st.columns(4)
    t_rev, t_ad, t_sp, t_stock = master[b_sales].sum(), master[a_sales].sum(), master[a_spend].sum(), master['Stock'].sum()
    ov1.metric("Total Business Sales", f"AED {t_rev:,.2f}")
    ov2.metric("Total Ad Sales", f"AED {t_ad:,.2f}")
    ov3.metric("Total Ad Spend", f"AED {t_sp:,.2f}")
    ov4.metric("Sellable Stock", f"{t_stock:,.0f} Units")

    tabs = st.tabs(["📊 Brand Summary"] + list(BRAND_MAP.values()))

    with tabs[0]:
        summary = master.groupby('Brand').agg({b_sales: 'sum', a_sales: 'sum', a_spend: 'sum', 'Stock': 'sum'}).reset_index()
        st.dataframe(summary.sort_values(by=b_sales, ascending=False).style.format({b_sales: '{:,.2f}', a_sales: '{:,.2f}', a_spend: '{:,.2f}', 'Stock': '{:,.0f}'}), use_container_width=True, hide_index=True)

    for idx, brand_name in enumerate(BRAND_MAP.values(), start=1):
        with tabs[idx]:
            b_data = master[master['Brand'] == brand_name]
            st.dataframe(b_data[['Final_ASIN', 'Item Name', 'Stock', b_sales, a_sales, a_spend, 'ACOS', 'TACOS']].sort_values(by=b_sales, ascending=False).style.format({b_sales: '{:,.2f}', a_sales: '{:,.2f}', a_spend: '{:,.2f}', 'ACOS': '{:.1%}', 'TACOS': '{:.1%}', 'Stock': '{:,.0f}'}), use_container_width=True, hide_index=True)

    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        master.to_excel(writer, sheet_name='Audit', index=False)
    st.sidebar.download_button("📥 Download Master Audit", data=output.getvalue(), file_name="Amazon_Performance_Master.xlsx")
