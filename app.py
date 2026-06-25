import streamlit as st
import pandas as pd
import requests
from fpdf import FPDF
import io
import folium
from streamlit.components.v1 import html

# URL Master Anda
MASTER_SHEET_URL = "https://docs.google.com/spreadsheets/d/11BXZ5Wt8AvuDwI0x1taxdlnNIgd4Grc9/export?format=csv"

# --- FUNGSI PDF (Warna Biru untuk Link) ---
def generate_pdf(df):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(200, 10, txt="Daftar Kunjungan Toko", ln=True, align='C')
    pdf.set_font("Arial", size=10)
    pdf.ln(5)
    pdf.set_fill_color(200, 200, 200)
    
    cols = df.columns.tolist()
    pdf.cell(10, 10, "No", border=1, fill=True)
    for c in cols[1:-1]:
        pdf.cell(35, 10, str(c), border=1, fill=True)
    pdf.cell(20, 10, "Maps", border=1, fill=True)
    pdf.ln()
    
    for _, row in df.iterrows():
        pdf.cell(10, 10, str(row['No']), border=1)
        for c in cols[1:-1]:
            pdf.cell(35, 10, str(row[c])[:20], border=1)
        pdf.set_text_color(0, 0, 255)
        pdf.cell(20, 10, "Buka", border=1, link=row['Link Maps'], align='C')
        pdf.set_text_color(0, 0, 0)
        pdf.ln()
    return pdf.output(dest='S').encode('latin-1')

# --- FUNGSI MAPS ---
def get_road_geometry(lat1, lon1, lat2, lon2):
    url = f"http://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}?overview=full&geometries=geojson"
    try:
        res = requests.get(url).json()
        coords = res['routes'][0]['geometry']['coordinates']
        return [[c[1], c[0]] for c in coords]
    except:
        return [[lat1, lon1], [lat2, lon2]]

def get_single_leg_link(lat1, lon1, lat2, lon2):
    return f"https://www.google.com/maps/dir/?api=1&origin={lat1},{lon1}&destination={lat2},{lon2}&travelmode=driving"

def get_batch_gmaps_link(locations_list):
    start = locations_list[0]
    waypoints = "|".join([f"{loc[0]},{loc[1]}" for loc in locations_list])
    return f"https://www.google.com/maps/dir/?api=1&origin={start[0]},{start[1]}&waypoints={waypoints}&destination={locations_list[-1][0]},{locations_list[-1][1]}&travelmode=driving"

# --- UI APP ---
st.set_page_config(layout="wide", page_title="Wismilak Optimizer")
st.title("📍 Wismilak Route Optimizer")

# --- SUMBER DATA ---
st.sidebar.subheader("⚙️ Sumber Data")
source = st.sidebar.radio("Pilih Sumber Data:", ["Upload Excel", "Google Sheets Master"])
df = None

if source == "Upload Excel":
    uploaded_file = st.sidebar.file_uploader("Upload File Excel (.xlsx)", type=["xlsx"])
    if uploaded_file:
        df = pd.read_excel(uploaded_file)
else:
    try:
        df = pd.read_csv(MASTER_SHEET_URL)
        st.sidebar.success("Master Data Terhubung!")
    except:
        st.sidebar.error("Gagal terhubung ke Google Sheet.")

if df is not None:
    cols = df.columns.tolist()
    kode_opt = ["Tidak Ada"] + cols
    default_kode_idx = 0
    for i, c in enumerate(cols):
        if 'kode' in c.lower() or 'code' in c.lower():
            default_kode_idx = i + 1
            break
            
    kode_col = st.sidebar.selectbox("Kolom Kode Toko:", kode_opt, index=default_kode_idx)
    name_col = st.sidebar.selectbox("Kolom Nama:", cols, index=cols.index([c for c in cols if 'nama' in c.lower() or 'toko' in c.lower()][0] if any('nama' in c.lower() or 'toko' in c.lower() for c in cols) else cols[0]))
    lat_col = st.sidebar.selectbox("Kolom Lat:", cols, index=cols.index([c for c in cols if 'lat' in c.lower()][0] if any('lat' in c.lower() for c in cols) else cols[1] if len(cols)>1 else cols[0]))
    lon_col = st.sidebar.selectbox("Kolom Long:", cols, index=cols.index([c for c in cols if 'long' in c.lower() or 'lng' in c.lower()][0] if any('long' in c.lower() or 'lng' in c.lower() for c in cols) else cols[2] if len(cols)>2 else cols[0]))

    # Konversi data ke format bersih
    df[lat_col] = pd.to_numeric(df[lat_col], errors='coerce')
    df[lon_col] = pd.to_numeric(df[lon_col], errors='coerce')
    df[kode_col] = df[kode_col].astype(str).str.strip() # Bersihkan spasi
    df = df.dropna(subset=[lat_col, lon_col])

    tab1, tab2 = st.tabs(["📂 Mode A: Generate via Copas Kode", "🚀 Mode B: Optimasi Rute"])

    with tab1:
        st.subheader("🔍 Generate Link via Copas Kode Toko")
        if kode_col == "Tidak Ada":
            st.warning("⚠️ Pilih 'Kolom Kode Toko' di sidebar kiri.")
        else:
            input_codes = st.text_area("Tinggal input (paste) urutan kode toko di sini (Enter per baris):")
            if st.button("Generate Link"):
                if input_codes:
                    list_kode = [x.strip() for x in input_codes.split('\n') if x.strip()]
                    master_indexed = df.set_index(kode_col)
                    
                    valid_kodes = [k for k in list_kode if k in master_indexed.index]
                    invalid_kodes = [k for k in list_kode if k not in master_indexed.index]

                    if invalid_kodes:
                        st.warning(f"Kode tidak ada di database: {', '.join(invalid_kodes)}")
                        st.info(f"Contoh format kode di master: {df[kode_col].iloc[0]}")

                    if valid_kodes:
                        filtered_df = master_indexed.loc[valid_kodes].reset_index()
                        filtered_df = filtered_df.rename(columns={'index': kode_col})
                        filtered_df = filtered_df[[kode_col, name_col, lat_col, lon_col]].copy()
                        filtered_df['Link Maps'] = filtered_df.apply(lambda row: f"https://www.google.com/maps/dir/?api=1&destination={row[lat_col]},{row[lon_col]}", axis=1)
                        filtered_df.insert(0, "No", range(1, 1 + len(filtered_df)))

                        st.success(f"Berhasil: {len(valid_kodes)} toko ditemukan!")
                        st.data_editor(filtered_df, column_config={"Link Maps": st.column_config.LinkColumn("Buka", display_text="📍 Navigasi")}, use_container_width=True, hide_index=True)

                        c3, c4 = st.columns(2)
                        c3.download_button("📥 Download PDF", generate_pdf(filtered_df), "Rute_Sales_Copas.pdf", "application/pdf")
                        excel_buffer_f = io.BytesIO()
                        with pd.ExcelWriter(excel_buffer_f, engine='xlsxwriter') as writer:
                            filtered_df.to_excel(writer, index=False)
                        c4.download_button("📥 Download Excel", excel_buffer_f.getvalue(), "Rute_Sales_Copas.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    with tab2:
        st.subheader("Mode B: Optimasi Rute")
        if st.button("Jalankan Optimasi"):
            with st.spinner('Menghitung Rute Realistis...'):
                clean_df = df.drop_duplicates(subset=[lat_col, lon_col])
                data_combined = clean_df[[name_col, lat_col, lon_col]].to_dict('records')
                data_combined.sort(key=lambda x: (x[lat_col], x[lon_col]))
                
                locations = [[x[lat_col], x[lon_col]] for x in data_combined]
                names = [x[name_col] for x in data_combined]
                
                coords = ";".join([f"{loc[1]},{loc[0]}" for loc in locations])
                url = f"http://router.project-osrm.org/table/v1/driving/{coords}?annotations=duration,distance"
                data = requests.get(url, headers={'User-Agent': 'Sales/1.0'}).json()
                matrix = data['durations']
                
                route_indices, total_seconds = [0], 0
                unvisited = list(range(1, len(locations)))
                while unvisited:
                    curr = route_indices[-1]
                    best = min(unvisited, key=lambda x: matrix[curr][x])
                    total_seconds += matrix[curr][best]
                    route_indices.append(best)
                    unvisited.remove(best)
                route_indices.append(0)
                
                table_data = []
                for i in range(len(route_indices) - 1):
                    curr, next_n = route_indices[i], route_indices[i+1]
                    table_data.append({
                        "Checklist": False, "No": i + 1, "Dari": names[curr], "Ke": names[next_n],
                        "Waktu (Menit)": round(matrix[curr][next_n] / 60, 2),
                        "Navigasi A->B": get_single_leg_link(locations[curr][0], locations[curr][1], locations[next_n][0], locations[next_n][1]),
                        "Rute 10 toko kedepan": get_batch_gmaps_link([locations[route_indices[idx]] for idx in range(i, min(i+10, len(route_indices)))])
                    })
                
                st.data_editor(pd.DataFrame(table_data), column_config={"Navigasi A->B": st.column_config.LinkColumn("Navigasi", display_text="🗺️ Cek Rute"), "Rute 10 toko kedepan": st.column_config.LinkColumn("Batch", display_text="🚀 Lihat Rute")}, use_container_width=True, hide_index=True)
                st.metric("Total Waktu", f"{int(total_seconds//3600)} Jam {int((total_seconds%3600)//60)} Menit")
                
                m_b = folium.Map(location=locations[0], zoom_start=15)
                for i in range(len(route_indices) - 1):
                    path = get_road_geometry(locations[route_indices[i]][0], locations[route_indices[i]][1], locations[route_indices[i+1]][0], locations[route_indices[i+1]][1])
                    folium.PolyLine(path, color="blue", weight=5).add_to(m_b)
                for i, node in enumerate(route_indices):
                    folium.Marker(locations[node], popup=names[node]).add_to(m_b)
                html(m_b._repr_html_(), height=400)
