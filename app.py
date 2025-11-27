import streamlit as st
import requests
import time
import base64
from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO

# --- 1. 页面配置 ---
st.set_page_config(page_title="Amazon AI Studio (Anti-502)", layout="wide")

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
    st.error("❌ Secrets 读取失败，请检查配置")
    st.stop()

# --- 4. 侧边栏配置 ---
with st.sidebar:
    st.success("✅ 系统就绪")
    st.info("💎 模型: Flux.1 [Dev]")
    
    # 这里记得填对，不要带 /v1
    base_url = st.text_input("中转接口地址", value="https://api.vectorengine.ai")
    st.caption("⚡ 已开启 502/500 自动重连模式")
    
    st.markdown("---")
    st.header("🎨 风格与尺寸")
    
    style_opt = st.selectbox("图片风格", [
        "Lifestyle (生活实景)", 
        "Studio (极简棚拍)", 
        "Luxury (高端暗调)", 
        "Outdoors (自然户外)"
    ])
    
    strength = st.slider("产品保留度", 0.5, 1.0, 0.75, help="推荐 0.75")
    
    mode = st.radio("图片类型", ("Listing Images (详情页)", "A+ Content (A+页面)"))
    
    if "Listing" in mode:
        size_opt = st.selectbox("选择尺寸", ["1024x1024 (标准)", "832x1216 (手机长图)"])
        wh_map = {"1024x1024 (标准)": (1024, 1024), "832x1216 (手机长图)": (832, 1216)}
    else:
        size_opt = st.selectbox("选择尺寸", ["970x300 (品牌横幅)", "970x600 (大图模块)"])
        wh_map = {"970x300 (品牌横幅)": (1536, 512), "970x600 (大图模块)": (1216, 768)}
    
    w, h = wh_map[size_opt]

# --- 5. 核心功能 ---

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
    """超级死磕版请求函数"""
    base_url = base_url.rstrip("/")
    submit_url = f"{base_url}/{model}"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    
    # 增加到 8 次重试
    max_retries = 8 
    
    for attempt in range(max_retries):
        try:
            resp = requests.post(submit_url, json=data, headers=headers)
            
            # !!! 关键更新：把 502 也加入了重试名单 !!!
            if resp.status_code in [500, 502, 503, 504]:
                st.toast(f"⚠️ 服务器崩溃 ({resp.status_code})，第 {attempt+1} 次尝试重连...")
                time.sleep(3) # 休息3秒，给服务器喘口气
                continue
            
            if resp.status_code != 200:
                st.error(f"❌ 请求被拒绝 (代码 {resp.status_code})")
                st.code(resp.text) # 打印错误给用户看
                return None
            
            # 成功挤进去了！
            res_json = resp.json()
            break
            
        except Exception as e:
            st.error(f"网络连接错误: {e}")
            return None
    else:
        st.error("❌ 试了8次，服务器还是 502 Bad Gateway。")
        st.warning("💡 建议：该中转平台极其不稳定，建议过半小时再试，或联系他们的客服报错。")
        return None

    # 获取结果
    if "images" in res_json: return res_json["images"][0]["url"]
    
    if "response_url" in res_json:
        poll_url = res_json["response_url"]
        if "queue.fal.run" in poll_url:
             target_path = poll_url.split("queue.fal.run")[-1]
             poll_url = f"{base_url}{target_path}"
    else:
        st.error("数据异常")
        return None

    # 轮询
    placeholder = st.empty()
    for i in range(60): 
        placeholder.text(f"⏳ 正在绘制... ({i*2}s)")
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
    full_prompt = f"{prompt}. The main product in the image stays unchanged. High quality, 8k."
    
    data = {
        "prompt": full_prompt, "image_url": base64_img, "strength": strength, 
        "image_size": {"width": w, "height": h}, "num_inference_steps": 28, 
        "guidance_scale": 3.5, "enable_safety_checker": False
    }
    return fal_request_relay_retry(api_key, base_url, "fal-ai/flux-1/dev", data)

def get_gpt_instruction(api_key, text, product_name, style):
    client = OpenAI(api_key=api_key)
    prompt = f"Role: Amazon Art Director. Product: {product_name}. Input: {text}. Style: {style}. Output: TITLE | SUBTITLE | PROMPT"
    try:
        res = client.chat.completions.create(
            model="gpt-4o", messages=[{"role": "user", "content": prompt}]
        )
        return res.choices[0].message.content.split("|")
    except:
        return ["Feature", text, f"Photo of {product_name}, {text}, {style}"]

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
st.title("🛒 Amazon AI Studio (Pro)")

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("1. 上传产品")
    product_name = st.text_input("产品名称", "Product")
    uploaded_file = st.file_uploader("上传白底图", type=["jpg", "png", "jpeg"])
    
    if uploaded_file:
        original_img = Image.open(uploaded_file)
        st.image(original_img, caption="预览", use_column_width=True)
    
    st.subheader("2. 卖点描述")
    texts = [st.text_input(f"卖点 {i+1}", key=i) for i in range(1)]
    btn = st.button("🚀 开始生成", type="primary")

with col2:
    st.subheader("3. 结果")
    if btn and uploaded_file and base_url:
        st.info("🔄 初始化...")
        original_img = Image.open(uploaded_file)
        
        for i, text in enumerate([t for t in texts if t]):
            # 传入 style_opt 变量 (需要先定义)
            # 抱歉，刚才漏了定义 style_opt 的变量传递，这里补上：
            # 在侧边栏定义的 style_opt 已经有了，直接用
            
            info = get_gpt_instruction(openai_key, text, product_name, style_opt)
            if len(info)<3: info=["Title","Sub",text]
            
            st.info(f"🎨 正在生成 (Style: {style_opt})...")
            
            final_url = generate_scene_dev(fal_key, base_url, original_img, info[2], strength, w, h)
            
            if final_url:
                st.success("✅ 生成成功！")
                img_data = requests.get(final_url).content
                final_result = add_text(Image.open(BytesIO(img_data)), info[0], info[1])
                st.image(final_result, caption=f"最终效果", use_column_width=True)
                
                dl_data = convert_image_to_bytes(final_result)
                st.download_button("📥 下载图片", dl_data, f"img_{i}.png", "image/png")
            else:
                st.error("😭 服务器实在太烂了，一直 502。请稍后再试。")