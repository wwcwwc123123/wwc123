import streamlit as st
import pandas as pd
import plotly.express as px
import time
import json
from datetime import datetime
import pyproj
import folium
from folium.plugins import Draw
from streamlit_folium import st_folium
import math

# ====================== GCJ02 / WGS84 坐标转换 ======================
PI = 3.1415926535897932384626
EE = 0.006693421622965943
A = 6378245.0

def wgs84_to_gcj02(lng, lat):
    if out_of_china(lng, lat):
        return lng, lat
    dlat = transformlat(lng - 105.0, lat - 35.0)
    dlng = transformlng(lng - 105.0, lat - 35.0)
    radlat = lat / 180.0 * PI
    magic = math.sin(radlat)
    magic = 1 - EE * magic * magic
    sqrtmagic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((A * (1 - EE)) / (magic * sqrtmagic) * PI)
    dlng = (dlng * 180.0) / (A / sqrtmagic * math.cos(radlat) * PI)
    return lng + dlng, lat + dlat

def transformlat(lng, lat):
    ret = -100.0 + 2.0 * lng + 3.0 * lat + 0.2 * lat * lat + 0.1 * lng * lat + 0.2 * math.sqrt(math.fabs(lng))
    ret += (20.0 * math.sin(6.0 * lng * PI) + 20.0 * math.sin(2.0 * lng * PI)) * 2.0 / 3.0
    ret += (20.0 * math.sin(lat * PI) + 40.0 * math.sin(lat / 3.0 * PI)) * 2.0 / 3.0
    ret += (160.0 * math.sin(lat / 12.0 * PI) + 320 * math.sin(lat / 30.0 * PI)) * 2.0 / 3.0
    return ret

def transformlng(lng, lat):
    ret = 300.0 + lng + 2.0 * lat + 0.1 * lng * lng + 0.1 * lng * lat + 0.1 * math.sqrt(math.fabs(lng))
    ret += (20.0 * math.sin(6.0 * lng * PI) + 20.0 * math.sin(2.0 * lng * PI)) * 2.0 / 3.0
    ret += (20.0 * math.sin(lng * PI) + 40.0 * math.sin(lng / 3.0 * PI)) * 2.0 / 3.0
    ret += (150.0 * math.sin(lng / 12.0 * PI) + 300.0 * math.sin(lng / 30.0 * PI)) * 2.0 / 3.0
    return ret

def out_of_china(lng, lat):
    return not (72.004 <= lng <= 137.8347 and 0.8293 <= lat <= 55.8271)

# ====================== 页面配置 ======================
st.set_page_config(page_title="无人机监控系统", layout="wide")
st.title("🎓 校园无人机航线规划 + 飞行监控")

# ====================== 坐标转换 ======================
class CoordConverter:
    def __init__(self):
        self.wgs2utm = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:32650", always_xy=True)
        self.campus = {"lat_min": 32.231, "lat_max": 32.235, "lng_min": 118.747, "lng_max": 118.751}

    def wgs_to_utm(self, lng, lat):
        x, y = self.wgs2utm.transform(lng, lat)
        return round(x, 2), round(y, 2)

    def in_campus(self, lng, lat):
        return self.campus["lat_min"] <= lat <= self.campus["lat_max"] and self.campus["lng_min"] <= lng <= self.campus["lng_max"]

coord = CoordConverter()

# ====================== 固定AB点 ======================
A_LNG, A_LAT = 118.749, 32.2322
B_LNG, B_LAT = 118.749, 32.2343

# ====================== 状态持久化 ======================
if "obstacles" not in st.session_state:
    st.session_state.obstacles = []
if "map_data" not in st.session_state:
    st.session_state.map_data = None

# 心跳状态
if "heart_data" not in st.session_state:
    st.session_state.heart_data = []
if "last_recv" not in st.session_state:
    st.session_state.last_recv = time.time()
if "seq" not in st.session_state:
    st.session_state.seq = 1
if "running" not in st.session_state:
    st.session_state.running = False

# ====================== 双页面 ======================
tab1, tab2 = st.tabs(["🗺️ 航线规划（高德/OSM地图）", "📡 飞行监控（心跳包）"])

# ====================== 页面1：航线规划 ======================
with tab1:
    st.subheader("📍 起点 A / 终点 B")
    c1, c2 = st.columns(2)
    with c1:
        st.success(f"A 经度：{A_LNG}  纬度：{A_LAT}")
    with c2:
        st.success(f"B 经度：{B_LNG}  纬度：{B_LAT}")

    if st.button("✅ 校验坐标 & 坐标系转换"):
        if coord.in_campus(A_LNG, A_LAT) and coord.in_campus(B_LNG, B_LAT):
            st.success("✅ AB 均在校园内")
            a_gcj = wgs84_to_gcj02(A_LNG, A_LAT)
            b_gcj = wgs84_to_gcj02(B_LNG, B_LAT)
            ax, ay = coord.wgs_to_utm(A_LNG, A_LAT)
            bx, by = coord.wgs_to_utm(B_LNG, B_LAT)
            st.info(f"A GCJ02：{a_gcj[0]:.6f}, {a_gcj[1]:.6f} | UTM：{ax}, {ay}")
            st.info(f"B GCJ02：{b_gcj[0]:.6f}, {b_gcj[1]:.6f} | UTM：{bx}, {by}")
        else:
            st.error("❌ 坐标超出校园")

    st.divider()
    st.subheader("🚧 障碍物圈选 + 导出/导入 JSON")

    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("🗑️ 清空所有障碍物"):
            st.session_state.obstacles = []
            st.rerun()
    with col2:
        st.download_button(
            label="💾 一键导出障碍物为 JSON",
            data=json.dumps(st.session_state.obstacles, ensure_ascii=False, indent=2),
            file_name="obstacles.json",
            mime="application/json"
        )
    with col3:
        uploaded = st.file_uploader("📂 导入障碍物 JSON", type="json")
        if uploaded is not None:
            data = json.load(uploaded)
            st.session_state.obstacles = data
            st.success("✅ 导入成功！")
            st.rerun()

    st.markdown("👉 操作：点地图左上角**多边形图标** → 描点圈选 → 自动保存")
    st.divider()

    # 地图选择
    map_type = st.radio("选择地图", ["高德卫星地图", "OpenStreetMap"], horizontal=True)
    center = [(A_LAT + B_LAT) / 2, (A_LNG + B_LNG) / 2]

    # 创建地图
    m = folium.Map(location=center, zoom_start=19)
    if map_type == "高德卫星地图":
        folium.TileLayer(
            tiles="https://webst01.is.autonavi.com/appmaptile?style=6&x={x}&y={y}&z={z}",
            attr="高德卫星"
        ).add_to(m)
    else:
        folium.TileLayer(tiles="OpenStreetMap").add_to(m)

    # 绘图工具
    Draw(
        export=True,
        position="topleft",
        draw_options={
            "polygon": True, "polyline": False, "rectangle": False,
            "circle": False, "marker": False
        }
    ).add_to(m)

    # AB点 + 航线
    folium.Marker([A_LAT, A_LNG], icon=folium.Icon(color="red"), popup="起点A").add_to(m)
    folium.Marker([B_LAT, B_LNG], icon=folium.Icon(color="blue"), popup="终点B").add_to(m)
    folium.PolyLine([[A_LAT, A_LNG], [B_LAT, B_LNG]], color="green", weight=4).add_to(m)

    # 绘制已保存障碍物
    for p in st.session_state.obstacles:
        folium.Polygon(
            locations=p, color="red", fill=True, fill_color="red", fill_opacity=0.4
        ).add_to(m)

    # 渲染地图
    output = st_folium(m, key="main_map", width="100%", height=600, returned_objects=["all_drawings"])

    # 自动保存圈选的多边形
    if output and output.get("all_drawings"):
        for d in output["all_drawings"]:
            if d["geometry"]["type"] == "Polygon":
                coords = d["geometry"]["coordinates"][0]
                points = [[p[1], p[0]] for p in coords[:-1]]
                if points not in st.session_state.obstacles:
                    st.session_state.obstacles.append(points)
        st.rerun()

    # 显示障碍物列表
    st.subheader("✅ 已圈选障碍物")
    if st.session_state.obstacles:
        df = pd.DataFrame({
            "障碍物": [f"第{i + 1}个" for i in range(len(st.session_state.obstacles))],
            "顶点数": [len(o) for o in st.session_state.obstacles]
        })
        st.dataframe(df, use_container_width=True)
    else:
        st.info("暂无障碍物")

# ====================== 页面2：飞行监控（心跳包） ======================
with tab2:
    st.subheader("📡 无人机心跳实时监控")
    bc1, bc2 = st.columns(2)
    with bc1:
        if st.button("▶️ 启动心跳"):
            st.session_state.running = True
    with bc2:
        if st.button("⏹️ 停止心跳"):
            st.session_state.running = False
            st.session_state.heart_data = []
            st.session_state.seq = 1

    status = st.empty()
    warn = st.empty()
    chart = st.empty()
    table = st.empty()

    def add_beat():
        now = datetime.now().strftime("%H:%M:%S")
        st.session_state.heart_data.append({"序号": st.session_state.seq, "时间": now})
        st.session_state.last_recv = time.time()
        st.session_state.seq += 1

    def is_timeout():
        return time.time() - st.session_state.last_recv > 3

    if st.session_state.running:
        add_beat()
        status.success("✅ 心跳运行中")
        if is_timeout():
            warn.error("🔴 心跳超时：3 秒未接收！")
        else:
            warn.success(f"🟢 正常 | 最新序号：{st.session_state.seq - 1}")

        df = pd.DataFrame(st.session_state.heart_data)
        fig = px.line(df, x="时间", y="序号", markers=True, title="心跳时序图")
        chart.plotly_chart(fig, use_container_width=True)
        table.dataframe(df, use_container_width=True)
        time.sleep(1)
