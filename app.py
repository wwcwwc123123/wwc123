import streamlit as st
import pandas as pd
import plotly.express as px
import time
from datetime import datetime
import pyproj
import folium
from streamlit_folium import st_folium

# 页面全局配置
st.set_page_config(page_title="校园无人机航线&心跳监控系统", layout="wide")
st.title("🎓 校园无人机航线规划 + 飞行心跳监控平台")

# -------------------------- 坐标系转换类 WGS84(经纬度)<->UTM平面坐标(EPSG32650) --------------------------
class CoordTransformer:
    def __init__(self):
        self.wgs2utm = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:32650", always_xy=True)
        self.utm2wgs = pyproj.Transformer.from_crs("EPSG:32650", "EPSG:4326", always_xy=True)
        # 校园范围（适配AB点位）
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

# -------------------------- 固定起点终点坐标 --------------------------
# 起点A：经度118.749，纬度32.2322
A_LON, A_LAT = 118.749, 32.2322
# 终点B：经度118.749，纬度32.2343
B_LON, B_LAT = 118.749, 32.2343
# AB中间障碍物坐标
obstacle_list = [
    {"建筑名称": "障碍物1", "经度": 118.749, "纬度": 32.2327},
    {"建筑名称": "障碍物2", "经度": 118.749, "纬度": 32.2332},
    {"建筑名称": "障碍物3", "经度": 118.749, "纬度": 32.2337}
]
obs_df = pd.DataFrame(obstacle_list)

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
tab_plan, tab_monitor = st.tabs(["🗺️ 航线规划（高德地图+AB点位+障碍物）", "📡 飞行监控（心跳包时序）"])

# ====================== 页面1：航线规划【高德地图替换原pydeck】 ======================
with tab_plan:
    st.subheader("1. 起点A & 终点B 坐标（已固定）")
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("📍 起点A坐标")
        st.success(f"经度：{A_LON}\n纬度：{A_LAT}")
    with col_b:
        st.markdown("📍 终点B坐标")
        st.success(f"经度：{B_LON}\n纬度：{B_LAT}")

    check_btn = st.button("✅ 校验坐标 + 转换坐标系 + 加载高德地图")

    if check_btn:
        a_in = coord.check_in_campus(A_LON, A_LAT)
        b_in = coord.check_in_campus(B_LON, B_LAT)
        if not a_in:
            st.error("❌ A点超出校园边界！")
        if not b_in:
            st.error("❌ B点超出校园边界！")
        if a_in and b_in:
            st.success("✅ A、B两点均在校内！")
            ax, ay = coord.lnglat_to_xy(A_LON, A_LAT)
            bx, by = coord.lnglat_to_xy(B_LON, B_LAT)
            c1, c2 = st.columns(2)
            with c1:
                st.info(f"A点平面UTM坐标 X={ax}, Y={ay} m")
            with c2:
                st.info(f"B点平面UTM坐标 X={bx}, Y={by} m")
            st.subheader("AB航线间障碍物（3个）")
            st.dataframe(obs_df, use_container_width=True)

    st.divider()
    st.subheader("2. 高德电子地图（国内路网）")
    # 地图中心点：AB中间
    center_lat = (A_LAT + B_LAT)/2
    center_lon = (A_LON + B_LON)/2

    # ========== 高德官方路网瓦片地址（无需KEY，电子地图） ==========
    amap_tile = "http://webrd02.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=7&x={x}&y={y}&z={z}"
    attr = '© <a href="https://amap.com">高德地图</a>'

    # 创建Folium高德底图
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=18,
        tiles=amap_tile,
        attr=attr
    )

    # 添加起点标记（红色）
    folium.Marker(
        location=[A_LAT, A_LON],
        popup="起点A",
        icon=folium.Icon(color="red", icon="plane-departure")
    ).add_to(m)
    # 添加终点标记（蓝色）
    folium.Marker(
        location=[B_LAT, B_LON],
        popup="终点B",
        icon=folium.Icon(color="blue", icon="plane-arrival")
    ).add_to(m)
    # 添加障碍物标记（黄色）
    for _, obs in obs_df.iterrows():
        folium.Marker(
            location=[obs["纬度"], obs["经度"]],
            popup=obs["建筑名称"],
            icon=folium.Icon(color="orange", icon="building")
        ).add_to(m)
    # AB之间连线（航线，绿色实线）
    folium.PolyLine(
        locations=[[A_LAT, A_LON], [B_LAT, B_LON]],
        color="green", weight=3, popup="规划航线AB"
    ).add_to(m)

    # streamlit渲染高德地图
    st_folium(m, width="100%", height=600, returned_objects=[])

# ====================== 页面2：飞行监控 心跳包模块（代码不变） ======================
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
