import streamlit as st
import requests
import base64
import time
from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO

# ==========================================
# ✨ 页面配置
# ==========================================
st.set_page_config(
    page_title="Amazon AI Studio (SiliconFlow Img2Img)",
    page_icon="🚀",
    layout="wide"
)

# CSS 美化
st.markdown("""
    <style>
    .main-title { font-size: 2.5em; color: #7047EB; font-weight: bold; text-align: center; margin-bottom: 20px; }
    .stButton>button { background-color: #7047EB; color: white; border-radius: 8px; height: 3em; font-size: 1.2em;}
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 🔐 安全登录
# ==========================================
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False
    if not st.session_state.password_correct:
        pwd = st.sidebar.text_input("🔒 访问密码", type="password")
        if st.sidebar.button("验证"):
            if pwd == st.secrets["APP_PASSWORD"]:
                st.session_state.password_correct = True
                st.rerun()
            else:
                st.sidebar.error("密码错误")
        st.stop()
check_password()

# 读取 Key (注意：这里我们用 OpenAI_KEY 这个变量来存硅基流动的 Key，方便统一)
try:
    # 请确保 Secrets 里 OPENAI_KEY 填的是硅基流动的 sk-xxx
    sf_key = st.secrets["OPENAI_KEY"] 
except:
    st.error("❌ Secrets 配置错误，请检查 OPENAI_KEY 是否填写")
    st.stop()

# ==========================================
# ⚙️ 侧边栏设置
# ==========================================
with st.sidebar:
    st.title("⚙️ 硅基流动设置")
    st.success("✅ 已连接: SiliconFlow")
    st.info("💎 模型: Flux.1 [Dev]")
    
    st.markdown("---")
    st.header("🎨 风格与参数")
    
    style_opt = st.selectbox("图片风格", [
        "Lifestyle (生活实景)", 
        "Studio (极简棚拍)", 
        "Luxury (高端暗调)", 
        "Outdoors (自然户外)"
    ])
    
    # 关键参数：控制产品变形程度
    strength = st.slider("产品重绘幅度 (Strength)", 0.5, 1.0, 0.75, 
                         help="0.75 表示：保留大部分产品特征，但在光影和背景上做融合。")
    
    mode = st.radio("图片用途", ("Listing (详情页)", "A+ Content (A+页面)"))
    
    if "Listing" in mode:
        size_str = "1024x1024"
    else:
        size_str = "1024x576" # 硅基支持的标准宽幅
    
    st.write(f"📐 分辨率: {size_str}")

# ==========================================
# 🛠️ 核心功能函数
# ==========================================

def image_to_base64(image):
    buffered = BytesIO()
    image.convert("RGB").save(buffered, format="JPEG")
    return base64.b64encode(buffered.getvalue()).decode('utf-8')

def convert_image_to_bytes(img):
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

def generate_image_siliconflow_img2img(api_key, original_img, prompt, strength, size):
    """
    调用硅基流动的 Flux 图生图接口
    注意：硅基流动的 API 路径和 Payload 与官方 Fal 不同
    """
    url = "https://api.siliconflow.cn/v1/images/generations"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    # 图片转 Base64
    base64_str = image_to_base64(original_img)
    # 补全前缀
    image_data = f"data:image/jpeg;base64,{base64_str}"
    
    # Flux 图生图 Prompt 优化
    full_prompt = f"{prompt}. The main product in the image MUST remain unchanged. Realistic physical interaction. High quality, 8k."

    data = {
        "model": "black-forest-labs/FLUX.1-dev", # 指定使用 Flux Dev
        "prompt": full_prompt,
        "image": image_data, # 硅基流动的特殊字段，传入 Base64
        "image_size": size,
        "num_inference_steps": 28,
        "prompt_enhancement": False # 关闭自动改词，听我们的
    }
    
    try:
        # 发送请求
        resp = requests.post(url, json=data, headers=headers)
        
        if resp.status_code != 200:
            st.error(f"❌ 生成失败 (代码 {resp.status_code})")
            st.code(resp.text)
            return None
            
        res_json = resp.json()
        
        # 硅基流动返回的是 data 列表
        if "data" in res_json and len(res_json["data"]) > 0:
            return res_json["data"][0]["url"]
        else:
            st.error("API 返回格式异常: " + str(res_json))
            return None
            
    except Exception as e:
        st.error(f"网络错误: {e}")
        return None

def get_gpt_instruction(api_key, text, product_name, style):
    # 使用硅基流动的 LLM (Qwen) 来生成 Prompt
    client = OpenAI(
        api_key=api_key, 
        base_url="https://api.siliconflow.cn/v1"
    )
    
    prompt = f"""
    Role: Amazon Art Director. 
    Product: {product_name}. 
    User Input: {text}. 
    Style: {style}.
    Task: Create a visual prompt for Flux AI Image-to-Image generation.
    Focus on the scene and interaction, assuming the product image is provided.
    Output Format: TITLE | SUBTITLE | PROMPT
    """
    try:
        # 使用 Qwen2.5 免费且强大
        res = client.chat.completions.create(
            model="Qwen/Qwen2.5-72B-Instruct", 
            messages=[{"role": "user", "content": prompt}]
        )
        return res.choices[0].message.content.split("|")
    except:
        return ["Feature", text, f"Photo of {product_name} interacting with {text}"]

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
st.markdown('<p class="main-title">🚀 Amazon AI Studio (SiliconFlow I2I)</p>', unsafe_allow_html=True)
st.caption("Powered by 硅基流动 - 图生图稳定版")

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("1. 上传产品")
    product_name = st.text_input("产品名称", placeholder="e.g. Clothespin")
    # 这一步很关键：上传你的白底图
    uploaded_file = st.file_uploader("📂 上传产品图 (推荐白底/透明底)", type=["jpg", "png", "jpeg"])
    
    if uploaded_file:
        original_img = Image.open(uploaded_file)
        st.image(original_img, caption="✅ 已加载源图片", width=200)
    
    st.subheader("2. 卖点描述")
    texts = [st.text_input(f"卖点 {i+1}", key=i) for i in range(1)]
    
    btn = st.button("🚀 立即生成", type="primary", use_container_width=True)

with col2:
    st.subheader("3. 生成结果")
    if btn and uploaded_file:
        for i, text in enumerate([t for t in texts if t]):
            
            # 1. 构思 Prompt
            with st.status("🧠 AI 正在构思场景..."):
                info = get_gpt_instruction(sf_key, text, product_name, style_opt)
                if len(info)<3: info=["Title","Sub",text]
            
            # 2. 调用 Flux 图生图
            st.info(f"🎨 正在绘制 (Prompt: {info[2]})...")
            
            # 这里的魔法在于：把你的 original_img 传进去了！
            img_url = generate_image_siliconflow_img2img(sf_key, original_img, info[2], strength, size_str)
            
            if img_url:
                st.success("✅ 生成成功！")
                
                # 下载并加字
                img_data = requests.get(img_url).content
                final_pil = add_text(Image.open(BytesIO(img_data)), info[0], info[1])
                
                st.image(final_pil, caption=f"风格: {style_opt}", use_column_width=True)
                
                dl_data = convert_image_to_bytes(final_pil)
                st.download_button("📥 下载图片", dl_data, f"img_{i}.png", "image/png")
            else:
                st.error("生成失败，请检查 Secrets 配置或余额。")