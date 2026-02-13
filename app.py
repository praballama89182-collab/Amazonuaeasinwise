import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO

# 1. Page Configuration
st.set_page_config(page_title="AMAZON MASTER AUDIT", page_icon="🎯", layout="wide")

# 2. Maison Reference Dictionary
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
    """Deep clean of currency, commas, and hidden spaces."""
    if isinstance(val, str):
        cleaned = val.replace('AED', '').replace('$', '').replace('\xa0', '').replace(',', '').strip()
        try: return pd.to_numeric(cleaned)
        except: return 0.0
    return val if isinstance(val, (int, float)) else 0.0

def get_brand_logic(text):
    """Robust keyword detection for all 6 core brands."""
    text = str(text).upper()
    targets = {
        'Maison de l’Avenir': ['MAISON', 'MA_', 'JPP', 'CEB', 'PGN', 'VGA'],
        'Creation Lamis': ['LAMIS', 'CL_', 'CL |', 'CLP', 'CPL', '3DM', 'CLAM'],
        'Jean Paul Dupont': ['DUPONT', 'JPD'],
        'Paris Collection': ['PARIS COLLECTION', 'PC_', 'PC |', 'PCB', 'PCH', 'PCBC', 'PCF', 'PCK', 'PCL'],
        'Dorall Collection': ['DORALL', 'DC_', 'DC |', 'DCL'],
        'CP Trendies': ['TRENDIES', 'CPT', 'CP_', 'CPMK', 'CPM', 'CPN', 'TGJ', 'COCP']
    }
    for brand_name, keywords in targets.items():
        if any(kw in text for kw in keywords): return brand_name
    return "Unmapped"

def find_col(df, keywords, exclude=None):
    """Finds columns regardless of brackets or trailing spaces."""
    for col in df.columns:
        c_low = str(col).strip().lower()
        if any(kw.lower() in c_low for kw in keywords):
            if exclude and any(ex.lower() in c_low for ex in exclude): continue
            return col
    return None

# --- Main App ---
st.title("🎯 Final Amazon Master Audit")
st.info("Verified: Mapping from ASIN History | Smart-Stacked Layout | Purchase % Removed")

# Sidebar Uploads
st.sidebar.header("📁 Report Upload Center")
file_types = ["csv", "xlsx", "xls", "xlsm", "xlsb"]
ad_f = st.sidebar.file_uploader("1. Ad Report", type=file_types)
biz_f = st.sidebar.file_uploader("2. Business Report", type=file_types)
inv_f = st.sidebar.file_uploader("3. Inventory Report (.txt)", type=["txt"])

if ad_f and biz_f and inv_f:
    with st.spinner('Building Master ASIN Map and Syncing Data...'):
        # 1. Load Data
        df_ad = pd.read_csv(ad_f) if ad_f.name.endswith('.csv') else pd.read_excel(ad_f)
        df_biz = pd.read_csv(biz_f) if biz_f.name.endswith('.csv') else pd.read_excel(biz_f)
        df_inv = pd.read_csv(inv_f, sep='\t')

        for df in [df_ad, df_biz, df_inv]: df.columns = [str(c).strip() for c in df.columns]

        # 2. Identify Primary Columns
        b_asin, b_sales, b_title = find_col(df_biz, ['child asin', 'asin']), find_col(df_biz, ['ordered product sales']), find_col(df_biz, ['title', 'item name'])
        a_asin, a_sales, a_spend, a_camp = find_col(df_ad, ['advertised asin']), find_col(df_ad, ['7 day total sales']), find_col(df_ad, ['spend']), find_col(df_ad, ['campaign name'])
        i_asin, i_qty, i_cond, i_sku = find_col(df_inv, ['asin']), find_col(df_inv, ['quantity available']), find_col(df_inv, ['warehouse-condition-code']), find_col(df_inv, ['seller-sku'])

        # 3. Build Master ASIN-to-Brand Map from Sales Reports
        df_biz['Brand_Mapped'] = df_biz[b_title].apply(get_brand_logic)
        df_ad['Brand_Mapped'] = df_ad[a_camp].apply(get_brand_logic)
        
        # Create dictionary for mapping inventory
        asin_map = {**df_ad.set_index(a_asin)['Brand_Mapped'].to_dict(), 
                    **df_biz.set_index(b_asin)['Brand_Mapped'].to_dict()}

        # 4. Process Inventory (Sellable Only)
        df_inv_sell = df_inv[df_inv[i_cond].astype(str).str.strip().str.upper() == 'SELLABLE'].copy()
        # Map Brand by ASIN first, then fallback to SKU logic
        df_inv_sell['Brand'] = df_inv_sell[i_asin].map(asin_map).fillna(df_inv_sell[i_sku].apply(get_brand_logic))
        
        inv_pivot = df_inv_sell.groupby([i_asin, 'Brand'])[i_qty].sum().reset_index()
        inv_pivot.columns = ['Final_ASIN', 'Brand', 'Stock']

        # 5. Clean Sales Data
        df_biz[b_sales] = df_biz[b_sales].apply(clean_numeric)
        df_ad[a_sales], df_ad[a_spend] = df_ad[a_sales].apply(clean_numeric), df_ad[a_spend].apply(clean_numeric)

        # 6. Final Merge
        ad_agg = df_ad.groupby(a_asin).agg({a_sales: 'sum', a_spend: 'sum', a_camp: 'first'}).reset_index()
        master = pd.merge(inv_pivot, df_biz, left_on='Final_ASIN', right_on=b_asin, how='outer')
        master['Final_ASIN'] = master['Final_ASIN'].fillna(master[b_asin])
        master = pd.merge(master, ad_agg, left_on='Final_ASIN', right_on=a_asin, how='outer', suffixes=('', '_ad'))
        master['Final_ASIN'] = master['Final_ASIN'].fillna(master[a_asin])

        # Resolve Final Item Names & Brands
        master['Brand'] = master['Brand'].fillna(master['Final_ASIN'].map(asin_map)).fillna("Unmapped")
        master['Item Name'] = master.apply(lambda r: MAISON_REF.get(r['Final_ASIN'], r[b_title] if pd.notna(r[b_title]) else "New Item"), axis=1)

        # Ratios
        master['ACOS'] = (master[a_spend] / master[a_sales]).replace([np.inf, -np.inf], 0).fillna(0)
        master['TACOS'] = (master[a_spend] / master[b_sales]).replace([np.inf, -np.inf], 0).fillna(0)
        
        for c in [b_sales, a_sales, a_spend, 'Stock']: master[c] = master[c].fillna(0)

    # --- UI LAYOUT ---
    st.subheader("🌎 Global Performance Summary")
    ov1, ov2, ov3, ov4, ov5 = st.columns(5)
    t_rev, t_ad, t_sp = master[b_sales].sum(), master[a_sales].sum(), master[a_spend].sum()
    ov1.metric("Total Business Sales", f"AED {t_rev:,.2f}")
    ov2.metric("Total Ad Sales", f"AED {t_ad:,.2f}")
    ov3.metric("Total Ad Spend", f"AED {t_sp:,.2f}")
    ov4.metric("ACOS / TACOS", f"{(t_sp/t_ad if t_ad > 0 else 0):.1%} / {(t_sp/t_rev if t_rev > 0 else 0):.1%}")
    ov5.metric("Sellable Stock", f"{master['Stock'].sum():,.0f} Units")

    tabs = st.tabs(["📊 Brand Overview"] + list(BRAND_MAP.values()))

    # Global Brand Breakdown
    with tabs[0]:
        brand_perf = master.groupby('Brand').agg({b_sales: 'sum', a_sales: 'sum', a_spend: 'sum', 'Stock': 'sum'}).reset_index()
        st.dataframe(brand_perf.sort_values(by=b_sales, ascending=False).style.format({
            b_sales: '{:,.2f}', a_sales: '{:,.2f}', a_spend: '{:,.2f}', 'Stock': '{:,.0f}'
        }), use_container_width=True, hide_index=True)

    # Individual Brand Tabs
    for idx, brand_name in enumerate(BRAND_MAP.values(), start=1):
        with tabs[idx]:
            b_data = master[master['Brand'] == brand_name]
            st.subheader(f"{brand_name} Performance")
            
            k1, k2, k3, k4, k5 = st.columns(5)
            k_rev, k_ad, k_sp = b_data[b_sales].sum(), b_data[a_sales].sum(), b_data[a_spend].sum()
            k1.metric("Sales", f"AED {k_rev:,.2f}")
            k2.metric("Ad Sales", f"AED {k_ad:,.2f}")
            k3.metric("Spend", f"AED {k_sp:,.2f}")
            k4.metric("ACOS", f"{(k_sp/k_ad if k_ad > 0 else 0):.1%}")
            k5.metric("Stock", f"{b_data['Stock'].sum():,.0f}")
            
            st.dataframe(b_data[['Final_ASIN', 'Item Name', 'Stock', b_sales, a_sales, a_spend, 'ACOS', 'TACOS']].sort_values(by=b_sales, ascending=False).style.format({
                b_sales: '{:,.2f}', a_sales: '{:,.2f}', a_spend: '{:,.2f}', 'Stock': '{:,.0f}', 'ACOS': '{:.1%}', 'TACOS': '{:.1%}'
            }), use_container_width=True, hide_index=True)

    # Excel Download
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        master.to_excel(writer, sheet_name='Master_Audit', index=False)
    st.sidebar.download_button("📥 Download Final Report", data=output.getvalue(), file_name="Amazon_Performance_Master.xlsx")

else:
    st.info("Upload your reports to generate the dashboard with accurate ASIN-level brand tracking.")
