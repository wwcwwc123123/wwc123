import streamlit as st
import time
from datetime import datetime
import pandas as pd

# 页面配置
st.set_page_config(page_title="无人机心跳监控", layout="wide")
st.title("📡 无人机心跳包 自发自收监控")

# 初始化数据（必须这样写）
if "heartbeat_list" not in st.session_state:
    st.session_state.heartbeat_list = []
if "last_time" not in st.session_state:
    st.session_state.last_time = time.time()
if "seq" not in st.session_state:
    st.session_state.seq = 1

# 状态显示区域
status = st.empty()
seq_display = st.empty()

# 图表 + 表格区域
chart_col, table_col = st.columns(2)
with chart_col:
    st.subheader("📈 序号变化曲线")
    chart_area = st.empty()
with table_col:
    st.subheader("📋 最近心跳记录")
    table_area = st.empty()

# ---------------------- 核心逻辑 ----------------------
now = time.time()
current_time = datetime.now().strftime("%H:%M:%S")

# 每秒自动新增一条心跳
if now - st.session_state.last_time >= 1.0:
    # 新增数据
    st.session_state.heartbeat_list.append({
        "序号": st.session_state.seq,
        "时间": current_time
    })
    
    # 更新状态
    st.session_state.seq += 1
    st.session_state.last_time = now

# 超时判断（3秒）
time_diff = now - st.session_state.last_time
if time_diff > 3:
    status.error(f"🔴 连接超时 | {time_diff:.1f}s 未收到心跳")
else:
    status.success(f"🟢 正常连接 | 最后接收 {time_diff:.1f}s 前")

seq_display.metric("当前心跳序号", st.session_state.seq - 1)

# 显示图表
df = pd.DataFrame(st.session_state.heartbeat_list)
if not df.empty:
    chart_area.line_chart(df, x="时间", y="序号", use_container_width=True)
    table_area.dataframe(df.tail(10), use_container_width=True)

# 自动刷新（关键！解决卡死问题）
time.sleep(0.1)
st.rerun()
