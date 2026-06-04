import streamlit as st
import time
import datetime
import pandas as pd
import matplotlib.pyplot as plt

# -------------------------- 页面设置 --------------------------
st.set_page_config(page_title="无人机心跳包监控", layout="wide")
st.title("📡 无人机心跳包 自发自收实时监控")
st.subheader("每秒发送1次心跳包 | 3秒未收到 = 连接超时")

# -------------------------- 初始化会话状态（重启不丢失数据） --------------------------
if "heartbeat_list" not in st.session_state:
    st.session_state.heartbeat_list = []  # 保存所有心跳数据
if "last_receive_time" not in st.session_state:
    st.session_state.last_receive_time = time.time()  # 最后一次收到包的时间
if "seq" not in st.session_state:
    st.session_state.seq = 1  # 心跳序号从1开始

# -------------------------- 状态显示区域 --------------------------
status_col1, status_col2 = st.columns(2)
with status_col1:
    status_placeholder = st.empty()  # 状态提示
with status_col2:
    seq_placeholder = st.empty()     # 当前序号

# 图表 + 数据列表
chart_placeholder = st.empty()
data_table_placeholder = st.empty()

# -------------------------- 主循环：每秒收发心跳 --------------------------
try:
    while True:
        now = time.time()
        current_dt = datetime.datetime.now().strftime("%H:%M:%S")
        
        # 1. 发送 + 接收心跳包（模拟）
        st.session_state.last_receive_time = now
        packet = {
            "心跳序号": st.session_state.seq,
            "接收时间": current_dt,
            "时间戳": now
        }
        st.session_state.heartbeat_list.append(packet)

        # 2. 更新序号
        current_seq = st.session_state.seq
        st.session_state.seq += 1

        # 3. 判断是否超时（3秒）
        time_diff = now - st.session_state.last_receive_time
        if time_diff > 3:
            status_placeholder.error(f"🔴 连接超时 | {time_diff:.1f}s 未收到心跳包")
        else:
            status_placeholder.success(f"🟢 正常连接 | 最后接收 {time_diff:.1f}s 前")

        seq_placeholder.info(f"📶 当前心跳序号：{current_seq}")

        # -------------------------- 绘制折线图 --------------------------
        df = pd.DataFrame(st.session_state.heartbeat_list)
        with chart_placeholder.container():
            st.subheader("📈 心跳序号随时间变化曲线")
            if len(df) > 0:
                fig, ax = plt.subplots(figsize=(10, 4))
                ax.plot(df["接收时间"], df["心跳序号"], marker="o", color="#1f77b4", linewidth=2)
                ax.set_xlabel("时间")
                ax.set_ylabel("心跳序号")
                ax.grid(True)
                plt.xticks(rotation=45)
                plt.tight_layout()
                st.pyplot(fig)

        # -------------------------- 显示数据列表 --------------------------
        with data_table_placeholder.container():
            st.subheader("📋 心跳包数据列表")
            st.dataframe(df, use_container_width=True, height=200)

        # 每秒一次
        time.sleep(1)

except Exception as e:
    st.error(f"程序异常：{str(e)}")
