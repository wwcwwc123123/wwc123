import streamlit as st
import pandas as pd
import plotly.express as px
import time
from datetime import datetime
import pyproj
import pydeck

# -------------------------- 页面基础配置 --------------------------
st.set_page_config(page_title="无人机监控系统", layout="wide")
st.title("🎓 校园无人机监控与航线规划系统")

# -------------------------- 坐标系转换工具 --------------------------
class CoordTransformer:
    def __init__(self):
        self.transformer = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:32650", always_xy=True)
        self.inv_transformer = pyproj.Transformer.from_crs("EPSG:32650", "EPSG:4326", always_xy=True)
        # 校园经纬度范围，按需修改
        self.LAT_MIN, self.LAT_MAX = 39.900, 39.910
        self.LNG_MIN, self.LNG_MAX = 116.380, 116.390

    def wgs84_to_xy(self, lng, lat):
        x, y = self.transformer.transform(lng, lat)
        return round(x, 2), round(y, 2)

    def xy_to_wgs84(self, x, y):
        lng, lat = self.inv_transformer.transform(x, y)
        return round(lng, 6), round(lat, 6)

    def is_in_campus(self, lng, lat):
        return (self.LAT_MIN <= lat <= self.LAT_MAX) and (self.LNG_MIN <= lng <= self.LNG_MAX)

coord_tool = CoordTransformer()

# -------------------------- 会话状态初始化 --------------------------
if "heartbeat_list" not in st.session_state:
    st.session_state.heartbeat_list = []
if "last_beat_time" not in st.session_state:
    st.session_state.last_beat_time = time.time()
if "seq" not in st.session_state:
    st.session_state.seq = 1
if "timeout" not in st.session_state:
    st.session_state.timeout = False

# 分页标签
tab1, tab2 = st.tabs(["🗺️ 航线规划", "📡 飞行监控"])

# ========== 航线规划：3D地图+AB坐标+坐标系转换 ==========
with tab1:
    st.subheader("🗺️ 3D校园地图 + 航线规划")
    st.divider()

    colA, colB = st.columns(2)
    with colA:
        st.markdown("#### 📍 起点A")
        lng_a = st.number_input("A经度", 116.380, 116.390, 116.382, format="%.3f")
        lat_a = st.number_input("A纬度", 39.900, 39.910, 39.902, format="%.3f")
    with colB:
        st.markdown("#### 📍 终点B")
        lng_b = st.number_input("B经度", 116.380, 116.390, 116.387, format="%.3f")
        lat_b = st.number_input("B纬度", 39.900, 39.910, 39.907, format="%.3f")

    if st.button("✅ 校验坐标并生成航线"):
        a_in = coord_tool.is_in_campus(lng_a, lat_a)
        b_in = coord_tool.is_in_campus(lng_b, lat_b)
        if not a_in:
            st.error("❌ A点不在校园范围！")
        if not b_in:
            st.error("❌ B点不在校园范围！")
        if a_in and b_in:
            st.success("✅ AB均在校内")
            xa, ya = coord_tool.wgs84_to_xy(lng_a, lat_a)
            xb, yb = coord_tool.wgs84_to_xy(lng_b, lat_b)
            c1,c2 = st.columns(2)
            with c1:st.info(f"A平面坐标 X:{xa},Y:{ya}")
            with c2:st.info(f"B平面坐标 X:{xb},Y:{yb}")

            st.subheader("🚧 AB间障碍物")
            obs = [
                {"名称":"教学楼","lng":116.383,"lat":39.903},
                {"名称":"实验楼","lng":116.385,"lat":39.904},
                {"名称":"图书馆","lng":116.386,"lat":39.905}
            ]
            st.dataframe(pd.DataFrame(obs), use_container_width=True)

    st.divider()
    st.subheader("🌍 3D/2D切换地图(放大变2D便于圈障碍物)")
    map_df = pd.DataFrame({
        "name":["A点","B点","教学楼","实验楼","图书馆"],
        "lon":[lng_a,lng_b,116.383,116.385,116.386],
        "lat":[lat_a,lat_b,39.903,39.904,39.905],
        "color":[[255,0,0],[0,0,255],[255,255,0],[255,255,0],[255,255,0]]
    })

    deck = pydeck.Deck(
        layers=[
            pydeck.ScatterplotLayer(
                map_df,
                get_position=["lon","lat"],
                get_color="color",
                get_radius=8,
                pickable=True
            )
        ],
        initial_view_state=pydeck.ViewState(
            latitude=(lat_a+lat_b)/2,
            longitude=(lng_a+lng_b)/2,
            zoom=16,
            pitch=45
        ),
        map_style="light"
    )
    st.pydeck_chart(deck)

# ========== 飞行监控：心跳包+折线+3s超时 ==========
with tab2:
    st.subheader("📡 无人机心跳实时监控")
    st.divider()
    c1,c2 = st.columns(2)
    with c1:start_btn = st.button("▶️启动心跳(1s/次)")
    with c2:stop_btn = st.button("⏹️停止心跳")

    status_box = st.empty()
    warn_box = st.empty()
    chart_box = st.empty()
    data_box = st.empty()

    def add_heart():
        now_str = datetime.now().strftime("%H:%M:%S")
        row = {
            "心跳序号":st.session_state.seq,
            "接收时间":now_str,
            "时间戳":time.time()
        }
        st.session_state.heartbeat_list.append(row)
        st.session_state.last_beat_time = time.time()
        st.session_state.seq +=1
        st.session_state.timeout = False

    def check_time_out():
        if time.time()-st.session_state.last_beat_time>3:
            st.session_state.timeout = True

    if start_btn:
        status_box.success("✅心跳启动，每秒自发自收")
        while True:
            add_heart()
            check_time_out()
            if st.session_state.timeout:
                warn_box.error("🔴连接超时：超过3s无心跳")
            else:
                warn_box.success(f"🟢在线，最新序号：{st.session_state.seq-1}")
            df_beat = pd.DataFrame(st.session_state.heartbeat_list)
            fig = px.line(df_beat,x="接收时间",y="心跳序号",markers=True,title="心跳序号时序")
            chart_box.plotly_chart(fig,use_container_width=True)
            data_box.dataframe(df_beat[["心跳序号","接收时间"]],use_container_width=True)
            time.sleep(1)

    if stop_btn:
        status_box.warning("⏹️心跳已停止，序号重置")
        st.session_state.seq = 1
