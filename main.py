From fastapi import FastAPI, HTTPException
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
