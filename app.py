import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO

st.set_page_config(page_title="AMAZON MASTER AUDIT", page_icon="🎯", layout="wide")

# 1. Maison Brand Reference (Ensures names are NEVER missing)
MAISON_REF = {
    'B0DGLHHJFZ': 'Electra Elixir', 'B0DGLHTX18': 'Oud Intense', 'B0DGLKQJBY': 'Nebula Nectar',
    'B0DGLLSH43': 'Eternal Oud', 'B0DGLM918B': 'Ethereal Embrace', 'B0DG919KGY': 'Jardin De Jade',
    'B0DGLHTYB2': 'Midnight Solstice', 'B0DGLHZCNX': 'Aurora Opulence', 'B0DGLJHCJJ': 'Oud Opulence',
    'B0DGLJJZX8': 'Opulent Odyssey', 'B0DGLJKQHN': 'Nova Noir', 'B0DGLJYGKW': 'Avenir Triumph',
    'B0DGLLBR1R': 'Majestic Millennium', 'B0DGLM8XYD': 'Vortex Echo', 'B0DZX2RL6P': 'Noir Intense'
}

BRAND_MAP = {
    'MA': 'Maison de l’Avenir', 'CL': 'Creation Lamis', 'JPD': 'Jean Paul Dupont', 
    'PC': 'Paris Collection', 'DC': 'Dorall Collection', 'CPT': 'CP Trendies'
}

def clean_numeric(val):
    """Deep clean currency and numeric strings."""
    if isinstance(val, str):
        cleaned = val.replace('AED', '').replace('$', '').replace('\xa0', '').replace(',', '').strip()
        try: return pd.to_numeric(cleaned)
        except: return 0.0
    return val if isinstance(val, (int, float)) else 0.0

def get_brand_robust(row, title_col=None, sku_col=None, camp_col=None):
    """Advanced mapping for Maison and others using SKU codes."""
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
        if any(kw in text for kw in keywords): return brand_name
    return "Unmapped"

def find_col(df, keywords, exclude=None):
    for col in df.columns:
        c_low = str(col).strip().lower()
        if any(kw.lower() in c_low for kw in keywords):
            if exclude and any(ex.lower() in c_low for ex in exclude): continue
            return col
    return None

st.title("🎯 Final Amazon Master Audit Dashboard")

# Sidebar Uploads
st.sidebar.header("📁 Report Upload Center")
file_types = ["csv", "xlsx", "xls", "xlsm", "xlsb"]
ad_f = st.sidebar.file_uploader("1. Ad Report", type=file_types)
biz_f = st.sidebar.file_uploader("2. Business Report", type=file_types)
inv_f = st.sidebar.file_uploader("3. Inventory Report (.txt)", type=["txt"])

if ad_f and biz_f and inv_f:
    with st.spinner('Calculating total spend and mapping stock...'):
        # Load Data
        df_ad = pd.read_csv(ad_f) if ad_f.name.endswith('.csv') else pd.read_excel(ad_f)
        df_biz = pd.read_csv(biz_f) if biz_f.name.endswith('.csv') else pd.read_excel(biz_f)
        df_inv = pd.read_csv(inv_f, sep='\t')

        for df in [df_ad, df_biz, df_inv]: df.columns = [str(c).strip() for c in df.columns]

        # 1. Inventory: Aggregating SELLABLE ASINs only
        i_asin, i_qty, i_cond, i_sku = find_col(df_inv, ['asin']), find_col(df_inv, ['quantity available']), find_col(df_inv, ['warehouse-condition-code']), find_col(df_inv, ['seller-sku'])
        df_inv_sell = df_inv[df_inv[i_cond].astype(str).str.strip().str.upper() == 'SELLABLE']
        inv_pivot = df_inv_sell.groupby(i_asin)[i_qty].sum().reset_index()
        inv_pivot.columns = ['ASIN_KEY_INV', 'Stock']

        # 2. Identify Metrics
        b_asin, b_sales, b_title = find_col(df_biz, ['child asin', 'asin']), find_col(df_biz, ['ordered product sales', 'revenue']), find_col(df_biz, ['title', 'item name'])
        a_asin, a_sales, a_spend, a_camp = find_col(df_ad, ['advertised asin']), find_col(df_ad, ['7 day total sales']), find_col(df_ad, ['spend']), find_col(df_ad, ['campaign name'])

        # 3. Clean
        df_biz[b_sales] = df_biz[b_sales].apply(clean_numeric)
        df_ad[a_sales], df_ad[a_spend] = df_ad[a_sales].apply(clean_numeric), df_ad[a_spend].apply(clean_numeric)

        # 4. Final Merge (Outer Join for 100% visibility)
        ad_agg = df_ad.groupby(a_asin).agg({a_sales: 'sum', a_spend: 'sum', a_camp: 'first'}).reset_index()
        merged = pd.merge(df_biz, ad_agg, left_on=b_asin, right_on=a_asin, how='outer')
        merged['Final_ASIN'] = merged[b_asin].fillna(merged[a_asin])
        merged = pd.merge(merged, inv_pivot, left_on='Final_ASIN', right_on='ASIN_KEY_INV', how='outer').fillna(0)
        merged['Final_ASIN'] = merged['Final_ASIN'].fillna(merged['ASIN_KEY_INV'])

        # 5. Mapping Names & Brands
        merged['Brand'] = merged.apply(lambda r: get_brand_robust(r, b_title, None, a_camp), axis=1)
        merged['Item Name'] = merged.apply(lambda r: MAISON_REF.get(r['Final_ASIN'], r[b_title] if r[b_title] != 0 else "Unidentified SKU"), axis=1)
        
        # 6. Final Ratio Calculations
        merged['ACOS'] = (merged[a_spend] / merged[a_sales]).replace([np.inf, -np.inf], 0).fillna(0)
        merged['TACOS'] = (merged[a_spend] / merged[b_sales]).replace([np.inf, -np.inf], 0).fillna(0)

    # --- UI LAYOUT ---
    st.subheader("🌎 Global Portfolio Overview")
    ov1, ov2, ov3, ov4, ov5 = st.columns(5)
    t_rev, t_ad, t_sp = merged[b_sales].sum(), merged[a_sales].sum(), merged[a_spend].sum()
    ov1.metric("Total Sales", f"AED {t_rev:,.2f}")
    ov2.metric("Ad Sales", f"AED {t_ad:,.2f}")
    ov3.metric("Total Spend", f"AED {t_sp:,.2f}")
    ov4.metric("ACOS / TACOS", f"{(t_sp/t_ad if t_ad > 0 else 0):.1%} / {(t_sp/t_rev if t_rev > 0 else 0):.1%}")
    ov5.metric("Sellable Stock", f"{merged['Stock'].sum():,.0f} Units")

    tabs = st.tabs(["📊 Brand Overview"] + list(BRAND_MAP.values()))

    # Global Brand Breakdown
    with tabs[0]:
        brand_summary = merged.groupby('Brand').agg({b_sales: 'sum', a_sales: 'sum', a_spend: 'sum', 'Stock': 'sum'}).reset_index()
        brand_summary['ACOS'] = (brand_summary[a_spend] / brand_summary[a_sales]).fillna(0)
        brand_summary['TACOS'] = (brand_summary[a_spend] / brand_summary[b_sales]).fillna(0)
        st.dataframe(brand_summary.sort_values(by=b_sales, ascending=False).style.format({
            b_sales: '{:,.2f}', a_sales: '{:,.2f}', a_spend: '{:,.2f}', 'Stock': '{:,.0f}', 'ACOS': '{:.1%}', 'TACOS': '{:.1%}'
        }), use_container_width=True, hide_index=True)

    # Individual Brand Tabs
    for idx, brand_name in enumerate(BRAND_MAP.values(), start=1):
        with tabs[idx]:
            b_data = merged[merged['Brand'] == brand_name]
            st.subheader(f"{brand_name} Metrics")
            k1, k2, k3, k4, k5 = st.columns(5)
            k_rev, k_ad, k_sp = b_data[b_sales].sum(), b_data[a_sales].sum(), b_data[a_spend].sum()
            k1.metric("Business Sales", f"AED {k_rev:,.2f}")
            k2.metric("Ad Sales", f"AED {k_ad:,.2f}")
            k3.metric("Brand Spend", f"AED {k_sp:,.2f}")
            k4.metric("ACOS", f"{(k_sp/k_ad if k_ad > 0 else 0):.1%}")
            k5.metric("Sellable Stock", f"{b_data['Stock'].sum():,.0f}")
            
            st.dataframe(b_data[['Final_ASIN', 'Item Name', 'Stock', b_sales, a_sales, a_spend, 'ACOS', 'TACOS']].sort_values(by=b_sales, ascending=False).style.format({
                b_sales: '{:,.2f}', a_sales: '{:,.2f}', a_spend: '{:,.2f}', 'Stock': '{:,.0f}', 'ACOS': '{:.1%}', 'TACOS': '{:.1%}'
            }), use_container_width=True, hide_index=True)

    # Excel Download
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        merged.to_excel(writer, sheet_name='Master_Audit', index=False)
    st.sidebar.download_button("📥 Download Final Report", data=output.getvalue(), file_name="Amazon_Performance_Master.xlsx")

else:
    st.info("Upload your reports to see the accurate Spend, Maison names, and Sellable inventory.")
