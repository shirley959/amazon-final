import streamlit as st
import requests
import time
import base64
from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO

# --- 1. 页面配置 ---
st.set_page_config(page_title="Amazon AI Studio (Economy Mode)", layout="wide")

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
    st.info("💰 当前模式：极速省钱版 (Flux Schnell)")
    # 填入你之前报错里的那个域名
    base_url = st.text_input("中转接口地址", value="https://api.vectorengine.ai") 
    
    st.markdown("---")
    st.header("🎨 参数设置")
    # Schnell 对 Strength 不敏感，但为了兼容性保留
    strength = st.slider("产品保留度", 0.5, 1.0, 0.70)
    
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
        resp.raise_for_status() 
        res_json = resp.json()
    except Exception as e:
        st.error(f"提交任务失败: {e}")
        return None

    # 获取结果查询地址 (做了一些兼容性处理)
    if "response_url" in res_json:
        target_path = res_json["response_url"].split("queue.fal.run")[-1]
        poll_url = f"{base_url}{target_path}"
    elif "images" in res_json:
        return res_json["images"][0]["url"]
    else:
        st.error("中转站返回格式异常")
        return None

    # 轮询
    placeholder = st.empty()
    for i in range(20): # Schnell 很快，不用等太久
        placeholder.text(f"⏳ AI 正在极速绘图... ({i*1}s)")
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
    """调用便宜的 Schnell 模型"""
    base64_img = image_to_base64(original_img)
    
    full_prompt = f"{prompt}. The main product in the image stays unchanged. High quality."
    
    data = {
        "prompt": full_prompt,
        "image_url": base64_img,
        "strength": strength, 
        "image_size": {"width": w, "height": h},
        # !!! 省钱的关键点 !!!
        "num_inference_steps": 4, # Schnell 只需要 4 步 (Dev 需要 28 步)
        "guidance_scale": 3.5,
        "enable_safety_checker": False
    }
    
    # 切换到 Schnell 模型 (在你的列表里是支持的)
    return fal_request_relay(api_key, base_url, "fal-ai/flux-1/schnell", data)

def get_gpt_instruction(api_key, text, product_name):
    client = OpenAI(api_key=api_key)
    # 为了省钱，GPT prompt 也精简点
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
st.title("🛒 Amazon AI Studio (Economy Test)")
st.caption("当前使用 Flux Schnell 模型 (成本极低，仅用于测试流程)")

col1, col2 = st.columns([1, 1])
with col1:
    product_name = st.text_input("产品名称", "Product")
    uploaded_file = st.file_uploader("📂 上传产品图 (推荐白底)", type=["jpg", "png", "jpeg"])
    texts = [st.text_input(f"卖点 {i+1}", key=i) for i in range(1)]
    btn = st.button("🚀 低成本生成", type="primary")

with col2:
    if btn and uploaded_file and base_url:
        st.info("🔄 正在处理图片...")
        original_img = Image.open(uploaded_file)
        
        for i, text in enumerate([t for t in texts if t]):
            info = get_gpt_instruction(openai_key, text, product_name)
            if len(info)<3: info=["Title","Sub",text]
            
            st.info(f"🎨 正在生成 (Prompt: {info[2]})...")
            
            # 调用省钱版函数
            final_url = generate_scene_economy(fal_key, base_url, original_img, info[2], strength, w, h)
            
            if final_url:
                img_data = requests.get(final_url).content
                final_result = add_text(Image.open(BytesIO(img_data)), info[0], info[1])
                st.image(final_result, caption="测试结果 (Schnell版)", use_column_width=True)
            else:
                st.error("生成失败 (请检查余额是否彻底为0)")