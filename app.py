import streamlit as st
import pandas as pd
import plotly.express as px
import time
from datetime import datetime
import pyproj
import folium
from streamlit_folium import st_folium

# -------------------------- 页面配置 --------------------------
st.set_page_config(page_title="无人机监控系统", layout="wide")
st.title("🎓 校园无人机航线规划 + 飞行心跳监控")

# -------------------------- 坐标转换工具（WGS84 <-> UTM） --------------------------
class CoordTransformer:
    def __init__(self):
        self.wgs2utm = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:32650", always_xy=True)
        self.utm2wgs = pyproj.Transformer.from_crs("EPSG:32650", "EPSG:4326", always_xy=True)
        self.campus_lat = [32.231, 32.235]
        self.campus_lng = [118.747, 118.751]

    def to_xy(self, lng, lat):
        x, y = self.wgs2utm.transform(lng, lat)
        return round(x, 2), round(y, 2)

    def in_campus(self, lng, lat):
        return (self.campus_lat[0] <= lat <= self.campus_lat[1]) and (self.campus_lng[0] <= lng <= self.campus_lng[1])

coord = CoordTransformer()

# -------------------------- 固定AB坐标 --------------------------
A_LNG, A_LAT = 118.749, 32.2322
B_LNG, B_LAT = 118.749, 32.2343

obstacles = [
    {"名称": "障碍物1", "lng": 118.749, "lat": 32.2327},
    {"名称": "障碍物2", "lng": 118.749, "lat": 32.2332},
    {"名称": "障碍物3", "lng": 118.749, "lat": 32.2337},
]
obs_df = pd.DataFrame(obstacles)

# -------------------------- 心跳状态初始化 --------------------------
if "heartbeat" not in st.session_state:
    st.session_state.heartbeat = []
if "last_time" not in st.session_state:
    st.session_state.last_time = time.time()
if "seq" not in st.session_state:
    st.session_state.seq = 1
if "timeout" not in st.session_state:
    st.session_state.timeout = False
if "running" not in st.session_state:
    st.session_state.running = False

# -------------------------- 双页面 --------------------------
tab1, tab2 = st.tabs(["🗺️ 航线规划（3D高德地图）", "📡 飞行监控（心跳包）"])

# ====================== 页面1：航线规划 ======================
with tab1:
    st.subheader("📍 固定坐标")
    col1, col2 = st.columns(2)
    with col1:
        st.success(f"起点 A\n经度：{A_LNG}\n纬度：{A_LAT}")
    with col2:
        st.success(f"终点 B\n经度：{B_LNG}\n纬度：{B_LAT}")

    if st.button("✅ 校验坐标并转换坐标系"):
        a_ok = coord.in_campus(A_LNG, A_LAT)
        b_ok = coord.in_campus(B_LNG, B_LAT)
        if a_ok and b_ok:
            st.success("✅ AB两点均在校园内")
            ax, ay = coord.to_xy(A_LNG, A_LAT)
            bx, by = coord.to_xy(B_LNG, B_LAT)
            c1, c2 = st.columns(2)
            with c1:
                st.info(f"A 平面坐标：X={ax} Y={ay} 米")
            with c2:
                st.info(f"B 平面坐标：X={bx} Y={by} 米")
            st.subheader("🚧 AB之间障碍物")
            st.dataframe(obs_df, use_container_width=True)
        else:
            st.error("❌ 坐标超出校园范围")

    st.divider()
    st.subheader("🌍 高德3D卫星地图（放大自动变2D）")

    # 高德3D卫星地图
    m = folium.Map(
        location=[(A_LAT+B_LAT)/2, (A_LNG+B_LNG)/2],
        zoom_start=19,
        tiles="https://webst01.is.autonavi.com/appmaptile?style=6&x={x}&y={y}&z={z}",
        attr="高德地图"
    )

    # 标记A、B、障碍物
    folium.Marker([A_LAT, A_LNG], popup="起点A", icon=folium.Icon(color="red")).add_to(m)
    folium.Marker([B_LAT, B_LNG], popup="终点B", icon=folium.Icon(color="blue")).add_to(m)
    for _, o in obs_df.iterrows():
        folium.Marker([o["lat"], o["lng"]], popup=o["名称"], icon=folium.Icon(color="orange")).add_to(m)

    # 航线
    folium.PolyLine([[A_LAT, A_LNG], [B_LAT, B_LNG]], color="green", weight=4).add_to(m)
    st_folium(m, width="100%", height=600, returned_objects=[])

# ====================== 页面2：飞行监控（心跳包） ======================
with tab2:
    st.subheader("📡 心跳包实时监控（1秒1次 | 3秒超时）")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("▶️ 启动心跳"):
            st.session_state.running = True
    with c2:
        if st.button("⏹️ 停止心跳"):
            st.session_state.running = False
            st.session_state.heartbeat = []
            st.session_state.seq = 1

    status = st.empty()
    warn = st.empty()
    chart = st.empty()
    table = st.empty()

    def add_beat():
        now = datetime.now().strftime("%H:%M:%S")
        st.session_state.heartbeat.append({
            "序号": st.session_state.seq,
            "时间": now
        })
        st.session_state.last_time = time.time()
        st.session_state.seq += 1
        st.session_state.timeout = False

    def check():
        if time.time() - st.session_state.last_time > 3:
            st.session_state.timeout = True

    if st.session_state.running:
        add_beat()
        check()
        status.success("✅ 心跳运行中")
        if st.session_state.timeout:
            warn.error("🔴 连接超时：3秒未收到心跳！")
        else:
            warn.success(f"🟢 正常 | 最新序号：{st.session_state.seq-1}")

        df = pd.DataFrame(st.session_state.heartbeat)
        fig = px.line(df, x="时间", y="序号", markers=True, title="心跳序号时序图")
        chart.plotly_chart(fig, use_container_width=True)
        table.dataframe(df, use_container_width=True)
        time.sleep(1)
