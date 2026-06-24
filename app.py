import streamlit as st
import pandas as pd
import requests, folium
from streamlit.components.v1 import html

# --- FUNGSI PEMBANTU ---
def get_single_maps_link(lat, lon):
    return f"https://www.google.com/maps/dir/?api=1&destination={lat},{lon}"

def get_gmaps_link(lat1, lon1, lat2, lon2):
    return f"https://www.google.com/maps/dir/{lat1},{lon1}/{lat2},{lon2}"

# FUNGSI DIPERBAIKI: Menggabungkan 10 koordinat menjadi satu rute Google Maps
def get_batch_gmaps_link(locations_list):
    # Format: https://www.google.com/maps/dir/lat1,lon1/lat2,lon2/.../lat10,lon10
    path = "/".join([f"{loc[0]},{loc[1]}" for loc in locations_list])
    return f"https://www.google.com/maps/dir/{path}"

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

    # --- TABS ---
    tab1, tab2 = st.tabs(["📂 Mode A: Link Koordinat (Raw/Urut)", "🚀 Mode B: Optimasi Rute (Hybrid AI)"])

    with tab1:
        st.subheader("Mode: Koordinat Murni")
        raw_data = df.copy()
        raw_data['Google Maps Link'] = raw_data.apply(lambda row: get_single_maps_link(row[lat_col], row[lon_col]), axis=1)
        
        st.data_editor(
            raw_data[[name_col, lat_col, lon_col, 'Google Maps Link']],
            column_config={
                "Google Maps Link": st.column_config.LinkColumn("Buka Maps", display_text="📍 Navigasi")
            },
            use_container_width=True
        )

    with tab2:
        st.subheader("Mode: Optimasi Rute")
        if st.button("Jalankan Optimasi Rute"):
            with st.spinner('AI sedang menganalisis rute...'):
                locations = df[[lat_col, lon_col]].values.tolist()
                names = df[name_col].tolist()

                # Hitung Matriks
                coords = ";".join([f"{loc[1]},{loc[0]}" for loc in locations])
                url = f"http://router.project-osrm.org/table/v1/driving/{coords}?annotations=duration"
                matrix = requests.get(url, headers={'User-Agent': 'Sales/1.0'}).json()['durations']

                # Optimasi (Nearest Neighbor)
                current_node = 0 
                unvisited = list(range(1, len(locations)))
                route_indices = [0]
                total_travel_seconds = 0
                
                while unvisited:
                    best_node = min(unvisited, key=lambda x: matrix[current_node][x])
                    total_travel_seconds += matrix[current_node][best_node]
                    route_indices.append(best_node)
                    unvisited.remove(best_node)
                    current_node = best_node
                
                route_indices.append(0)

                # Tabel Hasil
                table_data = []
                for i in range(len(route_indices) - 1):
                    curr = route_indices[i]
                    next_n = route_indices[i+1]
                    dur_sec = round(matrix[curr][next_n])
                    
                    # Batching: Ambil 10 toko kedepan (termasuk dirinya sendiri)
                    end_idx = min(i + 10, len(route_indices))
                    batch_locations = [locations[route_indices[idx]] for idx in range(i, end_idx)]
                    
                    table_data.append({
                        "Checklist": False,
                        "No": i + 1,
                        "Dari": names[curr],
                        "Ke": names[next_n],
                        "Waktu (Menit)": round(dur_sec / 60, 2),
                        "Link Maps": get_gmaps_link(locations[curr][0], locations[curr][1], locations[next_n][0], locations[next_n][1]),
                        "Rute 10 toko kedepan": get_batch_gmaps_link(batch_locations)
                    })

                st.data_editor(
                    pd.DataFrame(table_data),
                    column_config={
                        "Checklist": st.column_config.CheckboxColumn("Checklist", default=False),
                        "Link Maps": st.column_config.LinkColumn("Navigasi", display_text="📍 Navigasi"),
                        "Rute 10 toko kedepan": st.column_config.LinkColumn("Batch", display_text="🚀 Lihat Rute 10 Toko")
                    },
                    use_container_width=True,
                    hide_index=True
                )
