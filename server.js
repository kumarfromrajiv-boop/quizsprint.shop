const http = require("http");

const PORT = process.env.PORT || 3000;
const API_KEY = process.env.OPENROUTER_API_KEY; "sk-live-5a74481789e240a89212adff968994a4a4853f45cb03379614df8b0ee1011f57"
const BROWSER_URL = process.env.PLAYWRIGHT_SERVER_URL; from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from playwright.sync_api import sync_playwright

app = FastAPI()

# CORS चालू करना ताकि आपका फ्रंटएंड (HTML पेज) इससे आसानी से बात कर सके
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
    followup: bool = False

@app.post("/api/chat")
def handle_chat(req: ChatRequest):
    if req.mode == "browser" and req.url:
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                
                # यूज़र द्वारा दी गई वेबसाइट खोलना
                page.goto(req.url, timeout=60000)
                
                page_title = page.title()
                page_text = page.inner_text("body")[:1000] # शुरुआती 1000 अक्षर
                
                browser.close()
                
                return {
                    "reply": f"सफलतापूर्वक वेबसाइट खोली गई!\n\nटाइटुल: {page_title}\n\nपेज का मुख्य अंश:\n{page_text}"
                }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    return {"reply": "ब्राउज़र मोड या सही URL नहीं मिला।"}

@app.get("/")
def home():
    return {"status": "Render Playwright Backend is running successfully!"}
const SHARED_SECRET = process.env.BROWSER_SHARED_SECRET;

const MODEL = process.env.OPENROUTER_MODEL || "openai/gpt-4o-mini";

function send(res, status, data) {
res.writeHead(status, {
"Content-Type": "application/json; charset=utf-8",
"Access-Control-Allow-Origin": "*",
"Access-Control-Allow-Methods": "GET, POST, OPTIONS",
"Access-Control-Allow-Headers": "Content-Type"
});

res.end(JSON.stringify(data));
}

async function readBody(req) {
let body = "";

for await (const chunk of req) {
body += chunk;

if (body.length > 1000000) {  
  throw new Error("Request too large");  
}

}

return JSON.parse(body);
}

// OpenRouter AI
async function askAI(messages) {
if (!API_KEY) {
throw new Error("OPENROUTER_API_KEY सेट नहीं है।");
}

const response = await fetch(
"https://openrouter.ai/api/v1/chat/completions",
{
method: "POST",
headers: {
"Authorization": "Bearer " + API_KEY,
"Content-Type": "application/json",
"HTTP-Referer": "https://quizsprint-shop-2.onrender.com",
"X-Title": "AI Studio"
},
body: JSON.stringify({
model: MODEL,
messages,
temperature: 0.2
})
}
);

const result = await response.json();

if (!response.ok) {
throw new Error(
result.error?.message || "OpenRouter API Error"
);
}

const reply = result.choices?.[0]?.message?.content;

if (!reply) {
throw new Error("AI से जवाब प्राप्त नहीं हुआ।");
}

return reply;
}

// Playwright दूसरे Server से कनेक्शन
async function runBrowser(url, task, steps) {
if (!BROWSER_URL || !SHARED_SECRET) {
throw new Error("Playwright Server की सेटिंग पूरी नहीं है।");
}
  const response = await fetch(
    BROWSER_URL.replace(/\/$/, "") + "/api/run",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + SHARED_SECRET
      },
      body: JSON.stringify({
        url,
        task,
        steps
      })
    }
  );

  const result = await response.json();
if (!response.ok) {
throw new Error(
result.error || "Browser Server Error"
);
}

return result;
}

const server = http.createServer(async (req, res) => {

// CORS settings
if (req.method === "OPTIONS") {
res.writeHead(204, {
"Access-Control-Allow-Origin": "*",
"Access-Control-Allow-Methods": "GET, POST, OPTIONS",
"Access-Control-Allow-Headers": "Content-Type"
});

return res.end();

}

// Health check
if (req.method === "GET" && req.url === "/") {
return send(res, 200, {
status: "online",
message: "OpenRouter AI Server is running"
});
}

// Chat API
if (req.method !== "POST" || req.url !== "/api/chat") {
return send(res, 404, {
error: "Route not found"
});
}

try {
const data = await readBody(req);

const message = String(data.message || "").trim();  
const mode = data.mode || "chat";  
const url = String(data.url || "").trim();  

if (!message) {  
  return send(res, 400, {  
    error: "Message is required"  
  });  
}  

// सामान्य AI बातचीत  
if (mode !== "browser") {  
  const reply = await askAI([  
    {  
      role: "system",  
      content:  
        "You are a helpful AI assistant. Reply in the user's language. Be clear and useful."  
    },  
    {  
      role: "user",  
      content: message  
    }  
  ]);  

  return send(res, 200, {  
    type: "success",  
    reply  
  });  
}  

// Browser URL validation  
let parsed;  

try {  
  parsed = new URL(url);  
} catch {  
  return send(res, 400, {  
    error: "सही वेबसाइट URL डालें।"  
  });  
}  

if (!["http:", "https:"].includes(parsed.protocol)) {  
  return send(res, 400, {  
    error: "केवल HTTP और HTTPS वेबसाइट स्वीकार हैं।"  
  });  
}  

// OpenRouter से Browser Action Plan  
const planText = await askAI([  
  {  
    role: "system",  
    content: `You create browser automation plans.

Return ONLY valid JSON in this format:
{"steps":[{"action":"click","selector":"CSS selector"},{"action":"fill","selector":"CSS selector","value":"text"},{"action":"wait","ms":1000},{"action":"read"}]}

Allowed actions: click, fill, wait, read.
Do not include goto; the browser server opens the supplied URL.
Never create steps for purchases, payments, deleting accounts/data,
sending messages, submitting orders, or changing security settings.
For those tasks, return {"steps":[],"message":"User confirmation or manual action required."}
Use simple CSS selectors. Do not invent selectors when uncertain.`
},
{
role: "user",
content: "Website URL: " + url + "\nTask: " + message
}
]);

let plan;  

try {  
  plan = JSON.parse(planText);  
} catch {  
  throw new Error("OpenRouter ने सही Browser Plan नहीं दिया।");  
}  

if (!Array.isArray(plan.steps)) {  
  throw new Error("Browser Plan में steps नहीं मिले।");  
}  

if (plan.steps.length === 0) {  
  return send(res, 200, {  
    type: "need_input",  
    reply:  
      plan.message ||  
      "इस काम के लिए आपकी पुष्टि या मैन्युअल कार्रवाई जरूरी है।"  
  });  
}  

// दूसरे Render Server पर Playwright चलाना  
const browserResult = await runBrowser(  
  url,  
  message,  
  plan.steps  
);  

// Browser के परिणाम को AI से समझवाना  
const finalReply = await askAI([  
  {  
    role: "system",  
    content:  
      "Explain the browser execution result honestly in the user's language. Never claim an action succeeded unless the result confirms it."  
  },  
  {  
    role: "user",  
    content: JSON.stringify({  
      originalTask: message,  
      browserResult  
    })  
  }  
]);  

return send(res, 200, {  
  type: "success",  
  reply: finalReply,  
  browser: browserResult  
});

} catch (error) {
console.error("Server Error:", error);

return send(res, 500, {  
  error: error.message || "Internal Server Error"  
});

}
});

// Start server
server.listen(PORT, "0.0.0.0", () => {
console.log(
"OpenRouter AI Server running on port " + PORT
);
});
