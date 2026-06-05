import streamlit as st
import pandas as pd
import plotly.express as px
import time
from datetime import datetime
import pyproj
import folium
from streamlit_folium import st_folium

# 页面配置
st.set_page_config(page_title="校园无人机航线+心跳监控", layout="wide")
st.title("🎓 校园无人机航线规划(高德3D卫星地图)+飞行心跳监控")

# 坐标转换类 WGS84↔UTM平面
class CoordTransformer:
    def __init__(self):
        self.wgs2utm = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:32650", always_xy=True)
        self.utm2wgs = pyproj.Transformer.from_crs("EPSG:32650", "EPSG:4326", always_xy=True)
        # 校园范围
        self.campus_lat_range = [32.231, 32.235]
        self.campus_lon_range = [118.747, 118.751]

    def lnglat_to_xy(self, lng, lat):
        x, y = self.wgs2utm.transform(lng, lat)
        return round(x,2), round(y,2)

    def xy_to_lnglat(self, x, y):
        lon, lat = self.utm2wgs.transform(x, y)
        return round(lon,6), round(lat,6)

    def check_in_campus(self, lon, lat):
        lat_ok = self.campus_lat_range[0] <= lat <= self.campus_lat_range[1]
        lon_ok = self.campus_lon_range[0] <= lon <= self.campus_lon_range[1]
        return lat_ok and lon_ok

coord = CoordTransformer()

# 固定AB坐标
A_LON, A_LAT = 118.749, 32.2322
B_LON, B_LAT = 118.749, 32.2343

# 航线中间3处障碍物
obstacle_list = [
    {"建筑名称":"障碍物1","经度":118.749,"纬度":32.2327},
    {"建筑名称":"障碍物2","经度":118.749,"纬度":32.2332},
    {"建筑名称":"障碍物3","经度":118.749,"纬度":32.2337}
]
obs_df = pd.DataFrame(obstacle_list)

# session初始化
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

# 双标签页
tab_plan, tab_monitor = st.tabs(["🗺️航线规划｜高德3D卫星地图","📡飞行监控｜心跳数据"])

# ==========页面1：航线规划（高德3D卫星图）==========
with tab_plan:
    st.subheader("AB点位信息")
    c1,c2 = st.columns(2)
    with c1:
        st.success(f"起点A\n经度:{A_LON}\n纬度:{A_LAT}")
    with c2:
        st.success(f"终点B\n经度:{B_LON}\n纬度:{B_LAT}")

    check_btn = st.button("✅坐标校验+坐标系换算")
    if check_btn:
        a_in = coord.check_in_campus(A_LON,A_LAT)
        b_in = coord.check_in_campus(B_LON,B_LAT)
        if not a_in:
            st.error("A超出校园")
        if not b_in:
            st.error("B超出校园")
        if a_in and b_in:
            st.success("AB均在校内")
            ax,ay = coord.lnglat_to_xy(A_LON,A_LAT)
            bx,by = coord.lnglat_to_xy(B_LON,B_LAT)
            cc1,cc2 = st.columns(2)
            with cc1:st.info(f"A平面坐标 X:{ax},Y:{ay}m")
            with cc2:st.info(f"B平面坐标 X:{bx},Y:{by}m")
            st.dataframe(obs_df,use_container_width=True)

    st.divider()
    st.subheader("高德3D卫星地图（远景立体、放大变2D精细）")
    center_lat = (A_LAT+B_LAT)/2
    center_lon = (A_LON+B_LON)/2

    # 高德卫星瓦片(带建筑立体观感，3D效果)
    amap_sat = "https://webst01.is.autonavi.com/appmaptile?style=6&x={x}&y={y}&z={z}"
    attr = "©高德地图"
    m = folium.Map(location=[center_lat,center_lon],zoom_start=18,tiles=amap_sat,attr=attr)

    # A红色
    folium.Marker([A_LAT,A_LON],popup="起点A",icon=folium.Icon(color="red",icon="plane")).add_to(m)
    # B蓝色
    folium.Marker([B_LAT,B_LON],popup="终点B",icon=folium.Icon(color="blue",icon="flag")).add_to(m)
    # 障碍物黄色
    for _,row in obs_df.iterrows():
        folium.Marker([row["纬度"],row["经度"]],popup=row["建筑名称"],icon=folium.Icon(color="orange",icon="building")).add_to(m)
    # 绿色航线
    folium.PolyLine([[A_LAT,A_LON],[B_LAT,B_LON]],color="green",weight=3,popup="规划航线AB").add_to(m)

    st_folium(m,width="100%",height=620,returned_objects=[])

# ==========页面2：心跳监控 每秒发包，3秒超时==========
with tab_monitor:
    st.subheader("无人机自发自收心跳｜1s/次｜3s无数据超时告警")
    c_start,c_stop = st.columns(2)
    with c_start:start_btn=st.button("▶启动心跳")
    with c_stop:stop_btn=st.button("⏹停止心跳清空数据")

    info_text = st.empty()
    warn_text = st.empty()
    chart_box = st.empty()
    table_box = st.empty()

    def add_beat():
        now = datetime.now().strftime("%H:%M:%S")
        t = time.time()
        item = {"心跳序号":st.session_state["seq_num"],"接收时刻":now,"时间戳":t}
        st.session_state["heart_data"].append(item)
        st.session_state["last_recv_time"] = t
        st.session_state["seq_num"] += 1
        st.session_state["is_timeout"] = False

    def check_timeout():
        if time.time()-st.session_state["last_recv_time"]>3:
            st.session_state["is_timeout"]=True

    if start_btn:
        st.session_state["run_heart"]=True
        info_text.success("心跳模拟器开启")
    if stop_btn:
        st.session_state["run_heart"]=False
        st.session_state["heart_data"].clear()
        st.session_state["seq_num"]=1
        info_text.warning("心跳已停止，数据重置")

    if st.session_state["run_heart"]:
        add_beat()
        check_timeout()
        if st.session_state["is_timeout"]:
            warn_text.error("🔴超时：超过3秒未收到心跳")
        else:
            warn_text.success(f"🟢正常｜最新序号：{st.session_state['seq_num']-1}")
        df = pd.DataFrame(st.session_state["heart_data"])
        fig = px.line(df,x="接收时刻",y="心跳序号",markers=True,title="心跳序号时序变化")
        chart_box.plotly_chart(fig,use_container_width=True)
        table_box.dataframe(df[["心跳序号","接收时刻"]],use_container_width=True)
        time.sleep(1)
