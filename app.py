import streamlit as st
import requests
import time
import base64
from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO

# --- 1. 页面基础设置 ---
st.set_page_config(page_title="Amazon AI Studio (Final Dev)", layout="wide")

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
openai_key = st.secrets["OPENAI_KEY"]
fal_key = st.secrets["FAL_KEY"]

# --- 4. 侧边栏 ---
with st.sidebar:
    st.success("✅ 验证通过")
    st.info("💎 当前模型: Flux.1 [Dev] 高清版")
    
    # 帮你把默认地址改成了你现在的平台，注意不要带 /v1
    base_url = st.text_input("中转接口地址", value="https://api.vectorengine.ai")
    
    st.markdown("---")
    # Strength: 控制产品保留度。0.75 是比较平衡的
    strength = st.slider("产品保留度 (Strength)", 0.5, 1.0, 0.75, help="越低越像原图，越高背景融合越好")
    
    mode = st.radio("尺寸", ("Listing (1024x1024)", "A+ Banner (1536x512)"))
    if "Listing" in mode: w, h = 1024, 1024
    else: w, h = 1536, 512

# --- 5. 核心功能函数 ---

def image_to_base64(image):
    """图片转字符"""
    buffered = BytesIO()
    image.convert("RGB").save(buffered, format="JPEG")
    img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
    return f"data:image/jpeg;base64,{img_str}"

def fal_request_relay(api_key, base_url, model, data):
    """发送请求到中转站"""
    # 1. 处理地址
    base_url = base_url.rstrip("/")
    submit_url = f"{base_url}/{model}"
    
    st.caption(f"正在连接: {submit_url} ...") # 显示正在连哪里，方便排查
    
    headers = {
        "Authorization": f"Bearer {api_key}", 
        "Content-Type": "application/json"
    }
    
    # 2. 提交任务
    try:
        resp = requests.post(submit_url, json=data, headers=headers)
        
        # 如果报错，直接打印中转站的回复
        if resp.status_code != 200:
            st.error(f"❌ 请求被拒绝 (代码 {resp.status_code})")
            st.code(resp.text) # 打印详细错误信息
            st.stop()
            
        res_json = resp.json()
    except Exception as e:
        st.error(f"网络连接失败: {e}")
        return None

    # 3. 处理结果 (兼容直接返回和轮询)
    if "images" in res_json:
        return res_json["images"][0]["url"]
    
    if "response_url" in res_json:
        poll_url = res_json["response_url"]
        # 修正轮询地址域名
        if "queue.fal.run" in poll_url:
             target_path = poll_url.split("queue.fal.run")[-1]
             poll_url = f"{base_url}{target_path}"
    else:
        st.error("中转站返回数据异常，找不到图片或查询地址")
        st.write(res_json)
        return None

    # 4. 轮询等待
    placeholder = st.empty()
    for i in range(30): 
        placeholder.text(f"⏳ AI 正在精心绘制... ({i*2}s)")
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
    """调用 Flux Dev 模型"""
    base64_img = image_to_base64(original_img)
    
    # Prompt 强调保留产品
    full_prompt = f"{prompt}. The main product in the image stays unchanged. High quality, 8k, photorealistic."
    
    data = {
        "prompt": full_prompt,
        "image_url": base64_img,
        "strength": strength, 
        "image_size": {"width": w, "height": h},
        "num_inference_steps": 28, # Dev 模型必须 28 步以上
        "guidance_scale": 3.5,
        "enable_safety_checker": False
    }
    
    # 切换回通用的 Dev 模型
    return fal_request_relay(api_key, base_url, "fal-ai/flux-1/dev", data)

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
st.title("🛒 Amazon AI Studio (中转站适配版)")

col1, col2 = st.columns([1, 1])
with col1:
    product_name = st.text_input("产品名称", "Product")
    uploaded_file = st.file_uploader("📂 上传产品图 (白底)", type=["jpg", "png", "jpeg"])
    texts = [st.text_input(f"卖点 {i+1}", key=i) for i in range(1)]
    btn = st.button("🚀 开始生成", type="primary")

with col2:
    if btn and uploaded_file and base_url:
        st.info("🔄 正在处理...")
        original_img = Image.open(uploaded_file)
        
        for i, text in enumerate([t for t in texts if t]):
            info = get_gpt_instruction(openai_key, text, product_name)
            if len(info)<3: info=["Title","Sub",text]
            
            st.info(f"🎨 正在生成 (Prompt: {info[2]})...")
            
            # 调用 Dev 版生成函数
            final_url = generate_scene_dev(fal_key, base_url, original_img, info[2], strength, w, h)
            
            if final_url:
                st.success("✅ 生成成功！")
                img_data = requests.get(final_url).content
                final_result = add_text(Image.open(BytesIO(img_data)), info[0], info[1])
                st.image(final_result, caption="最终结果", use_column_width=True)
            else:
                st.error("生成超时或失败，请查看上方报错详情")