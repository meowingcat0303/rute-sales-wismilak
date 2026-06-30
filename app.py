import streamlit as st
import pandas as pd
import requests
from fpdf import FPDF
import io
import folium
import re
import math
import time
import random
from streamlit.components.v1 import html

# URL Master Anda
MASTER_SHEET_URL = "https://docs.google.com/spreadsheets/d/11BXZ5Wt8AvuDwI0x1taxdlnNIgd4Grc9/export?format=csv"

# Fungsi pembersihan mutlak
def clean_id(val):
    return re.sub(r'[^A-Z0-9]', '', str(val).upper())

# OPTIMASI 1: Amankan penarikan data Google Sheets di memori agar tidak membebani RAM setiap kali klik
@st.cache_data(ttl=600)
def fetch_master_data(url):
    return pd.read_csv(url)

# OPTIMASI 2: Amankan penyimpanan rute jalan agar tidak menembak API OSRM berulang-ulang untuk titik yang sama
@st.cache_data(ttl=86400)
def get_road_geometry(lat1, lon1, lat2, lon2):
    url = f"http://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}?overview=full&geometries=geojson"
    try:
        res = requests.get(url).json()
        coords = res['routes'][0]['geometry']['coordinates']
        return [[c[1], c[0]] for c in coords]
    except:
        return [[lat1, lon1], [lat2, lon2]]

# OPTIMASI 3: Amankan proses deteksi wilayah OpenStreetMap
@st.cache_data(ttl=86400)
def get_location_details(lat, lon):
    url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}&zoom=18&addressdetails=1"
    headers = {'User-Agent': 'WismilakRouteOptimizer/1.0'}
    try:
        res = requests.get(url, headers=headers, timeout=5).json()
        address = res.get('address', {})
        kecamatan = address.get('town', address.get('city_district', address.get('county', '-')))
        desa = address.get('village', address.get('suburb', address.get('neighbourhood', '-')))
        return kecamatan, desa
    except:
        return "-", "-"

def get_single_leg_link(lat1, lon1, lat2, lon2):
    return f"https://www.google.com/maps/dir/?api=1&origin={lat1},{lon1}&destination={lat2},{lon2}&travelmode=driving"

def get_batch_gmaps_link(locations_list):
    start = locations_list[0]
    waypoints = "|".join([f"{loc[0]},{loc[1]}" for loc in locations_list])
    return f"https://www.google.com/maps/dir/?api=1&origin={start[0]},{start[1]}&waypoints={waypoints}&destination={locations_list[-1][0]},{locations_list[-1][1]}&travelmode=driving"

# ============================================================
# ALGORITMA CLUSTERING (ALTERNATIF DARI GREEDY)
# ============================================================

def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(min(1, a)))

def simple_kmeans(points, k, max_iter=50):
    n = len(points)
    if n == 0:
        return []
    k = max(1, min(k, n))

    random.seed(42)
    centroids = [list(p) for p in random.sample(points, k)]
    labels = [-1] * n

    for _ in range(max_iter):
        new_labels = []
        for p in points:
            dists = [haversine_distance(p[0], p[1], c[0], c[1]) for c in centroids]
            new_labels.append(dists.index(min(dists)))

        if new_labels == labels:
            break
        labels = new_labels

        for ci in range(k):
            cluster_points = [points[i] for i in range(n) if labels[i] == ci]
            if cluster_points:
                centroids[ci] = [
                    sum(p[0] for p in cluster_points) / len(cluster_points),
                    sum(p[1] for p in cluster_points) / len(cluster_points)
                ]
    return labels

def order_clusters_by_depot_proximity(cluster_centroids, depot_lat, depot_lon):
    n = len(cluster_centroids)
    visited = [False] * n
    order = []
    current = [depot_lat, depot_lon]
    for _ in range(n):
        best_idx, best_dist = None, float('inf')
        for i in range(n):
            if not visited[i]:
                d = haversine_distance(current[0], current[1], cluster_centroids[i][0], cluster_centroids[i][1])
                if d < best_dist:
                    best_dist, best_idx = d, i
        order.append(best_idx)
        visited[best_idx] = True
        current = cluster_centroids[best_idx]
    return order

def solve_route_with_clustering(raw_locations, depot_lat, depot_lon, n_clusters=None):
    n = len(raw_locations)
    if n == 0:
        return [], []
    if n_clusters is None or n_clusters <= 0:
        n_clusters = max(1, round(n / 10))
    n_clusters = min(n_clusters, n)

    labels = simple_kmeans(raw_locations, n_clusters)
    clusters = {}
    for i, lbl in enumerate(labels):
        clusters.setdefault(lbl, []).append(i)
    cluster_ids = list(clusters.keys())

    centroids = []
    for cid in cluster_ids:
        idxs = clusters[cid]
        centroids.append([
            sum(raw_locations[i][0] for i in idxs) / len(idxs),
            sum(raw_locations[i][1] for i in idxs) / len(idxs)
        ])

    cluster_visit_order = order_clusters_by_depot_proximity(centroids, depot_lat, depot_lon)

    visit_order, leg_seconds = [], []
    current_pos = [depot_lat, depot_lon]

    for pos in cluster_visit_order:
        cid = cluster_ids[pos]
        member_idxs = clusters[cid]
        sub_points = [raw_locations[i] for i in member_idxs]

        temp_points = [current_pos] + sub_points
        coords = ";".join([f"{p[1]},{p[0]}" for p in temp_points])
        url = f"http://router.project-osrm.org/table/v1/driving/{coords}?annotations=duration,distance"
        try:
            res_data = requests.get(url, headers={'User-Agent': 'Sales/1.0'}).json()
            matrix = res_data['durations']
        except:
            matrix = [[0] * len(temp_points) for _ in temp_points]

        local_route = [0]
        unvisited_local = list(range(1, len(temp_points)))
        while unvisited_local:
            curr = local_route[-1]
            best = min(unvisited_local, key=lambda x: matrix[curr][x])
            leg_seconds.append(matrix[curr][best])
            local_route.append(best)
            unvisited_local.remove(best)

        for local_idx in local_route[1:]:
            real_idx = member_idxs[local_idx - 1]
            visit_order.append(real_idx)

        current_pos = sub_points[local_route[-1] - 1]

    try:
        back_url = f"http://router.project-osrm.org/route/v1/driving/{current_pos[1]},{current_pos[0]};{depot_lon},{depot_lat}?overview=false"
        back_data = requests.get(back_url).json()
        back_seconds = back_data['routes'][0]['duration']
    except:
        back_seconds = 0
    leg_seconds.append(back_seconds)

    return visit_order, leg_seconds

# ============================================================
# METODE INTEGRASI "CLARKE-WRIGHT DAN INSERTION HEURISTIC"
# ============================================================

def clarke_wright_savings_route(n, matrix, depot=0):
    customers = [i for i in range(n) if i != depot]
    if not customers:
        return []
    routes = {c: [c] for c in customers}
    route_of = {c: c for c in customers}

    savings = []
    for a in range(len(customers)):
        for b in range(a + 1, len(customers)):
            i, j = customers[a], customers[b]
            s = matrix[depot][i] + matrix[depot][j] - matrix[i][j]
            savings.append((s, i, j))
    savings.sort(key=lambda x: -x[0])

    for s, i, j in savings:
        ri, rj = route_of.get(i), route_of.get(j)
        if ri is None or rj is None or ri == rj:
            continue
        route_i, route_j = routes[ri], routes[rj]
        if i not in (route_i[0], route_i[-1]):
            continue
        if j not in (route_j[0], route_j[-1]):
            continue
        if route_i[0] == i:
            route_i = route_i[::-1]
        if route_j[-1] == j:
            route_j = route_j[::-1]
        merged = route_i + route_j
        routes[ri] = merged
        del routes[rj]
        for node in merged:
            route_of[node] = ri

    return list(routes.values())

def merge_segments_insertion_heuristic(segments, matrix, depot=0):
    if not segments:
        return []
    segments_sorted = sorted(segments, key=len, reverse=True)
    base = list(segments_sorted[0])

    for seg in segments_sorted[1:]:
        best_delta, best_pos, best_seg = None, None, None
        for seg_try in (seg, list(reversed(seg))):
            extended = [depot] + base + [depot]
            for pos in range(len(extended) - 1):
                a, b = extended[pos], extended[pos + 1]
                original = matrix[a][b]
                inserted = matrix[a][seg_try[0]]
                for k in range(len(seg_try) - 1):
                    inserted += matrix[seg_try[k]][seg_try[k + 1]]
                inserted += matrix[seg_try[-1]][b]
                delta = inserted - original
                if best_delta is None or delta < best_delta:
                    best_delta, best_pos, best_seg = delta, pos, seg_try
        base = base[:best_pos] + best_seg + base[best_pos:]

    return base

def solve_route_clarke_wright_insertion(n, matrix, depot=0):
    segments = clarke_wright_savings_route(n, matrix, depot=depot)
    if len(segments) <= 1:
        return segments[0] if segments else []
    return merge_segments_insertion_heuristic(segments, matrix, depot=depot)

# ============================================================
# METODE MURNI: ANGULAR SWEEP (TEORI CLOVERLEAF UNTUK MODE B)
# ============================================================

def compute_angle(lat, lon, depot_lat, depot_lon):
    """
    Menghitung sudut (angle) titik terhadap depot menggunakan atan2.
    Hasilnya berupa radian, digunakan untuk mengurutkan titik secara melingkar.
    """
    return math.atan2(lon - depot_lon, lat - depot_lat)

def solve_route_pure_angular_sweep(raw_locations, depot_lat, depot_lon):
    """
    Mengurutkan toko murni berdasarkan sapuan sudut (Angular Sweep).
    Pola ini akan menghasilkan rute melingkar seperti kelopak (Cloverleaf) 
    sesuai teori manual Salesman.
    """
    n = len(raw_locations)
    if n == 0:
        return []

    points = []
    for i in range(n):
        angle = compute_angle(raw_locations[i][0], raw_locations[i][1], depot_lat, depot_lon)
        points.append({"index": i, "angle": angle})

    # Urutkan titik berdasarkan putaran sudut
    points.sort(key=lambda x: x["angle"])

    # Susun rute: mulai dari depot (0), kunjungi titik searah putaran, kembali ke depot (0)
    route = [0] + [p["index"] + 1 for p in points] + [0]
    return route

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
    for c in cols[2:-1]:
        pdf.cell(35, 10, str(c), border=1, fill=True)
    pdf.cell(20, 10, "Maps", border=1, fill=True)
    pdf.ln()
    
    for _, row in df.iterrows():
        pdf.cell(25, 10, str(row[cols[0]]), border=1)
        pdf.cell(10, 10, str(row[cols[1]]), border=1)
        for c in cols[2:-1]:
            pdf.cell(35, 10, str(row[c])[:20], border=1)
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
    pdf.cell(25, 10, "Waktu", border=1, fill=True, align='C')
    pdf.cell(25, 10, "Maps", border=1, fill=True, align='C')
    pdf.ln()
    
    for _, row in df.iterrows():
        pdf.cell(25, 10, str(row['Kode Customer']), border=1)
        pdf.cell(10, 10, str(row['No']), border=1, align='C')
        pdf.cell(55, 10, str(row['Dari'])[:35], border=1)
        pdf.cell(55, 10, str(row['Ke'])[:35], border=1)
        pdf.cell(25, 10, f"{row['Waktu (Menit)']} Mnt", border=1, align='C')
        pdf.set_text_color(0, 0, 255)
        pdf.cell(25, 10, "Navigasi", border=1, link=row['Navigasi A->B'], align='C')
        pdf.set_text_color(0, 0, 0)
        pdf.ln()
    return pdf.output(dest='S').encode('latin-1')

# --- UI APP ---
st.set_page_config(layout="wide", page_title="Wismilak Optimizer")
st.title("📍 Wismilak Route Optimizer")
st.sidebar.subheader("Developed By Ghalib Damarillah Asahlintang (2026)")

# --- SUMBER DATA ---
source = st.sidebar.radio("Pilih Sumber Data:", ["Upload Excel", "Google Sheets Master"])
df = None

if source == "Upload Excel":
    uploaded_file = st.sidebar.file_uploader("Upload File Excel (.xlsx)", type=["xlsx"])
    if uploaded_file:
        df = pd.read_excel(uploaded_file)
else:
    try:
        df_raw = fetch_master_data(MASTER_SHEET_URL)
        df = df_raw.copy()
        st.sidebar.success("Master Data Terhubung!")
    except:
        st.sidebar.error("Gagal terhubung ke Google Sheet.")

if df is not None:
    cols = df.columns.tolist()
    kode_opt = ["Tidak Ada"] + cols
    default_kode_idx = 0
    
    for target_keyword in ['customerno', 'kode', 'code', 'customer']:
        for i, c in enumerate(cols):
            if target_keyword in c.lower():
                default_kode_idx = i + 1
                break
        if default_kode_idx != 0:
            break
            
    kode_col = st.sidebar.selectbox("Kolom Kode Toko:", kode_opt, index=default_kode_idx)
    name_col = st.sidebar.selectbox("Kolom Nama:", cols, index=cols.index([c for c in cols if 'nama' in c.lower() or 'toko' in c.lower()][0] if any('nama' in c.lower() or 'toko' in c.lower() for c in cols) else cols[0]))
    lat_col = st.sidebar.selectbox("Kolom Lat:", cols, index=cols.index([c for c in cols if 'lat' in c.lower()][0] if any('lat' in c.lower() for c in cols) else cols[1] if len(cols)>1 else cols[0]))
    lon_col = st.sidebar.selectbox("Kolom Long:", cols, index=cols.index([c for c in cols if 'long' in c.lower() or 'lng' in c.lower()][0] if any('long' in c.lower() or 'lng' in c.lower() for c in cols) else cols[2] if len(cols)>2 else cols[0]))

    df[lat_col] = pd.to_numeric(df[lat_col].astype(str).str.replace(',', '.'), errors='coerce')
    df[lon_col] = pd.to_numeric(df[lon_col].astype(str).str.replace(',', '.'), errors='coerce')
    
    if kode_col != "Tidak Ada":
        df[kode_col] = df[kode_col].astype(str).apply(lambda x: x[:-2] if x.endswith('.0') else x).str.strip().str.upper()
    
    df = df.dropna(subset=[lat_col, lon_col])

    tab1, tab2, tab3, tab4 = st.tabs(["📂 Mode A: Generate Data", "🚀 Mode B: Optimasi Rute", "🗺️ Mode C: Sort Wilayah", "📅 Mode D: Jadwal Mingguan"])

    with tab1:
        has_kode = kode_col != "Tidak Ada"
        if source == "Google Sheets Master":
            st.subheader("🔍 Generate Link Google Maps")
            if has_kode:
                input_codes = st.text_area("Input urutan kode toko di sini:")
                if st.button("Generate Link"):
                    raw_list = [clean_id(x) for x in input_codes.split('\n') if clean_id(x) != ""]
                    master_indexed = df.set_index(kode_col)
                    valid_kodes = [k for k in raw_list if k in master_indexed.index]
                    if valid_kodes:
                        filtered_df = master_indexed.loc[valid_kodes].reset_index()
                        filtered_df = filtered_df.rename(columns={'index': kode_col})
                        filtered_df = filtered_df[[kode_col, name_col, lat_col, lon_col]].copy()
                        filtered_df['Link Maps'] = filtered_df.apply(lambda row: f"https://www.google.com/maps/dir/?api=1&destination={row[lat_col]},{row[lon_col]}", axis=1)
                        filtered_df.insert(0, "No", range(1, 1 + len(filtered_df)))
                        filtered_df = filtered_df[[kode_col, 'No', name_col, lat_col, lon_col, 'Link Maps']]
                        
                        st.data_editor(filtered_df, column_config={"Link Maps": st.column_config.LinkColumn("Buka", display_text="📍 Navigasi")}, width='stretch', hide_index=True)
                        
                        c3, c4 = st.columns(2)
                        c3.download_button("📥 Download PDF", generate_pdf(filtered_df), "Rute_Sales_Copas.pdf", "application/pdf")
                        excel_buffer_f = io.BytesIO()
                        with pd.ExcelWriter(excel_buffer_f, engine='xlsxwriter') as writer:
                            filtered_df.to_excel(writer, index=False)
                        c4.download_button("📥 Download Excel", excel_buffer_f.getvalue(), "Rute_Sales_Copas.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                        
                        st.markdown("### 🗺️ Visualisasi Rute")
                        with st.spinner('Menggambar rute...'):
                            depot_lat, depot_lon = -6.509198, 106.757705
                            locs_a = [[depot_lat, depot_lon]] + [[row[lat_col], row[lon_col]] for _, row in filtered_df.iterrows()]
                            nms_a = ["Kantor Area Bogor"] + [row[name_col] for _, row in filtered_df.iterrows()]
                            m_copas = folium.Map(location=locs_a[0], zoom_start=14)
                            for i in range(len(locs_a) - 1):
                                path = get_road_geometry(locs_a[i][0], locs_a[i][1], locs_a[i+1][0], locs_a[i+1][1])
                                folium.PolyLine(path, color="blue", weight=5).add_to(m_copas)
                            for i, loc in enumerate(locs_a):
                                folium.Marker(loc, popup=nms_a[i]).add_to(m_copas)
                            html(m_copas._repr_html_(), height=400)
        else:
            cols_to_use = [kode_col, name_col, lat_col, lon_col] if has_kode else [name_col, lat_col, lon_col]
            df_display = df[cols_to_use].copy()
            if not df_display.empty:
                df_display['Link Maps'] = df_display.apply(lambda row: f"https://www.google.com/maps/dir/?api=1&destination={row[lat_col]},{row[lon_col]}", axis=1)
                df_display.insert(0, "No", range(1, 1 + len(df_display)))
                if has_kode:
                    df_display = df_display[[kode_col, 'No'] + [c for c in df_display.columns if c not in ['No', kode_col]]]
                st.data_editor(df_display, column_config={"Link Maps": st.column_config.LinkColumn("Buka", display_text="📍 Navigasi")}, width='stretch', hide_index=True)

    with tab2:
        st.subheader("Mode B: Optimasi Rute")
        st.caption("Metode: Murni Angular Sweep (Cloverleaf). Rute disusun secara melingkar berdasarkan sapuan sudut dari kantor, sangat ringan dan sesuai dengan pola manual Salesman.")

        if st.button("Jalankan Optimasi"):
            with st.spinner('Menghitung Rute Realistis...'):
                clean_df = df.drop_duplicates(subset=[lat_col, lon_col])
                has_kode_b = kode_col != "Tidak Ada"
                cols_b = ([kode_col] if has_kode_b else []) + [name_col, lat_col, lon_col]
                data_combined = clean_df[cols_b].to_dict('records')
                data_combined.sort(key=lambda x: (x[lat_col], x[lon_col]))
                
                depot_lat, depot_lon = -6.509198, 106.757705
                locations = [[depot_lat, depot_lon]] + [[x[lat_col], x[lon_col]] for x in data_combined]
                names = ["Kantor Area Bogor"] + [x[name_col] for x in data_combined]
                codes = ["-"] + [(x[kode_col] if has_kode_b else "-") for x in data_combined]

                # ====================================================
                # METODE: MURNI ANGULAR SWEEP
                # ====================================================
                coords = ";".join([f"{loc[1]},{loc[0]}" for loc in locations])
                url = f"http://router.project-osrm.org/table/v1/driving/{coords}?annotations=duration,distance"
                data = requests.get(url, headers={'User-Agent': 'Sales/1.0'}).json()
                matrix = data['durations']

                raw_locations_b = locations[1:]
                
                route_indices = solve_route_pure_angular_sweep(raw_locations_b, depot_lat, depot_lon)
                
                total_seconds = sum(matrix[route_indices[i]][route_indices[i+1]] for i in range(len(route_indices) - 1))

                table_data = []
                for i in range(len(route_indices) - 1):
                    curr, next_n = route_indices[i], route_indices[i+1]
                    table_data.append({
                        "Checklist": False, "Kode Customer": codes[next_n], "No": i + 1, "Dari": names[curr], "Ke": names[next_n],
                        "Waktu (Menit)": round(matrix[curr][next_n] / 60, 2),
                        "Navigasi A->B": get_single_leg_link(locations[curr][0], locations[curr][1], locations[next_n][0], locations[next_n][1]),
                        "Rute 10 toko kedepan": get_batch_gmaps_link([locations[route_indices[idx]] for idx in range(i, min(i+10, len(route_indices)))])
                    })
                df_mode_b = pd.DataFrame(table_data)

                st.data_editor(df_mode_b, column_config={"Navigasi A->B": st.column_config.LinkColumn("Navigasi", display_text="🗺️ Cek Rute"), "Rute 10 toko kedepan": st.column_config.LinkColumn("Batch", display_text="🚀 Lihat Rute")}, width='stretch', hide_index=True)
                st.metric("Total Waktu", f"{int(total_seconds//3600)} Jam {int((total_seconds%3600)//60)} Menit")
                
                c1, c2 = st.columns(2)
                c1.download_button("📥 Download PDF (Rute Optimal)", generate_pdf_b(df_mode_b), "Rute_Optimasi.pdf", "application/pdf")
                excel_buffer_b = io.BytesIO()
                with pd.ExcelWriter(excel_buffer_b, engine='xlsxwriter') as writer:
                    df_mode_b.to_excel(writer, index=False)
                c2.download_button("📥 Download Excel (Rute Optimal)", excel_buffer_b.getvalue(), "Rute_Optimasi.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

                m_b = folium.Map(location=locations[0], zoom_start=15)
                for i in range(len(route_indices) - 1):
                    path = get_road_geometry(locations[route_indices[i]][0], locations[route_indices[i]][1], locations[route_indices[i+1]][0], locations[route_indices[i+1]][1])
                    folium.PolyLine(path, color="blue", weight=5).add_to(m_b)
                for i, node in enumerate(route_indices):
                    folium.Marker(locations[node], popup=names[node]).add_to(m_b)
                html(m_b._repr_html_(), height=400)

    with tab3:
        st.subheader("🗺️ Mode C: Sort Wilayah (Desa/Kecamatan)")
        if st.button("Mulai Deteksi Wilayah"):
            df_wilayah = df.copy()
            my_bar = st.progress(0, text="Memproses...")
            kec_list, desa_list = [], []
            total_data = len(df_wilayah)
            for i, row in enumerate(df_wilayah.iterrows()):
                kec, desa = get_location_details(row[1][lat_col], row[1][lon_col])
                kec_list.append(kec); desa_list.append(desa)
                my_bar.progress(int(((i + 1) / total_data) * 100))
                time.sleep(0.1)
            df_wilayah['Kecamatan'] = kec_list; df_wilayah['Desa/Kelurahan'] = desa_list
            my_bar.empty()
            st.success("Selesai!")
            st.dataframe(df_wilayah, width='stretch')
            excel_buffer_wilayah = io.BytesIO()
            with pd.ExcelWriter(excel_buffer_wilayah, engine='xlsxwriter') as writer:
                df_wilayah.to_excel(writer, index=False)
            st.download_button("📥 Download Excel", excel_buffer_wilayah.getvalue(), "Database_Wilayah.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    with tab4:
        st.subheader("📅 Mode D: Jadwal Rute Mingguan Otomatis")

        # ============================================================
        # PILIHAN ASUMSI ALGORITMA
        # ============================================================
        algo_mode_d = st.radio(
            "🧠 Pilih Asumsi Algoritma Rute Harian:",
            ["Greedy (Default - Titik Terdekat)", "Clustering (Kelompokkan Wilayah Dulu)", "Integrasi Clarke-Wright dan Insertion Heuristic"],
            horizontal=True,
            key="algo_choice_mode_d",
            help="Greedy: rute tiap hari dihitung murni titik terdekat berikutnya. Clustering: toko dalam satu hari dikelompokkan per wilayah kecil dulu, kurir menyelesaikan satu wilayah sebelum pindah, agar tidak 'melompat' antar gang. Integrasi Clarke-Wright & Insertion Heuristic: rute harian dibangun dari penghematan waktu tempuh terbesar antar titik, lalu sisa potongan rute disatukan di posisi termurah."
        )
        n_cluster_input_d = None
        if algo_mode_d.startswith("Clustering"):
            n_cluster_input_d = st.number_input(
                "Jumlah Kelompok Wilayah per Hari (Cluster):", min_value=0, value=0, step=1,
                help="Isi 0 untuk otomatis (kira-kira 1 cluster per 8 toko per hari)."
            )
        elif algo_mode_d.startswith("Integrasi"):
            st.caption("Metode Integrasi Clarke-Wright & Insertion Heuristic: rute tiap hari dibangun dari penghematan waktu tempuh terbesar antar titik, lalu sisa potongan rute disatukan di posisi termurah. Tidak perlu mengatur jumlah cluster.")

        s = [st.number_input(h, min_value=0, value=40) for h in ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu"]]
        if st.button("Generate Jadwal Mingguan"):
            clean_df = df.drop_duplicates(subset=[lat_col, lon_col])
            data = clean_df.to_dict('records')
            clat, clon = clean_df[lat_col].mean(), clean_df[lon_col].mean()
            for r in data: r['angle'] = math.atan2(r[lat_col] - clat, r[lon_col] - clon)
            data.sort(key=lambda x: x['angle'])
            idx = 0
            jadwal_final = {}
            for i, hari in enumerate(["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu"]):
                chunk = data[idx : idx + s[i]]; idx += s[i]
                if not chunk: continue
                
                depot_lat, depot_lon = -6.509198, 106.757705
                locations = [[depot_lat, depot_lon]] + [[x[lat_col], x[lon_col]] for x in chunk]
                names = ["Kantor Area Bogor"] + [x[name_col] for x in chunk]
                codes = ["-"] + [str(x[kode_col]) if kode_col != "Tidak Ada" else "-" for x in chunk]

                if algo_mode_d.startswith("Greedy"):
                    # ====================================================
                    # GREEDY NEAREST NEIGHBOR
                    # ====================================================
                    coords = ";".join([f"{loc[1]},{loc[0]}" for loc in locations])
                    url = f"http://router.project-osrm.org/table/v1/driving/{coords}?annotations=duration,distance"
                    try:
                        res_data = requests.get(url, headers={'User-Agent': 'Sales/1.0'}).json()
                        matrix = res_data['durations']
                        route_indices, total_seconds = [0], 0
                        unvisited = list(range(1, len(locations)))
                        while unvisited:
                            curr = route_indices[-1]
                            best = min(unvisited, key=lambda x: matrix[curr][x])
                            total_seconds += matrix[curr][best]
                            route_indices.append(best)
                            unvisited.remove(best)
                        route_indices.append(0)
                        table_data = []
                        for k in range(len(route_indices) - 1):
                            curr, next_n = route_indices[k], route_indices[k+1]
                            table_data.append({
                                "Hari": hari, "Urutan": k + 1, "Kode Customer": codes[next_n], "Toko": names[next_n],
                                "Waktu (Menit)": round(matrix[curr][next_n] / 60, 2), "Navigasi A->B": get_single_leg_link(locations[curr][0], locations[curr][1], locations[next_n][0], locations[next_n][1])
                            })
                        jadwal_final[hari] = pd.DataFrame(table_data)
                    except:
                        st.error(f"Gagal rute {hari}")
                elif algo_mode_d.startswith("Clustering"):
                    # ====================================================
                    # CLUSTERING WILAYAH DULU, BARU GREEDY
                    # ====================================================
                    try:
                        raw_locations_d = locations[1:]
                        n_cluster_d = int(n_cluster_input_d) if n_cluster_input_d else max(1, round(len(raw_locations_d) / 8))
                        visit_order_d, leg_seconds_d = solve_route_with_clustering(raw_locations_d, depot_lat, depot_lon, n_clusters=n_cluster_d)

                        table_data = []
                        prev_lat, prev_lon = depot_lat, depot_lon
                        for k, real_idx in enumerate(visit_order_d):
                            store_idx = real_idx + 1
                            cur_lat, cur_lon = locations[store_idx][0], locations[store_idx][1]
                            table_data.append({
                                "Hari": hari, "Urutan": k + 1, "Kode Customer": codes[store_idx], "Toko": names[store_idx],
                                "Waktu (Menit)": round(leg_seconds_d[k] / 60, 2),
                                "Navigasi A->B": get_single_leg_link(prev_lat, prev_lon, cur_lat, cur_lon)
                            })
                            prev_lat, prev_lon = cur_lat, cur_lon
                        jadwal_final[hari] = pd.DataFrame(table_data)
                    except:
                        st.error(f"Gagal rute {hari}")
                else:
                    # ====================================================
                    # INTEGRASI CLARKE-WRIGHT DAN INSERTION HEURISTIC
                    # ====================================================
                    try:
                        coords = ";".join([f"{loc[1]},{loc[0]}" for loc in locations])
                        url = f"http://router.project-osrm.org/table/v1/driving/{coords}?annotations=duration,distance"
                        res_data = requests.get(url, headers={'User-Agent': 'Sales/1.0'}).json()
                        matrix = res_data['durations']

                        visit_order_cw_d = solve_route_clarke_wright_insertion(len(locations), matrix, depot=0)
                        route_indices = [0] + visit_order_cw_d + [0]

                        table_data = []
                        for k in range(len(route_indices) - 1):
                            curr, next_n = route_indices[k], route_indices[k+1]
                            table_data.append({
                                "Hari": hari, "Urutan": k + 1, "Kode Customer": codes[next_n], "Toko": names[next_n],
                                "Waktu (Menit)": round(matrix[curr][next_n] / 60, 2), "Navigasi A->B": get_single_leg_link(locations[curr][0], locations[curr][1], locations[next_n][0], locations[next_n][1])
                            })
                        jadwal_final[hari] = pd.DataFrame(table_data)
                    except:
                        st.error(f"Gagal rute {hari}")
            
            st.success("Jadwal Berhasil!")
            tabs_hari = st.tabs(list(jadwal_final.keys()))
            for idx, hari in enumerate(jadwal_final.keys()):
                with tabs_hari[idx]:
                    st.data_editor(jadwal_final[hari], column_config={"Navigasi A->B": st.column_config.LinkColumn("Buka", display_text="📍 Rute")}, width='stretch', hide_index=True)
