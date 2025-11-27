import streamlit as st
import requests
import time
import base64
from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO

# ==========================================
# ✨ 硅基流动专用版 (SiliconFlow Edition)
# ==========================================
st.set_page_config(
    page_title="Amazon AI Studio (SiliconFlow)",
    page_icon="🚀",
    layout="wide"
)

# CSS 美化
st.markdown("""
    <style>
    .main-title { font-size: 2.5em; color: #7047EB; font-weight: bold; text-align: center; margin-bottom: 20px; }
    .stButton>button { background-color: #7047EB; color: white; border-radius: 8px; height: 3em; font-size: 1.1em;}
    </style>
""", unsafe_allow_html=True)

# 1. 安全登录
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

# 2. 读取 Key (双 Key 合一)
try:
    # 硅基流动一个 Key 通吃
    sf_key = st.secrets["FAL_KEY"] 
except:
    st.error("❌ Secrets 配置错误")
    st.stop()

# 3. 侧边栏设置
with st.sidebar:
    st.title("⚙️ 设置面板")
    st.success("✅ 已连接: 硅基流动")
    
    # 硅基流动的固定地址
    base_url = "https://api.siliconflow.cn/v1"
    
    st.markdown("---")
    st.header("🎨 风格与尺寸")
    
    style_opt = st.selectbox("图片风格", [
        "Lifestyle (生活实景)", 
        "Studio (极简棚拍)", 
        "Luxury (高端暗调)", 
        "Outdoors (自然户外)"
    ])
    
    mode = st.radio("图片用途", ("Listing (详情页)", "A+ Content (A+页面)"))
    
    if "Listing" in mode:
        size_str = "1024x1024"
    else:
        # 硅基流动目前对 Flux 的尺寸支持比较标准
        size_str = "1024x576" # 接近 16:9 的宽幅
    
    st.info(f"📐 生成分辨率: {size_str}")

# 4. 核心功能函数

def convert_image_to_bytes(img):
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

def generate_image_siliconflow(api_key, prompt, size):
    """调用硅基流动的 Flux 模型"""
    url = "https://api.siliconflow.cn/v1/images/generations"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    # 硅基流动的标准 Payload
    data = {
        "model": "black-forest-labs/FLUX.1-dev", # 顶级模型
        "prompt": f"{prompt}. High quality, 8k, photorealistic, commercial photography.",
        "image_size": size,
        "num_inference_steps": 28,
        "seed": int(time.time()) # 随机种子
    }
    
    try:
        resp = requests.post(url, json=data, headers=headers)
        
        if resp.status_code != 200:
            st.error(f"❌ 生成失败 (代码 {resp.status_code})")
            st.code(resp.text)
            return None
            
        res_json = resp.json()
        # 解析返回的图片链接
        if "data" in res_json and len(res_json["data"]) > 0:
            return res_json["data"][0]["url"]
        else:
            st.error("API 返回格式异常")
            return None
            
    except Exception as e:
        st.error(f"网络错误: {e}")
        return None

def get_gpt_instruction(api_key, text, product_name, style):
    # 使用硅基流动的 LLM (Qwen 或 DeepSeek) 来省钱，或者继续用 GPT格式
    client = OpenAI(
        api_key=api_key, 
        base_url="https://api.siliconflow.cn/v1"
    )
    
    prompt = f"""
    Role: Amazon Art Director. 
    Product: {product_name}. 
    User Input: {text}. 
    Style: {style}.
    Task: Create a detailed visual prompt for Flux AI. Describe the product appearance in detail since we are generating from text.
    Output Format: TITLE | SUBTITLE | PROMPT
    """
    try:
        # 硅基流动免费送 Qwen/DeepSeek，我们可以用 Qwen2.5-72B，非常强且免费/便宜
        res = client.chat.completions.create(
            model="Qwen/Qwen2.5-72B-Instruct", 
            messages=[{"role": "user", "content": prompt}]
        )
        return res.choices[0].message.content.split("|")
    except Exception as e:
        st.warning(f"文案生成出错: {e}，将使用默认提示词")
        return ["Feature", text, f"Professional photo of {product_name}, {text}"]

def add_text(image, title, subtitle):
    draw = ImageDraw.Draw(image)
    w, h = image.size
    draw.rectangle([(0, h - h//5), (w, h)], fill=(0, 0, 0, 180))
    try: font = ImageFont.truetype("arial.ttf", int(h/20))
    except: font = ImageFont.load_default()
    draw.text((30, h - h//5 + 20), title.strip(), fill="white", font=font)
    draw.text((30, h - h//5 + 60), subtitle.strip(), fill="#CCCCCC", font=font)
    return image

# --- 主界面 ---
st.markdown('<p class="main-title">🚀 Amazon AI Studio (SiliconFlow)</p>', unsafe_allow_html=True)
st.caption("Powered by 硅基流动 - 极速稳定版")

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("📦 产品信息")
    product_name = st.text_input("产品名称 (必填)", placeholder="e.g. Blue Running Shoes")
    # 硅基标准版暂不传图，靠文字描述生成
    # uploaded_file = st.file_uploader("上传参考图 (仅作展示)", type=["jpg", "png"])
    
    st.subheader("📝 卖点描述")
    texts = [st.text_input(f"卖点 {i+1}", key=i) for i in range(1)]
    
    st.info("💡 提示：因为切换到了硅基流动标准版，AI 会根据您的【产品名称】和【卖点】直接绘制产品。Flux 模型非常聪明，只要描述准确，效果很棒！")
    
    btn = st.button("🚀 立即生成", type="primary", use_container_width=True)

with col2:
    st.subheader("🖼️ 生成结果")
    if btn and product_name:
        for i, text in enumerate([t for t in texts if t]):
            
            # 1. 调用 LLM 写 Prompt
            with st.status("🧠 AI 正在构思方案..."):
                info = get_gpt_instruction(sf_key, text, product_name, style_opt)
                if len(info)<3: info=["Title","Sub",text]
            
            # 2. 调用 Flux 画图
            st.info(f"🎨 正在绘制: {info[2]}")
            img_url = generate_image_siliconflow(sf_key, info[2], size_str)
            
            if img_url:
                st.success("✅ 生成成功！")
                img_data = requests.get(img_url).content
                final_pil = add_text(Image.open(BytesIO(img_data)), info[0], info[1])
                
                st.image(final_pil, caption=f"{style_opt}", use_column_width=True)
                
                dl_data = convert_image_to_bytes(final_pil)
                st.download_button("📥 下载图片", dl_data, f"img_{i}.png", "image/png")
            else:
                st.error("生成失败，请检查余额或网络。")