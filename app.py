import streamlit as st
import pandas as pd
import requests
from fpdf import FPDF
import io
import folium
from streamlit.components.v1 import html

# --- FUNGSI PDF ---
def generate_pdf(df):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(200, 10, txt="Daftar Kunjungan Toko", ln=True, align='C')
    pdf.set_font("Arial", size=10)
    pdf.ln(5)
    pdf.set_fill_color(200, 200, 200)
    pdf.cell(10, 10, "No", border=1, fill=True)
    pdf.cell(50, 10, "Nama Toko", border=1, fill=True)
    pdf.cell(30, 10, "Lat", border=1, fill=True)
    pdf.cell(30, 10, "Long", border=1, fill=True)
    pdf.cell(40, 10, "Link Maps", border=1, fill=True)
    pdf.ln()
    i = 1
    for _, row in df.iterrows():
        pdf.cell(10, 10, str(i), border=1)
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
def get_batch_gmaps_link(locations_list):
    start = locations_list[0]
    waypoints = "|".join([f"{loc[0]},{loc[1]}" for loc in locations_list])
    return f"https://www.google.com/maps/dir/?api=1&origin={start[0]},{start[1]}&waypoints={waypoints}&destination={locations_list[-1][0]},{locations_list[-1][1]}&travelmode=driving"

# --- UI APP ---
st.set_page_config(layout="wide", page_title="Wismilak Optimizer")
st.title("📍 Wismilak Route Optimizer")

if 'data_storage' not in st.session_state:
    st.session_state['data_storage'] = {}

uploaded_file = st.file_uploader("Upload File Excel (.xlsx)", type=["xlsx"])
if uploaded_file:
    st.session_state['data_storage'][uploaded_file.name] = pd.read_excel(uploaded_file)

if st.session_state['data_storage']:
    selected_file = st.sidebar.selectbox("Pilih Data:", list(st.session_state['data_storage'].keys()))
    df = st.session_state['data_storage'][selected_file]
    cols = df.columns.tolist()
    name_col = st.selectbox("Kolom Nama:", cols, index=cols.index([c for c in cols if 'nama' in c.lower() or 'toko' in c.lower()][0] if any('nama' in c.lower() or 'toko' in c.lower() for c in cols) else cols[0]))
    lat_col = st.selectbox("Kolom Lat:", cols, index=cols.index([c for c in cols if 'lat' in c.lower()][0] if any('lat' in c.lower() for c in cols) else cols[1]))
    lon_col = st.selectbox("Kolom Long:", cols, index=cols.index([c for c in cols if 'long' in c.lower() or 'lng' in c.lower()][0] if any('long' in c.lower() or 'lng' in c.lower() for c in cols) else cols[2]))

    tab1, tab2 = st.tabs(["📂 Mode A: List Koordinat", "🚀 Mode B: Optimasi Rute"])

    with tab1:
        st.subheader("Mode A: List Koordinat")
        raw_data = df.copy()
        raw_data['Link Maps'] = raw_data.apply(lambda row: f"https://www.google.com/maps/dir/?api=1&destination={row[lat_col]},{row[lon_col]}", axis=1)
        st.data_editor(raw_data[[name_col, lat_col, lon_col, 'Link Maps']], column_config={"Link Maps": st.column_config.LinkColumn("Buka", display_text="📍 Navigasi")}, use_container_width=True)
        st.download_button("📥 Download PDF (Bisa Klik Link)", generate_pdf(raw_data[[name_col, lat_col, lon_col, 'Link Maps']]), "Daftar_Toko.pdf", "application/pdf")
        
        # Peta Mode A
        m_a = folium.Map(location=[df[lat_col].mean(), df[lon_col].mean()], zoom_start=13)
        for _, row in df.iterrows():
            folium.Marker([row[lat_col], row[lon_col]], popup=row[name_col]).add_to(m_a)
        html(m_a._repr_html_(), height=400)

    with tab2:
        st.subheader("Mode B: Optimasi Rute")
        if st.button("Jalankan Optimasi"):
            with st.spinner('AI menghitung rute...'):
                locations = df[[lat_col, lon_col]].values.tolist()
                names = df[name_col].tolist()
                coords = ";".join([f"{loc[1]},{loc[0]}" for loc in locations])
                matrix = requests.get(f"http://router.project-osrm.org/table/v1/driving/{coords}?annotations=duration", headers={'User-Agent': 'Sales/1.0'}).json()['durations']
                
                # Optimasi
                route_indices, total_seconds = [0], 0
                unvisited = list(range(1, len(locations)))
                while unvisited:
                    best = min(unvisited, key=lambda x: matrix[route_indices[-1]][x])
                    total_seconds += matrix[route_indices[-1]][best]
                    route_indices.append(best)
                    unvisited.remove(best)
                route_indices.append(0)
                
                table_data = []
                for i in range(len(route_indices) - 1):
                    curr, next_n = route_indices[i], route_indices[i+1]
                    batch_locs = [locations[route_indices[idx]] for idx in range(i, min(i+10, len(route_indices)))]
                    table_data.append({
                        "Checklist": False,
                        "No": i + 1,
                        "Dari": names[curr],
                        "Ke": names[next_n],
                        "Waktu (Menit)": round(matrix[curr][next_n] / 60, 2),
                        "Rute 10 toko kedepan": get_batch_gmaps_link(batch_locs)
                    })
                
                st.data_editor(pd.DataFrame(table_data), column_config={"Rute 10 toko kedepan": st.column_config.LinkColumn("Batch", display_text="🚀 Lihat Rute")}, use_container_width=True)
                st.metric("Total Waktu", f"{int(total_seconds//3600)} Jam {int((total_seconds%3600)//60)} Menit")
                
                # Peta Mode B
                m_b = folium.Map(location=locations[0], zoom_start=15)
                for i in range(len(route_indices) - 1):
                    start, end = locations[route_indices[i]], locations[route_indices[i+1]]
                    folium.PolyLine([start, end], color="blue", weight=5).add_to(m_b)
                for i, node in enumerate(route_indices):
                    folium.Marker(locations[node], popup=names[node]).add_to(m_b)
                html(m_b._repr_html_(), height=400)
