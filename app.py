import streamlit as st
import requests
import time
import base64
from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO

# --- 1. 页面配置 ---
st.set_page_config(page_title="Amazon AI Studio (Direct Flux)", layout="wide")

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

# --- 3. 读取后台 Key ---
openai_key = st.secrets["OPENAI_KEY"]
fal_key = st.secrets["FAL_KEY"]

# --- 4. 侧边栏配置 ---
with st.sidebar:
    st.success("✅ 验证通过")
    st.info("⚠️ 当前模式：直接融合 (跳过抠图)")
    # 默认填入你报错里的这个域名
    base_url = st.text_input("中转接口地址", value="https://api.vectorengine.ai") 
    
    st.markdown("---")
    st.header("🎨 参数设置")
    # 关键参数：控制 AI 改图的幅度
    strength = st.slider("产品保留度 (Strength)", 0.5, 1.0, 0.75, 
                         help="0.75是最佳平衡点：既能保留产品，又能融合背景。")
    
    mode = st.radio("尺寸", ("Listing (1024x1024)", "A+ Banner (1536x512)"))
    if "Listing" in mode: w, h = 1024, 1024
    else: w, h = 1536, 512

# --- 5. 核心工具函数 ---

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
        resp.raise_for_status() # 如果报错403这里会抛出异常
        res_json = resp.json()
    except Exception as e:
        st.error(f"提交任务失败: {e}")
        return None

    # 获取结果查询地址
    if "response_url" in res_json:
        target_path = res_json["response_url"].split("queue.fal.run")[-1]
        poll_url = f"{base_url}{target_path}"
    elif "images" in res_json:
        # 有的中转站秒回结果
        return res_json["images"][0]["url"]
    else:
        st.error("中转站返回格式异常")
        return None

    # 轮询
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

def generate_scene_direct(api_key, base_url, original_img, prompt, strength, w, h):
    """直接调用 Flux 图生图 (避开不支持的 Birefnet)"""
    base64_img = image_to_base64(original_img)
    
    # 既然是图生图，Prompt 必须强调保留产品
    full_prompt = f"{prompt}. The main product in the image stays unchanged, only the background changes to the described scene. High quality, 8k."
    
    data = {
        "prompt": full_prompt,
        "image_url": base64_img,
        "strength": strength, # 这里用 Strength 来控制融合
        "image_size": {"width": w, "height": h},
        "num_inference_steps": 30,
        "guidance_scale": 3.5
    }
    # 使用你支持列表里的模型
    return fal_request_relay(api_key, base_url, "fal-ai/flux-1/dev/image-to-image", data)

def get_gpt_instruction(api_key, text, product_name):
    client = OpenAI(api_key=api_key)
    prompt = f"Role: Amazon Art Director. Product: {product_name}. Input: {text}. Output: TITLE | SUBTITLE | PROMPT"
    try:
        res = client.chat.completions.create(
            model="gpt-4o", messages=[{"role": "user", "content": prompt}]
        )
        return res.choices[0].message.content.split("|")
    except:
        return ["Feature", text, f"Photo of {product_name}, {text}"]

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
st.title("🛒 Amazon AI Studio (Direct)")
st.caption("适配 Vector Engine 聚合平台 | Flux 图生图模式")

col1, col2 = st.columns([1, 1])
with col1:
    product_name = st.text_input("产品名称", "Product")
    uploaded_file = st.file_uploader("📂 上传产品图 (推荐白底)", type=["jpg", "png", "jpeg"])
    texts = [st.text_input(f"卖点 {i+1}", key=i) for i in range(1)]
    btn = st.button("🚀 开始生成", type="primary")

with col2:
    if btn and uploaded_file and base_url:
        st.info("🔄 正在处理图片...")
        original_img = Image.open(uploaded_file)
        
        # 不再调用 remove_bg，直接进入 Flux 生成
        for i, text in enumerate([t for t in texts if t]):
            info = get_gpt_instruction(openai_key, text, product_name)
            if len(info)<3: info=["Title","Sub",text]
            
            st.info(f"🎨 正在生成场景 (Prompt: {info[2]})...")
            
            # 调用 Flux 图生图
            final_url = generate_scene_direct(fal_key, base_url, original_img, info[2], strength, w, h)
            
            if final_url:
                img_data = requests.get(final_url).content
                final_result = add_text(Image.open(BytesIO(img_data)), info[0], info[1])
                st.image(final_result, caption="最终结果", use_column_width=True)
            else:
                st.error("生成失败，可能是 Strength 参数太高或 Prompt 违规")