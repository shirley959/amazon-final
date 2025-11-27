import streamlit as st
import requests
import time
import base64
from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO

st.set_page_config(page_title="Amazon AI Studio (Debug Mode)", layout="wide")

# --- 安全检查 ---
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False
    if not st.session_state.password_correct:
        pwd = st.text_input("🔒 请输入访问密码", type="password")
        if st.button("登录"):
            if pwd == st.secrets["APP_PASSWORD"]:
                st.session_state.password_correct = True
                st.rerun()
            else:
                st.error("❌ 密码错误")
        st.stop()
check_password()

openai_key = st.secrets["OPENAI_KEY"]
fal_key = st.secrets["FAL_KEY"]

# --- 侧边栏 ---
with st.sidebar:
    st.success("✅ 验证通过")
    st.error("👇 这里最重要！必须填对！")
    # 我把默认值清空了，强制你填入正确的
    base_url = st.text_input("中转接口地址 (API Domain)", placeholder="去你买Key的网站复制，例如 https://api.openai-hk.com")
    
    st.markdown("---")
    strength = st.slider("产品保留度", 0.5, 1.0, 0.75)
    mode = st.radio("尺寸", ("Listing (1024x1024)", "A+ Banner (1536x512)"))
    if "Listing" in mode: w, h = 1024, 1024
    else: w, h = 1536, 512

# --- 核心函数 ---
def image_to_base64(image):
    buffered = BytesIO()
    image.convert("RGB").save(buffered, format="JPEG")
    img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
    return f"data:image/jpeg;base64,{img_str}"

def fal_request_relay(api_key, base_url, model, data):
    # 确保地址没有斜杠结尾
    base_url = base_url.rstrip("/")
    # 拼接完整地址
    submit_url = f"{base_url}/{model}"
    
    # 打印出来给你看，检查对不对
    st.write(f"正在连接: {submit_url}")
    
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    
    try:
        resp = requests.post(submit_url, json=data, headers=headers)
        
        # !!! 关键修改：如果有错，直接打印服务器返回的文字 !!!
        if resp.status_code != 200:
            st.error(f"❌ 报错代码: {resp.status_code}")
            st.error(f"❌ 报错详情: {resp.text}") # 这里会显示真实的错误原因
            st.stop()
            
        res_json = resp.json()
        
    except Exception as e:
        st.error(f"连接失败: {e}")
        return None

    # 获取结果逻辑 (Schnell版)
    if "images" in res_json:
        return res_json["images"][0]["url"]
    
    # 轮询逻辑
    if "response_url" in res_json:
        poll_url = res_json["response_url"]
        # 处理部分中转站 URL 替换问题
        if "queue.fal.run" in poll_url:
             target_path = poll_url.split("queue.fal.run")[-1]
             poll_url = f"{base_url}{target_path}"
    else:
        st.error("中转站返回数据格式不对，没有 images 也没 response_url")
        st.write(res_json) # 打印出来看
        return None

    placeholder = st.empty()
    for i in range(20): 
        placeholder.text(f"⏳ 正在生成... ({i}s)")
        time.sleep(1)
        try:
            poll_resp = requests.get(poll_url, headers=headers)
            if poll_resp.status_code == 200:
                poll_data = poll_resp.json()
                if "images" in poll_data:
                    placeholder.empty()
                    return poll_data["images"][0]["url"]
        except:
            pass
    return None

def generate_scene_economy(api_key, base_url, original_img, prompt, strength, w, h):
    base64_img = image_to_base64(original_img)
    full_prompt = f"{prompt}. The main product stays unchanged. High quality."
    data = {
        "prompt": full_prompt,
        "image_url": base64_img,
        "strength": strength, 
        "image_size": {"width": w, "height": h},
        "num_inference_steps": 4, 
        "guidance_scale": 3.5,
        "enable_safety_checker": False
    }
    # 使用便宜的 Schnell 模型
    return fal_request_relay(api_key, base_url, "fal-ai/flux-1/schnell", data)

# --- 主界面 ---
st.title("🛠️ 故障排查模式")

col1, col2 = st.columns([1, 1])
with col1:
    uploaded_file = st.file_uploader("上传产品图", type=["jpg", "png", "jpeg"])
    btn = st.button("🚀 测试连接", type="primary")

with col2:
    if btn and uploaded_file and base_url:
        st.info("🔄 开始测试...")
        original_img = Image.open(uploaded_file)
        
        # 发送测试请求
        final_url = generate_scene_economy(fal_key, base_url, original_img, "A product on table", strength, w, h)
        
        if final_url:
            st.success("✅ 成功！就是钱或地址的问题，现在通了！")
            st.image(final_url)