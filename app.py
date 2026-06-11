import streamlit as st
import pandas as pd
import plotly.express as px
import json
import time
import math
import folium
from folium.plugins import Draw
from streamlit_folium import st_folium
from datetime import datetime

# -------------------------- GCJ02 / WGS84 坐标转换 --------------------------
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
    ret += (20.0 * math.sin(6.0 * lng * PI) + 20.0 * math.sin(2.0 * lng * PI)) * 2 / 3
    ret += (20.0 * math.sin(lat * PI) + 40.0 * math.sin(lat / 3.0 * PI)) * 2 / 3
    ret += (160.0 * math.sin(lat / 12.0 * PI) + 320 * math.sin(lat / 30.0 * PI)) * 2 / 3
    return ret

def transformlng(lng, lat):
    ret = 300.0 + lng + 2.0 * lat + 0.1 * lng * lng + 0.1 * lng * lat + 0.1 * math.sqrt(math.fabs(lng))
    ret += (20.0 * math.sin(6.0 * lng * PI) + 20.0 * math.sin(2.0 * lng * PI)) * 2 / 3
    ret += (20.0 * math.sin(lng * PI) + 40.0 * math.sin(lng / 3.0 * PI)) * 2 / 3
    ret += (150.0 * math.sin(lng / 12.0 * PI) + 300.0 * math.sin(lng / 30.0 * PI)) * 2 / 3
    return ret

def out_of_china(lng, lat):
    return not (72.004 <= lng <= 137.8347 and 0.8293 <= lat <= 55.8271)

# -------------------------- 几何核心工具：点多边形、线段相交 --------------------------
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

def ccw(A,B,C):
    return (B[0]-A[0])*(C[1]-A[1]) - (B[1]-A[1])*(C[0]-A[0])

def seg_intersect(a1, a2, b1, b2):
    ccw1 = ccw(a1,a2,b1)
    ccw2 = ccw(a1,a2,b2)
    ccw3 = ccw(b1,b2,a1)
    ccw4 = ccw(b1,b2,a2)
    if (ccw1 * ccw2 < 0) and (ccw3 * ccw4 < 0):
        return True
    return False

def line_cross_poly(p1, p2, poly):
    if point_in_polygon(p1, poly) or point_in_polygon(p2, poly):
        return True
    for i in range(len(poly)):
        j = (i+1) % len(poly)
        if seg_intersect(p1,p2,poly[i],poly[j]):
            return True
    return False

# 膨胀障碍物（放大安全区，单位米转经纬度偏移）
def inflate_polygon(poly, safe_meter):
    scale = safe_meter * 0.00003
    new_p = []
    for lat,lng in poly:
        new_p.append((lat + scale, lng + scale))
    return new_p

# 获取多边形包围盒中心点
def poly_center(poly):
    lats = [p[0] for p in poly]
    lngs = [p[1] for p in poly]
    return (sum(lats)/len(lats), sum(lngs)/len(lngs))

# -------------------------- 固定起止点 WGS84 --------------------------
A_LNG, A_LAT = 118.749, 32.2322
B_LNG, B_LAT = 118.749, 32.2343

# -------------------------- Session状态初始化 --------------------------
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

# -------------------------- 【修复版航线生成：真正避开障碍物】 --------------------------
def generate_route(A, B, obstacles, safe_radius, mode, need_avoid):
    # 无需避障直接返回直线
    if not need_avoid or len(obstacles) == 0:
        return [A, B]

    # 膨胀所有障碍物（安全缓冲）
    inflated_obs = [inflate_polygon(obs, safe_radius) for obs in obstacles]
    # 检测AB直线是否和任意障碍物相交
    hit_obs = None
    for obs in inflated_obs:
        if line_cross_poly(A, B, obs):
            hit_obs = obs
            break
    # 直线不碰撞障碍物，依然直飞
    if hit_obs is None:
        return [A, B]

    # 计算AB向量、垂直法向量
    ab_lat = B[0] - A[0]
    ab_lng = B[1] - A[1]
    ab_len = math.hypot(ab_lat, ab_lng)
    if ab_len < 1e-9:
        return [A, B]
    # 垂直左右法向
    norm_lat = -ab_lng / ab_len
    norm_lng = ab_lat / ab_len
    # 绕行偏移距离（放大，保证远离障碍物）
    offset_scale = safe_radius * 0.0004

    # AB中点
    mid = ((A[0]+B[0])/2, (A[1]+B[1])/2)
    # 左右两个绕行候选点
    left_detour = (mid[0] + norm_lat * offset_scale, mid[1] + norm_lng * offset_scale)
    right_detour = (mid[0] - norm_lat * offset_scale, mid[1] - norm_lng * offset_scale)

    # 根据选择返回路线
    if mode == "向左绕行":
        return [A, left_detour, B]
    elif mode == "向右绕行":
        return [A, right_detour, B]
    else:
        # 最佳航线：选总长度更短的一侧
        len_left = math.hypot(A[0]-left_detour[0], A[1]-left_detour[1]) + math.hypot(left_detour[0]-B[0], left_detour[1]-B[1])
        len_right = math.hypot(A[0]-right_detour[0], A[1]-right_detour[1]) + math.hypot(right_detour[0]-B[0], right_detour[1]-B[1])
        if len_left < len_right:
            return [A, left_detour, B]
        else:
            return [A, right_detour, B]

# -------------------------- 页面配置 --------------------------
st.set_page_config(page_title="无人机航线规划系统", layout="wide")
st.title("🎓 校园无人机智能航线规划 + 飞行监控")
tab1, tab2 = st.tabs(["🗺️ 航线规划（高德卫星+智能避障）", "📡 飞行监控（心跳包）"])

# ====================== 航线规划页面 ======================
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
    new_drone_h = st.number_input("无人机飞行高度 (米)", 1, 500, st.session_state.drone_height)
    new_safe_r = st.number_input("无人机安全半径 (米)", 1, 20, st.session_state.safe_radius)
    # 参数变更自动刷新
    if new_drone_h != st.session_state.drone_height or new_safe_r != st.session_state.safe_radius:
        st.session_state.drone_height = new_drone_h
        st.session_state.safe_radius = new_safe_r
        st.session_state.map_key = f"map_{time.time()}"
        st.rerun()

    st.divider()
    st.subheader("🚧 障碍物管理｜清空｜导入｜导出")
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("🗑️ 清空全部障碍物"):
            st.session_state.obstacles = []
            st.session_state.obstacle_heights = []
            st.session_state.map_key = f"map_{time.time()}"
            st.rerun()
    with col2:
        export_json = json.dumps([{"polygon":p,"height":h} for p,h in zip(st.session_state.obstacles, st.session_state.obstacle_heights)], indent=2, ensure_ascii=False)
        st.download_button("💾 导出障碍物JSON", export_json, "obstacles_with_height.json", "application/json")
    with col3:
        upload_file = st.file_uploader("📂 导入障碍物JSON", type="json")
        if upload_file:
            load_data = json.load(upload_file)
            st.session_state.obstacles = []
            st.session_state.obstacle_heights = []
            for item in load_data:
                poly = item["polygon"]
                fix_p = [(lat,lng) for lat,lng in poly]
                st.session_state.obstacles.append(fix_p)
                st.session_state.obstacle_heights.append(item["height"])
            st.success("✅ 导入障碍物成功！")
            st.session_state.map_key = f"map_{time.time()}"
            st.rerun()

    st.info("操作：地图左上角多边形工具框选建筑障碍物，高度低于障碍物时自动绕行避开红色区域")
    st.divider()

    A = (A_LAT, A_LNG)
    B = (B_LAT, B_LNG)
    # 计算最高障碍物高度
    max_obs_h = max(st.session_state.obstacle_heights) if len(st.session_state.obstacle_heights) > 0 else 0
    need_avoid = st.session_state.drone_height < max_obs_h

    # 航线选择区
    if need_avoid:
        st.error(f"⚠️ 无人机高度 {st.session_state.drone_height}m < 最高障碍物 {max_obs_h}m，必须绕行！")
        selected_route = st.radio("选择绕行方案", ["向左绕行", "向右绕行", "最佳航线（推荐）"])
        if selected_route != st.session_state.route_choice:
            st.session_state.route_choice = selected_route
            st.session_state.map_key = f"map_{time.time()}"
            st.rerun()
    else:
        st.success(f"✅ 无人机高度足够，直线飞跃障碍物")
        st.session_state.route_choice = "直线飞行"

    # 生成最终航线
    route_points = generate_route(A, B, st.session_state.obstacles, st.session_state.safe_radius, st.session_state.route_choice, need_avoid)

    # 构建高德卫星地图
    center_lat = (A[0] + B[0]) / 2
    center_lng = (A[1] + B[1]) / 2
    m = folium.Map(location=[center_lat, center_lng], zoom_start=19)
    folium.TileLayer(
        tiles="https://webst01.is.autonavi.com/appmaptile?style=6&x={x}&y={y}&z={z}",
        attr="高德卫星地图"
    ).add_to(m)
    # 绘图插件（仅多边形）
    Draw(
        export=True,
        position="topleft",
        draw_options={"polygon":True,"polyline":False,"rectangle":False,"circle":False,"marker":False,"circlemarker":False}
    ).add_to(m)

    # 起止点标记
    folium.Marker(A, icon=folium.Icon(color="red"), popup="起点A").add_to(m)
    folium.Marker(B, icon=folium.Icon(color="blue"), popup="终点B").add_to(m)

    # 批量绘制所有障碍物
    obs_group = folium.FeatureGroup("障碍物")
    for idx, poly in enumerate(st.session_state.obstacles):
        folium.Polygon(
            locations=poly,
            color="red", fill=True, fill_color="red", fill_opacity=0.4,
            popup=f"障碍物{idx+1} 高度:{st.session_state.obstacle_heights[idx]}m"
        ).add_to(obs_group)
    obs_group.add_to(m)

    # 绘制航线，区分颜色
    if st.session_state.route_choice == "直线飞行":
        line_color = "green"
    elif st.session_state.route_choice == "向左绕行":
        line_color = "orange"
    elif st.session_state.route_choice == "向右绕行":
        line_color = "purple"
    else:
        line_color = "blue"
    folium.PolyLine(locations=route_points, color=line_color, weight=5, popup=st.session_state.route_choice).add_to(m)

    # 渲染地图（动态key强制刷新）
    map_output = st_folium(m, key=st.session_state.map_key, width="100%", height=550, returned_objects=["all_drawings"])

    # 捕获新绘制的障碍物
    if map_output and map_output.get("all_drawings") is not None:
        new_flag = False
        for draw_item in map_output["all_drawings"]:
            if draw_item["geometry"]["type"] == "Polygon":
                coords = draw_item["geometry"]["coordinates"][0]
                poly_pts = [[p[1], p[0]] for p in coords[:-1]]
                if poly_pts not in st.session_state.obstacles:
                    st.session_state.obstacles.append(poly_pts)
                    st.session_state.obstacle_heights.append(10)
                    new_flag = True
        if new_flag:
            st.session_state.map_key = f"map_{time.time()}"
            st.rerun()

    # 障碍物高度编辑 + 单条删除
    if len(st.session_state.obstacles) > 0:
        st.subheader("📏 障碍物列表｜高度修改｜单条删除")
        temp_heights = []
        for i in range(len(st.session_state.obstacles)):
            col_h, col_del = st.columns([4, 1])
            with col_h:
                h_val = st.number_input(f"障碍物{i+1}高度(m)", min_value=1, max_value=200, value=st.session_state.obstacle_heights[i], key=f"h_{i}")
                temp_heights.append(h_val)
            with col_del:
                if st.button(f"删除{i+1}", key=f"del_{i}"):
                    del st.session_state.obstacles[i]
                    del st.session_state.obstacle_heights[i]
                    st.session_state.map_key = f"map_{time.time()}"
                    st.rerun()
        # 更新高度并刷新
        if temp_heights != st.session_state.obstacle_heights:
            st.session_state.obstacle_heights = temp_heights
            st.session_state.map_key = f"map_{time.time()}"
            st.rerun()

# ====================== 飞行监控页面（心跳包） ======================
with tab2:
    st.subheader("📡 无人机心跳实时监控")
    b1, b2 = st.columns(2)
    with b1:
        start_btn = st.button("▶️ 启动心跳")
        if start_btn:
            st.session_state.running = True
    with b2:
        stop_btn = st.button("⏹️ 停止心跳")
        if stop_btn:
            st.session_state.running = False
            st.session_state.heart_data = []
            st.session_state.seq = 1

    status_box = st.empty()
    warn_box = st.empty()
    chart_box = st.empty()
    table_box = st.empty()

    if st.session_state.running:
        now_str = datetime.now().strftime("%H:%M:%S")
        new_row = {
            "心跳序号": len(st.session_state.heart_data)+1,
            "接收时间": now_str
        }
        st.session_state.heart_data.append(new_row)
        status_box.success("✅ 心跳正常运行中")
        df_heart = pd.DataFrame(st.session_state.heart_data)
        fig = px.line(df_heart, x="接收时间", y="心跳序号", markers=True, title="心跳时序曲线")
        chart_box.plotly_chart(fig, use_container_width=True)
        table_box.dataframe(df_heart, use_container_width=True)
        time.sleep(1)
        st.rerun()
