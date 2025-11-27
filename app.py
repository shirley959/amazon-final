import streamlit as st
import requests
import time
import base64
from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO

# ==========================================
# ✨ 页面配置 (Official Direct Edition)
# ==========================================
st.set_page_config(
    page_title="Amazon AI Studio (Official)",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 🎨 注入高级 CSS (保持美观)
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    .stApp { background-color: #F8F9FC; }
    .main-title { font-size: 2.5em; color: #232F3E; font-weight: 800; text-align: center; margin-bottom: 20px; }
    .section-header { font-size: 1.2em; color: #555; font-weight: 600; border-bottom: 1px solid #ddd; margin-top: 20px; margin-bottom: 10px; }
    .stButton>button { background: linear-gradient(45deg, #FF9900, #FFB84D); color: white; border: none; border-radius: 8px; height: 3em; font-size: 1.1em; font-weight: bold; width: 100%; }
    div[data-testid="stVerticalBlock"] > div > div[data-testid="stVerticalBlock"] { background-color: white; padding: 1.5rem; border-radius: 15px; box-shadow: 0 4px 20px rgba(0,0,0,0.05); }
    .badge { padding: 4px 12px; border-radius: 99px; font-size: 0.8em; font-weight: 600; background: #DEF7EC; color: #03543F; border: 1px solid #84E1BC; }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 🔐 安全检查
# ==========================================
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False
    if not st.session_state.password_correct:
        pwd = st.sidebar.text_input("🔒 Access Password", type="password")
        if st.sidebar.button("Unlock"):
            if pwd == st.secrets["APP_PASSWORD"]:
                st.session_state.password_correct = True
                st.rerun()
            else:
                st.sidebar.error("Wrong Password")
        st.stop()
check_password()

try:
    # 读取官方 Key
    fal_key = st.secrets["FAL_KEY"]
    openai_key = st.secrets["OPENAI_KEY"]
except:
    st.error("❌ Secrets 配置缺失，请检查 FAL_KEY 和 OPENAI_KEY")
    st.stop()

# ==========================================
# ⚙️ 侧边栏 (无中转地址版)
# ==========================================
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/a/a9/Amazon_logo.svg", width=100)
    st.markdown('<div style="margin:10px 0;"><span class="badge">● Official Direct</span></div>', unsafe_allow_html=True)
    st.success("✅ 已连接 Fal.ai 官方高速通道")
    
    st.markdown("---")
    st.header("🎨 风格配置")
    
    style_map = {
        "Lifestyle": "🌿 Lifestyle (生活感)",
        "Studio": "💡 Studio (极简棚拍)",
        "Luxury": "✨ Luxury (高端暗调)", 
        "Outdoors": "🏔️ Outdoors (自然户外)"
    }
    style_opt = st.radio("选择风格:", list(style_map.keys()), format_func=lambda x: style_map[x])
    
    st.markdown("---")
    mode = st.radio("图片用途:", ("Listing (详情页)", "A+ Content (A+页面)"))
    
    if "Listing" in mode:
        size_opt = st.selectbox("尺寸:", ["1024x1024 (方图)", "832x1216 (长图)"])
        wh_map = {"1024x1024 (方图)": (1024, 1024), "832x1216 (长图)": (832, 1216)}
    else:
        size_opt = st.selectbox("尺寸:", ["970x600 (大图)", "970x300 (横幅)"])
        wh_map = {"970x600 (大图)": (1536, 896), "970x300 (横幅)": (1536, 512)}
    
    w, h = wh_map[size_opt]
    
    st.markdown("---")
    strength = st.slider("产品保留度", 0.5, 1.0, 0.75, help="官方建议 0.75-0.8")

# ==========================================
# 🛠️ 核心函数 (官方协议)
# ==========================================

def image_to_base64(image):
    buffered = BytesIO()
    image.convert("RGB").save(buffered, format="JPEG")
    img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
    return f"data:image/jpeg;base64,{img_str}"

def convert_image_to_bytes(img):
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

def generate_flux_official(api_key, original_img, prompt, strength, width, height):
    """
    Fal.ai 官方 API 调用逻辑 (Submit -> Queue -> Poll)
    """
    submit_url = "https://queue.fal.run/fal-ai/flux/dev"
    
    headers = {
        "Authorization": f"Key {api_key}", # 官方认证头
        "Content-Type": "application/json"
    }
    
    base64_img = image_to_base64(original_img)
    
    data = {
        "prompt": f"{prompt}. The main product MUST remain unchanged. High quality, 8k, commercial photography.",
        "image_url": base64_img,
        "strength": strength,
        "image_size": {"width": width, "height": height},
        "num_inference_steps": 28,
        "guidance_scale": 3.5,
        "enable_safety_checker": False
    }
    
    try:
        # 1. 提交任务
        resp = requests.post(submit_url, json=data, headers=headers)
        if resp.status_code != 200:
            st.error(f"❌ 提交失败 ({resp.status_code}): {resp.text}")
            return None
        
        request_id = resp.json().get("request_id")
        status_url = f"https://queue.fal.run/fal-ai/flux/requests/{request_id}/status"
        
        # 2. 轮询查询 (官方速度很快)
        placeholder = st.empty()
        for i in range(60):
            placeholder.caption(f"⏳ 官方绘制中... {i+1}s")
            time.sleep(1)
            
            status_resp = requests.get(status_url, headers=headers)
            status_data = status_resp.json()
            
            if status_data["status"] == "COMPLETED":
                placeholder.empty()
                return status_data["images"][0]["url"]
            elif status_data["status"] == "FAILED":
                st.error(f"❌ 生成失败: {status_data.get('error', 'Unknown')}")
                return None
            # IN_QUEUE 或 IN_PROGRESS 继续循环
            
    except Exception as e:
        st.error(f"连接错误: {e}")
        return None
    
    return None

def get_gpt_instruction_batch(api_key, long_text, product_name, style, num_images=6):
    client = OpenAI(api_key=api_key)
    prompt = f"""
    Role: Amazon Art Director. Product: {product_name}. 
    Input Description: "{long_text}". Target Style: {style}.
    Task: Generate {num_images} distinct visual concepts.
    Output Format: Exactly {num_images} lines. Each line: TITLE | SUBTITLE | PROMPT
    """
    fallback = [["Feature", "Highlight", f"Photo of {product_name}"]] * num_images
    try:
        res = client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": prompt}])
        lines = res.choices[0].message.content.strip().split("\n")
        results = []
        for line in lines:
            if not line.strip(): continue
            parts = line.split("|")
            if len(parts) >= 3: results.append([p.strip() for p in parts])
        while len(results) < num_images: results.append(["Detail", "Shot", f"Professional shot of {product_name}"])
        return results[:num_images]
    except: return fallback

def add_text(image, title, subtitle):
    draw = ImageDraw.Draw(image)
    w, h = image.size
    draw.rectangle([(0, h - h//5), (w, h)], fill=(0, 0, 0, 180))
    try: font = ImageFont.truetype("arial.ttf", int(h/20))
    except: font = ImageFont.load_default()
    draw.text((30, h - h//5 + 20), title.strip(), fill="white", font=font)
    draw.text((30, h - h//5 + 60), subtitle.strip(), fill="#CCCCCC", font=font)
    return image

# ==========================================
# 🎨 主界面
# ==========================================
st.markdown('<p class="main-title">Amazon AI Studio <span style="font-size:0.4em; color:#FF9900;">OFFICIAL</span></p>', unsafe_allow_html=True)

main_col1, main_col2 = st.columns([3, 2], gap="large")

with main_col1:
    st.markdown('<p class="section-header">📦 Step 1: Product</p>', unsafe_allow_html=True)
    product_name = st.text_input("Product Name", placeholder="e.g. Coffee Mug")
    
    col_up1, col_up2 = st.columns([3, 2])
    with col_up1:
        uploaded_file = st.file_uploader("Upload Source Image (White BG)", type=["jpg", "png", "jpeg"])
        if uploaded_file:
            original_img = Image.open(uploaded_file)
            st.success("✅ Image Loaded")

    with col_up2:
        if uploaded_file:
            st.image(original_img, caption="Preview", width=150)

    st.markdown('<p class="section-header">📝 Step 2: Bullet Points</p>', unsafe_allow_html=True)
    long_text_input = st.text_area("Paste your features here...", height=150)

with main_col2:
    st.info("💡 提示：此版本直连 Fal.ai 官方服务器，生成速度极快且稳定。")
    st.markdown("---")
    # 一个巨大的生成按钮
    btn_generate = st.button("🚀 GENERATE 6 IMAGES", type="primary", use_container_width=True)

# ==========================================
# 🎉 结果展示区
# ==========================================
if btn_generate:
    if not uploaded_file or not long_text_input:
        st.error("⚠️ 请上传图片并填写文案。")
        st.stop()
        
    st.markdown("---")
    st.subheader("🎉 Generation Results")
    
    with st.status("🧠 AI Brainstorming...", expanded=True) as status:
        gpt_results = get_gpt_instruction_batch(openai_key, long_text_input, product_name, style_opt, 6)
        st.success(f"Generated {len(gpt_results)} concepts")
        status.update(label="Starting Rendering Engine...", state="complete", expanded=False)

    rows = [st.columns(3), st.columns(3)]
    
    for i, item in enumerate(gpt_results):
        title, subtitle, prompt = item[0], item[1], item[2]
        row_idx = i // 3
        col_idx = i % 3
        
        if row_idx < 2:
            with rows[row_idx][col_idx]:
                with st.container():
                    with st.spinner(f"Rendering Img {i+1}..."):
                        # 调用官方生成函数
                        img_url = generate_flux_official(fal_key, original_img, prompt, strength, w, h)
                        
                        if img_url:
                            img_data = requests.get(img_url).content
                            final_pil = add_text(Image.open(BytesIO(img_data)), title, subtitle)
                            st.image(final_pil, use_column_width=True)
                            st.caption(f"**{title}**")
                            
                            dl_data = convert_image_to_bytes(final_pil)
                            st.download_button(f"📥 Download", dl_data, f"img_{i}.png", "image/png", key=f"d_{i}")
                        else:
                            st.error("Failed")