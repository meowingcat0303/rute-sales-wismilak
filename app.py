import streamlit as st
import pandas as pd
import requests, folium
from streamlit.components.v1 import html

# --- FUNGSI PEMBANTU ---
# Menggunakan format resmi Google Maps URL untuk rute langsung
def get_gmaps_link(lat1, lon1, lat2, lon2):
    return f"https://www.google.com/maps/dir/?api=1&origin={lat1},{lon1}&destination={lat2},{lon2}&travelmode=driving"

def get_batch_gmaps_link(locations_list):
    # Untuk rute batch, kita buat link ke titik pertama
    lat, lon = locations_list[0]
    return f"https://www.google.com/maps/dir/?api=1&destination={lat},{lon}&travelmode=driving"

def get_road_geometry(start_lat, start_lon, end_lat, end_lon):
    url = f"http://router.project-osrm.org/route/v1/driving/{start_lon},{start_lat};{end_lon},{end_lat}?overview=full&geometries=geojson"
    try:
        res = requests.get(url).json()
        coords = res['routes'][0]['geometry']['coordinates']
        return [[c[1], c[0]] for c in coords]
    except:
        return [[start_lat, start_lon], [end_lat, end_lon]]

# --- UI APP ---
st.set_page_config(layout="wide")
st.title("📍 Wismilak Route Optimizer (Developed by Ghalib Damarillah Asahlintang)")
st.caption("Pastikan rute koordinat benar benar sesuai agar tidak terjadi kesalahan penghitungan rute")

uploaded_file = st.file_uploader("Upload File Excel Toko (.xlsx)", type=["xlsx"])

if uploaded_file:
    # 1. BACA FILE & AUTO DETECT KOLOM
    with st.spinner('Membaca file Excel...'):
        df = pd.read_excel(uploaded_file)
        cols = df.columns.tolist()

        def find_best_col(keywords):
            for col in cols:
                for kw in keywords:
                    if kw in str(col).lower():
                        return col
            return cols[0]

        st.write("### Konfirmasi Kolom Excel:")
        c1, c2, c3 = st.columns(3)
        with c1:
            name_col = st.selectbox("Pilih kolom Nama Toko:", cols, index=cols.index(find_best_col(['nama', 'toko', 'outlet', 'name'])))
        with c2:
            lat_col = st.selectbox("Pilih kolom Latitude:", cols, index=cols.index(find_best_col(['lat', 'latitude'])))
        with c3:
            lon_col = st.selectbox("Pilih kolom Longitude:", cols, index=cols.index(find_best_col(['long', 'lng', 'longitude'])))

    # 2. PROSES ROUTING
    with st.spinner('AI sedang menganalisis rute paling efisien dan realistis...'):
        locations = df[[lat_col, lon_col]].values.tolist()
        names = df[name_col].tolist()

        coords = ";".join([f"{loc[1]},{loc[0]}" for loc in locations])
        url = f"http://router.project-osrm.org/table/v1/driving/{coords}?annotations=duration"
        matrix = requests.get(url, headers={'User-Agent': 'Sales/1.0'}).json()['durations']

        # Logika Hybrid (Fleksibel)
        current_node = 0 
        unvisited = list(range(1, len(locations)))
        route_indices = [0]
        total_travel_seconds = 0
        
        while unvisited:
            best_node = None
            min_score = float('inf')
            for next_node in unvisited:
                score = matrix[current_node][next_node]
                if score < min_score:
                    min_score = score
                    best_node = next_node
            
            total_travel_seconds += matrix[current_node][best_node]
            route_indices.append(best_node)
            unvisited.remove(best_node)
            current_node = best_node
        
        total_travel_seconds += matrix[current_node][0]
        route_indices.append(0)

    # 3. TAMPILAN TABEL & MAP
    st.success("Rute Selesai Dihitung!")
    
    table_data = []
    for i in range(len(route_indices) - 1):
        curr = route_indices[i]
        next_n = route_indices[i+1]
        
        dur_sec = round(matrix[curr][next_n])
        
        table_data.append({
            "Checklist": False,
            "No": i + 1,
            "Dari": names[curr],
            "Ke": names[next_n],
            "Waktu (Menit)": round(dur_sec / 60, 2),
            "Link Maps": get_gmaps_link(locations[curr][0], locations[curr][1], locations[next_n][0], locations[next_n][1])
        })

    st.write("### Jadwal Kunjungan:")
    st.data_editor(
        pd.DataFrame(table_data),
        column_config={
            "Checklist": st.column_config.CheckboxColumn("Checklist", default=False),
            "Link Maps": st.column_config.LinkColumn("Buka Google Maps", display_text="📍 Navigasi"),
        },
        use_container_width=True,
        hide_index=True
    )
    
    total_hours = int(total_travel_seconds // 3600)
    total_minutes = int((total_travel_seconds % 3600) // 60)
    st.metric(label="Total Estimasi Waktu Perjalanan", value=f"{total_hours} Jam {total_minutes} Menit")
    
    st.write("### Peta Rute:")
    m = folium.Map(location=locations[0], zoom_start=15)
    for i in range(len(route_indices) - 1):
        start, end = locations[route_indices[i]], locations[route_indices[i+1]]
        path_coords = get_road_geometry(start[0], start[1], end[0], end[1])
        folium.PolyLine(path_coords, color="blue", weight=5, opacity=0.8).add_to(m)
        
    for i, node in enumerate(route_indices):
        folium.Marker(locations[node], popup=names[node]).add_to(m)
    html(m._repr_html_(), height=500)
