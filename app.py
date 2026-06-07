import streamlit as st
import pandas as pd
import plotly.express as px
import json
import time
import math
import pyproj
import folium
from folium.plugins import Draw
from streamlit_folium import st_folium
from datetime import datetime

# ====================== 坐标系转换 ======================
def wgs84_to_gcj02(lng, lat):
    return lng, lat

class CoordConverter:
    def __init__(self):
        self.wgs2utm = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:32650", always_xy=True)
        self.campus = {"lat_min":32.231, "lat_max":32.235, "lng_min":118.747, "lng_max":118.751}
    def wgs_to_utm(self,lng,lat):
        x,y = self.wgs2utm.transform(lng,lat)
        return round(x,2), round(y,2)
    def in_campus(self,lng,lat):
        return self.campus["lat_min"]<=lat<=self.campus["lat_max"] and self.campus["lng_min"]<=lng<=self.campus["lng_max"]

coord = CoordConverter()

# ====================== 固定AB点 ======================
A_LNG, A_LAT = 118.749, 32.2322
B_LNG, B_LAT = 118.749, 32.2343

# ====================== 状态初始化 ======================
if "obstacles" not in st.session_state:
    st.session_state.obstacles = []
if "obstacle_heights" not in st.session_state:
    st.session_state.obstacle_heights = []
if "map_draw" not in st.session_state:
    st.session_state.map_draw = None

if "heart_data" not in st.session_state:
    st.session_state.heart_data = []
if "drone_height" not in st.session_state:
    st.session_state.drone_height = 10
if "safe_radius" not in st.session_state:
    st.session_state.safe_radius = 5

# ====================== 页面 ======================
st.set_page_config(page_title="无人机航线规划系统", layout="wide")
st.title("🎓 校园无人机智能航线规划 + 飞行监控")

tab1, tab2 = st.tabs(["🗺️ 航线规划（含障碍物圈选）", "📡 飞行监控（心跳包）"])

# ====================== 航线规划 ======================
with tab1:
    st.subheader("📍 起点 A / 终点 B")
    colA, colB = st.columns(2)
    with colA:
        st.success(f"A 经度：{A_LNG}  纬度：{A_LAT}")
    with colB:
        st.success(f"B 经度：{B_LNG}  纬度：{B_LAT}")

    st.divider()
    st.subheader("⚙️ 无人机参数设置")
    c1, c2 = st.columns(2)
    with c1:
        st.session_state.drone_height = st.number_input("无人机飞行高度 (米)", 1, 500, 10)
    with c2:
        st.session_state.safe_radius = st.number_input("无人机安全半径 (米)", 1, 20, 5)

    st.divider()
    st.subheader("🚧 障碍物圈选 + 高度设置 + 导出JSON")

    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("🗑️ 清空所有障碍物"):
            st.session_state.obstacles = []
            st.session_state.obstacle_heights = []
            st.rerun()
    with col2:
        export_data = []
        for poly, h in zip(st.session_state.obstacles, st.session_state.obstacle_heights):
            export_data.append({"polygon": poly, "height": h})
        st.download_button(
            "💾 导出障碍物（含高度）为JSON",
            data=json.dumps(export_data, ensure_ascii=False, indent=2),
            file_name="obstacles_with_height.json",
            mime="application/json"
        )
    with col3:
        file = st.file_uploader("📂 导入JSON障碍物", type="json")
        if file:
            data = json.load(file)
            st.session_state.obstacles = []
            st.session_state.obstacle_heights = []
            for d in data:
                st.session_state.obstacles.append(d["polygon"])
                st.session_state.obstacle_heights.append(d["height"])
            st.success("✅ 导入成功！")
            st.rerun()

    st.info("👉 操作：地图左上角点【多边形】→圈选→下方设置高度→导出保存")
    st.divider()

    # 地图
    m = folium.Map(location=[(A_LAT+B_LAT)/2, (A_LNG+B_LNG)/2], zoom_start=19)
    folium.TileLayer(
        tiles="https://webst01.is.autonavi.com/appmaptile?style=6&x={x}&y={y}&z={z}",
        attr="高德卫星"
    ).add_to(m)

    Draw(
        export=True,
        position="topleft",
        draw_options={"polygon":True,"polyline":False,"rectangle":False,"circle":False,"marker":False}
    ).add_to(m)

    folium.Marker([A_LAT,A_LNG], icon=folium.Icon(color="red"), popup="起点A").add_to(m)
    folium.Marker([B_LAT,B_LNG], icon=folium.Icon(color="blue"), popup="终点B").add_to(m)
    folium.PolyLine([[A_LAT,A_LNG],[B_LAT,B_LNG]], color="green", weight=3).add_to(m)

    for idx, obs in enumerate(st.session_state.obstacles):
        folium.Polygon(
            locations=obs,
            color="red", fill=True, fill_color="red", fill_opacity=0.4,
            popup=f"障碍物{idx+1} 高度：{st.session_state.obstacle_heights[idx]}m"
        ).add_to(m)

    out = st_folium(m, key="map1", width="100%", height=550, returned_objects=["all_drawings"])

    if out and out.get("all_drawings"):
        for d in out["all_drawings"]:
            if d["geometry"]["type"] == "Polygon":
                coords = d["geometry"]["coordinates"][0]
                pts = [[p[1], p[0]] for p in coords[:-1]]
                if pts not in st.session_state.obstacles:
                    st.session_state.obstacles.append(pts)
                    st.session_state.obstacle_heights.append(10)
        st.rerun()

    # 障碍物高度设置
    if st.session_state.obstacles:
        st.subheader("📏 设置每个障碍物高度")
        new_heights = []
        for i in range(len(st.session_state.obstacles)):
            h = st.number_input(f"障碍物 {i+1} 高度 (m)", 1, 200, st.session_state.obstacle_heights[i])
            new_heights.append(h)
        st.session_state.obstacle_heights = new_heights

    st.divider()
    st.subheader("🛫 自动航线规划（飞跃 / 绕行）")

    need_avoid = False
    obstacle_max_h = 0
    if st.session_state.obstacle_heights:
        obstacle_max_h = max(st.session_state.obstacle_heights)
        if st.session_state.drone_height < obstacle_max_h:
            need_avoid = True

    if need_avoid:
        st.error(f"⚠️ 无人机高度 {st.session_state.drone_height}m ＜ 障碍物最高 {obstacle_max_h}m → 需要绕行")
        route_mode = st.radio("选择绕行航线", ["向左绕行", "向右绕行", "最佳航线（推荐）"])
    else:
        st.success(f"✅ 无人机高度 {st.session_state.drone_height}m ＞ 障碍物最高 {obstacle_max_h}m → 可直接飞跃")
        st.info("航线：直线 A → B")

# ====================== 飞行监控 ======================
with tab2:
    st.subheader("📡 无人机心跳实时监控")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("▶️ 启动心跳"):
            st.session_state.running = True
    with c2:
        if st.button("⏹️ 停止心跳"):
            st.session_state.running = False
            st.session_state.heart_data = []

    status = st.empty()
    chart = st.empty()
    table = st.empty()

    if "running" not in st.session_state:
        st.session_state.running = False

    if st.session_state.running:
        now = datetime.now().strftime("%H:%M:%S")
        st.session_state.heart_data.append({"时间": now, "心跳": len(st.session_state.heart_data)+1})
        status.success(f"✅ 心跳正常 | 最新序号：{len(st.session_state.heart_data)}")
        df = pd.DataFrame(st.session_state.heart_data)
        fig = px.line(df, x="时间", y="心跳", markers=True, title="心跳时序")
        chart.plotly_chart(fig, use_container_width=True)
        table.dataframe(df, use_container_width=True)
        time.sleep(1)
        st.rerun()
