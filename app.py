import streamlit as st
import pandas as pd
import requests
from fpdf import FPDF
import io

# --- FUNGSI PDF (DENGAN PENOMORAN) ---
def generate_pdf(df):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(200, 10, txt="Daftar Kunjungan Toko", ln=True, align='C')
    pdf.set_font("Arial", size=10)
    pdf.ln(5)
    
    # Header PDF
    pdf.set_fill_color(200, 200, 200)
    pdf.cell(10, 10, "No", border=1, fill=True) # Kolom Nomor Baru
    pdf.cell(50, 10, "Nama Toko", border=1, fill=True)
    pdf.cell(30, 10, "Lat", border=1, fill=True)
    pdf.cell(30, 10, "Long", border=1, fill=True)
    pdf.cell(40, 10, "Link Maps", border=1, fill=True)
    pdf.ln()
    
    # Isi PDF
    i = 1
    for _, row in df.iterrows():
        pdf.cell(10, 10, str(i), border=1) # Penomoran otomatis
        pdf.cell(50, 10, str(row.iloc[0])[:25], border=1)
        pdf.cell(30, 10, str(row.iloc[1]), border=1)
        pdf.cell(30, 10, str(row.iloc[2]), border=1)
        pdf.set_text_color(0, 0, 255)
        pdf.cell(40, 10, "Klik Disini", border=1, link=str(row.iloc[3]))
        pdf.set_text_color(0, 0, 0)
        pdf.ln()
        i += 1
    return pdf.output(dest='S').encode('latin-1')

# --- FUNGSI MAPS ---
def get_single_maps_link(lat, lon):
    return f"https://www.google.com/maps/dir/?api=1&destination={lat},{lon}"

def get_batch_gmaps_link(locations_list):
    # Menggabungkan waypoint untuk 10 toko ke depan
    start = locations_list[0]
    waypoints = "|".join([f"{loc[0]},{loc[1]}" for loc in locations_list])
    return f"https://www.google.com/maps/dir/?api=1&origin={start[0]},{start[1]}&waypoints={waypoints}&destination={locations_list[-1][0]},{locations_list[-1][1]}&travelmode=driving"

# --- UI APP ---
st.set_page_config(layout="wide", page_title="Wismilak Optimizer")
st.title("📍 Wismilak Route Optimizer (Developed by Ghalib Damarillah Asahlintang")

# Session Storage
if 'data_storage' not in st.session_state:
    st.session_state['data_storage'] = {}

uploaded_file = st.file_uploader("Upload File Excel (.xlsx)", type=["xlsx"])
if uploaded_file:
    df_temp = pd.read_excel(uploaded_file)
    st.session_state['data_storage'][uploaded_file.name] = df_temp

if st.session_state['data_storage']:
    selected_file = st.sidebar.selectbox("Pilih Data Tersimpan:", list(st.session_state['data_storage'].keys()))
    df = st.session_state['data_storage'][selected_file]
    
    # Auto Detect
    cols = df.columns.tolist()
    name_col = st.selectbox("Kolom Nama:", cols, index=cols.index([c for c in cols if 'nama' in c.lower() or 'toko' in c.lower()][0] if any('nama' in c.lower() or 'toko' in c.lower() for c in cols) else cols[0]))
    lat_col = st.selectbox("Kolom Lat:", cols, index=cols.index([c for c in cols if 'lat' in c.lower()][0] if any('lat' in c.lower() for c in cols) else cols[1]))
    lon_col = st.selectbox("Kolom Long:", cols, index=cols.index([c for c in cols if 'long' in c.lower() or 'lng' in c.lower()][0] if any('long' in c.lower() or 'lng' in c.lower() for c in cols) else cols[2]))

    tab1, tab2 = st.tabs(["📂 Mode A: List Koordinat", "🚀 Mode B: Optimasi Rute"])

    with tab1:
        st.subheader("Mode A: Link Koordinat (Raw)")
        raw_data = df.copy()
        raw_data['Link Maps'] = raw_data.apply(lambda row: get_single_maps_link(row[lat_col], row[lon_col]), axis=1)
        
        st.data_editor(raw_data[[name_col, lat_col, lon_col, 'Link Maps']], column_config={"Link Maps": st.column_config.LinkColumn("Buka", display_text="📍 Navigasi")}, use_container_width=True)
        
        pdf_bytes = generate_pdf(raw_data[[name_col, lat_col, lon_col, 'Link Maps']])
        st.download_button("📥 Download PDF (Bisa Klik Link)", pdf_bytes, "Daftar_Toko.pdf", "application/pdf")

    with tab2:
        st.subheader("Mode B: Optimasi Rute (Restored Feature)")
        if st.button("Jalankan Optimasi"):
            with st.spinner('AI menghitung rute...'):
                locations = df[[lat_col, lon_col]].values.tolist()
                names = df[name_col].tolist()
                coords = ";".join([f"{loc[1]},{loc[0]}" for loc in locations])
                url = f"http://router.project-osrm.org/table/v1/driving/{coords}?annotations=duration"
                matrix = requests.get(url, headers={'User-Agent': 'Sales/1.0'}).json()['durations']

                # Optimasi Nearest Neighbor
                current_node, unvisited = 0, list(range(1, len(locations)))
                route_indices, total_seconds = [0], 0
                while unvisited:
                    best_node = min(unvisited, key=lambda x: matrix[current_node][x])
                    total_seconds += matrix[current_node][best_node]
                    route_indices.append(best_node)
                    unvisited.remove(best_node)
                    current_node = best_node
                
                table_data = []
                for i in range(len(route_indices) - 1):
                    curr, next_n = route_indices[i], route_indices[i+1]
                    batch_locs = [locations[route_indices[idx]] for idx in range(i, min(i+10, len(route_indices)))]
                    
                    table_data.append({
                        "No": i + 1,
                        "Dari": names[curr],
                        "Ke": names[next_n],
                        "Rute 10 toko kedepan": get_batch_gmaps_link(batch_locs)
                    })

                st.data_editor(
                    pd.DataFrame(table_data),
                    column_config={"Rute 10 toko kedepan": st.column_config.LinkColumn("Batch", display_text="🚀 Lihat Rute")},
                    use_container_width=True
                )
