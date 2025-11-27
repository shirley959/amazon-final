import streamlit as st
import requests
import time
import base64
from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO

# ==========================================
# ✨ UI 设计与页面配置区
# ==========================================
st.set_page_config(
    page_title="Amazon AI Creative Studio",
    page_icon="✨",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 引入一些自定义 CSS 来美化标题和间距
st.markdown("""
    <style>
    .main-title {
        font-size: 2.5em;
        color: #FF9900; /* 亚马逊橙 */
        font-weight: bold;
        text-align: center;
        margin-bottom: 20px;
    }
    .section-header {
        font-size: 1.5em;
        color: #232F3E; /* 亚马逊深蓝 */
        font-weight: 600;
        border-bottom: 2px solid #FF9900;
        padding-bottom: 10px;
        margin-top: 30px;
        margin-bottom: 20px;
    }
    .stButton>button {
        background-color: #FF9900;
        color: white;
        font-size: 1.2em;
        border-radius: 10px;
        height: 3em;
    }
    /* 让图片预览居中且紧凑 */
    [data-testid="stImage"] {
        display: block;
        margin-left: auto;
        margin-right: auto;
    }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 🔐 安全与设置区 (侧边栏)
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

# 读取 Key
try:
    openai_key = st.secrets["OPENAI_KEY"]
    fal_key = st.secrets["FAL_KEY"]
except:
    st.error("❌ Secrets 配置错误，请检查后台。")
    st.stop()

# 侧边栏全局设置
with st.sidebar:
    st.title("⚙️ 全局设置")
    st.success("✅ 服务器连接就绪")
    
    with st.expander("🔌 接口与模型设置", expanded=True):
        base_url = st.text_input("中转接口地址 (Base URL)", value="https://api.vectorengine.ai")
        st.info("💎 核心模型: Flux.1 [Dev]")
        st.caption("⚡ 已激活：502/500 自动重试机制")

    st.markdown("---")
    st.write("Developed for Amazon Sellers 🚀")


# ==========================================
# 🛠️ 核心功能函数区 (后端逻辑不变)
# ==========================================
# (为了代码整洁，折叠这部分，逻辑与之前“死磕版”完全一致)

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
    """死磕版请求函数 (抗 502/500)"""
    base_url = base_url.rstrip("/")
    submit_url = f"{base_url}/{model}"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    max_retries = 8 
    
    for attempt in range(max_retries):
        try:
            resp = requests.post(submit_url, json=data, headers=headers)
            if resp.status_code in [500, 502, 503, 504]:
                st.toast(f"⚠️ 服务器拥堵 ({resp.status_code})，正在第 {attempt+1} 次尝试挤入...")
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
        st.error("❌ 尝试 8 次失败，服务器当前不可用。")
        return None

    if "images" in res_json: return res_json["images"][0]["url"]
    if "response_url" in res_json:
        poll_url = res_json["response_url"]
        if "queue.fal.run" in poll_url:
             target_path = poll_url.split("queue.fal.run")[-1]
             poll_url = f"{base_url}{target_path}"
    else: return None

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
    full_prompt = f"{prompt}. The main product in the image stays unchanged. High quality, 8k."
    data = {
        "prompt": full_prompt, "image_url": base64_img, "strength": strength, 
        "image_size": {"width": w, "height": h}, "num_inference_steps": 28, 
        "guidance_scale": 3.5, "enable_safety_checker": False
    }
    return fal_request_relay_retry(api_key, base_url, "fal-ai/flux-1/dev", data)

# 修改了 GPT 指令，让它一次性提取6个点，或者基于一大段话生成
def get_gpt_instruction_batch(api_key, long_text, product_name, style, num_images=6):
    client = OpenAI(api_key=api_key)
    prompt = f"""
    Role: Amazon Art Director. Product: {product_name}. 
    Input Description: "{long_text}". 
    Target Style: {style}.
    Task: Based on the input description, generate {num_images} distinct visual concepts.
    Output Format: Return exactly {num_images} lines. Each line format: TITLE | SUBTITLE | PROMPT
    """
    try:
        res = client.chat.completions.create(
            model="gpt-4o", messages=[{"role": "user", "content": prompt}]
        )
        # 将结果按行分割，得到多个方案
        lines = res.choices[0].message.content.strip().split("\n")
        results = []
        for line in lines:
            parts = line.split("|")
            if len(parts) >= 3:
                results.append(parts)
        # 确保返回指定数量，不够就补齐
        while len(results) < num_images:
            results.append(["Feature Highlight", "High Quality", f"A professional shot of {product_name} in {style} style."])
        return results[:num_images]
    except:
        # 出错时的兜底方案
        return [["Feature", "Highlight", f"Photo of {product_name}"] * num_images]

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
# 🎨 主界面布局区 (核心修改)
# ==========================================

# 标题栏
st.markdown('<p class="main-title">✨ Amazon AI Creative Studio ✨</p>', unsafe_allow_html=True)
st.write("### 一站式生成 Listing 主图、附图及 A+ 页面素材")
st.markdown("---")

# 创建两个主要列，左侧操作，右侧预览和设置
main_col1, main_col2 = st.columns([3, 2], gap="large")

with main_col1:
    # --- 板块 1: 产品源 ---
    st.markdown('<p class="section-header">📦 Step 1: 上传产品 (Product Source)</p>', unsafe_allow_html=True)
    product_name = st.text_input("👉 输入产品名称 (例如: Stainless Steel Water Bottle)", placeholder="输入产品核心关键词...")
    
    col_up1, col_up2 = st.columns([3, 2])
    with col_up1:
        uploaded_file = st.file_uploader("📂 上传白底图或透明图 (推荐 PNG)", type=["jpg", "png", "jpeg"])
        if uploaded_file:
            original_img = Image.open(uploaded_file)
            st.success(f"✅ 已加载: {uploaded_file.name}")
        else:
            st.info("👈 请在左侧上传您的产品图片")

    with col_up2:
        # 需求 2: 紧凑型预览，固定宽度
        if uploaded_file:
            st.image(original_img, caption="当前产品预览", width=200) # 固定宽度，不再巨大
        else:
            # 占位符
            st.markdown("""
                <div style='background-color: #f0f2f6; width: 200px; height: 200px; border-radius: 10px; display: flex; justify-content: center; align-items: center; color: #888;'>
                    暂无图片
                </div>
            """, unsafe_allow_html=True)

    # --- 板块 2: 文案输入 ---
    st.markdown('<p class="section-header">📝 Step 2: 输入卖点 (Selling Points)</p>', unsafe_allow_html=True)
    # 需求 3.2: 大段文本输入框
    long_text_input = st.text_area(
        "👉 粘贴您的产品描述 (英文整段，AI 将自动提取 6 个卖点)", 
        height=150,
        placeholder="E.g., This thermos features double-wall vacuum insulation, keeping drinks cold for 24h and hot for 12h. Made of food-grade 18/8 stainless steel, BPA-free. Leak-proof lid design perfect for travel and outdoor activities..."
    )

with main_col2:
    # --- 板块 3: 风格与参数 ---
    st.markdown('<p class="section-header">🎨 Step 3: 风格与尺寸 (Style & Size)</p>', unsafe_allow_html=True)
    
    with st.container(border=True):
        st.subheader("① 选择视觉风格")
        # 使用带图标的 Radio，视觉上更直观
        style_icon_map = {
            "Lifestyle (生活实景)": "🌿 Lifestyle",
            "Studio (极简棚拍)": "💡 Studio Clean",
            "Luxury (高端暗调)": "✨ Luxury Dark",
            "Outdoors (自然户外)": "🏔️ Outdoors",
            "Creative (创意合成)": "🎨 Creative"
        }
        selected_style_key = st.radio(
            "选择一种风格基调:", 
            list(style_icon_map.keys()),
            format_func=lambda x: style_icon_map[x],
            horizontal=False
        )

        st.markdown("---")
        st.subheader("② 选择应用场景与尺寸")
        mode = st.radio("图片用途:", ("Listing (详情页)", "A+ Content (A+页面)"), horizontal=True)
        
        if "Listing" in mode:
            size_opt = st.selectbox("画布尺寸", ["1024x1024 (标准方图)", "832x1216 (手机长图)"])
            wh_map = {"1024x1024 (标准方图)": (1024, 1024), "832x1216 (手机长图)": (832, 1216)}
        else:
            size_opt = st.selectbox("画布尺寸", ["970x600 (A+大图)", "970x300 (品牌横幅)"])
            wh_map = {"970x600 (A+大图)": (1536, 896), "970x300 (品牌横幅)": (1536, 512)} # 调整了分辨率比例以获得更好效果
        w, h = wh_map[size_opt]

        st.markdown("---")
        st.subheader("③ 高级微调")
        strength = st.slider("产品保留度 (Strength)", 0.5, 1.0, 0.75, help="数值越高，对原产品的改动越小。推荐 0.75-0.85")

# --- 生成按钮区 ---
st.markdown("---")
# 使用全宽大按钮
btn_generate = st.button("🚀 立即启动 AI 引擎，生成 6 张套图 ✨", type="primary", use_container_width=True)

# ==========================================
# 🖼️ 结果展示区 (画廊布局)
# ==========================================
if btn_generate:
    # 基本校验
    if not uploaded_file or not long_text_input or not base_url or not product_name:
        st.error("⚠️ 请确保您已上传图片、填写了产品名称和描述，并确认接口地址正确。")
        st.stop()
        
    st.markdown('<p class="section-header">🎉 Step 4: 生成结果 (Results Gallery)</p>', unsafe_allow_html=True)
    
    # 1. GPT 分析文案
    with st.status("🧠 AI 大脑正在分析文案并构思画面...", expanded=True) as status:
        st.write("正在调用 GPT-4o 提取卖点...")
        # 调用新的批量生成指令函数
        gpt_results = get_gpt_instruction_batch(openai_key, long_text_input, product_name, selected_style_key, num_images=6)
        st.success(f"✅ 成功构思了 {len(gpt_results)} 个创意方案！")
        status.update(label="🧠 文案构思完成，准备绘图！", state="complete", expanded=False)

    # 2. 循环绘图并展示 (3x2 网格布局)
    result_container = st.container()
    with result_container:
        # 创建两行，每行三列
        rows = [st.columns(3), st.columns(3)]
        
        for i, (title, subtitle, prompt) in enumerate(gpt_results):
            # 计算当前在第几行第几列
            row_idx = i // 3
            col_idx = i % 3
            current_col = rows[row_idx][col_idx]
            
            with current_col:
                with st.spinner(f"🎨 正在绘制第 {i+1} 张图..."):
                    # 调用死磕版绘图函数
                    final_url = generate_scene_dev(fal_key, base_url, original_img, prompt, strength, w, h)
                    
                    if final_url:
                        # 下载并加字
                        img_data = requests.get(final_url).content
                        final_pil = add_text(Image.open(BytesIO(img_data)), title, subtitle)
                        
                        # 展示图片
                        st.image(final_pil, caption=f"图 {i+1}: {title}", use_column_width=True)
                        
                        # 提供下载按钮
                        dl_data = convert_image_to_bytes(final_pil)
                        st.download_button(
                            f"📥 下载图 {i+1}",
                            dl_data,
                            file_name=f"{product_name}_{mode}_{i+1}.png",
                            mime="image/png",
                            key=f"btn_dl_{i}"
                        )
                    else:
                        st.error(f"图 {i+1} 生成失败，服务器拥堵。")
                        # 放一个占位图
                        st.markdown("<div style='height:200px; background:#eee; text-align:center; padding-top:80px;'>Generation Failed</div>", unsafe_allow_html=True)

    st.success("🎉 所有任务处理完毕！请及时下载满意的图片。")