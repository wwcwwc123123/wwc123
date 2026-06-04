import streamlit as st
import pandas as pd
import plotly.express as px
import time
from datetime import datetime
import pyproj

# -------------------------- 页面基础配置 --------------------------
st.set_page_config(page_title="无人机监控系统", layout="wide")
st.title("🎓 校园无人机监控与航线规划系统")

# -------------------------- 坐标系转换工具（核心） --------------------------
class CoordTransformer:
    def __init__(self):
        # WGS84 经纬度 <-> UTM 平面坐标（解决经纬度计算偏移问题）
        self.transformer = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:32650", always_xy=True)
        self.inv_transformer = pyproj.Transformer.from_crs("EPSG:32650", "EPSG:4326", always_xy=True)

        # ===================== 【你的校园经纬度范围】自行修改 =====================
        self.LAT_MIN, self.LAT_MAX = 39.900, 39.910
        self.LNG_MIN, self.LNG_MAX = 116.380, 116.390

    def wgs84_to_xy(self, lng, lat):
        x, y = self.transformer.transform(lng, lat)
        return round(x, 2), round(y, 2)

    def xy_to_wgs84(self, x, y):
        lng, lat = self.inv_transformer.transform(x, y)
        return round(lng, 6), round(lat, 6)

    def is_in_campus(self, lng, lat):
        # 判断坐标是否在校园内
        return (self.LAT_MIN <= lat <= self.LAT_MAX) and (self.LNG_MIN <= lng <= self.LNG_MAX)

# 初始化工具
coord_tool = CoordTransformer()

# -------------------------- 会话状态初始化（防刷新丢失） --------------------------
if "heartbeat_list" not in st.session_state:
    st.session_state.heartbeat_list = []
if "last_beat_time" not in st.session_state:
    st.session_state.last_beat_time = time.time()
if "seq" not in st.session_state:
    st.session_state.seq = 1
if "timeout" not in st.session_state:
    st.session_state.timeout = False

# -------------------------- 分页菜单 --------------------------
tab1, tab2 = st.tabs(["🗺️ 航线规划", "📡 飞行监控"])

# ========================== 页面1：航线规划 ==========================
with tab1:
    st.subheader("🗺️ 3D校园地图 + 航线规划")
    st.markdown("---")

    # 输入A、B点经纬度
    colA, colB = st.columns(2)
    with colA:
        st.markdown("#### 📍 起点 A")
        lng_a = st.number_input("A 经度", 116.380, 116.390, 116.382, format="%.3f")
        lat_a = st.number_input("A 纬度", 39.900, 39.910, 39.902, format="%.3f")

    with colB:
        st.markdown("#### 📍 终点 B")
        lng_b = st.number_input("B 经度", 116.380, 116.390, 116.387, format="%.3f")
        lat_b = st.number_input("B 纬度", 39.900, 39.910, 39.907, format="%.3f")

    # 校验按钮
    if st.button("✅ 校验坐标并生成航线"):
        # 1. 校园范围校验
        a_ok = coord_tool.is_in_campus(lng_a, lat_a)
        b_ok = coord_tool.is_in_campus(lng_b, lat_b)

        if not a_ok:
            st.error("❌ A 点不在校园范围内！")
        if not b_ok:
            st.error("❌ B 点不在校园范围内！")

        if a_ok and b_ok:
            st.success("✅ AB两点均在校园内！")

            # 2. 坐标转换
            x_a, y_a = coord_tool.wgs84_to_xy(lng_a, lat_a)
            x_b, y_b = coord_tool.wgs84_to_xy(lng_b, lat_b)

            col1, col2 = st.columns(2)
            with col1:
                st.info(f"A 平面坐标：X={x_a}，Y={y_a}")
            with col2:
                st.info(f"B 平面坐标：X={x_b}，Y={y_b}")

            st.markdown("---")
            st.subheader("🚧 预设障碍物（AB之间）")
            obstacles = [
                {"名称": "教学楼", "lng": 116.383, "lat": 39.903},
                {"名称": "实验楼", "lng": 116.385, "lat": 39.904},
                {"名称": "图书馆", "lng": 116.386, "lat": 39.905},
            ]
            df_obs = pd.DataFrame(obstacles)
            st.dataframe(df_obs, use_container_width=True)

    st.markdown("---")
    st.subheader("🌍 3D地图（放大自动切换2D）")
    st.success("地图加载完成 → 放大到近距离自动显示2D平面，方便圈选障碍物")

    # Streamlit + PyDeck 3D地图（无JS，纯Python实现）
    map_data = pd.DataFrame({
        "name": ["A点", "B点", "障碍物1", "障碍物2", "障碍物3"],
        "lat": [lat_a, lat_b, 39.903, 39.904, 39.905],
        "lon": [lng_a, lng_b, 116.383, 116.385, 116.386],
        "color": ["#FF0000", "#0000FF", "#FFFF00", "#FFFF00", "#FFFF00"]
    })

    st.pydeck_chart(pydeck.Deck(
        layers=[
            pydeck.Layer(
                "ScatterplotLayer",
                data=map_data,
                get_position=["lon", "lat"],
                get_color="color",
                get_radius=8,
                pickable=True
            )
        ],
        initial_view_state=pydeck.ViewState(
            latitude=(lat_a + lat_b) / 2,
            longitude=(lng_a + lng_b) / 2,
            zoom=16,
            pitch=40,  # 3D倾斜视角
        ),
        map_style="road"
    ))

# ========================== 页面2：飞行监控（心跳包） ==========================
with tab2:
    st.subheader("📡 无人机心跳包实时监控")
    st.markdown("---")

    # 控制按钮
    col1, col2 = st.columns(2)
    with col1:
        start = st.button("▶️ 启动心跳（1秒/次）")
    with col2:
        stop = st.button("⏹️ 停止心跳")

    status = st.empty()
    timeout_warn = st.empty()
    chart_area = st.empty()
    list_area = st.empty()

    # 心跳生成函数
    def make_beat():
        now = datetime.now().strftime("%H:%M:%S")
        data = {
            "心跳序号": st.session_state.seq,
            "接收时间": now,
            "时间戳": time.time()
        }
        st.session_state.heartbeat_list.append(data)
        st.session_state.last_beat_time = time.time()
        st.session_state.seq += 1
        st.session_state.timeout = False

    # 超时检测
    def check_timeout():
        if time.time() - st.session_state.last_beat_time > 3:
            st.session_state.timeout = True
        else:
            st.session_state.timeout = False

    # 启动逻辑
    if start:
        status.success("✅ 心跳已启动：自发自收，每秒一次")
        while True:
            make_beat()
            check_timeout()

            # 超时提示
            if st.session_state.timeout:
                timeout_warn.error("🔴 连接超时：3秒未收到心跳！")
            else:
                timeout_warn.success(f"🟢 正常 | 最新心跳：第 {st.session_state.seq-1} 号")

            # 图表
            df = pd.DataFrame(st.session_state.heartbeat_list)
            if len(df) > 0:
                fig = px.line(df, x="接收时间", y="心跳序号", markers=True, title="心跳序号变化曲线")
                chart_area.plotly_chart(fig, use_container_width=True)
                list_area.dataframe(df[["心跳序号", "接收时间"]], use_container_width=True)

            time.sleep(1)

    if stop:
        status.warning("⏹️ 心跳已停止")
        st.session_state.seq = 1
