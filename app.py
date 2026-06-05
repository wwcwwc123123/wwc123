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
        self.wgs2utm = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:32650", always_xy=True)
        self.utm2wgs = pyproj.Transformer.from_crs("EPSG:32650", "EPSG:4326", always_xy=True)
        
        # 校园范围（适配你的起点终点）
        self.campus_lat_range = [32.231, 32.235]
        self.campus_lon_range = [118.747, 118.751]

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

# -------------------------- 会话缓存初始化 --------------------------
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
    st.subheader("1. 起点A & 终点B 坐标（已固定）")
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("📍 起点A坐标 **(已固定)**")
        a_lon = 118.749
        a_lat = 32.2322
        st.success(f"经度：{a_lon}")
        st.success(f"纬度：{a_lat}")

    with col_b:
        st.markdown("📍 终点B坐标 **(已固定)**")
        b_lon = 118.749
        b_lat = 32.2343
        st.success(f"经度：{b_lon}")
        st.success(f"纬度：{b_lat}")

    check_btn = st.button("✅ 校验坐标 + 转换坐标系 + 显示障碍物")
    obstacle_list = [
        {"建筑名称": "障碍物1", "经度": 118.749, "纬度": 32.2327},
        {"建筑名称": "障碍物2", "经度": 118.749, "纬度": 32.2332},
        {"建筑名称": "障碍物3", "经度": 118.749, "纬度": 32.2337}
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
            st.success("✅ A、B两点均在校内！")
            ax, ay = coord.lnglat_to_xy(a_lon, a_lat)
            bx, by = coord.lnglat_to_xy(b_lon, b_lat)
            c1, c2 = st.columns(2)
            with c1:
                st.info(f"A点平面坐标 X={ax}, Y={ay} m")
            with c2:
                st.info(f"B点平面坐标 X={bx}, Y={by} m")
            st.subheader("AB航线间障碍物（3个）")
            st.dataframe(obs_df, use_container_width=True)

    st.divider()
    st.subheader("2. 3D地图（放大自动变2D）")
    map_data = pd.DataFrame({
        "name": ["起点A", "终点B"] + obs_df["建筑名称"].tolist(),
        "lon": [a_lon, b_lon] + obs_df["经度"].tolist(),
        "lat": [a_lat, b_lat] + obs_df["纬度"].tolist(),
        "color": [[255, 0, 0], [0, 80, 255], [255, 220, 0], [255, 220, 0], [255, 220, 0]]
    })
    layer = pydeck.Layer(
        "ScatterplotLayer",
        map_data,
        get_position=["lon", "lat"],
        get_color="color",
        get_radius=12,
        pickable=True
    )
    init_view = pydeck.ViewState(
        latitude=(a_lat + b_lat)/2,
        longitude=(a_lon + b_lon)/2,
        zoom=18,
        pitch=45
    )
    deck_map = pydeck.Deck(layers=[layer], initial_view_state=init_view, map_style="light")
    st.pydeck_chart(deck_map)

# ====================== 页面2：飞行监控 心跳包模块 ======================
with tab_monitor:
    st.subheader("无人机心跳自发自收 | 1秒一次 | 3秒超时告警")
    col_ctrl1, col_ctrl2 = st.columns(2)
    with col_ctrl1:
        start_bt = st.button("▶️ 启动心跳")
    with col_ctrl2:
        stop_bt = st.button("⏹️ 停止心跳")

    info_box = st.empty()
    warn_box = st.empty()
    chart_box = st.empty()
    data_table = st.empty()

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

    def check_timeout():
        gap = time.time() - st.session_state["last_recv_time"]
        if gap > 3:
            st.session_state["is_timeout"] = True

    if start_bt:
        st.session_state["run_heart"] = True
        info_box.success("✅ 心跳已启动")

    if stop_bt:
        st.session_state["run_heart"] = False
        st.session_state["heart_data"].clear()
        st.session_state["seq_num"] = 1
        st.session_state["is_timeout"] = False
        info_box.warning("⏹️ 心跳已停止")

    if st.session_state["run_heart"]:
        add_heartbeat()
        check_timeout()
        if st.session_state["is_timeout"]:
            warn_box.error("🔴 连接超时：3秒未收到心跳！")
        else:
            warn_box.success(f"🟢 正常 | 最新心跳：{st.session_state['seq_num']-1}")
            
        df_heart = pd.DataFrame(st.session_state["heart_data"])
        fig = px.line(df_heart, x="接收时刻", y="心跳序号", markers=True, title="心跳序号变化曲线")
        chart_box.plotly_chart(fig, use_container_width=True)
        data_table.dataframe(df_heart[["心跳序号", "接收时刻"]], use_container_width=True)
        time.sleep(1)
