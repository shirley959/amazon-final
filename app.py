import streamlit as st
import requests
import time
import base64
from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO

# --- 1. 页面配置 ---
st.set_page_config(page_title="Amazon AI Studio (Ultimate Relay)", layout="wide")

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
    st.warning("👇 必填：聚合平台域名")
    # 比如 https://api.openai-hk.com
    base_url = st.text_input("中转接口地址 (BASE_URL)", value="https://api.openai-hk.com") 
    
    st.markdown("---")
    st.header("🖼️ 生成设置")
    mode = st.radio("选择模式", ("Listing Images (主图/附图)", "A+ Content (品牌横幅)"))
    
    if "Listing" in mode:
        width, height = 1024, 1024
    else:
        width, height = 1536, 512

# --- 5. 核心工具函数 (适配中转站) ---

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

    if "response_url" in res_json:
        # 替换为中转域名进行查询
        target_path = res_json["response_url"].split("queue.fal.run")[-1]
        poll_url = f"{base_url}{target_path}"
    else:
        # 有些中转站直接返回结果，做个兼容
        if "images" in res_json: return res_json["images"][0]["url"]
        st.error("中转站未返回查询地址")
        return None

    placeholder = st.empty()
    for i in range(60): 
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

def step_1_remove_bg(api_key, base_url, original_image):
    # 步骤1：调用 BirefNet 抠图
    base64_str = image_to_base64(original_image)
    data = {"image_url": base64_str} 
    return fal_request_relay(api_key, base_url, "fal-ai/birefnet", data)

def step_2_generate_scene(api_key, base_url, clean_img_url, prompt, w, h):
    # 步骤2：Flux 场景融合
    data = {
        "prompt": f"{prompt}. Product integrated naturally. High quality, 8k.",
        "image_url": clean_img_url, 
        "strength": 0.95, 
        "image_size": {"width": w, "height": h},
        "num_inference_steps": 28,
        "guidance_scale": 3.5
    }
    return fal_request_relay(api_key, base_url, "fal-ai/flux-1/dev/image-to-image", data)

def get_gpt_instruction(api_key, text, product_name, mode):
    client = OpenAI(api_key=api_key)
    prompt = f"Role: Amazon Art Director. Product: {product_name}. Input: {text}. Mode: {mode}. Output: TITLE | SUBTITLE | PROMPT"
    try:
        res = client.chat.completions.create(
            model="gpt-4o", messages=[{"role": "user", "content": prompt}]
        )
        return res.choices[0].message.content.split("|")
    except:
        return ["Feature", text, f"Photo of {product_name}"]

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
st.title("🛒 Amazon AI Studio (Relay)")

col1, col2 = st.columns([1, 1])
with col1:
    product_name = st.text_input("产品名称", "Product")
    uploaded_file = st.file_uploader("📂 上传任意背景图", type=["jpg", "png", "jpeg"])
    texts = [st.text_input(f"卖点 {i+1}", key=i) for i in range(1)] # 演示只生成1张
    btn = st.button("🚀 开始生成", type="primary")

with col2:
    if btn and uploaded_file and base_url:
        st.info("✂️ 正在智能抠图...")
        original_img = Image.open(uploaded_file)
        clean_url = step_1_remove_bg(fal_key, base_url, original_img)
        
        if clean_url:
            st.image(clean_url, width=150, caption="抠图成功")
            for i, text in enumerate([t for t in texts if t]):
                st.info(f"🎨 正在生成场景图...")
                info = get_gpt_instruction(openai_key, text, product_name, mode)
                if len(info)<3: info=["Title","Sub",text]
                
                final_url = step_2_generate_scene(fal_key, base_url, clean_url, info[2], width, height)
                if final_url:
                    img_data = requests.get(final_url).content
                    final_result = add_text(Image.open(BytesIO(img_data)), info[0], info[1])
                    st.image(final_result, caption="最终结果", use_column_width=True)
        else:
            st.error("抠图失败，请检查中转站是否支持 fal-ai/birefnet")