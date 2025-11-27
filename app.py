import streamlit as st
import requests
import base64
from PIL import Image
from io import BytesIO

st.set_page_config(page_title="Amazon AI Studio (侦探模式)", layout="wide")

st.title("🕵️‍♂️ API 连接侦探模式")
st.markdown("### 我们来看看 Key 到底去哪了？")

# 1. 直接读取 Secrets，不加 try-except，让报错直接暴露
st.write("---")
st.write("#### 第一步：检查保险箱 (Secrets)")

if "FAL_KEY" in st.secrets:
    raw_key = st.secrets["FAL_KEY"]
    # 显示 Key 的前 6 位和长度，看看是不是你填的那个
    st.info(f"✅ 成功从后台读到 Key: `{raw_key[:6]}...` (总长度: {len(raw_key)} 位)")
    
    # 检查是否有空格 (常见错误)
    if " " in raw_key:
        st.error("❌ 警告：你的 Key 里面包含了空格！请去 Secrets 删除空格！")
    
    # 检查是否包含 Bearer (常见错误)
    if "Bearer" in raw_key:
        st.error("❌ 警告：你的 Key 里面包含了 'Bearer' 单词！请去 Secrets 删掉它，只保留 sk- 开头的部分！")
else:
    st.error("❌ 严重错误：Secrets 里根本没有 'FAL_KEY' 这个变量！请检查变量名是否写错。")
    st.stop()

# 2. 模拟发送请求，查看“信封”
st.write("---")
st.write("#### 第二步：检查发送出的信封 (Headers)")

base_url = st.text_input("中转接口地址", value="https://api.vectorengine.ai")

if st.button("🚀 发射侦查请求"):
    # 构造请求头
    headers = {
        "Authorization": f"Bearer {raw_key}",
        "Content-Type": "application/json"
    }
    
    # 展示给用户看，我们发了什么
    st.code(f"""
    发送目标: {base_url}/fal-ai/flux-1/dev
    
    关键请求头 (Headers):
    {{
        "Authorization": "{headers['Authorization'][:15]}......", 
        "Content-Type": "application/json"
    }}
    """)
    
    # 真的发一次试试
    try:
        # 这里故意发一个空数据，只想验证 Key 是否被服务器认可
        # 如果 Key 对了，服务器会报 "Missing body" (400)
        # 如果 Key 没带，服务器会报 "Token not provided" (401)
        resp = requests.post(
            f"{base_url}/fal-ai/flux-1/dev", 
            json={"test": "ping"}, 
            headers=headers
        )
        
        st.write("#### 第三步：服务器的回信")
        st.write(f"状态码: **{resp.status_code}**")
        st.json(resp.json())
        
        if resp.status_code == 401 or "Token not provided" in resp.text:
            st.error("结论：服务器依然说没收到 Key。这说明 Key 本身无效，或者中转站的 Bearer 格式特殊。")
        elif resp.status_code == 400 or "Validation Error" in resp.text:
            st.success("🎉 破案了！Key 是通的！（服务器报参数错误，说明它验证了你的 Key 是对的，只是我们没传图片而已）")
        elif resp.status_code == 500:
            st.warning("服务器又崩溃了 (500)，但说明 Key 是通的。")
            
    except Exception as e:
        st.error(f"连接报错: {e}")