import streamlit as st
import requests
import time
import base64
from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO

# ==========================================
# ✨ 页面配置
# ==========================================
st.set_page_config(
    page_title="Amazon AI Creative Studio",
    page_icon="✨",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS 美化
st.markdown("""
    <style>
    .main-title { font-size: 2.5em; color: #FF9900; font-weight: bold; text-align: center; margin-bottom: 20px; }
    .section-header { font-size: 1.5em; color: #232F3E; font-weight: 600; border-bottom: 2px solid #FF9900; padding-bottom: 10px; margin-top: 30px; margin-bottom: 20px; }
    .stButton>button { background-color: #FF9900; color: white; font-size: 1.2em; border-radius: 10px; height: 3em; }
    [data-testid="stImage"] { display: block; margin-left: auto; margin-right: auto; }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 🔐 安全与设置
# ==========================================
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False
    if not st.session_state.password_correct:
        st.sidebar.header("🔐 安全登录")
        pwd = st.sidebar.text_input("请输入访问密码", type="password")
        if st.sidebar.button("验证"):
            if pwd == st.secrets["APP_PASSWORD"]:
                st.session_state.password_correct = True
                st.rerun()
            else:
                st.sidebar.error("❌ 密码错误")
        st.stop()
check_password()

try:
    openai_key = st.secrets["OPENAI_KEY"]
    fal_key = st.secrets["FAL_KEY"]
except:
    st.error("❌ Secrets 配置错误，请检查后台。")
    st.stop()

# 侧边栏
with st.sidebar:
    st.title("⚙️ 全局设置")
    st.success("✅ 聚合平台模式")
    
    # 默认填入 Vector Engine 的地址
    base_url = st.text_input("中转接口地址", value="https://api.vectorengine.ai")
    st.info("💎 模型: Flux.1 [Dev]")
    st.caption("⚡ 已开启 502/500 自动重连")

# ==========================================
# 🛠️ 核心功能函数
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

def fal_request_relay_retry(api_key, base_url, model, data):
    """死磕版请求函数：遇到500/502会自动重试8次"""
    base_url = base_url.rstrip("/")
    submit_url = f"{base_url}/{model}"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    
    max_retries = 8
    for attempt in range(max_retries):
        try:
            resp = requests.post(submit_url, json=data, headers=headers)
            
            # 遇到服务器拥堵，休息3秒重试
            if resp.status_code in [500, 502, 503, 504]:
                st.toast(f"⚠️ 服务器拥堵 ({resp.status_code})，第 {attempt+1} 次尝试挤入...")
                time.sleep(3)
                continue
            
            if resp.status_code != 200:
                st.error(f"❌ 请求失败 (代码 {resp.status_code}): {resp.text}")
                return None
            
            res_json = resp.json()
            break
        except Exception as e:
            st.error(f"网络错误: {e}")
            return None
    else:
        st.error("❌ 尝试 8 次失败，服务器当前不可用，请稍后再试。")
        return None

    # 获取结果逻辑
    if "images" in res_json: return res_json["images"][0]["url"]
    
    if "response_url" in res_json:
        poll_url = res_json["response_url"]
        if "queue.fal.run" in poll_url:
             target_path = poll_url.split("queue.fal.run")[-1]
             poll_url = f"{base_url}{target_path}"
    else: return None

    # 轮询
    for i in range(60): 
        time.sleep(2)
        try:
            poll_resp = requests.get(poll_url, headers=headers)
            if poll_resp.status_code == 200:
                poll_data = poll_resp.json()
                if "images" in poll_data: return poll_data["images"][0]["url"]
        except: pass
    return None

def generate_scene_dev(api_key, base_url, original_img, prompt, strength, w, h):
    base64_img = image_to_base64(original_img)
    # 这里的 Prompt 强调保留产品
    full_prompt = f"{prompt}. The main product in the image stays unchanged. High quality, 8k."
    
    data = {
        "prompt": full_prompt, "image_url": base64_img, "strength": strength, 
        "image_size": {"width": w, "height": h}, "num_inference_steps": 28, 
        "guidance_scale": 3.5, "enable_safety_checker": False
    }
    return fal_request_relay_retry(api_key, base_url, "fal-ai/flux-1/dev", data)

def get_gpt_instruction_batch(api_key, long_text, product_name, style, num_images=6):
    """防崩版 GPT 指令函数"""
    client = OpenAI(api_key=api_key)
    prompt = f"""
    Role: Amazon Art Director. Product: {product_name}. 
    Input Description: "{long_text}". Target Style: {style}.
    Task: Generate {num_images} distinct visual concepts.
    Output Format: Exactly {num_images} lines. Each line: TITLE | SUBTITLE | PROMPT
    """
    
    fallback = [["Feature", "Highlight", f"Photo of {product_name}"]] * num_images
    
    try:
        res = client.chat.completions.create(
            model="gpt-4o", messages=[{"role": "user", "content": prompt}]
        )
        content = res.choices[0].message.content.strip()
        lines = content.split("\n")
        results = []
        for line in lines:
            if not line.strip(): continue
            parts = line.split("|")
            if len(parts) >= 3:
                results.append([p.strip() for p in parts])
        
        while len(results) < num_images:
            results.append(["Extra View", "Detail", f"Professional shot of {product_name}"])
            
        return results[:num_images]
    except:
        return fallback

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
# 🎨 主界面布局
# ==========================================
st.markdown('<p class="main-title">✨ Amazon AI Creative Studio ✨</p>', unsafe_allow_html=True)

main_col1, main_col2 = st.columns([3, 2], gap="large")

with main_col1:
    st.markdown('<p class="section-header">📦 Step 1: 上传产品</p>', unsafe_allow_html=True)
    product_name = st.text_input("产品名称", placeholder="e.g. Water Bottle")
    
    col_up1, col_up2 = st.columns([3, 2])
    with col_up1:
        uploaded_file = st.file_uploader("📂 上传图片 (推荐白底)", type=["jpg", "png", "jpeg"])
        if uploaded_file:
            original_img = Image.open(uploaded_file)
            st.success("✅ 图片已加载")

    with col_up2:
        if uploaded_file:
            st.image(original_img, caption="预览", width=200)

    st.markdown('<p class="section-header">📝 Step 2: 卖点描述</p>', unsafe_allow_html=True)
    long_text_input = st.text_area("粘贴整段英文描述", height=150)

with main_col2:
    st.markdown('<p class="section-header">🎨 Step 3: 风格与设置</p>', unsafe_allow_html=True)
    with st.container(border=True):
        style_map = {
            "Lifestyle (生活实景)": "🌿 Lifestyle",
            "Studio (极简棚拍)": "💡 Studio Clean",
            "Luxury (高端暗调)": "✨ Luxury Dark",
            "Outdoors (自然户外)": "🏔️ Outdoors",
            "Creative (创意合成)": "🎨 Creative"
        }
        selected_style_key = st.radio("风格基调:", list(style_map.keys()), format_func=lambda x: style_map[x])

        st.markdown("---")
        mode = st.radio("图片用途:", ("Listing (详情页)", "A+ Content (A+页面)"), horizontal=True)
        
        if "Listing" in mode:
            size_opt = st.selectbox("画布尺寸", ["1024x1024 (标准方图)", "832x1216 (手机长图)"])
            wh_map = {"1024x1024 (标准方图)": (1024, 1024), "832x1216 (手机长图)": (832, 1216)}
        else:
            size_opt = st.selectbox("画布尺寸", ["970x600 (A+大图)", "970x300 (品牌横幅)"])
            wh_map = {"970x600 (A+大图)": (1536, 896), "970x300 (品牌横幅)": (1536, 512)}
        w, h = wh_map[size_opt]

        st.markdown("---")
        strength = st.slider("产品保留度", 0.5, 1.0, 0.75)

st.markdown("---")
btn_generate = st.button("🚀 立即生成 6 张套图 ✨", type="primary", use_container_width=True)

if btn_generate:
    if not uploaded_file or not long_text_input or not base_url:
        st.error("⚠️ 请完善信息：图片、文案、接口地址不能为空。")
        st.stop()
        
    st.markdown('<p class="section-header">🎉 生成结果 (Gallery)</p>', unsafe_allow_html=True)
    
    with st.status("🧠 AI 正在构思...", expanded=True) as status:
        gpt_results = get_gpt_instruction_batch(openai_key, long_text_input, product_name, selected_style_key, num_images=6)
        st.success(f"✅ 已生成 {len(gpt_results)} 个方案")
        status.update(label="开始绘图", state="complete", expanded=False)

    rows = [st.columns(3), st.columns(3)]
    
    for i, item in enumerate(gpt_results):
        title, subtitle, prompt = item[0], item[1], item[2]
        row_idx = i // 3
        col_idx = i % 3
        
        if row_idx < 2:
            with rows[row_idx][col_idx]:
                with st.spinner(f"绘制图 {i+1}..."):
                    final_url = generate_scene_dev(fal_key, base_url, original_img, prompt, strength, w, h)
                    
                    if final_url:
                        img_data = requests.get(final_url).content
                        final_pil = add_text(Image.open(BytesIO(img_data)), title, subtitle)
                        st.image(final_pil, caption=title, use_column_width=True)
                        
                        dl_data = convert_image_to_bytes(final_pil)
                        st.download_button(f"📥 下载", dl_data, f"img_{i}.png", "image/png", key=f"dl_{i}")
                    else:
                        st.error("服务器拥堵 (500/502)")