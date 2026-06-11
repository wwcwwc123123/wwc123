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

# -------------------------- 坐标转换（保留） --------------------------
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

# -------------------------- 几何工具（修复版） --------------------------
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

def seg_intersect(a1,a2,b1,b2):
    ccw1=ccw(a1,a2,b1)
    ccw2=ccw(a1,a2,b2)
    ccw3=ccw(b1,b2,a1)
    ccw4=ccw(b1,b2,a2)
    if (ccw1*ccw2 < 0) and (ccw3*ccw4 < 0):
        return True
    return False

# 核心：线段与多边形是否相交（含端点在内部）
def line_cross_poly(p1,p2,poly):
    if point_in_polygon(p1,poly) or point_in_polygon(p2,poly):
        return True
    for i in range(len(poly)):
        j=(i+1)%len(poly)
        if seg_intersect(p1,p2,poly[i],poly[j]):
            return True
    return False

# 膨胀障碍物（系数拉满）
def inflate_polygon(poly, safe_meter):
    scale=safe_meter * 0.00025  # 比之前大很多
    new_p=[]
    for lat,lng in poly:
        new_p.append((lat+scale, lng+scale))
    return new_p

# -------------------------- 起止点 --------------------------
A_LNG, A_LAT=118.749, 32.2322
B_LNG, B_LAT=118.749, 32.2343

# -------------------------- Session --------------------------
if "obstacles" not in st.session_state:
    st.session_state.obstacles=[]
if "obstacle_heights" not in st.session_state:
    st.session_state.obstacle_heights=[]
if "drone_height" not in st.session_state:
    st.session_state.drone_height=10
if "safe_radius" not in st.session_state:
    st.session_state.safe_radius=15
if "route_choice" not in st.session_state:
    st.session_state.route_choice="直线飞行"
if "map_key" not in st.session_state:
    st.session_state.map_key="map_0"

# -------------------------- 避障核心（彻底修复） --------------------------
def generate_route(A,B,obstacles,safe_radius,mode,need_avoid):
    if not need_avoid or len(obstacles)==0:
        return [A,B]

    # 1. 膨胀所有障碍物
    inflated=[inflate_polygon(o,safe_radius) for o in obstacles]

    # 2. 检测是否碰撞
    cross=False
    for o in inflated:
        if line_cross_poly(A,B,o):
            cross=True
            break
    if not cross:
        return [A,B]

    # 3. 计算垂直方向
    ab_dlat=B[0]-A[0]
    ab_dlng=B[1]-A[1]
    ab_len=math.hypot(ab_dlat,ab_dlng)
    if ab_len < 1e-9:
        return [A,B]

    norm_dlat=-ab_dlng/ab_len
    norm_dlng=ab_dlat/ab_len

    # 4. 超大偏移（绕得很远）
    big_offset=safe_radius * 0.0025

    # 5. 加密采样整条线
    n=9
    base=[]
    for i in range(n):
        r=i/(n-1)
        lat=A[0]*(1-r)+B[0]*r
        lng=A[1]*(1-r)+B[1]*r
        base.append((lat,lng))

    # 6. 左右整体偏移
    left=[(lat+norm_dlat*big_offset, lng+norm_dlng*big_offset) for lat,lng in base]
    right=[(lat-norm_dlat*big_offset, lng-norm_dlng*big_offset) for lat,lng in base]

    if mode=="向左绕行":
        return left
    elif mode=="向右绕行":
        return right
    else:
        def len_route(r):
            return sum(math.hypot(r[i+1][0]-r[i][0], r[i+1][1]-r[i][1]) for i in range(len(r)-1))
        return left if len_route(left) < len_route(right) else right

# -------------------------- 页面 --------------------------
st.set_page_config(page_title="无人机避障（修复版）", layout="wide")
st.title("🛠️ 航线避障（彻底解决穿透）")

A=(A_LAT, A_LNG)
B=(B_LAT, B_LNG)

# 参数
st.subheader("参数设置")
drone_h=st.number_input("无人机高度(m)", 1, 500, st.session_state.drone_height)
safe_r=st.number_input("安全半径(m)", 5, 50, st.session_state.safe_radius)
if drone_h != st.session_state.drone_height or safe_r != st.session_state.safe_radius:
    st.session_state.drone_height=drone_h
    st.session_state.safe_radius=safe_r
    st.session_state.map_key=f"map_{time.time()}"
    st.rerun()

# 障碍物管理
st.subheader("障碍物管理")
if st.button("清空障碍物"):
    st.session_state.obstacles=[]
    st.session_state.obstacle_heights=[]
    st.session_state.map_key=f"map_{time.time()}"
    st.rerun()

# 高度判断（清晰化）
max_obs_h=max(st.session_state.obstacle_heights) if st.session_state.obstacle_heights else 0
need_avoid=drone_h < max_obs_h

if need_avoid:
    st.error(f"⚠️ 无人机({drone_h}m) < 障碍物({max_obs_h}m) → 启用避障")
    route_choice=st.radio("绕行方式", ["向左绕行", "向右绕行", "自动选优"])
    st.session_state.route_choice=route_choice
else:
    st.success(f"✅ 无人机({drone_h}m) ≥ 障碍物({max_obs_h}m) → 直飞")
    st.session_state.route_choice="直线飞行"

# 生成航线
route=generate_route(A,B,st.session_state.obstacles,safe_r,st.session_state.route_choice,need_avoid)

# 地图
center=((A[0]+B[0])/2, (A[1]+B[1])/2)
m=folium.Map(location=center, zoom_start=19)
folium.TileLayer(
    tiles="https://webst01.is.autonavi.com/appmaptile?style=6&x={x}&y={y}&z={z}",
    attr="高德卫星"
).add_to(m)
Draw(export=True, draw_options={"polygon":True,"polyline":False,"rectangle":False,"circle":False,"marker":False}).add_to(m)

folium.Marker(A, icon=folium.Icon(color="red"), popup="A").add_to(m)
folium.Marker(B, icon=folium.Icon(color="blue"), popup="B").add_to(m)

# 画障碍物
for i,poly in enumerate(st.session_state.obstacles):
    folium.Polygon(poly, color="red", fill=True, fill_color="red", fill_opacity=0.5,
                    popup=f"障碍物{i+1} {st.session_state.obstacle_heights[i]}m").add_to(m)

# 画航线
color="green"
if st.session_state.route_choice=="向左绕行":
    color="orange"
elif st.session_state.route_choice=="向右绕行":
    color="purple"
elif st.session_state.route_choice=="自动选优":
    color="blue"
folium.PolyLine(route, color=color, weight=6).add_to(m)

# 显示地图
out=st_folium(m, key=st.session_state.map_key, width="100%", height=600, returned_objects=["all_drawings"])

# 新增障碍物（强制纠正坐标顺序）
if out and out.get("all_drawings"):
    new_obs=False
    for d in out["all_drawings"]:
        if d["geometry"]["type"]=="Polygon":
            coords=d["geometry"]["coordinates"][0]
            poly=[(p[1], p[0]) for p in coords[:-1]]  # 强制 (lat,lng)
            if poly not in st.session_state.obstacles:
                st.session_state.obstacles.append(poly)
                st.session_state.obstacle_heights.append(15)
                new_obs=True
    if new_obs:
        st.session_state.map_key=f"map_{time.time()}"
        st.rerun()

# 障碍物列表
if st.session_state.obstacles:
    st.subheader("障碍物列表")
    for i in range(len(st.session_state.obstacles)):
        col1,col2=st.columns([4,1])
        with col1:
            h=st.number_input(f"高度(m)", 1, 200, st.session_state.obstacle_heights[i], key=f"h{i}")
            st.session_state.obstacle_heights[i]=h
        with col2:
            if st.button("删除", key=f"del{i}"):
                del st.session_state.obstacles[i]
                del st.session_state.obstacle_heights[i]
                st.session_state.map_key=f"map_{time.time()}"
                st.rerun()
