import streamlit as st
import pandas as pd
import plotly.express as px
import time
from datetime import datetime
import pyproj
import folium
from streamlit_folium import st_folium
import json

# ================== 页面配置 ==================
st.set_page_config(page_title="校园无人机监控系统", layout="wide")
st.title("🎓 校园无人机航线规划 + 飞行监控平台")

# ================== 坐标转换工具（WGS84 ↔ GCJ-02 ↔ UTM） ==================
class CoordConverter:
    def __init__(self):
        self.wgs84 = "EPSG:4326"
        self.utm = "EPSG:32650"
        self.wgs2utm = pyproj.Transformer.from_crs(self.wgs84, self.utm, always_xy=True)
        self.utm2wgs = pyproj.Transformer.from_crs(self.utm, self.wgs84, always_xy=True)

        # 校园范围
        self.campus = {
            "lat_min": 32.231, "lat_max": 32.235,
            "lng_min": 118.747, "lng_max": 118.751
        }

    def wgs_to_utm(self, lng, lat):
        x, y = self.wgs2utm.transform(lng, lat)
        return round(x, 2), round(y, 2)

    def in_campus(self, lng, lat):
        return (self.campus["lat_min"] <= lat <= self.campus["lat_max"]) and \
               (self.campus["lng_min"] <= lng <= self.campus["lng_max"])

coord = CoordConverter()

# ================== 固定AB点 ==================
A_LNG, A_LAT = 118.749, 32.2322
B_LNG, B_LAT = 118.749, 32.2343

# ================== 会话状态（持久化障碍物） ==================
if "obstacles" not in st.session_state:
    st.session_state.obstacles = []  # 多边形障碍物记忆存储
if "draw_mode" not in st.session_state:
    st.session_state.draw_mode = False

# 心跳状态
if "heart_data" not in st.session_state:
    st.session_state.heart_data = []
if "last_recv" not in st.session_state:
    st.session_state.last_recv = time.time()
if "seq" not in st.session_state:
    st.session_state.seq = 1
if "timeout" not in st.session_state:
    st.session_state.timeout = False
if "running" not in st.session_state:
    st.session_state.running = False

# ================== 双页面 ==================
tab1, tab2 = st.tabs(["🗺️ 航线规划（高德卫星地图）", "📡 飞行监控（心跳包）"])

# ========================== 页面1：航线规划 ==========================
with tab1:
    st.subheader("📍 起点A & 终点B")
    colA, colB = st.columns(2)
    with colA:
        st.success(f"**起点 A**\n经度：{A_LNG}\n纬度：{A_LAT}")
    with colB:
        st.success(f"**终点 B**\n经度：{B_LNG}\n纬度：{B_LAT}")

    # 坐标校验
    if st.button("✅ 校验坐标 & 转换坐标系"):
        a_ok = coord.in_campus(A_LNG, A_LAT)
        b_ok = coord.in_campus(B_LNG, B_LAT)
        if a_ok and b_ok:
            st.success("✅ AB两点均在校园内")
            ax, ay = coord.wgs_to_utm(A_LNG, A_LAT)
            bx, by = coord.wgs_to_utm(B_LNG, B_LAT)
            c1, c2 = st.columns(2)
            with c1:
                st.info(f"A UTM 平面坐标：X={ax} Y={ay} m")
            with c2:
                st.info(f"B UTM 平面坐标：X={bx} Y={by} m")
        else:
            st.error("❌ 坐标超出校园范围")

    st.divider()

    # 障碍物圈选控制
    st.subheader("🚧 障碍物多边形圈选（带记忆）")
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("🖌️ 开启圈选模式"):
            st.session_state.draw_mode = True
    with col2:
        if st.button("✅ 完成圈选"):
            st.session_state.draw_mode = False
    with col3:
        if st.button("🗑️ 清空所有障碍物"):
            st.session_state.obstacles = []

    st.info("💡 开启圈选后，在地图上**点击多点形成多边形**，完成后点击【完成圈选】即可自动保存记忆")

    st.divider()
    st.subheader("🌍 高德卫星地图（放大自动2D）")

    # ================== 高德卫星地图 ==================
    m = folium.Map(
        location=[(A_LAT + B_LAT)/2, (A_LNG + B_LNG)/2],
        zoom_start=19,
        tiles="https://webst01.is.autonavi.com/appmaptile?style=6&x={x}&y={y}&z={z}",
        attr="高德卫星地图"
    )

    # AB点
    folium.Marker([A_LAT, A_LNG], popup="起点A", icon=folium.Icon(color="red")).add_to(m)
    folium.Marker([B_LAT, B_LNG], popup="终点B", icon=folium.Icon(color="blue")).add_to(m)

    # 航线
    folium.PolyLine(
        locations=[[A_LAT, A_LNG], [B_LAT, B_LNG]],
        color="green", weight=4, popup="规划航线"
    ).add_to(m)

    # 绘制已保存的障碍物（记忆功能）
    for idx, obs in enumerate(st.session_state.obstacles):
        try:
            folium.Polygon(
                locations=obs,
                color="red", fill_color="red", fill_opacity=0.4,
                popup=f"障碍物{idx+1}"
            ).add_to(m)
        except:
            pass

    # 圈选交互
    draw_control = False
    if st.session_state.draw_mode:
        draw_control = True

    # 渲染地图
    map_data = st_folium(
        m, width="100%", height=600,
        returned_objects=["all_drawings"],
        feature_group_to_add=folium.FeatureGroup(name="obstacle") if draw_control else None
    )

    # 自动保存圈选的多边形（记忆）
    if st.session_state.draw_mode and map_data and "all_drawings" in map_data:
        try:
            drawings = map_data["all_drawings"]
            if drawings:
                for d in drawings:
                    coords = d["geometry"]["coordinates"][0]
                    points = [[p[1], p[0]] for p in coords]
                    if points not in st.session_state.obstacles:
                        st.session_state.obstacles.append(points)
        except:
            pass

    # 显示障碍物列表
    if len(st.session_state.obstacles) > 0:
        st.subheader("✅ 已保存障碍物（刷新不丢失）")
        st.dataframe(pd.DataFrame({
            "障碍物编号": [f"第{i+1}个" for i in range(len(st.session_state.obstacles))],
            "点数": [len(o) for o in st.session_state.obstacles]
        }), use_container_width=True)

# ========================== 页面2：飞行监控（心跳包） ==========================
with tab2:
    st.subheader("📡 无人机心跳包实时监控")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("▶️ 启动心跳（1秒/次）"):
            st.session_state.running = True
    with c2:
        if st.button("⏹️ 停止心跳"):
            st.session_state.running = False
            st.session_state.heart_data = []
            st.session_state.seq = 1

    status_box = st.empty()
    warn_box = st.empty()
    chart_box = st.empty()
    table_box = st.empty()

    def add_heartbeat():
        now = datetime.now().strftime("%H:%M:%S")
        st.session_state.heart_data.append({
            "心跳序号": st.session_state.seq,
            "接收时间": now
        })
        st.session_state.last_recv = time.time()
        st.session_state.seq += 1
        st.session_state.timeout = False

    def check_timeout():
        if time.time() - st.session_state.last_recv > 3:
            st.session_state.timeout = True

    if st.session_state.running:
        add_heartbeat()
        check_timeout()
        status_box.success("✅ 心跳已启动")

        if st.session_state.timeout:
            warn_box.error("🔴 连接超时：3秒未收到心跳！")
        else:
            warn_box.success(f"🟢 正常 | 最新序号：{st.session_state.seq-1}")

        df = pd.DataFrame(st.session_state.heart_data)
        fig = px.line(df, x="接收时间", y="心跳序号", markers=True, title="心跳序号时序图")
        chart_box.plotly_chart(fig, use_container_width=True)
        table_box.dataframe(df, use_container_width=True)
        time.sleep(1)
