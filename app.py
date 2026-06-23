import streamlit as st
import pandas as pd
import requests, folium
from streamlit.components.v1 import html

# Fungsi untuk link Google Maps Individual (A ke B)
def get_gmaps_link(lat1, lon1, lat2, lon2):
    return f"https://www.google.com/maps/dir/?api=1&origin={lat1},{lon1}&destination={lat2},{lon2}&travelmode=driving"

# Fungsi untuk membuat link Rute Panjang (10 Toko ke Depan)
def get_batch_gmaps_link(locations_list):
    base_url = "https://www.google.com/maps/dir/"
    coords_path = "/".join([f"{loc[0]},{loc[1]}" for loc in locations_list])
    return base_url + coords_path

# Fungsi untuk geometri jalan
def get_road_geometry(start_lat, start_lon, end_lat, end_lon):
    url = f"http://router.project-osrm.org/route/v1/driving/{start_lon},{start_lat};{end_lon},{end_lat}?overview=full&geometries=geojson"
    try:
        res = requests.get(url).json()
        coords = res['routes'][0]['geometry']['coordinates']
        return [[c[1], c[0]] for c in coords]
    except:
        return [[start_lat, start_lon], [end_lat, end_lon]]

st.set_page_config(layout="wide")
st.title("📍 Wismilak Route Optimizer Pro")
st.caption("Pastikan rute koordinat benar benar sesuai agar tidak terjadi kesalahan penghitungan rute")

uploaded_file = st.file_uploader("Upload File Excel Toko (.xlsx)", type=["xlsx"])

if uploaded_file:
    df = pd.read_excel(uploaded_file)
    locations = df[['Latitude', 'Longitude']].values.tolist()
    names = df['Outlet Name'].tolist()

    # Hitung Matriks Jarak
    coords = ";".join([f"{lon},{lat}" for lat, lon in locations])
    url = f"http://router.project-osrm.org/table/v1/driving/{coords}?annotations=duration"
    matrix = requests.get(url, headers={'User-Agent': 'Sales/1.0'}).json()['durations']

    # Logika Nearest Neighbor
    current_node = 0
    unvisited = list(range(1, len(locations)))
    route_indices = [0]
    
    while unvisited:
        next_node = min(unvisited, key=lambda x: matrix[current_node][x])
        route_indices.append(next_node)
        unvisited.remove(next_node)
        current_node = next_node
    route_indices.append(0)

    st.success("Rute Berhasil Dihitung!")
    
    table_data = []
    # Loop untuk membuat baris tabel
    for i in range(len(route_indices) - 1):
        curr = route_indices[i]
        next_n = route_indices[i+1]
        
        dur_sec = round(matrix[curr][next_n])
        dur_min = round(dur_sec / 60, 2)
        
        # Logika 10 toko ke depan
        end_batch = min(i + 10, len(route_indices) - 1)
        batch_indices = route_indices[i : end_batch + 1]
        batch_locations = [locations[idx] for idx in batch_indices]
        
        table_data.append({
            "No": i + 1,
            "Dari": names[curr],
            "Ke": names[next_n],
            "Waktu (Detik)": dur_sec,
            "Waktu (Menit)": dur_min,
            "Link Perjalanan (1 Toko)": get_gmaps_link(locations[curr][0], locations[curr][1], locations[next_n][0], locations[next_n][1]),
            "Link 10 Toko Kedepan": get_batch_gmaps_link(batch_locations)
        })
    
    df_result = pd.DataFrame(table_data)
    
    # Menambahkan kolom "Centang" di posisi paling awal
    df_result.insert(0, "Centang", False)
    
    st.write("### Jadwal Kunjungan:")
    st.data_editor(
        df_result,
        column_config={
            "Centang": st.column_config.CheckboxColumn("Centang", default=False),
            "Link Perjalanan (1 Toko)": st.column_config.LinkColumn(display_text="Buka A->B"),
            "Link 10 Toko Kedepan": st.column_config.LinkColumn(display_text="Buka Rute Batch")
        },
        use_container_width=True,
        hide_index=True
    )
    
    # Tampilan Peta
    st.write("### Peta Rute:")
    m = folium.Map(location=locations[0], zoom_start=15)
    for i in range(len(route_indices) - 1):
        start, end = locations[route_indices[i]], locations[route_indices[i+1]]
        path_coords = get_road_geometry(start[0], start[1], end[0], end[1])
        folium.PolyLine(path_coords, color="blue", weight=5, opacity=0.8).add_to(m)
        
    for i, node in enumerate(route_indices):
        folium.Marker(locations[node], popup=names[node]).add_to(m)
    html(m._repr_html_(), height=500)
