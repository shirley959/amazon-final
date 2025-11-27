import streamlit as st
import requests
import time
import base64
from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO

# --- 1. 页面配置 ---
st.set_page_config(page_title="Amazon AI Studio (Fixed)", layout="wide")

# --- 2. 安全门禁 ---
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

# --- 3. 读取 Key ---
try:
    openai_key = st.secrets["OPENAI_KEY"]
    fal_key = st.secrets["FAL_KEY"]
except:
    st.error("❌ Secrets 配置读取失败")
    st.stop()

# --- 4. 侧边栏配置 ---
with st.sidebar:
    st.success("✅ 系统就绪")
    st.info("💎 模型: Flux.1 [Dev]")
    
    base_url = st.text_input("中转接口地址", value="https://api.vectorengine.ai")
    st.markdown("---")
    
    # 风格选择器
    st.header("🎨 风格与尺寸")
    style_opt = st.selectbox(
        "图片风格 (Image Style)",
        [
            "Lifestyle (生活实景 - 通用)", 
            "Studio Minimalist (极简棚拍 - 干净)", 
            "Luxury Cinematic (高端暗调 - 质感)", 
            "Nature Outdoors (自然户外 - 阳光)", 
            "Warm Home (温馨家居 - 柔和)"
        ]
    )
    
    strength = st.slider("产品保留度", 0.5, 1.0, 0.75, help="推荐 0.75-0.85")
    
    mode = st.radio("图片类型", ("Listing Images (详情页)", "A+ Content (A+页面)"))
    
    if "Listing" in mode:
        size_opt = st.selectbox("画布尺寸", ["1024x1024 (标准方图)", "832x1216 (手机端长图)"])
        wh_map = {
            "1024x1024 (标准方图)": (1024, 1024),
            "832x1216 (手机端长图)": (832, 1216)
        }
    else:
        size_opt = st.selectbox("画布尺寸", ["970x300 (品牌横幅)", "970x600 (大图模块)"])
        wh_map = {
            "970x300 (品牌横幅)": (1536, 512), 
            "970x600 (大图模块)": (1216, 768)
        }
    
    # !!! 修复点：这里改回 w, h 以匹配下方调用 !!!
    w, h = wh_map[size_opt]

# --- 5. 核心功能函数 ---

def convert_image_to_bytes(img):
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

def image_to_base64(image):
    buffered = BytesIO()
    image.convert("RGB").save(buffered, format="JPEG")
    img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
    return f"data:image/jpeg;base64,{img_str}"

def fal_request_relay(api_key, base_url, model, data):
    base_url = base_url.rstrip("/")
    submit_url = f"{base_url}/{model}"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    
    try:
        resp = requests.post(submit_url, json=data, headers=headers)
        if resp.status_code == 500:
            st.error("🚦 服务器繁忙 (500)。请稍等几分钟再试！")
            return None
        if resp.status_code != 200:
            st.error(f"❌ 请求失败 (代码 {resp.status_code}): {resp.text}")
            st.stop()
        res_json = resp.json()
    except Exception as e:
        st.error(f"网络错误: {e}")
        return None

    if "images" in res_json: return res_json["images"][0]["url"]
    
    if "response_url" in res_json:
        poll_url = res_json["response_url"]
        if "queue.fal.run" in poll_url:
             target_path = poll_url.split("queue.fal.run")[-1]
             poll_url = f"{base_url}{target_path}"
    else:
        st.error("返回数据异常")
        return None

    placeholder = st.empty()
    for i in range(40): 
        placeholder.text(f"⏳ AI 正在绘图... ({i*2}s)")
        time.sleep(2)
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

def generate_scene_dev(api_key, base_url, original_img, prompt, strength, w, h):
    base64_img = image_to_base64(original_img)
    full_prompt = f"{prompt}. The main product stays unchanged. High quality, 8k."
    data = {
        "prompt": full_prompt, "image_url": base64_img, "strength": strength, 
        "image_size": {"width": w, "height": h}, "num_inference_steps": 28, 
        "guidance_scale": 3.5, "enable_safety_checker": False
    }
    return fal_request_relay(api_key, base_url, "fal-ai/flux-1/dev", data)

def get_gpt_instruction(api_key, text, product_name, style):
    client = OpenAI(api_key=api_key)
    prompt = f"""
    Role: Amazon Art Director. 
    Product: {product_name}. 
    User Input: {text}. 
    Target Visual Style: {style}.
    Task: Create a visual prompt for Flux AI matching the style.
    Output Format: TITLE | SUBTITLE | PROMPT
    """
    try:
        res = client.chat.completions.create(
            model="gpt-4o", messages=[{"role": "user", "content": prompt}]
        )
        return res.choices[0].message.content.split("|")
    except:
        return ["Feature", text, f"Photo of {product_name}, {text}, {style} style"]

def add_text(image, title, subtitle):
    draw = ImageDraw.Draw(image)
    w, h = image.size
    draw.rectangle([(0, h - h//5), (w, h)], fill=(0, 0, 0, 180))
    try: font = ImageFont.truetype("arial.ttf", int(h/20))
    except: font = ImageFont.load_default()
    draw.text((30, h - h//5 + 20), title.strip(), fill="white", font=font)
    draw.text((30, h - h//5 + 60), subtitle.strip(), fill="#CCCCCC", font=font)
    return image

# --- 6. 主界面 ---
st.title("🛒 Amazon AI Studio (Ultimate Fixed)")

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("1. 上传产品")
    product_name = st.text_input("产品名称", "Product")
    uploaded_file = st.file_uploader("点击上传白底图", type=["jpg", "png", "jpeg"])
    
    if uploaded_file:
        original_img = Image.open(uploaded_file)
        st.image(original_img, caption="✅ 已上传预览", use_column_width=True)
    
    st.markdown("---")
    st.subheader("2. 输入卖点")
    texts = [st.text_input(f"卖点文案 {i+1}", key=i) for i in range(1)]
    btn = st.button("🚀 开始生成", type="primary")

with col2:
    st.subheader("3. 生成结果")
    if btn and uploaded_file and base_url:
        st.info(f"🔄 初始化风格: {style_opt} ...")
        
        for i, text in enumerate([t for t in texts if t]):
            info = get_gpt_instruction(openai_key, text, product_name, style_opt)
            if len(info)<3: info=["Title","Sub",text]
            
            st.info(f"🎨 正在绘图 (Prompt: {info[2]})...")
            
            # 这里的 w, h 已经被修复了
            final_url = generate_scene_dev(fal_key, base_url, original_img, info[2], strength, w, h)
            
            if final_url:
                st.success("✅ 生成成功！")
                
                img_data = requests.get(final_url).content
                final_result = add_text(Image.open(BytesIO(img_data)), info[0], info[1])
                
                st.image(final_result, caption=f"风格: {style_opt}", use_column_width=True)
                
                download_data = convert_image_to_bytes(final_result)
                st.download_button(
                    label="📥 下载高清原图",
                    data=download_data,
                    file_name=f"amazon_ai_{i+1}.png",
                    mime="image/png",
                    key=f"dl_btn_{i}"
                )