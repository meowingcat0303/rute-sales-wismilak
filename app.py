import streamlit as st
import pandas as pd
import requests
from fpdf import FPDF
import io
import folium
import re
import math
import time
from streamlit.components.v1 import html

# URL Master Anda
MASTER_SHEET_URL = "https://docs.google.com/spreadsheets/d/11BXZ5Wt8AvuDwI0x1taxdlnNIgd4Grc9/export?format=csv"

# Fungsi pembersihan mutlak
def clean_id(val):
    return re.sub(r'[^A-Z0-9]', '', str(val).upper())

# --- FUNGSI PDF MODE A ---
def generate_pdf(df):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(200, 10, txt="Daftar Kunjungan Toko", ln=True, align='C')
    pdf.set_font("Arial", size=10)
    pdf.ln(5)
    pdf.set_fill_color(200, 200, 200)
    cols = df.columns.tolist()
    pdf.cell(25, 10, str(cols[0]), border=1, fill=True) 
    pdf.cell(10, 10, str(cols[1]), border=1, fill=True) 
    for c in cols[2:-1]: pdf.cell(35, 10, str(c), border=1, fill=True)
    pdf.cell(20, 10, "Maps", border=1, fill=True)
    pdf.ln()
    for _, row in df.iterrows():
        pdf.cell(25, 10, str(row[cols[0]]), border=1)
        pdf.cell(10, 10, str(row[cols[1]]), border=1)
        for c in cols[2:-1]: pdf.cell(35, 10, str(row[c])[:20], border=1)
        pdf.set_text_color(0, 0, 255)
        pdf.cell(20, 10, "Buka", border=1, link=row['Link Maps'], align='C')
        pdf.set_text_color(0, 0, 0)
        pdf.ln()
    return pdf.output(dest='S').encode('latin-1')

# --- FUNGSI PDF MODE B ---
def generate_pdf_b(df):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(200, 10, txt="Daftar Rute Optimasi", ln=True, align='C')
    pdf.set_font("Arial", size=10)
    pdf.ln(5)
    pdf.set_fill_color(200, 200, 200)
    pdf.cell(25, 10, "Kode", border=1, fill=True)
    pdf.cell(10, 10, "No", border=1, fill=True, align='C')
    pdf.cell(55, 10, "Dari", border=1, fill=True)
    pdf.cell(55, 10, "Ke", border=1, fill=True)
    pdf.cell(20, 10, "Waktu", border=1, fill=True, align='C')
    pdf.cell(20, 10, "Maps", border=1, fill=True, align='C')
    pdf.ln()
    for _, row in df.iterrows():
        pdf.cell(25, 10, str(row['Kode Customer']), border=1)
        pdf.cell(10, 10, str(row['No']), border=1, align='C')
        pdf.cell(55, 10, str(row['Dari'])[:30], border=1)
        pdf.cell(55, 10, str(row['Ke'])[:30], border=1)
        pdf.cell(20, 10, f"{row['Waktu (Menit)']} Mnt", border=1, align='C')
        pdf.set_text_color(0, 0, 255)
        pdf.cell(20, 10, "Nav", border=1, link=row['Navigasi A->B'], align='C')
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
    except: return [[lat1, lon1], [lat2, lon2]]

def get_single_leg_link(lat1, lon1, lat2, lon2):
    return f"https://www.google.com/maps/dir/?api=1&origin={lat1},{lon1}&destination={lat2},{lon2}&travelmode=driving"

def get_batch_gmaps_link(locations_list):
    start = locations_list[0]
    waypoints = "|".join([f"{loc[0]},{loc[1]}" for loc in locations_list])
    return f"https://www.google.com/maps/dir/?api=1&origin={start[0]},{start[1]}&waypoints={waypoints}&destination={locations_list[-1][0]},{locations_list[-1][1]}&travelmode=driving"

# --- FUNGSI AUTO-SORT WILAYAH ---
def get_location_details(lat, lon):
    url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}&zoom=18&addressdetails=1"
    headers = {'User-Agent': 'WismilakRouteOptimizer/1.0'}
    try:
        res = requests.get(url, headers=headers, timeout=5).json()
        address = res.get('address', {})
        kecamatan = address.get('town', address.get('city_district', address.get('county', '-')))
        desa = address.get('village', address.get('suburb', address.get('neighbourhood', '-')))
        return kecamatan, desa
    except: return "-", "-"

# --- UI APP ---
st.set_page_config(layout="wide", page_title="Wismilak Optimizer")
st.title("📍 Wismilak Route Optimizer")
st.sidebar.subheader("Developed By Ghalib Damarillah Asahlintang (2026)")

source = st.sidebar.radio("Pilih Sumber Data:", ["Upload Excel", "Google Sheets Master"])
df = None

if source == "Upload Excel":
    uploaded_file = st.sidebar.file_uploader("Upload File Excel (.xlsx)", type=["xlsx"])
    if uploaded_file: df = pd.read_excel(uploaded_file)
else:
    try:
        df = pd.read_csv(MASTER_SHEET_URL)
        st.sidebar.success("Master Data Terhubung!")
    except: st.sidebar.error("Gagal terhubung ke Google Sheet.")

if df is not None:
    cols = df.columns.tolist()
    kode_opt = ["Tidak Ada"] + cols
    
    kode_col = st.sidebar.selectbox("Kolom Kode Toko:", kode_opt, index=0)
    name_col = st.sidebar.selectbox("Kolom Nama:", cols, index=0)
    lat_col = st.sidebar.selectbox("Kolom Lat:", cols, index=1 if len(cols)>1 else 0)
    lon_col = st.sidebar.selectbox("Kolom Long:", cols, index=2 if len(cols)>2 else 0)

    df[lat_col] = pd.to_numeric(df[lat_col].astype(str).str.replace(',', '.'), errors='coerce')
    df[lon_col] = pd.to_numeric(df[lon_col].astype(str).str.replace(',', '.'), errors='coerce')
    if kode_col != "Tidak Ada": df[kode_col] = df[kode_col].astype(str).str.strip().str.upper()
    df = df.dropna(subset=[lat_col, lon_col])

    tab1, tab2, tab3, tab4 = st.tabs(["📂 Mode A: Generate Data", "🚀 Mode B: Optimasi Rute", "🗺️ Mode C: Sort Wilayah", "📅 Mode D: Jadwal Mingguan"])

    with tab1:
        has_kode = kode_col != "Tidak Ada"
        if source == "Google Sheets Master" and has_kode:
            input_codes = st.text_area("Input kode toko:")
            if st.button("Generate Link"):
                raw_list = [clean_id(x) for x in input_codes.split('\n') if clean_id(x) != ""]
                master_indexed = df.set_index(kode_col)
                valid_kodes = [k for k in raw_list if k in master_indexed.index]
                if valid_kodes:
                    filtered_df = master_indexed.loc[valid_kodes].reset_index()
                    filtered_df['Link Maps'] = filtered_df.apply(lambda row: f"https://www.google.com/maps/dir/?api=1&destination={row[lat_col]},{row[lon_col]}", axis=1)
                    filtered_df.insert(0, "No", range(1, 1 + len(filtered_df)))
                    filtered_df = filtered_df[[kode_col, 'No', name_col, lat_col, lon_col, 'Link Maps']]
                    st.data_editor(filtered_df, column_config={"Link Maps": st.column_config.LinkColumn("Buka", display_text="📍 Navigasi")}, width='stretch', hide_index=True)
        else:
            cols_to_use = [kode_col, name_col, lat_col, lon_col] if has_kode else [name_col, lat_col, lon_col]
            df_display = df[cols_to_use].copy()
            if not df_display.empty:
                df_display['Link Maps'] = df_display.apply(lambda row: f"https://www.google.com/maps/dir/?api=1&destination={row[lat_col]},{row[lon_col]}", axis=1)
                df_display.insert(0, "No", range(1, 1 + len(df_display)))
                if has_kode: df_display = df_display[[kode_col, 'No'] + [c for c in df_display.columns if c not in ['No', kode_col]]]
                st.data_editor(df_display, column_config={"Link Maps": st.column_config.LinkColumn("Buka", display_text="📍 Navigasi")}, width='stretch', hide_index=True)

    with tab2:
        if st.button("Jalankan Optimasi"):
            clean_df = df.drop_duplicates(subset=[lat_col, lon_col])
            has_kode_b = kode_col != "Tidak Ada"
            cols_b = ([kode_col] if has_kode_b else []) + [name_col, lat_col, lon_col]
            data_combined = clean_df[cols_b].to_dict('records')
            data_combined.sort(key=lambda x: (x[lat_col], x[lon_col]))
            locations = [[-6.509198, 106.757705]] + [[x[lat_col], x[lon_col]] for x in data_combined]
            names = ["Kantor Area Bogor"] + [x[name_col] for x in data_combined]
            codes = ["-"] + [(x[kode_col] if has_kode_b else "-") for x in data_combined]
            
            coords = ";".join([f"{loc[1]},{loc[0]}" for loc in locations])
            data = requests.get(f"http://router.project-osrm.org/table/v1/driving/{coords}?annotations=duration,distance", headers={'User-Agent': 'Sales/1.0'}).json()
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
            table_data = [{"Checklist": False, "Kode Customer": codes[route_indices[i+1]], "No": i + 1, "Dari": names[route_indices[i]], "Ke": names[route_indices[i+1]], "Waktu (Menit)": round(matrix[route_indices[i]][route_indices[i+1]] / 60, 2), "Navigasi A->B": get_single_leg_link(locations[route_indices[i]][0], locations[route_indices[i]][1], locations[route_indices[i+1]][0], locations[route_indices[i+1]][1])} for i in range(len(route_indices)-1)]
            df_mode_b = pd.DataFrame(table_data)
            st.data_editor(df_mode_b, column_config={"Navigasi A->B": st.column_config.LinkColumn("Navigasi", display_text="🗺️ Cek Rute")}, width='stretch', hide_index=True)
            st.metric("Total Waktu", f"{int(total_seconds//3600)} Jam {int((total_seconds%3600)//60)} Menit")
            c1, c2 = st.columns(2)
            c1.download_button("📥 Download PDF", generate_pdf_b(df_mode_b), "Rute_Optimasi.pdf", "application/pdf")
            excel_buffer_b = io.BytesIO()
            with pd.ExcelWriter(excel_buffer_b, engine='xlsxwriter') as writer: df_mode_b.to_excel(writer, index=False)
            c2.download_button("📥 Download Excel", excel_buffer_b.getvalue(), "Rute_Optimasi.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            
            m_b = folium.Map(location=locations[0], zoom_start=15)
            for i in range(len(route_indices) - 1):
                path = get_road_geometry(locations[route_indices[i]][0], locations[route_indices[i]][1], locations[route_indices[i+1]][0], locations[route_indices[i+1]][1])
                folium.PolyLine(path, color="blue", weight=5).add_to(m_b)
            for i, node in enumerate(route_indices): folium.Marker(locations[node], popup=names[node]).add_to(m_b)
            html(m_b._repr_html_(), height=400)

    with tab3:
        st.subheader("🗺️ Mode C: Sort Wilayah")
        if st.button("Mulai Deteksi Wilayah"):
            df_wilayah = df.copy()
            my_bar = st.progress(0, text="Memproses...")
            kec_list, desa_list = [], []
            for i, row in enumerate(df_wilayah.iterrows()):
                kec, desa = get_location_details(row[1][lat_col], row[1][lon_col])
                kec_list.append(kec); desa_list.append(desa)
                my_bar.progress(int(((i + 1) / len(df_wilayah)) * 100))
                time.sleep(0.5)
            df_wilayah['Kecamatan'] = kec_list; df_wilayah['Desa/Kelurahan'] = desa_list
            my_bar.empty()
            st.dataframe(df_wilayah, width='stretch')

    with tab4:
        st.subheader("📅 Mode D: Jadwal Mingguan")
        s = [st.number_input(h, min_value=0, value=40) for h in ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu"]]
        if st.button("Generate Jadwal"):
            clean_df = df.drop_duplicates(subset=[lat_col, lon_col])
            data = clean_df.to_dict('records')
            clat, clon = clean_df[lat_col].mean(), clean_df[lon_col].mean()
            for r in data: r['angle'] = math.atan2(r[lat_col] - clat, r[lon_col] - clon)
            data.sort(key=lambda x: x['angle'])
            idx = 0
            for i, hari in enumerate(["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu"]):
                chunk = data[idx : idx + s[i]]; idx += s[i]
                if not chunk: continue
                # Logic optimasi harian...
                st.write(f"### {hari}")
                df_h = pd.DataFrame([{"Kode Customer": x[kode_col] if kode_col != "Tidak Ada" else "-", "Toko": x[name_col]} for x in chunk])
                st.data_editor(df_h, width='stretch', hide_index=True)
