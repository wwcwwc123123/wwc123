import streamlit as st
import time
from datetime import datetime
import pandas as pd

# 页面配置
st.set_page_config(page_title="无人机心跳监控", layout="wide")
st.title("📡 无人机心跳包 自发自收监控")

# 初始化会话状态
if "heartbeat_list" not in st.session_state:
    st.session_state.heartbeat_list = []
if "last_time" not in st.session_state:
    st.session_state.last_time = time.time()
if "seq" not in st.session_state:
    st.session_state.seq = 1
if "paused" not in st.session_state:
    st.session_state.paused = False  # 暂停开关

# ---------------------- 暂停 / 继续 按钮 ----------------------
col1, col2 = st.columns(2)
with col1:
    if st.button("⏸️ 暂停心跳"):
        st.session_state.paused = True
with col2:
    if st.button("▶️ 继续心跳"):
        st.session_state.paused = False

# 状态显示
status_area = st.empty()
seq_area = st.empty()

# 图表 + 表格
chart_col, table_col = st.columns(2)
with chart_col:
    st.subheader("📈 心跳序号曲线")
    chart_box = st.empty()
with table_col:
    st.subheader("📋 最近记录")
    table_box = st.empty()

# ---------------------- 核心逻辑 ----------------------
now = time.time()
current_time = datetime.now().strftime("%H:%M:%S")

# 暂停状态
if st.session_state.paused:
    status_area.warning("⏸️ 已暂停心跳接收")
else:
    # 每秒生成一次心跳
    if now - st.session_state.last_time >= 1.0:
        st.session_state.heartbeat_list.append({
            "序号": st.session_state.seq,
            "时间": current_time
        })
        st.session_state.seq += 1
        st.session_state.last_time = now

    # 超时判断（3秒未收到 = 超时）
    time_diff = now - st.session_state.last_time
    if time_diff > 3:
        status_area.error(f"🔴 连接超时 | {time_diff:.1f}s 未收到心跳")
    else:
        status_area.success(f"🟢 正常连接 | 最后收到 {time_diff:.1f}s 前")

# 显示当前序号
seq_area.metric("当前心跳序号", st.session_state.seq - 1)

# 显示图表和表格
df = pd.DataFrame(st.session_state.heartbeat_list)
if not df.empty:
    chart_box.line_chart(df, x="时间", y="序号", use_container_width=True)
    table_box.dataframe(df.tail(12), use_container_width=True, height=350)

# 自动刷新（流畅不报错）
time.sleep(0.1)
st.rerun()
