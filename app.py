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

# -------------------------- 坐标系转换（GCJ-02） --------------------------
PI = math.pi
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

# -------------------------- 几何工具：点在多边形内、线段相交 --------------------------
def point_in_polygon(pt, poly):
    x, y = pt
    inside = False
    for i in range(len(poly)):
        j = (i + 1) % len(poly)
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > y) != (yj > y)):
            x_intersect = (y - yi) * (xj - xi) / (yj - yi) + xi
            if x < x_intersect:
                inside = not inside
    return inside

def seg_intersect(a1, a2, b1, b2):
    def ccw(A,B,C):
        return (B[0]-A[0])*(C[1]-A[1]) - (B[1]-A[1])*(C[0]-A[0])
    A,B,C,D = a1,a2,b1,b2
    ccw1 = ccw(A,B,C)
    ccw2 = ccw(A,B,D)
    ccw3 = ccw(C,D,A)
    ccw4 = ccw(C,D,B)
    if (ccw1*ccw2 < 0) and (ccw3*ccw4 < 0):
        return True
    return False

def line_cross_poly(p1, p2, poly):
    if point_in_polygon(p1, poly) or point_in_polygon(p2, poly):
        return True
    for i in range(len(poly)):
        j = (i+1)%len(poly)
        if seg_intersect(p1,p2,poly[i],poly[j]):
            return True
    return False

# -------------------------- 膨胀多边形（安全半径） --------------------------
def inflate_polygon(poly, offset_m):
    offset = offset_m * 0.00001  # 简易经纬度偏移
    new_poly = []
    for (lat,lng) in poly:
        new_poly.append((lat+offset, lng+offset))
    return new_poly

# -------------------------- 固定AB点 --------------------------
A_LNG, A_LAT = 118.749, 32.2322
B_LNG, B_LAT = 118.749, 32.2343

# -------------------------- 状态初始化 --------------------------
if "obstacles" not in st.session_state:
    st.session_state.obstacles = []
if "obstacle_heights" not in st.session_state:
    st.session_state.obstacle_heights = []
if "drone_height" not in st.session_state:
    st.session_state.drone_height = 10
if "safe_radius" not in st.session_state:
    st.session_state.safe_radius = 5
if "route_choice" not in st.session_state:
    st.session_state.route_choice = "直线飞行"
if "map_key" not in st.session_state:
    st.session_state.map_key = "map_0"
if "heart_data" not in st.session_state:
    st.session_state.heart_data = []
if "running" not in st.session_state:
    st.session_state.running = False

# -------------------------- 核心：真正避障的航线生成 --------------------------
def generate_route(A, B, obstacles, safe_radius, mode="直线"):
    # A,B: (lat,lng)
    # obstacles: list of [(lat,lng)] polygons
    # mode: 直线/向左绕行/向右绕行/最佳航线
    if mode == "直线":
        return [A, B]

    # 膨胀障碍物（安全距离）
    inflated = [inflate_polygon(obs, safe_radius) for obs in obstacles]

    # 检查直线是否撞障
    need_avoid = False
    for poly in inflated:
        if line_cross_poly(A,B,poly):
            need_avoid = True
            break
    if not need_avoid:
        return [A,B]

    # 取第一个障碍物做绕行（多障碍可扩展）
    obs = inflated[0]
    # 计算AB中点
    mid_lat=(A[0]+B[0])/2
    mid_lng=(A[1]+B[1])/2
    # 找障碍物离中点最近的点
    closest_pt = obs[0]
    min_dist = 1e9
    for p in obs:
        d = math.hypot(p[0]-mid_lat, p[1]-mid_lng)
        if d < min_dist:
            min_dist = d
            closest_pt = p

    # 法向量偏移（左/右/最佳）
    dx = B[1]-A[1]
    dy = B[0]-A[0]
    L = math.hypot(dx, dy)
    if L == 0:
        return [A,B]
    nx = -dy / L
    ny = dx / L
    offset = safe_radius * 0.0002

    if mode == "向左绕行":
        detour = (closest_pt[0]+ny*offset, closest_pt[1]+nx*offset)
        return [A, detour, B]
    elif mode == "向右绕行":
        detour = (closest_pt[0]-ny*offset, closest_pt[1]-nx*offset)
        return [A, detour, B]
    else:  # 最佳航线：绕障碍物外侧最短
        detour1 = (closest_pt[0]+ny*offset, closest_pt[1]+nx*offset)
        detour2 = (closest_pt[0]-ny*offset, closest_pt[1]-nx*offset)
        d1 = math.hypot(A[0]-detour1[0], A[1]-detour1[1]) + math.hypot(detour1[0]-B[0], detour1[1]-B[1])
        d2 = math.hypot(A[0]-detour2[0], A[1]-detour2[1]) + math.hypot(detour2[0]-B[0], detour2[1]-B[1])
        detour = detour1 if d1 < d2 else detour2
        return [A, detour, B]

# -------------------------- 页面配置 --------------------------
st.set_page_config(page_title="无人机航线规划系统", layout="wide")
st.title("🎓 校园无人机智能航线规划 + 飞行监控")

tab1, tab2 = st.tabs(["🗺️ 航线规划（含障碍物圈选）", "📡 飞行监控（心跳包）"])

# -------------------------- 航线规划页面 --------------------------
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
        st.session_state.drone_height = st.number_input("无人机飞行高度 (米)", 1, 500, st.session_state.drone_height)
    with c2:
        st.session_state.safe_radius = st.number_input("无人机安全半径 (米)", 1, 20, st.session_state.safe_radius)

    st.divider()
    st.subheader("🚧 障碍物圈选 + 高度设置 + 导出JSON")

    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("🗑️ 清空所有障碍物"):
            st.session_state.obstacles = []
            st.session_state.obstacle_heights = []
            st.session_state.map_key = "map_" + str(time.time())
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
            st.success("✅ 导入成功！障碍物已加载到地图")
            st.session_state.map_key = "map_" + str(time.time())
            st.rerun()

    st.info("👉 操作：地图左上角点【多边形】→圈选→下方设置高度→自动更新航线")
    st.divider()

    A=(A_LAT, A_LNG)
    B=(B_LAT, B_LNG)
    obstacle_max_h = max(st.session_state.obstacle_heights) if st.session_state.obstacle_heights else 0
    need_avoid=(st.session_state.drone_height < obstacle_max_h)

    if need_avoid:
        st.error(f"⚠️ 无人机高度 {st.session_state.drone_height}m ＜ 障碍物最高 {obstacle_max_h}m → 需要绕行")
        st.session_state.route_choice = st.radio("选择绕行航线", ["向左绕行", "向右绕行", "最佳航线（推荐）"])
    else:
        st.success(f"✅ 无人机高度 {st.session_state.drone_height}m ＞ 障碍物最高 {obstacle_max_h}m → 直接飞跃")
        st.session_state.route_choice = "直线飞行"

    route_points = generate_route(A, B, st.session_state.obstacles, st.session_state.safe_radius, st.session_state.route_choice)

    # ---------- 绘制地图（动态key） ----------
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

    folium.Marker(A, icon=folium.Icon(color="red"), popup="起点A").add_to(m)
    folium.Marker(B, icon=folium.Icon(color="blue"), popup="终点B").add_to(m)

    for idx, obs in enumerate(st.session_state.obstacles):
        folium.Polygon(
            locations=obs,
            color="red", fill=True, fill_color="red", fill_opacity=0.4,
            popup=f"障碍物{idx+1} 高度：{st.session_state.obstacle_heights[idx]}m"
        ).add_to(m)

    if st.session_state.route_choice == "直线飞行":
        col = "green"
    elif st.session_state.route_choice == "向左绕行":
        col = "orange"
    elif st.session_state.route_choice == "向右绕行":
        col = "purple"
    else:
        col = "blue"
    folium.PolyLine(route_points, color=col, weight=5, popup=st.session_state.route_choice).add_to(m)

    out = st_folium(m, key=st.session_state.map_key, width="100%", height=550, returned_objects=["all_drawings"])

    if out and out.get("all_drawings"):
        new_obs = False
        for d in out["all_drawings"]:
            if d["geometry"]["type"] == "Polygon":
                coords = d["geometry"]["coordinates"][0]
                pts = [[p[1], p[0]] for p in coords[:-1]]
                if pts not in st.session_state.obstacles:
                    st.session_state.obstacles.append(pts)
                    st.session_state.obstacle_heights.append(10)
                    new_obs = True
        if new_obs:
            st.session_state.map_key = "map_" + str(time.time())
            st.rerun()

    if st.session_state.obstacles:
        st.subheader("📏 设置每个障碍物高度")
        new_heights = []
        for i in range(len(st.session_state.obstacles)):
            h = st.number_input(f"障碍物 {i+1} 高度 (m)", 1, 200, st.session_state.obstacle_heights[i])
            new_heights.append(h)
        if new_heights != st.session_state.obstacle_heights:
            st.session_state.obstacle_heights = new_heights
            st.session_state.map_key = "map_" + str(time.time())
            st.rerun()

# -------------------------- 飞行监控页面 --------------------------
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

    if st.session_state.running:
        now = datetime.now().strftime("%H:%M:%S")
        st.session_state.heart_data.append({"时间": now, "心跳": len(st.session_state.heart_data)+1})
        status.success(f"✅ 心跳正常 | 最新序号：{len(st.session_state.heart_data)}")
        df = pd.DataFrame(st.session_state.heart_data)
        fig = px.line(df, x="时间", y="心跳", markers=True, title="心跳时序图")
        chart.plotly_chart(fig, use_container_width=True)
        table.dataframe(df, use_container_width=True)
        time.sleep(1)
        st.rerun()
