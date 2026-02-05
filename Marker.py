import streamlit as st
import mysql.connector
import folium
from folium.plugins import LocateControl
from streamlit_folium import st_folium
import pandas as pd
import streamlit.components.v1 as components  # 자바스크립트용
import time
import math
from math import radians, cos, sin, asin, sqrt

# -----------------------------------------------------------------------------
# 0. 거리 계산 함수 - 하버사인 공식
# -----------------------------------------------------------------------------
def haversine(lon1, lat1, lon2, lat2):
    R = 6371  # 지구 반지름 (km)
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    return c * R # km 단위 반환

# -----------------------------------------------------------------------------
# 1. 페이지 설정
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="블루핸즈 근처 조회",
    page_icon="🚘",
    layout="wide",
    initial_sidebar_state="expanded",
)


# -----------------------------------------------------------------------------
# 2. 데이터베이스 연결 및 조회 함수
# -----------------------------------------------------------------------------
@st.cache_data(ttl=600)
def get_bluehands_data(search_text):
    results = []
    conn = None
    cursor = None
    try:
        # ⚠️ DB 정보 확인
        conn = mysql.connector.connect(
            host="localhost",
            user="root",
            password="root",
            database="bluehands_db"
        )
        cursor = conn.cursor(dictionary=True)
        query = "SELECT name, latitude, longitude, address, phone FROM bluehands_db.bluehands"
        params = []
        if search_text:
            query += " WHERE name LIKE %s OR address LIKE %s"
            pattern = f"%{search_text}%"
            params = [pattern, pattern]
        cursor.execute(query, params)
        results = cursor.fetchall()
    except Exception as e:
        st.error(f"DB Error: {e}")
        return []
    finally:
        if cursor: cursor.close()
        if conn: conn.close()
    return results


# -----------------------------------------------------------------------------
# 3. CSS 스타일
# -----------------------------------------------------------------------------
st.markdown("""
<style>
    .main-header {
        background: linear-gradient(135deg, #1e3a5f 0%, #2d5a87 50%, #3d7ab5 100%);
        padding: 2rem;
        border-radius: 20px;
        margin-bottom: 2rem;
        text-align: center;
        color: white;
    }
    .section-card {
        background: white;
        padding: 1.5rem;
        border-radius: 15px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.05);
        margin-bottom: 1rem;
    }
</style>
""", unsafe_allow_html=True)


# -----------------------------------------------------------------------------
# 4. 강제 스크롤 함수 (좌표 이동 방식)
# -----------------------------------------------------------------------------
def scroll_down():
    # 복잡하게 ID를 찾지 않고, 윈도우 스크롤을 Y축 600px 지점으로 내립니다.
    # (헤더 높이 + 검색창 높이 정도가 보통 500~600px 입니다)
    js = """
    <script>
        // 0.3초 뒤에 실행 (화면 렌더링 시간 벌기)
        setTimeout(function() {
            window.parent.scrollTo({
                top: 600, 
                behavior: 'smooth'
            });
        }, 300);
    </script>
    """
    components.html(js, height=0)


# -----------------------------------------------------------------------------
# 6. UI 구성
# -----------------------------------------------------------------------------

# [헤더]
st.markdown("""
<div class="main-header">
    <h1>🚘 내 근처 블루핸즈 찾기</h1>
    <p>검색어를 입력하면 해당 지역의 블루핸즈가 나타납니다 .</p>
</div>
""", unsafe_allow_html=True)

# [검색창]
search_query = st.text_input(
    "검색",
    placeholder="지역명 (예: 강남, 서초) 입력 후 엔터!",
    key="bluehands_search"
)

# [스크롤 트리거 체크]
if "last_search" not in st.session_state:
    st.session_state.last_search = ""

# 검색어가 변경되었을 때만 스크롤 함수 실행
if search_query and search_query != st.session_state.last_search:
    st.session_state.last_search = search_query
    scroll_down()  # 🚀 강제 스크롤 실행

# 데이터 조회
data_list = get_bluehands_data(search_query)

# [지도 섹션]
with st.container():
    st.markdown("### 📍 검색 위치 지도")

    # 지도 중심 잡기
    map_center = [37.5665, 126.9780]
    if data_list:
        first = data_list[0]
        # 좌표 데이터 확인 및 변환
        lat_val = first.get('latitude')
        lng_val = first.get('longitude')

        if lat_val and lng_val:
            try:
                map_center = [float(lat_val), float(lng_val)]
            except:
                pass

    m = folium.Map(location=map_center, zoom_start=14)
    LocateControl().add_to(m)

    fg = folium.FeatureGroup(name="검색 결과")

    if data_list:
        for row in data_list:
            r_lat = row.get('latitude')
            r_lng = row.get('longitude')

            if r_lat and r_lng:
                try:
                    lat = float(r_lat)
                    lng = float(r_lng)
                    name = row.get('name', '지점')
                    addr = row.get('address', '')
                    phone = row.get('phone', '')
                    dist = haversine(lat, lng, r_lat, r_lng)
                    if dist < 1:
                        dist_str = f"{dist * 1000}m"
                    else:
                        dist_str = f"{dist: .1f}km"

                    html = f"""
                    <div style="width:200px">
                        <b>{name}</b><br>
                        <span style="font-size:12px">{addr}</span><br>
                        <span style="color:blue;font-size:12px">{phone}</span>
                        <span style="color:red;font-size:12px">{dist_str}</span>
                    </div>
                    """

                    folium.Marker(
                        [lat, lng],
                        popup=folium.Popup(html, max_width=300),
                        tooltip=name,
                        icon=folium.Icon(color='blue', icon='car', prefix='fa')
                    ).add_to(fg)
                except:
                    continue

    fg.add_to(m)
    st_folium(m, height=500, use_container_width=True)

# [리스트 섹션]
if data_list:
    st.markdown("### 📋 목록 보기")
    df = pd.DataFrame(data_list)
    # 컬럼명 안전하게 변경
    rename_dict = {'name': '지점명', 'address': '주소', 'phone': '전화번호'}
    cols = [c for c in ['name', 'address', 'phone'] if c in df.columns]

    st.dataframe(
        df[cols].rename(columns=rename_dict),
        width=1200,
        hide_index=True
    )
else:
    st.info("검색 결과가 없습니다.")