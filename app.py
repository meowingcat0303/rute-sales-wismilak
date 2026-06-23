import streamlit as st
import pandas as pd
import requests, folium
from ortools.constraint_solver import routing_enums_pb2, pywrapcp
from streamlit.components.v1 import html

# Fungsi untuk link Google Maps
def get_gmaps_link(lat1, lon1, lat2, lon2):
    return f"https://www.google.com/maps/dir/?api=1&origin={lat1},{lon1}&destination={lat2},{lon2}&travelmode=driving"

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

uploaded_file = st.file_uploader("Upload File Excel Toko (.xlsx)", type=["xlsx"])

if uploaded_file:
    df = pd.read_excel(uploaded_file)
    locations = df[['Latitude', 'Longitude']].values.tolist()
    names = df['Outlet Name'].tolist()

    # Hitung Matriks Jarak & Waktu
    coords = ";".join([f"{lon},{lat}" for lat, lon in locations])
    url = f"http://router.project-osrm.org/table/v1/driving/{coords}?annotations=duration"
    matrix = requests.get(url, headers={'User-Agent': 'Sales/1.0'}).json()['durations']

    manager = pywrapcp.RoutingIndexManager(len(matrix), 1, 0)
    routing = pywrapcp.RoutingModel(manager)
    
    # Callback untuk menghitung waktu tempuh
    def time_callback(from_index, to_index):
        return int(matrix[manager.IndexToNode(from_index)][manager.IndexToNode(to_index)])
    
    routing.SetArcCostEvaluatorOfAllVehicles(routing.RegisterTransitCallback(time_callback))
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
        
        st.success("Rute Berhasil Dihitung!")
        col1, col2 = st.columns([1, 2])
        
        with col1:
            st.write("### Urutan Perjalanan:")
            for i in range(len(route_indices) - 1):
                curr = route_indices[i]
                next_n = route_indices[i+1]
                
                # Hitung waktu dalam menit
                duration_sec = matrix[curr][next_n]
                duration_min = round(duration_sec / 60)
                
                # Link Maps
                gmap_url = get_gmaps_link(locations[curr][0], locations[curr][1], locations[next_n][0], locations[next_n][1])
                
                st.markdown(f"""
                **{i+1}. {names[curr]}** ➔ {names[next_n]}
                *Estimasi: {duration_min} menit*
                [Buka di Google Maps]({gmap_url})
                ---
                """)
            st.write(f"**{len(route_indices)}. {names[route_indices[-1]]} (Finish)**")
        
        with col2:
            m = folium.Map(location=locations[0], zoom_start=14)
            for i in range(len(route_indices) - 1):
                start, end = locations[route_indices[i]], locations[route_indices[i+1]]
                path_coords = get_road_geometry(start[0], start[1], end[0], end[1])
                folium.PolyLine(path_coords, color="blue", weight=5).add_to(m)
                
            for i, node in enumerate(route_indices):
                folium.Marker(locations[node], popup=names[node]).add_to(m)
            html(m._repr_html_(), height=500)
