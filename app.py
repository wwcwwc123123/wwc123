import streamlit as st
import pandas as pd
import plotly.express as px
import time
from datetime import datetime
import pyproj
import pydeck

# 页面全局配置
st.set_page_config(page_title="校园无人机航线&心跳监控系统", layout="wide")
st.title("🎓 校园无人机航线规划 + 飞行心跳监控平台")

# -------------------------- 坐标系转换类 WGS84(经纬度)<->UTM平面坐标(EPSG32650) --------------------------
class CoordTransformer:
    def __init__(self):
        # WGS84经纬度 -> UTM平面直角坐标
        self.wgs2utm = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:32650", always_xy=True)
        # UTM平面 -> WGS84经纬度
        self.utm2wgs = pyproj.Transformer.from_crs("EPSG:32650", "EPSG:4326", always_xy=True)
        # 校园地理范围（可自行修改经纬度）
        self.campus_lat_range = [39.900, 39.910]
        self.campus_lon_range = [116.380, 116.390]

    # 经纬度转XY米坐标
    def lnglat_to_xy(self, lng, lat):
        x, y = self.wgs2utm.transform(lng, lat)
        return round(x, 2), round(y, 2)

    # XY米坐标转回经纬度
    def xy_to_lnglat(self, x, y):
        lon, lat = self.utm2wgs.transform(x, y)
        return round(lon, 6), round(lat, 6)

    # 判断点位是否在校园内
    def check_in_campus(self, lon, lat):
        lat_ok = self.campus_lat_range[0] <= lat <= self.campus_lat_range[1]
        lon_ok = self.campus_lon_range[0] <= lon <= self.campus_lon_range[1]
        return lat_ok and lon_ok

coord = CoordTransformer()

# -------------------------- 会话缓存初始化（心跳数据、时间、序号、超时标记） --------------------------
if "heart_data" not in st.session_state:
    st.session_state["heart_data"] = []
if "last_recv_time" not in st.session_state:
    st.session_state["last_recv_time"] = time.time()
if "seq_num" not in st.session_state:
    st.session_state["seq_num"] = 1
if "is_timeout" not in st.session_state:
    st.session_state["is_timeout"] = False
if "run_heart" not in st.session_state:
    st.session_state["run_heart"] = False

# 顶部两个标签页
tab_plan, tab_monitor = st.tabs(["🗺️ 航线规划（3D地图+AB点位+障碍物）", "📡 飞行监控（心跳包时序）"])

# ====================== 页面1：航线规划 ======================
with tab_plan:
    st.subheader("1. 输入校园A/B两点经纬度")
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("📍 起点A坐标")
        a_lon = st.number_input("A经度", min_value=116.380, max_value=116.390, value=116.382, format="%.3f")
        a_lat = st.number_input("A纬度", min_value=39.900, max_value=39.910, value=39.902, format="%.3f")
    with col_b:
        st.markdown("📍 终点B坐标")
        b_lon = st.number_input("B经度", min_value=116.380, max_value=116.390, value=116.387, format="%.3f")
        b_lat = st.number_input("B纬度", min_value=39.900, max_value=39.910, value=39.907, format="%.3f")

    check_btn = st.button("✅ 坐标校验 + 坐标系转换 + 生成航线障碍物")
    obstacle_list = [
        {"建筑名称": "一号教学楼", "经度": 116.383, "纬度": 39.903},
        {"建筑名称": "实验实训楼", "经度": 116.385, "纬度": 39.904},
        {"建筑名称": "图书馆", "经度": 116.386, "纬度": 39.905}
    ]
    obs_df = pd.DataFrame(obstacle_list)

    if check_btn:
        a_in = coord.check_in_campus(a_lon, a_lat)
        b_in = coord.check_in_campus(b_lon, b_lat)
        if not a_in:
            st.error("❌ A点超出校园边界！")
        if not b_in:
            st.error("❌ B点超出校园边界！")
        if a_in and b_in:
            st.success("✅ A、B两点均在校内")
            ax, ay = coord.lnglat_to_xy(a_lon, a_lat)
            bx, by = coord.lnglat_to_xy(b_lon, b_lat)
            c1, c2 = st.columns(2)
            with c1:
                st.info(f"A点平面UTM坐标 X={ax}, Y={ay} m")
            with c2:
                st.info(f"B点平面UTM坐标 X={bx}, Y={by} m")
            st.subheader("AB航线间预设障碍物列表")
            st.dataframe(obs_df, use_container_width=True)

    st.divider()
    st.subheader("2. 3D校园地图（滚轮放大切换2D视图，可后续圈选障碍物）")
    # 组装地图点位数据
    map_data = pd.DataFrame({
        "name": ["起点A", "终点B"] + obs_df["建筑名称"].tolist(),
        "lon": [a_lon, b_lon] + obs_df["经度"].tolist(),
        "lat": [a_lat, b_lat] + obs_df["纬度"].tolist(),
        "color": [[255, 0, 0], [0, 80, 255], [255, 220, 0], [255, 220, 0], [255, 220, 0]]
    })
    # 修复后pydeck标准写法
    layer = pydeck.Layer(
        "ScatterplotLayer",
        map_data,
        get_position=["lon", "lat"],
        get_color="color",
        get_radius=10,
        pickable=True
    )
    init_view = pydeck.ViewState(
        latitude=(a_lat + b_lat)/2,
        longitude=(a_lon + b_lon)/2,
        zoom=15.5,
        pitch=48
    )
    deck_map = pydeck.Deck(layers=[layer], initial_view_state=init_view, map_style="light")
    st.pydeck_chart(deck_map)

# ====================== 页面2：飞行监控 心跳包模块 ======================
with tab_monitor:
    st.subheader("无人机心跳自发自收监控 | 1s发包一次 | 超3s无数据=连接超时")
    col_ctrl1, col_ctrl2 = st.columns(2)
    with col_ctrl1:
        start_bt = st.button("▶️ 启动心跳模拟")
    with col_ctrl2:
        stop_bt = st.button("⏹️ 停止心跳，清空数据")

    info_box = st.empty()
    warn_box = st.empty()
    chart_box = st.empty()
    data_table = st.empty()

    # 心跳新增函数
    def add_heartbeat():
        now_time = datetime.now().strftime("%H:%M:%S")
        ts = time.time()
        new_row = {
            "心跳序号": st.session_state["seq_num"],
            "接收时刻": now_time,
            "时间戳": ts
        }
        st.session_state["heart_data"].append(new_row)
        st.session_state["last_recv_time"] = ts
        st.session_state["seq_num"] += 1
        st.session_state["is_timeout"] = False

    # 超时判断
    def check_timeout():
        gap = time.time() - st.session_state["last_recv_time"]
        if gap > 3:
            st.session_state["is_timeout"] = True

    # 启停逻辑
    if start_bt:
        st.session_state["run_heart"] = True
        info_box.success("✅ 心跳模拟器运行中，每秒生成一条心跳")

    if stop_bt:
        st.session_state["run_heart"] = False
        st.session_state["heart_data"].clear()
        st.session_state["seq_num"] = 1
        st.session_state["is_timeout"] = False
        info_box.warning("⏹️ 心跳已停止，数据已清空")

    # 循环刷新心跳
    if st.session_state["run_heart"]:
        add_heartbeat()
        check_timeout()
        # 告警展示
        if st.session_state["is_timeout"]:
            warn_box.error("🔴 告警：超过3秒未收到心跳，连接超时！")
        else:
            warn_box.success(f"🟢 链路正常 | 最新心跳序号：{st.session_state['seq_num']-1}")
        # 绘图
        df_heart = pd.DataFrame(st.session_state["heart_data"])
        fig = px.line(df_heart, x="接收时刻", y="心跳序号", markers=True, title="心跳序号随时间变化折线图")
        chart_box.plotly_chart(fig, use_container_width=True)
        data_table.dataframe(df_heart[["心跳序号", "接收时刻"]], use_container_width=True)
        time.sleep(1)
