import streamlit as st
import pandas as pd
import requests, folium
from streamlit.components.v1 import html

# --- FUNGSI PEMBANTU ---
def get_single_maps_link(lat, lon):
    # Link langsung ke titik koordinat
    return f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"

def get_gmaps_link(lat1, lon1, lat2, lon2):
    return f"https://www.google.com/maps/dir/?api=1&origin={lat1},{lon1}&destination={lat2},{lon2}&travelmode=driving"

def get_batch_gmaps_link(locations_list):
    # Rute batch 10 toko
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

    # --- TAB A: RAW KOORDINAT (NON-OPTIMIZED) ---
    tab1, tab2 = st.tabs(["📂 Mode A: Link Koordinat (Raw/Urut)", "🚀 Mode B: Optimasi Rute (Hybrid AI)"])

    with tab1:
        st.subheader("Mode: Koordinat Murni")
        st.write("Data ditampilkan sesuai urutan file Excel. Tidak ada optimasi rute.")
        
        raw_data = df.copy()
        raw_data['Google Maps Link'] = raw_data.apply(lambda row: get_single_maps_link(row[lat_col], row[lon_col]), axis=1)
        
        st.data_editor(
            raw_data[[name_col, lat_col, lon_col, 'Google Maps Link']],
            column_config={
                "Google Maps Link": st.column_config.LinkColumn("Buka Maps", display_text="📍 Navigasi")
            },
            use_container_width=True
        )

    # --- TAB B: OPTIMASI RUTE (HYBRID AI) ---
    with tab2:
        st.subheader("Mode: Optimasi Rute")
        if st.button("Jalankan Optimasi Rute"):
            with st.spinner('AI sedang menganalisis rute paling efisien...'):
                locations = df[[lat_col, lon_col]].values.tolist()
                names = df[name_col].tolist()

                # Hitung Matriks Durasi
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

                # Tampilkan Hasil
                table_data = []
                for i in range(len(route_indices) - 1):
                    curr = route_indices[i]
                    next_n = route_indices[i+1]
                    dur_sec = round(matrix[curr][next_n])
                    
                    # Batching
                    end_batch = min(i + 10, len(route_indices) - 1)
                    batch_locations = [locations[route_indices[idx]] for idx in range(i, end_batch + 1)]
                    
                    table_data.append({
                        "Checklist": False,
                        "No": i + 1,
                        "Dari": names[curr],
                        "Ke": names[next_n],
                        "Waktu (Menit)": round(dur_sec / 60, 2),
                        "Link Maps": get_gmaps_link(locations[curr][0], locations[curr][1], locations[next_n][0], locations[next_n][1]),
                        "Link 10 Toko": get_batch_gmaps_link(batch_locations)
                    })

                st.data_editor(
                    pd.DataFrame(table_data),
                    column_config={
                        "Checklist": st.column_config.CheckboxColumn("Checklist", default=False),
                        "Link Maps": st.column_config.LinkColumn("Navigasi", display_text="📍 Navigasi"),
                        "Link 10 Toko": st.column_config.LinkColumn("Batch", display_text="🚀 Batch 10")
                    },
                    use_container_width=True,
                    hide_index=True
                )
                
                st.metric("Total Estimasi", f"{int(total_travel_seconds//3600)} Jam {int((total_travel_seconds%3600)//60)} Menit")
