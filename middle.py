import os
import streamlit as st
import mysql.connector
import pandas as pd
import folium
from folium.plugins import LocateControl
from streamlit_folium import st_folium
import streamlit.components.v1 as components
from math import radians, cos, sin, asin, sqrt
from streamlit_js_eval import get_geolocation

# -----------------------------------------------------------------------------
# 1. 설정 및 옵션 정의
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="블루핸즈 찾기",
    page_icon="🚘",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 필터 옵션 -> DB 저장된 key값 사용하셔야 합니다.
FILTER_OPTIONS = {
    "is_ev": "⚡ 전기차 전담",
    "is_hydrogen": "💧 수소차 전담",
    "is_frame": "🔨 판금/차체 수리",
    "is_excellent": "🏆 우수 협력점",
    "is_n_line": "🏎️ N-Line 전담",
}
FLAG_COLS_SQL = ", ".join(FILTER_OPTIONS.keys())

######################## 개인마다 DB 비밀번호 수정하세요 #########################
DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "root",
    "database": "bluehands_db",
    "charset": "utf8mb4",
}


def get_conn():
    return mysql.connector.connect(**DB_CONFIG)


# -----------------------------------------------------------------------------
# 2. 유틸리티 함수 -> 하버사인 함수 설명은 노션에 정리해뒀습니다.
# -----------------------------------------------------------------------------

def haversine(lon1, lat1, lon2, lat2):
    if any(x is None for x in [lon1, lat1, lon2, lat2]): return None
    R = 6371
    lon1, lat1, lon2, lat2 = map(radians, [float(lon1), float(lat1), float(lon2), float(lat2)])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    c = 2 * asin(sqrt(a))
    return c * R


def scroll_down():
    js = """<script>setTimeout(function(){window.parent.scrollTo({top: 600, behavior:'smooth'});}, 300);</script>"""
    components.html(js, height=0)


def format_services_html(row):
    badges = ""
    for col, label in FILTER_OPTIONS.items():
        if row.get(col) == 1:
            badges += f'<span style="background:#e3f2fd; color:#0d47a1; padding:2px 6px; border-radius:4px; font-size:11px; margin-right:4px;">{label}</span>'
    return f'<div style="margin-top:5px;">{badges}</div>' if badges else ""


def add_markers_to_map(m, rows, user_lat=None, user_lng=None):
    fg = folium.FeatureGroup(name="검색 결과")
    for row in rows:
        try:
            lat, lng = float(row['latitude']), float(row['longitude'])
        except:
            continue

        name = row.get("name", "지점")
        addr = row.get("address", "")
        phone = row.get("phone", "")
        dist_str = "⚠️ 권한 필요"
        if user_lat and user_lng:
            d = haversine(user_lng, user_lat, lng, lat)
            if d is not None: dist_str = f"🚶 {int(d * 1000)}m" if d < 1 else f"🚗 {d:.1f}km"

        services_html = format_services_html(row)
        html = f"""
        <div style="width:240px; font-family:sans-serif;">
            <h4 style="margin:0; color:#0054a6;">{name}</h4>
            <p style="font-size:12px; margin:5px 0;">{addr}</p>
            {services_html}
            <p style="font-size:12px; margin:5px 0; color:blue;">📞 {phone}</p>
            <div style="border-top:1px solid #ddd; padding-top:5px; margin-top:5px;">
                <span style="color:red; font-weight:bold; font-size:13px;">{dist_str}</span>
            </div>
        </div>
        """
        folium.Marker([lat, lng], popup=folium.Popup(html, max_width=300), tooltip=name,
                      icon=folium.Icon(color="blue", icon="car", prefix="fa")).add_to(fg)
    fg.add_to(m)


# -----------------------------------------------------------------------------
# 3. DB 조회 함수
# -----------------------------------------------------------------------------
@st.cache_data(ttl=3600)
def get_regions():
    conn = None
    try:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM regions ORDER BY id")
        return [row[0] for row in cursor.fetchall()]
    except:
        return []
    finally:
        if conn: conn.close()


@st.cache_data(ttl=600)
def get_bluehands_data(search_text, selected_filters, region_filter):
    conn = None
    try:
        conn = get_conn()
        cursor = conn.cursor(dictionary=True)

        query = f"""
            SELECT a.id, a.name, a.latitude, a.longitude, a.address, a.phone, {FLAG_COLS_SQL}
            FROM bluehands a
            LEFT JOIN regions b ON a.region_id = b.id
        """

        conditions = []
        params = []

        if search_text:
            conditions.append("(a.name LIKE %s OR a.address LIKE %s)")
            ptn = f"%{search_text}%"
            params.extend([ptn, ptn])

        if selected_filters:
            for col in selected_filters:
                conditions.append(f"a.{col} = 1")

        if region_filter and region_filter != "(전체)":
            conditions.append("b.name = %s")
            params.append(region_filter)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        cursor.execute(query, params)
        return cursor.fetchall()

    except mysql.connector.Error as err:
        st.error(f"❌ SQL 에러: {err}")
        return []
    except Exception as e:
        st.error(f"❌ 기타 에러: {e}")
        return []
    finally:
        if conn: conn.close()


# -----------------------------------------------------------------------------
# 4. 메인 UI
# -----------------------------------------------------------------------------
st.markdown("""
<div class="main-header" style="background: linear-gradient(135deg, #1e3a5f 0%, #2d5a87 50%, #3d7ab5 100%); padding: 2rem; border-radius: 20px; margin-bottom: 2rem; text-align: center; color: white;">
    <h1>🚘 블루핸즈 통합 검색</h1>
</div>
""", unsafe_allow_html=True)

# (1) GPS 확인
loc = get_geolocation()
user_lat, user_lng = None, None
if loc and 'coords' in loc:
    user_lat, user_lng = loc['coords']['latitude'], loc['coords']['longitude']
    st.success("📍 현재 위치 확인 완료")
else:
    st.warning("⚠️ 위치 권한 대기 중... (기본값: 서울 강남)")

# (2) 사이드바 검색창(필터->검색)
with st.sidebar:
    st.header("🔍 검색 필터")

    region_list = get_regions()
    if not region_list:
        region_list = ["서울", "부산", "경기"]

    selected_region = st.selectbox("🗺️ 지역 선택 (시/도)", ["(전체)"] + region_list)
    st.write("---")
    st.info("🛠️ 서비스 옵션")
    selected_labels = st.multiselect("필요한 정비 항목", options=list(FILTER_OPTIONS.values()), default=[])
    reverse_map = {v: k for k, v in FILTER_OPTIONS.items()}
    selected_service_cols = [reverse_map[label] for label in selected_labels]

    # (3) 사이드 검색창(입력)
    col1, col2 = st.columns([4, 1])
    with col1:
        placeholder_text = f"'{selected_region}' 내 검색" if selected_region != "(전체)" else "지점명 또는 주소 검색"
        search_query = st.text_input("검색어 입력", placeholder=placeholder_text, key="main_search")

    with col2:
        st.write("")
        st.write("")
        if st.button("검색", use_container_width=True):
            if search_query: scroll_down()

# (4) 결과 조회
should_search = search_query or selected_service_cols or (selected_region != "(전체)")

if should_search:
    data_list = get_bluehands_data(search_query, selected_service_cols, selected_region)

    if not data_list:
        st.error("검색 결과가 없습니다.")
    else:
        st.subheader(f"🏢 검색 결과: {len(data_list)}개")

    # 📌 [수정됨] 기본 좌표를 강남역(37.4979, 127.0276)으로 설정
    map_center = [37.4979, 127.0276]

    if user_lat:
        map_center = [user_lat, user_lng]
    elif data_list and data_list[0].get('latitude'):
        map_center = [float(data_list[0]['latitude']), float(data_list[0]['longitude'])]

    m = folium.Map(location=map_center, zoom_start=13)
    LocateControl().add_to(m)
    if user_lat: folium.Marker([user_lat, user_lng], icon=folium.Icon(color="red", icon="user", prefix="fa")).add_to(m)
    if data_list: add_markers_to_map(m, data_list, user_lat, user_lng)

    st_folium(m, height=500, use_container_width=True)

    if data_list:
        df = pd.DataFrame(data_list)
        st.dataframe(df[["name", "address", "phone"]], use_container_width=True, hide_index=True)
else:
    st.info("👈 왼쪽 사이드바에서 지역을 선택하거나, 👆 위에서 검색어를 입력하세요.")

    # 📌 [수정됨] 초기 화면 좌표도 강남역(37.4979, 127.0276)으로 설정
    m = folium.Map(location=[37.4979, 127.0276], zoom_start=13)
    st_folium(m, height=400, use_container_width=True)