import streamlit as st
import time
from datetime import datetime
import pandas as pd

# -------------------------- 页面配置 --------------------------
st.set_page_config(page_title="无人机心跳监控", layout="wide")
st.title("📡 无人机心跳包 自发自收实时监控")
st.info("每秒发送1次心跳包 | 3秒未收到 → 连接超时")

# -------------------------- 初始化状态（防刷新丢失） --------------------------
if "heartbeat_data" not in st.session_state:
    st.session_state.heartbeat_data = []
if "last_recv_time" not in st.session_state:
    st.session_state.last_recv_time = time.time()
if "seq" not in st.session_state:
    st.session_state.seq = 1

# -------------------------- 占位符（避免重复渲染报错） --------------------------
status_box = st.empty()
seq_box = st.empty()
chart_box = st.empty()
table_box = st.empty()

# -------------------------- 每秒执行一次心跳 --------------------------
while True:
    now = time.time()
    current_time = datetime.now().strftime("%H:%M:%S")

    # 模拟：收到心跳包
    st.session_state.last_recv_time = now

    # 添加数据
    st.session_state.heartbeat_data.append({
        "心跳序号": st.session_state.seq,
        "接收时间": current_time,
        "时间戳": round(now, 1)
    })

    # 超时判断（3秒）
    gap = now - st.session_state.last_recv_time
    if gap > 3:
        status_box.error(f"🔴 连接超时 | {gap:.1f}s 未收到心跳")
    else:
        status_box.success(f"🟢 连接正常 | 最后收到 {gap:.1f}s 前")

    # 显示当前序号
    seq_box.metric("当前心跳序号", st.session_state.seq)

    # 序号+1
    st.session_state.seq += 1

    # 转DataFrame
    df = pd.DataFrame(st.session_state.heartbeat_data)

    # -------------------------- 绘制原生折线图（无BUG） --------------------------
    with chart_box.container():
        st.subheader("📈 心跳序号变化曲线")
        st.line_chart(df, x="接收时间", y="心跳序号", use_container_width=True)

    # -------------------------- 数据列表 --------------------------
    with table_box.container():
        st.subheader("📋 心跳包历史记录")
        st.dataframe(df.tail(15), use_container_width=True, height=300)

    # 每秒一次
    time.sleep(1)
