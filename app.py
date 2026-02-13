import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO

st.set_page_config(page_title="AMAZON MASTER AUDIT", page_icon="📈", layout="wide")

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
    """Handles currency symbols, commas, and non-breaking spaces."""
    if isinstance(val, str):
        cleaned = val.replace('AED', '').replace('$', '').replace('\xa0', '').replace(',', '').strip()
        try: return pd.to_numeric(cleaned)
        except: return 0.0
    return val if isinstance(val, (int, float)) else 0.0

def get_brand_robust(row, title_col, sku_col, campaign_col=None):
    """Categorizes rows into one of the 6 brands based on multiple data points."""
    # Priority identifiers
    targets = {
        'MA': ['MAISON', 'MA_'],
        'CL': ['LAMIS', 'CL |', 'CL_'],
        'JPD': ['DUPONT', 'JPD |', 'JPD_'],
        'PC': ['PARIS COLLECTION', 'PC |', 'PC_'],
        'DC': ['DORALL', 'DC |', 'DC_'],
        'CPT': ['TRENDIES', 'CPT', 'CP_', 'CPMK']
    }
    
    # Combine relevant text from the row
    text_to_scan = ""
    if title_col and pd.notna(row[title_col]): text_to_scan += " " + str(row[title_col]).upper()
    if sku_col and pd.notna(row[sku_col]): text_to_scan += " " + str(row[sku_col]).upper()
    if campaign_col and campaign_col in row and pd.notna(row[campaign_col]): 
        text_to_scan += " " + str(row[campaign_col]).upper()
    
    for code, full_name in BRAND_MAP.items():
        if any(keyword in text_to_scan for keyword in targets[code]):
            return full_name
    return "Unmapped"

def find_robust_col(df, keywords, exclude=None):
    """Finds column names matching keywords while avoiding exclusions like ACOS/ROAS."""
    for col in df.columns:
        col_clean = str(col).strip().lower()
        if any(kw.lower() in col_clean for kw in keywords):
            if exclude and any(ex.lower() in col_clean for ex in exclude):
                continue
            return col
    return None

# --- UI Setup ---
st.title("🚀 Amazon Master Performance Audit")
st.info("Verified: Global Summary + 6 Brand-Specific Tabs with ASIN Detail")

st.sidebar.header("📁 Upload Center")
ad_file = st.sidebar.file_uploader("1. Ad Report (CSV/XLSX)", type=["csv", "xlsx"])
biz_file = st.sidebar.file_uploader("2. Business Report (CSV/XLSX)", type=["csv", "xlsx"])
inv_file = st.sidebar.file_uploader("3. Inventory Report (.txt)", type=["txt"])

if ad_file and biz_file and inv_file:
    # Load Data
    with st.spinner('Syncing reports and mapping brands...'):
        # Ad Report
        ad_df = pd.read_csv(ad_file) if ad_file.name.endswith('.csv') else pd.read_excel(ad_file)
        ad_df.columns = [c.strip() for c in ad_df.columns]
        
        # Business Report
        biz_df = pd.read_csv(biz_file) if biz_file.name.endswith('.csv') else pd.read_excel(biz_file)
        biz_df.columns = [c.strip() for c in biz_df.columns]
        
        # Inventory Report
        inv_df = pd.read_csv(inv_file, sep='\t')
        inv_df.columns = [c.strip().lower() for c in inv_df.columns]

        # 1. Process Inventory
        inv_summary = inv_df.groupby('asin')['quantity available'].sum().reset_index()
        inv_summary.columns = ['ASIN_KEY', 'Stock']

        # 2. Identify Key Columns
        b_asin = find_robust_col(biz_df, ['asin', 'child asin'])
        b_sales = find_robust_col(biz_df, ['ordered product sales', 'revenue'])
        b_title = find_robust_col(biz_df, ['title', 'item name'])
        b_sku = find_robust_col(biz_df, ['sku', 'seller-sku'])
        
        a_asin = find_robust_col(ad_df, ['advertised asin'])
        a_sales = find_robust_col(ad_df, ['sales'], exclude=['acos', 'roas', 'other'])
        a_spend = find_robust_col(ad_df, ['spend', 'cost'])
        a_sku = find_robust_col(ad_df, ['sku', 'advertised sku'])
        a_camp = find_robust_col(ad_df, ['campaign name'])

        # 3. Clean & Aggregate Ad Data
        ad_df[a_sales] = ad_df[a_sales].apply(clean_numeric)
        ad_df[a_spend] = ad_df[a_spend].apply(clean_numeric)
        
        # Map brands in ad report to help with ASINs missing from Business report
        ad_df['Brand_Map'] = ad_df.apply(lambda r: get_brand_robust(r, None, a_sku, a_camp), axis=1)
        
        ad_summary = ad_df.groupby(a_asin).agg({
            a_sales: 'sum',
            a_spend: 'sum',
            'Brand_Map': 'first'
        }).reset_index()

        # 4. Merge Data onto Business Report
        biz_df[b_sales] = biz_df[b_sales].apply(clean_numeric)
        merged = pd.merge(biz_df, ad_summary, left_on=b_asin, right_on=a_asin, how='left').fillna(0)
        merged = pd.merge(merged, inv_summary, left_on=b_asin, right_on='ASIN_KEY', how='left').fillna(0)
        
        # Final Brand Mapping
        merged['Brand'] = merged.apply(lambda r: get_brand_robust(r, b_title, b_sku, 'Brand_Map'), axis=1)
        
        # Calculations
        merged['Organic Sales'] = merged[b_sales] - merged[a_sales]
        merged['TACOS'] = (merged[a_spend] / merged[b_sales]).replace([np.inf, -np.inf], 0).fillna(0)

    # --- TABS INTERFACE ---
    tabs = st.tabs(["🌎 Global Summary"] + [f"🏷️ {name}" for name in BRAND_MAP.values()])

    # Tab 1: Global Summary
    with tabs[0]:
        st.subheader("Account Performance Summary")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Sales", f"{merged[b_sales].sum():,.2f}")
        m2.metric("Ad Sales", f"{merged[a_sales].sum():,.2f}")
        m3.metric("Total Spend", f"{merged[a_spend].sum():,.2f}")
        m4.metric("Avg TACOS", f"{(merged[a_spend].sum() / merged[b_sales].sum()):.2%}")
        
        # Brand breakdown table
        brand_table = merged.groupby('Brand').agg({
            b_sales: 'sum',
            a_sales: 'sum',
            a_spend: 'sum',
            'Stock': 'sum'
        }).reset_index()
        brand_table['TACOS'] = (brand_table[a_spend] / brand_table[b_sales]).fillna(0)
        st.dataframe(brand_table.sort_values(by=b_sales, ascending=False), use_container_width=True, hide_index=True)

    # Brand-Specific Tabs
    for i, brand_name in enumerate(BRAND_MAP.values(), start=1):
        with tabs[i]:
            brand_data = merged[merged['Brand'] == brand_name]
            
            if not brand_data.empty:
                st.subheader(f"{brand_name} Metrics")
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Total Sales", f"{brand_data[b_sales].sum():,.2f}")
                c2.metric("Ad Sales", f"{brand_data[a_sales].sum():,.2f}")
                c3.metric("Stock Level", f"{brand_data['Stock'].sum():,.0f}")
                c4.metric("TACOS", f"{(brand_data[a_spend].sum() / brand_data[b_sales].sum() if brand_data[b_sales].sum() > 0 else 0):.2%}")
                
                st.markdown("### ASIN Details")
                st.dataframe(
                    brand_data[[b_asin, b_title, 'Stock', b_sales, a_sales, a_spend, 'Organic Sales', 'TACOS']]
                    .sort_values(by=b_sales, ascending=False),
                    use_container_width=True, hide_index=True
                )
            else:
                st.info(f"No data found for {brand_name} in the uploaded reports.")

    # --- EXPORT CENTER ---
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        brand_table.to_excel(writer, sheet_name='Global_Brand_Summary', index=False)
        for name in BRAND_MAP.values():
            sheet_name = name[:30] # Excel sheet name limit
            merged[merged['Brand'] == name].to_excel(writer, sheet_name=sheet_name, index=False)
    
    st.sidebar.markdown("---")
    st.sidebar.download_button(
        label="📥 Download Multi-Sheet Report",
        data=output.getvalue(),
        file_name="Amazon_Performance_Audit.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

else:
    st.warning("Please upload the Advertising, Business, and Inventory files to generate the dashboard.")
