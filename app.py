import streamlit as st
import requests
import time
import base64
from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO

st.set_page_config(page_title="Amazon AI Studio (Official)", page_icon="⚡", layout="wide")

# CSS 样式保持不变
st.markdown("""
    <style>
    .main-title { font-size: 2.5em; color: #232F3E; font-weight: 800; text-align: center; margin-bottom: 20px; }
    .stButton>button { background-color: #FF9900; color: white; border-radius: 8px; height: 3.5em; font-size: 1.2em; font-weight: bold;}
    .badge { padding: 4px 12px; border-radius: 99px; font-size: 0.8em; font-weight: 600; background: #E1EFFE; color: #1E429F; }
    </style>
""", unsafe_allow_html=True)

# 访问密码检查
def check_password():
    if "password_correct" not in st.session_state: st.session_state.password_correct = False
    if not st.session_state.password_correct:
        pwd = st.sidebar.text_input("🔑 访问密码", type="password")
        if st.sidebar.button("Login"):
            # 使用 .get() 避免 APP_PASSWORD 未设置时报错
            if pwd == st.secrets.get("APP_PASSWORD"): st.session_state.password_correct = True; st.rerun()
            else: st.sidebar.error("Wrong Password")
        st.stop()
check_password()

# ==============================================================================
# 关键修复区域：Fal.ai Key 处理 (Base64 + Key Auth)
# ==============================================================================
try:
    # 1. 获取 Key ID 和 Secret
    fal_key_id = st.secrets["FAL_KEY_ID"]
    fal_key_secret = st.secrets["FAL_KEY_SECRET"]
    llm_key = st.secrets["OPENAI_KEY"]
    
    # 2. Base64 编码：将 Key ID:Secret 组合编码
    credentials = f"{fal_key_id}:{fal_key_secret}".encode("utf-8")
    FAL_AUTH_TOKEN = base64.b64encode(credentials).decode("utf-8")
    
except KeyError as e:
    # 明确提示用户缺少的键名
    st.error(f"❌ Secrets 配置缺失：请检查 .streamlit/secrets.toml 中是否包含 FAL_KEY_ID, FAL_KEY_SECRET, OPENAI_KEY 和 APP_PASSWORD。缺少键名：{e}")
    st.stop()
except Exception as e:
    st.error(f"❌ 配置加载错误: {e}")
    st.stop()
# ==============================================================================

with st.sidebar:
    st.title("⚙️ 控制台")
    st.markdown('<span class="badge">● Fal.ai Official</span>', unsafe_allow_html=True)
    st.success("✅ 已连接官方高速通道")
    st.markdown("---")
    style_opt = st.selectbox("风格选择", ["Lifestyle (生活实景)", "Studio (极简棚拍)", "Luxury (高端暗调)", "Outdoors (自然户外)"])
    strength = st.slider("产品保留度", 0.5, 1.0, 0.75, help="推荐 0.75")
    mode = st.radio("图片用途", ("Listing (1024x1024)", "A+ Content (1536x512)"))
    if "Listing" in mode: w, h = 1024, 1024
    else: w, h = 1536, 512

def image_to_base64(image):
    # 确保保存为 RGB 格式以兼容 JPEG
    buffered = BytesIO()
    image.convert("RGB").save(buffered, format="JPEG")
    return base64.b64encode(buffered.getvalue()).decode("utf-8")

def convert_image_to_bytes(img):
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

# ==============================================================================
# 核心函数：Fal.ai API 调用和认证 Header 修正
# ==============================================================================
def generate_flux_official(auth_token, original_img, prompt, strength, width, height):
    submit_url = "https://queue.fal.run/fal-ai/flux/dev"
    
    # 【最终修正】：使用 Base64 编码后的 Token 配合 'Key' 前缀进行认证
    headers = {"Authorization": f"Key {auth_token}", "Content-Type": "application/json"}
    
    base64_img = image_to_base64(original_img)
    data = {
        "prompt": f"{prompt}. The main product MUST remain unchanged. High quality, 8k, commercial photography.",
        "image_url": base64_img, "strength": strength,
        "image_size": {"width": width, "height": height},
        "num_inference_steps": 28, "guidance_scale": 3.5, "enable_safety_checker": False
    }
    
    try:
        resp = requests.post(submit_url, json=data, headers=headers)
        if resp.status_code != 200: 
            st.error(f"❌ 提交失败 ({resp.status_code}): {resp.text}"); 
            return None
        
        request_id = resp.json().get("request_id")
        status_url = f"https://queue.fal.run/fal-ai/flux/requests/{request_id}/status"
        
        # 优化：使用 st.spinner 进行友好轮询
        with st.spinner(f"⏳ 官方服务器绘制中 (Request ID: {request_id})..."):
            start_time = time.time()
            timeout = 120 # 2分钟超时时间
            
            while time.time() - start_time < timeout:
                time.sleep(2) # 降低轮询频率
                
                status_resp = requests.get(status_url, headers=headers)
                status_data = status_resp.json()
                
                if status_data.get("status") == "COMPLETED": 
                    return status_data["images"][0]["url"]
                elif status_data.get("status") == "FAILED": 
                    st.error(f"❌ 生成失败: {status_data.get('error', '未知错误')}"); 
                    return None
            
            st.error("❌ 生成超时，请重试或检查 Fal.ai 状态。")
            return None

    except Exception as e: 
        st.error(f"网络连接错误或未知异常: {e}"); 
        return None
# ==============================================================================

def get_gpt_instruction(api_key, text, product_name, style):
    # 使用 SiliconFlow Base URL，以便兼容国内访问
    client = OpenAI(api_key=api_key, base_url="https://api.siliconflow.cn/v1")
    prompt = f"Role: Amazon Art Director. Product: {product_name}. Input: {text}. Style: {style}. Output: TITLE | SUBTITLE | PROMPT"
    try:
        res = client.chat.completions.create(model="Qwen/Qwen2.5-72B-Instruct", messages=[{"role": "user", "content": prompt}])
        return res.choices[0].message.content.split("|")
    except Exception as e: 
        st.error(f"❌ AI 构思失败: {e}")
        return ["Feature", text, f"Photo of {product_name}, {text}"]

def add_text(image, title, subtitle):
    # 确保图像为 RGBA 模式以支持透明度
    if image.mode != 'RGBA':
        image = image.convert('RGBA')
    
    draw = ImageDraw.Draw(image)
    w, h = image.size
    
    # 底部半透明阴影
    draw.rectangle([(0, h - h//5), (w, h)], fill=(0, 0, 0, 180))
    
    # 尝试加载字体
    try: 
        font_path = "arial.ttf" 
        title_font = ImageFont.truetype(font_path, int(h/20))
        subtitle_font = ImageFont.truetype(font_path, int(h/30))
    except Exception: 
        # 使用默认字体作为备用
        title_font = ImageFont.load_default()
        subtitle_font = ImageFont.load_default()
        
    # 文本定位
    title_y = h - h//5 + int(h/50)
    subtitle_y = title_y + int(h/20) + int(h/100)

    # 绘制文本
    draw.text((30, title_y), title.strip(), fill="white", font=title_font)
    draw.text((30, subtitle_y), subtitle.strip(), fill="#CCCCCC", font=subtitle_font)
    
    # 返回 RGB 模式
    return image.convert('RGB')

st.markdown('<p class="main-title">Amazon AI Studio <span style="font-size:0.4em; color:#FF9900;">OFFICIAL</span></p>', unsafe_allow_html=True)
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("🖼️ 1. 上传产品")
    product_name = st.text_input("产品名称", placeholder="e.g. Coffee Mug")
    uploaded_file = st.file_uploader("上传白底图", type=["jpg", "png", "jpeg"])
    if uploaded_file:
        original_img = Image.open(uploaded_file)
        st.image(original_img, caption="预览", width=200)
        
    st.subheader("📝 2. 卖点文案 (只处理第一个)")
    texts = [st.text_input(f"卖点 {i+1}", key=i) for i in range(1)]
    
    btn = st.button("🚀 官方极速生成", type="primary", use_container_width=True)

with col2:
    st.subheader("✨ 3. 结果展示")
    if btn and uploaded_file:
        valid_texts = [t for t in texts if t]
        if not valid_texts:
            st.warning("⚠️ 请输入至少一个卖点文案！")
            st.stop()
            
        text = valid_texts[0]
        
        with st.status("🧠 AI 正在构思..."):
            info = get_gpt_instruction(llm_key, text, product_name, style_opt)
            if len(info) < 3: 
                info=["Feature Title", "Feature Subtitle", text]
        
        st.info(f"💡 正在调用 Fal.ai 官方 API，Prompt: {info[2]}")
        
        # 调用函数时传入 FAL_AUTH_TOKEN
        img_url = generate_flux_official(FAL_AUTH_TOKEN, original_img, info[2], strength, w, h)
        
        if img_url:
            st.success("✅ 成功！")
            try:
                img_data = requests.get(img_url).content
                final_pil = add_text(Image.open(BytesIO(img_data)), info[0], info[1])
                st.image(final_pil, caption=f"风格: {style_opt}", use_column_width=True)
                
                dl_data = convert_image_to_bytes(final_pil)
                st.download_button("⬇️ 下载原图", dl_data, f"amazon_ai_img.png", "image/png", use_container_width=True)
            except Exception as e:
                st.error(f"❌ 图像处理/下载失败: {e}")