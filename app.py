import streamlit as st
import pandas as pd
import requests, folium
from streamlit.components.v1 import html

# Fungsi untuk link Google Maps Individual
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

# Header Baru
st.title("📍 Wismilak Route Optimizer (Developed by Ghalib Damarillah Asahlintang)")
# Caption Baru
st.caption("Pastikan rute koordinat benar benar sesuai agar tidak terjadi kesalahan penghitungan rute")

uploaded_file = st.file_uploader("Upload File Excel Toko (.xlsx)", type=["xlsx"])

if uploaded_file:
    # Menggunakan Spinner untuk indikator Loading
    with st.spinner('Sedang menghitung rute optimal dan memproses data, mohon tunggu...'):
        df = pd.read_excel(uploaded_file)
        
        # LOGIKA LINEAR SWEEP (Sorting)
        df = df.sort_values(by=['Latitude', 'Longitude']) 
        sorted_locations = df[['Latitude', 'Longitude']].values.tolist()
        sorted_names = df['Outlet Name'].tolist()

        total_travel_seconds = 0
        table_data = []

        for i in range(len(sorted_locations) - 1):
            curr = sorted_locations[i]
            next_n = sorted_locations[i+1]
            
            # Hitung durasi antar titik urut
            url = f"http://router.project-osrm.org/route/v1/driving/{curr[1]},{curr[0]};{next_n[1]},{next_n[0]}"
            res = requests.get(url).json()
            dur_sec = res['routes'][0]['duration']
            total_travel_seconds += dur_sec
            dur_min = round(dur_sec / 60, 2)
            
            # Batching 10 toko ke depan
            end_batch = min(i + 10, len(sorted_locations) - 1)
            batch_locations = sorted_locations[i : end_batch + 1]
            
            table_data.append({
                "Checklist": False,
                "No": i + 1,
                "Dari": sorted_names[i],
                "Ke": sorted_names[i+1],
                "Waktu (Detik)": round(dur_sec),
                "Waktu (Menit)": dur_min,
                "Link Perjalanan (1 Toko)": get_gmaps_link(curr[0], curr[1], next_n[0], next_n[1]),
                "Link 10 Toko Kedepan": get_batch_gmaps_link(batch_locations)
            })
        
        df_result = pd.DataFrame(table_data)
        
    st.success("Rute Berhasil Dihitung!")
    
    st.write("### Jadwal Kunjungan:")
    st.data_editor(
        df_result,
        column_config={
            "Checklist": st.column_config.CheckboxColumn("Checklist", default=False),
            "Link Perjalanan (1 Toko)": st.column_config.LinkColumn(display_text="Buka A->B"),
            "Link 10 Toko Kedepan": st.column_config.LinkColumn(display_text="Buka Rute Batch")
        },
        use_container_width=True,
        hide_index=True
    )
    
    # Menampilkan total waktu
    total_hours = int(total_travel_seconds // 3600)
    total_minutes = int((total_travel_seconds % 3600) // 60)
    st.metric(label="Total Estimasi Waktu Perjalanan", value=f"{total_hours} Jam {total_minutes} Menit")
    
    # Peta Rute
    st.write("### Peta Rute:")
    m = folium.Map(location=sorted_locations[0], zoom_start=15)
    
    for i in range(len(sorted_locations) - 1):
        start, end = sorted_locations[i], sorted_locations[i+1]
        path_coords = get_road_geometry(start[0], start[1], end[0], end[1])
        folium.PolyLine(path_coords, color="green", weight=5, opacity=0.8).add_to(m)
        
    for i, loc in enumerate(sorted_locations):
        folium.Marker(loc, popup=sorted_names[i]).add_to(m)
    html(m._repr_html_(), height=500)
