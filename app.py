import streamlit as st
import pandas as pd
import requests, folium
from ortools.constraint_solver import routing_enums_pb2, pywrapcp
from streamlit.components.v1 import html

# Fungsi untuk mengambil jalur jalan asli dari OSRM
def get_road_geometry(start_lat, start_lon, end_lat, end_lon):
    # Meminta geometri jalan dari API OSRM
    url = f"http://router.project-osrm.org/route/v1/driving/{start_lon},{start_lat};{end_lon},{end_lat}?overview=full&geometries=geojson"
    try:
        res = requests.get(url).json()
        coords = res['routes'][0]['geometry']['coordinates'] # OSRM return [lon, lat]
        return [[c[1], c[0]] for c in coords] # Konversi jadi [lat, lon] untuk Folium
    except:
        # Jika gagal, kembalikan garis lurus sebagai cadangan
        return [[start_lat, start_lon], [end_lat, end_lon]]

st.set_page_config(layout="wide")
st.title("📍 Wismilak Route Optimizer (developed by Ghalib Damarillah Asahlintang)")

uploaded_file = st.file_uploader("Upload File Excel Toko (.xlsx)", type=["xlsx"])

if uploaded_file:
    df = pd.read_excel(uploaded_file)
    locations = df[['Latitude', 'Longitude']].values.tolist()
    names = df['Outlet Name'].tolist()

    # Hitung Matriks Jarak
    coords = ";".join([f"{lon},{lat}" for lat, lon in locations])
    url = f"http://router.project-osrm.org/table/v1/driving/{coords}?annotations=duration"
    matrix = requests.get(url, headers={'User-Agent': 'Sales/1.0'}).json()['durations']

    # Optimasi Rute (OR-Tools)
    manager = pywrapcp.RoutingIndexManager(len(matrix), 1, 0)
    routing = pywrapcp.RoutingModel(manager)
    routing.SetArcCostEvaluatorOfAllVehicles(routing.RegisterTransitCallback(lambda i, j: int(matrix[manager.IndexToNode(i)][manager.IndexToNode(j)])))
    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    solution = routing.SolveWithParameters(params)

    if solution:
        idx = routing.Start(0)
        route_indices = []
        while not routing.IsEnd(idx):
            route_indices.append(manager.IndexToNode(idx))
            idx = solution.Value(routing.NextVar(idx))
        route_indices.append(manager.IndexToNode(idx))
        
        st.success("Rute Selesai Dihitung dengan Jalur Jalan Asli!")
        col1, col2 = st.columns([1, 2])
        
        with col1:
            st.write("### Urutan Kunjungan:")
            for i, node in enumerate(route_indices):
                st.write(f"**{i+1}. {names[node]}**")
        
        with col2:
            m = folium.Map(location=locations[0], zoom_start=15)
            
            # Menggambar jalur jalan asli
            for i in range(len(route_indices) - 1):
                start = locations[route_indices[i]]
                end = locations[route_indices[i+1]]
                
                # Panggil fungsi jalur jalan
                path_coords = get_road_geometry(start[0], start[1], end[0], end[1])
                folium.PolyLine(path_coords, color="blue", weight=5, opacity=0.8).add_to(m)
                
            # Marker
            for i, node in enumerate(route_indices):
                folium.Marker(locations[node], popup=names[node]).add_to(m)
            
            html(m._repr_html_(), height=500)
    else:
        st.error("Gagal menghitung rute.")
