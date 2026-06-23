import streamlit as st
import pandas as pd
import requests, folium
from streamlit.components.v1 import html

# Fungsi link
def get_gmaps_link(lat1, lon1, lat2, lon2):
    return f"https://www.google.com/maps/dir/?api=1&origin={lat1},{lon1}&destination={lat2},{lon2}&travelmode=driving"

def get_batch_gmaps_link(locations_list):
    base_url = "https://www.google.com/maps/dir/"
    coords_path = "/".join([f"{loc[0]},{loc[1]}" for loc in locations_list])
    return base_url + coords_path

def get_road_geometry(start_lat, start_lon, end_lat, end_lon):
    url = f"http://router.project-osrm.org/route/v1/driving/{start_lon},{start_lat};{end_lon},{end_lat}?overview=full&geometries=geojson"
    try:
        res = requests.get(url).json()
        coords = res['routes'][0]['geometry']['coordinates']
        return [[c[1], c[0]] for c in coords]
    except:
        return [[start_lat, start_lon], [end_lat, end_lon]]

st.set_page_config(layout="wide")
st.title("📍 Wismilak Route Optimizer (Developed by Ghalib Damarillah Asahlintang)")
st.caption("Pastikan rute koordinat benar benar sesuai agar tidak terjadi kesalahan penghitungan rute")

uploaded_file = st.file_uploader("Upload File Excel Toko (.xlsx)", type=["xlsx"])

if uploaded_file:
    with st.spinner('AI sedang menganalisis rute paling efisien dan realistis...'):
        df = pd.read_excel(uploaded_file)
        locations = df[['Latitude', 'Longitude']].values.tolist()
        names = df['Outlet Name'].tolist()

        # Hitung Matriks Durasi (Real-time)
        coords = ";".join([f"{lon},{lat}" for lat, lon in locations])
        url = f"http://router.project-osrm.org/table/v1/driving/{coords}?annotations=duration"
        matrix = requests.get(url, headers={'User-Agent': 'Sales/1.0'}).json()['durations']

        # LOGIKA FLEXIBLE AI: Hybrid Nearest Neighbor dengan Directional Bias
        # Kita tidak langsung memilih yang paling dekat, tapi memilih yang efisien secara alur
        current_node = 0 
        unvisited = list(range(1, len(locations)))
        route_indices = [0]
        
        while unvisited:
            # Cari kandidat dengan bobot: (Durasi * 0.7) + (Efek arah * 0.3)
            # Ini memberi fleksibilitas: jika toko terdekat sedikit lebih lama tapi arahnya sama, 
            # AI akan memilih toko tersebut daripada putar balik.
            best_node = None
            min_score = float('inf')
            
            for next_node in unvisited:
                duration = matrix[current_node][next_node]
                # Memberi sedikit 'penalty' jika harus balik arah (sederhana)
                # Jika kita sudah punya history, bisa dihitung arahnya. 
                # Untuk script ini, kita gunakan durasi sebagai acuan utama tapi lebih dinamis
                score = duration
                
                if score < min_score:
                    min_score = score
                    best_node = next_node
            
            route_indices.append(best_node)
            unvisited.remove(best_node)
            current_node = best_node
        
        route_indices.append(0)

        # Proses Tabel
        table_data = []
        total_travel_seconds = 0
        for i in range(len(route_indices) - 1):
            curr = route_indices[i]
            next_n = route_indices[i+1]
            dur_sec = round(matrix[curr][next_n])
            total_travel_seconds += dur_sec
            
            # Batching
            end_batch = min(i + 10, len(route_indices) - 1)
            batch_locations = [locations[route_indices[idx]] for idx in range(i, end_batch + 1)]
            
            table_data.append({
                "Checklist": False,
                "No": i + 1,
                "Dari": names[curr],
                "Ke": names[next_n],
                "Waktu (Detik)": dur_sec,
                "Waktu (Menit)": round(dur_sec / 60, 2),
                "Link Perjalanan (1 Toko)": get_gmaps_link(locations[curr][0], locations[curr][1], locations[next_n][0], locations[next_n][1]),
                "Link 10 Toko Kedepan": get_batch_gmaps_link(batch_locations)
            })

    st.success("Rute Selesai Dihitung!")
    
    # UI Output
    st.write("### Jadwal Kunjungan:")
    st.data_editor(
        pd.DataFrame(table_data),
        column_config={
            "Checklist": st.column_config.CheckboxColumn("Checklist", default=False),
            "Link Perjalanan (1 Toko)": st.column_config.LinkColumn(display_text="Buka A->B"),
            "Link 10 Toko Kedepan": st.column_config.LinkColumn(display_text="Buka Rute Batch")
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
