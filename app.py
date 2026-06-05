import streamlit as st
import pandas as pd
import plotly.express as px
import time
from datetime import datetime
import pyproj
import folium
from folium.plugins import Draw
from streamlit_folium import st_folium
import math

# ====================== GCJ02/WGS84坐标转换（高德纠偏核心） ======================
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
    mglat = lat + dlat
    mglng = lng + dlng
    return mglng, mglat

def gcj02_to_wgs84(lng, lat):
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
    mglat = lat + dlat
    mglng = lng + dlng
    return lng * 2 - mglng, lat * 2 - mglat

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

# ====================== 页面初始化 ======================
st.set_page_config(page_title="校园无人机监控系统", layout="wide")
st.title("🎓 校园无人机航线规划 + 飞行监控平台")

# WGS<->UTM转换
class CoordConverter:
    def __init__(self):
        self.wgs84 = "EPSG:4326"
        self.utm = "EPSG:32650"
        self.wgs2utm = pyproj.Transformer.from_crs(self.wgs84, self.utm, always_xy=True)
        self.utm2wgs = pyproj.Transformer.from_crs(self.utm, self.wgs84, always_xy=True)
        self.campus = {"lat_min":32.231,"lat_max":32.235,"lng_min":118.747,"lng_max":118.751}
    def wgs_to_utm(self,lng,lat):
        x,y = self.wgs2utm.transform(lng,lat)
        return round(x,2),round(y,2)
    def in_campus(self,lng,lat):
        return self.campus["lat_min"]<=lat<=self.campus["lat_max"] and self.campus["lng_min"]<=lng<=self.campus["lng_max"]

coord = CoordConverter()

# AB固定坐标(WGS84)
A_LNG,A_LAT = 118.749,32.2322
B_LNG,B_LAT = 118.749,32.2343

# session_state持久化：障碍物、绘图缓存
if "obstacle_list" not in st.session_state:
    st.session_state.obstacle_list = [] # 多边形障碍物永久记忆
if "map_draw_data" not in st.session_state:
    st.session_state.map_draw_data = None

# 心跳包缓存
if "heart_data" not in st.session_state:st.session_state.heart_data=[]
if "last_recv" not in st.session_state:st.session_state.last_recv=time.time()
if "seq" not in st.session_state:st.session_state.seq=1
if "running" not in st.session_state:st.session_state.running=False

# 双标签页
tab1,tab2 = st.tabs(["🗺️航线规划(高德卫星+障碍物圈选)","📡飞行监控(心跳包)"])

# ====================== 页面1：航线规划（修复圈选） ======================
with tab1:
    st.subheader("📍起点A / 终点B（WGS84经纬度）")
    c1,c2 = st.columns(2)
    with c1:st.success(f"A 经度{A_LNG} | 纬度{A_LAT}")
    with c2:st.success(f"B 经度{B_LNG} | 纬度{B_LAT}")

    if st.button("✅坐标校验+WGS→GCJ02+UTM转换"):
        a_in = coord.in_campus(A_LNG,A_LAT)
        b_in = coord.in_campus(B_LNG,B_LAT)
        if a_in and b_in:
            st.success("AB坐标在校园内")
            # GCJ02火星坐标
            a_gcj_lng,a_gcj_lat = wgs84_to_gcj02(A_LNG,A_LAT)
            b_gcj_lng,b_gcj_lat = wgs84_to_gcj02(B_LNG,B_LAT)
            ax,ay = coord.wgs_to_utm(A_LNG,A_LAT)
            bx,by = coord.wgs_to_utm(B_LNG,B_LAT)
            st.info(f"A:GCJ02({a_gcj_lng:.6f},{a_gcj_lat:.6f}) | UTM(X:{ax},Y:{ay})")
            st.info(f"B:GCJ02({b_gcj_lng:.6f},{b_gcj_lat:.6f}) | UTM(X:{bx},Y:{by})")
        else:
            st.error("坐标超出校园范围")

    st.divider()
    st.subheader("🚧障碍物多边形圈选操作指南")
    col_btn1,col_btn2 = st.columns(2)
    with col_btn1:
        if st.button("🗑️清空全部已存障碍物"):
            st.session_state.obstacle_list = []
            st.rerun()
    with col_btn2:
        st.info("1.地图左上角点【多边形图标】→在地图连续点击描边→闭合多边形\n2.画完自动存入缓存，永久保存；刷新页面不丢失")

    # ==========创建高德卫星地图+正确加载Draw绘图插件（关键修复）==========
    center_lat = (A_LAT+B_LAT)/2
    center_lng = (A_LNG+B_LNG)/2
    m = folium.Map(
        location=[center_lat,center_lng],
        zoom_start=19,
        tiles="https://webst01.is.autonavi.com/appmaptile?style=6&x={x}&y={y}&z={z}",
        attr="高德卫星实况地图"
    )
    # Draw配置：只启用多边形绘制，关闭多余绘图，开启导出数据
    draw_plugin = Draw(
        export=True,
        position="topleft",
        draw_options={
            "polygon":True,
            "polyline":False,
            "rectangle":False,
            "circle":False,
            "marker":False,
            "circlemarker":False
        },
        edit_options={"edit":True,"remove":True}
    )
    draw_plugin.add_to(m)

    # 绘制起点、终点、规划航线
    folium.Marker([A_LAT,A_LNG],popup="起点A",icon=folium.Icon(color="red")).add_to(m)
    folium.Marker([B_LAT,B_LNG],popup="终点B",icon=folium.Icon(color="blue")).add_to(m)
    folium.PolyLine([[A_LAT,A_LNG],[B_LAT,B_LNG]],color="green",weight=4,popup="航线AB").add_to(m)

    # 加载历史保存障碍物（记忆功能）
    for idx,poly_points in enumerate(st.session_state.obstacle_list):
        folium.Polygon(locations=poly_points,color="red",fill_color="red",fill_opacity=0.3,popup=f"障碍物{idx+1}").add_to(m)

    # st_folium固定key，保证绘图数据稳定接收（核心修复）
    map_out = st_folium(
        m,width="100%",height=620,
        key="campus_map", # 固定key！
        returned_objects=["all_drawings","last_active_drawing"]
    )

    # 解析新绘制多边形，存入session_state永久保存
    if map_out and "all_drawings" in map_out and map_out["all_drawings"] is not None:
        new_draws = map_out["all_drawings"]
        if new_draws != st.session_state.map_draw_data:
            st.session_state.map_draw_data = new_draws
            for draw_item in new_draws:
                if draw_item["geometry"]["type"] == "Polygon":
                    # geojson坐标[经度,纬度]→folium[纬度,经度]
                    poly_geo = draw_item["geometry"]["coordinates"][0]
                    poly_loc = [[p[1],p[0]] for p in poly_geo[:-1]] # 剔除闭合重复点
                    if poly_loc not in st.session_state.obstacle_list:
                        st.session_state.obstacle_list.append(poly_loc)
            st.rerun() # 保存后自动刷新地图，显示新障碍物

    # 展示已保存障碍物列表
    st.divider()
    st.subheader("✅已保存障碍物清单(持久化存储)")
    if len(st.session_state.obstacle_list)>0:
        df_obs = pd.DataFrame({
            "障碍物编号":[f"障碍物{i+1}" for i in range(len(st.session_state.obstacle_list))],
            "多边形顶点数":[len(item) for item in st.session_state.obstacle_list]
        })
        st.dataframe(df_obs,use_container_width=True)
    else:
        st.info("暂无圈选障碍物，请在地图绘制多边形")

# ======================页面2：飞行监控（心跳包）======================
with tab2:
    st.subheader("📡无人机心跳包实时接收监控")
    b1,b2 = st.columns(2)
    with b1:
        if st.button("▶️启动心跳(1Hz)"):
            st.session_state.running=True
    with b2:
        if st.button("⏹️停止心跳清空数据"):
            st.session_state.running=False
            st.session_state.heart_data=[]
            st.session_state.seq=1

    status_ = st.empty()
    warn_ = st.empty()
    chart_ = st.empty()
    table_ = st.empty()

    def add_beat():
        now_t = datetime.now().strftime("%H:%M:%S")
        st.session_state.heart_data.append({"序号":st.session_state.seq,"接收时刻":now_t})
        st.session_state.last_recv = time.time()
        st.session_state.seq +=1

    def check_timeout():
        return time.time()-st.session_state.last_recv>3

    if st.session_state.running:
        add_beat()
        timeout_flag = check_timeout()
        if timeout_flag:
            warn_.error("🔴心跳超时：超过3s未收到数据包！")
        else:
            warn_.success(f"🟢通讯正常，最新心跳序号：{st.session_state.seq-1}")
        status_.success("心跳采集运行中...")
        df_heart = pd.DataFrame(st.session_state.heart_data)
        fig = px.line(df_heart,x="接收时刻",y="序号",markers=True,title="心跳时序曲线")
        chart_.plotly_chart(fig,use_container_width=True)
        table_.dataframe(df_heart,use_container_width=True)
        time.sleep(1)
