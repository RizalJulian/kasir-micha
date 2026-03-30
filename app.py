import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from datetime import datetime
import json

# --- 1. CONFIG HALAMAN & CSS ---
st.set_page_config(page_title="Kasir MICHA", layout="centered")

st.markdown("""
    <style>
    /* Tombol Menu Besar untuk Jempol */
    div.stButton > button { width: 100%; height: 4em; margin-bottom: 8px; border-radius: 12px; font-weight: bold; font-size: 16px; }
    /* Area Rakitan Pesanan */
    .rakitan-box { background-color: #fff4e6; padding: 15px; border-radius: 10px; border: 1px solid #ff922b; margin-bottom: 20px; }
    /* Tab Menu */
    .stTabs [data-baseweb="tab"] { height: 50px; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. SISTEM CACHING (TURBO) ---
# Menghubungkan ke Google hanya 1x saat aplikasi baru dibuka
@st.cache_resource
def get_gspread_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = json.loads(st.secrets["gcp_credentials"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

# Mengunci data menu di memori selama 10 menit
@st.cache_data(ttl=600)
def fetch_katalog_data(sheet_name):
    client = get_gspread_client()
    sh = client.open(sheet_name)
    wk = sh.worksheet("Katalog_Menu")
    df = pd.DataFrame(wk.get_all_records())
    df['Kategori'] = df['Kategori'].astype(str).str.strip()
    return df

# Inisialisasi Koneksi & Data
client = get_gspread_client()
# --- GANTI NAMA FILE ANDA DI SINI ---
NAMA_FILE = "Kedai MICHA" 
sheet = client.open(NAMA_FILE)
data_katalog = fetch_katalog_data(NAMA_FILE)

# --- 3. SESSION STATE ---
if 'keranjang' not in st.session_state: st.session_state.keranjang = []
if 'temp_bundle' not in st.session_state: st.session_state.temp_bundle = []

tab1, tab2 = st.tabs(["💻 KASIR", "🍳 DAPUR"])

# ==========================================
# TAB 1: LAYAR KASIR (MULTI-SELECTION)
# ==========================================
with tab1:
    
    # --- DAFTAR MENU ---
    def render_menu(kat, ikon):
        st.write(f"### {ikon} {kat}")
        items = data_katalog[data_katalog['Kategori'] == kat]
        cols = st.columns(2)
        for idx, row in items.reset_index().iterrows():
            with cols[idx % 2]:
                if st.button(f"{row['Nama_Item']}", key=f"m_{row['ID_Item']}_{idx}"):
                    st.session_state.temp_bundle.append(row.to_dict())
                    st.rerun()
        st.write("")

    render_menu("Makanan", "🍱")
    render_menu("Topping", "✨")
    render_menu("Minuman", "🥤")
    
# --- AREA RAKITAN PESANAN ---
    if st.session_state.temp_bundle:
        with st.container(border=True):
            st.subheader("🔥 Rakitan Pesanan")
            nama_gabungan = " + ".join([item['Nama_Item'] for item in st.session_state.temp_bundle])
            harga_akumulasi = sum([int(item['Harga_Jual']) for item in st.session_state.temp_bundle])
            
            st.info(f"Isi: **{nama_gabungan}**")
            
            c1, c2 = st.columns(2)
            harga_final = c1.number_input("Harga Paket (Rp):", min_value=0, value=harga_akumulasi, step=500)
            qty_paket = c2.number_input("Jumlah (Qty):", min_value=1, value=1)
            catatan = st.text_input("Catatan (Misal: Pedas pol)", key="note_input")
            
            total_rakitan = int(harga_final * qty_paket)
            st.write(f"### Subtotal: Rp {total_rakitan:,}")
            
            cb1, cb2 = st.columns(2)
            if cb1.button("❌ BATAL", key="reset_bundle"):
                st.session_state.temp_bundle = []; st.rerun()
            if cb2.button("✅ KE KERANJANG", type="primary", key="add_bundle"):
                nama_fix = f"{nama_gabungan} ({catatan})" if catatan else nama_gabungan
                st.session_state.keranjang.append({
                    'ID_Item': "COMBO", 'Nama_Item': nama_fix, 
                    'Harga_Satuan': int(harga_final), 'Qty': int(qty_paket), 'Total_Harga': int(total_rakitan)
                })
                st.session_state.temp_bundle = []; st.rerun()

    # --- KERANJANG & BAYAR ---
    st.divider()
    st.subheader("🛒 Keranjang Belanja")
    if st.session_state.keranjang:
        total_nota = 0
        for i, item in enumerate(st.session_state.keranjang):
            cx, cd = st.columns([4, 1])
            cx.write(f"{item['Qty']}x **{item['Nama_Item']}**\nRp{item['Total_Harga']:,}")
            if cd.button("❌", key=f"del_{i}"):
                st.session_state.keranjang.pop(i); st.rerun()
            total_nota += item['Total_Harga']
        
        st.write(f"## Total Tagihan: Rp {total_nota:,}")
        metode = st.radio("Metode Bayar:", ["Cash", "QRIS", "Transfer"], horizontal=True)
        
        if st.button("🚀 PROSES BAYAR", type="primary", use_container_width=True):
            waktu = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            id_trx = f"TRX-{datetime.now().strftime('%d%H%M')}"
            log_sheet = sheet.worksheet("Log_Transaksi")
            
            rows = []
            for item in st.session_state.keranjang:
                # Kolom: Timestamp, ID_Trx, ID_Item, Nama, Harga_Sat, Kuantitas, Total, Metode, Status
                rows.append([waktu, id_trx, "COMBO", item['Nama_Item'], item['Harga_Satuan'], item['Qty'], item['Total_Harga'], metode, "Diproses"])
            
            log_sheet.append_rows(rows)
            st.session_state.keranjang = []; st.success("Tersimpan!"); st.rerun()
    else:
        st.info("Klik menu di atas untuk mulai.")

# ==========================================
# TAB 2: ANTREAN DAPUR
# ==========================================
with tab2:
    cd1, cd2 = st.columns(2)
    with cd1:
        if st.button("🔄 Segarkan Data"): st.rerun()
    with cd2:
        if st.button("✅ SELESAI SEMUA", type="secondary"):
            log_sheet = sheet.worksheet("Log_Transaksi")
            cells = log_sheet.findall("Diproses", in_column=9)
            if cells:
                for c in cells: c.value = "Selesai"
                log_sheet.update_cells(cells); st.rerun()

    st.divider()
    # Mengambil data log hanya saat tab dapur dibuka (Agar kasir tetap cepat)
    log_sheet = sheet.worksheet("Log_Transaksi")
    df_log = pd.DataFrame(log_sheet.get_all_records())
    
    if not df_log.empty and 'Status_Pesanan' in df_log.columns:
        antrean = df_log[df_log['Status_Pesanan'].str.strip() == "Diproses"]
        if not antrean.empty:
            for id_trx, grup in antrean.groupby('ID_Transaksi', sort=False):
                with st.container(border=True):
                    st.write(f"🆔 **Nota: {id_trx}**")
                    for _, row in grup.iterrows():
                        # Sesuaikan 'Kuantitas' dengan header kolom F di Sheets
                        st.write(f"• **{row['Kuantitas']}x {row['Nama_Item']}**")
                    if st.button("Selesai ✅", key=f"f_{id_trx}"):
                        c_find = log_sheet.findall(id_trx, in_column=2)
                        for c in c_find: log_sheet.update_cell(c.row, 9, "Selesai")
                        st.rerun()
        else:
            st.success("Dapur Aman!")