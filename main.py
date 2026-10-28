from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os

app = FastAPI()

# CORS इनेबल करें ताकि आपकी GitHub Pages वाली वेबसाइट इससे जुड़ सके
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    mode: str
    message: str
    url: str = None
    session_id: str = None

@app.get("/")
def home():
    return {"status": "Backend is running successfully!"}

@app.post("/api/chat")
def chat_endpoint(data: ChatRequest):
    try:
        # यहाँ आप Claude API या Playwright का लॉजिक जोड़ सकते हैं
        user_message = data.message
        mode = data.mode
        
        # अभी के लिए एक डमी रिस्पॉन्स भेज रहे हैं ताकि आपका फ्रंटएंड टेस्ट हो सके
        reply = f"مرحبا! मिला आपका संदेश: '{user_message}' (Mode: {mode})"
        
        return {
            "reply": reply,
            "status": "सफलतापूर्वक पूरा हुआ"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import anthropic

app = FastAPI()

# Anthropic client initialize करें (यह Render के Environment Variable से API Key उठा लेगा)
client = anthropic.Anthropic(
    api_key=os.environ.get("ANTHROPIC_API_KEY")
)

class ChatRequest(BaseModel):
    mode: str
    message: str
    url: str = None
    session_id: str

@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    try:
        # अगर यूज़र सामान्य चैट मोड में है
        if request.mode == "chat":
            response = client.messages.create(
                model="claude-3-5-sonnet-20051022",  # या आपका पसंदीदा Claude मॉडल
                max_tokens=1000,
                messages=[
                    {"role": "user", "content": request.message}
                ]
            )
            reply_text = response.content[0].text
            return {"reply": reply_text, "status": "सफलतापूर्वक पूरा हुआ"}

        # अगर यूज़र वेबसाइट ऑटोमेशन/ब्राउज़र मोड में है
        elif request.mode == "browser":
            # यहाँ Playwright या ब्राउज़र ऑटोमेशन का कोड आएगा
            # फिलहाल Claude को निर्देश भेजने का बेसिक सेटअप
            prompt = f"वेबसाइट URL: {request.url}\nनिर्देश: {request.message}"
            response = client.messages.create(
                model="claude-3-5-sonnet-20051022",
                max_tokens=1000,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            reply_text = response.content[0].text
            return {"reply": reply_text, "status": "वेबसाइट पर काम पूरा हुआ"}

        else:
            raise HTTPException(status_code=400, detail="अमान्य मोड (Invalid mode)")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
