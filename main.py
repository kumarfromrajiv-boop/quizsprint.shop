
import os
import json
import asyncio
from urllib.parse import urlparse

import anthropic
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

app = FastAPI(title="AI Browser Agent")

# GitHub Pages domain को CORS_ORIGINS में सेट करें।
# उदाहरण: https://yourname.github.io
origins = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "*").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

API_KEY = os.getenv("ANTHROPIC_API_KEY")
MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")
MAX_STEPS = int(os.getenv("MAX_AGENT_STEPS", "12"))

client = anthropic.AsyncAnthropic(api_key=API_KEY) if API_KEY else None


class ChatRequest(BaseModel):
    mode: str
    message: str = Field(min_length=1, max_length=10000)
    url: str | None = None
    session_id: str | None = None


def validate_url(url: str) -> str:
    """Only accept ordinary HTTP/HTTPS website URLs."""
    try:
        parsed = urlparse(url)
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            raise ValueError()
        host = parsed.hostname.lower()
        if host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
            raise ValueError()
        return url
    except Exception:
        raise ValueError(
            "कृपया सही public वेबसाइट URL दें (http:// या https://)।"
        )


TOOLS = [
    {
        "name": "open_website",
        "description": "Open a public website URL in the browser.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string"}
            },
            "required": ["url"],
        },
    },
    {
        "name": "inspect_page",
        "description": (
            "Read the current page title, visible text, links, buttons, "
            "and form fields. Use this to decide the next browser action."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "click_element",
        "description": (
            "Click a page element using a CSS selector. Inspect the page first "
            "and use a selector grounded in the page content."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "selector": {"type": "string"}
            },
            "required": ["selector"],
        },
    },
    {
        "name": "fill_field",
        "description": "Fill a form field identified by a CSS selector.",
        "input_schema": {
            "type": "object",
            "properties": {
                "selector": {"type": "string"},
                "value": {"type": "string"},
            },
            "required": ["selector", "value"],
        },
    },
    {
        "name": "press_key",
        "description": "Press a keyboard key on an identified page element.",
        "input_schema": {
            "type": "object",
            "properties": {
                "selector": {"type": "string"},
                "key": {"type": "string"},
            },
            "required": ["selector", "key"],
        },
    },
]


async def execute_tool(page, name: str, args: dict) -> str:
    try:
        if name == "open_website":
            url = validate_url(args["url"])
            await page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=30000,
            )
            return json.dumps({
                "ok": True,
                "url": page.url,
                "title": await page.title(),
            }, ensure_ascii=False)

        if name == "inspect_page":
            text = await page.locator("body").inner_text(timeout=10000)
            details = await page.locator(
                "a, button, input, textarea, select, [role='button']"
            ).evaluate_all("""
                els => els.slice(0, 100).map((e, i) => ({
                    index: i,
                    tag: e.tagName,
                    text: (e.innerText || e.getAttribute('aria-label')
                        || e.getAttribute('placeholder') || '').slice(0, 200),
                    type: e.getAttribute('type'),
                    name: e.getAttribute('name'),
                    id: e.id || null,
                    href: e.tagName === 'A' ? e.href : null,
                    disabled: !!e.disabled
                }))
            """)
            return json.dumps({
                "ok": True,
                "url": page.url,
                "title": await page.title(),
                "text": text[:12000],
                "elements": details,
            }, ensure_ascii=False)

        if name == "click_element":
            selector = args["selector"]
            await page.locator(selector).first.click(timeout=10000)
            await page.wait_for_timeout(700)
            return json.dumps({
                "ok": True,
                "url": page.url,
                "title": await page.title(),
            }, ensure_ascii=False)

        if name == "fill_field":
            selector = args["selector"]
            await page.locator(selector).first.fill(
                args["value"], timeout=10000
            )
            return json.dumps({"ok": True, "action": "field filled"})

        if name == "press_key":
            allowed_keys = {
                "Enter", "Tab", "Escape", "ArrowDown",
                "ArrowUp", "ArrowLeft", "ArrowRight"
            }
            key = args["key"]
            if key not in allowed_keys:
                return json.dumps({
                    "ok": False,
                    "error": "यह key अनुमति प्राप्त सूची में नहीं है।"
                }, ensure_ascii=False)
            await page.locator(args["selector"]).first.press(
                key, timeout=10000
            )
            return json.dumps({"ok": True, "key": key})

        return json.dumps({"ok": False, "error": "Unknown tool"})

    except PlaywrightTimeoutError:
        return json.dumps({
            "ok": False,
            "error": "Element नहीं मिला या समय समाप्त हो गया। पेज दोबारा inspect करें।"
        }, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({
            "ok": False,
            "error": str(exc)[:1000]
        }, ensure_ascii=False)


@app.get("/")
async def home():
    return {"status": "Backend is running successfully!"}


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "anthropic_configured": client is not None,
    }


@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    if client is None:
        raise HTTPException(
            status_code=503,
            detail="Render में ANTHROPIC_API_KEY सेट नहीं है।"
        )

    if request.mode not in ("chat", "browser"):
        raise HTTPException(
            status_code=400,
            detail="mode 'chat' या 'browser' होना चाहिए।"
        )

    if request.mode == "browser" and not request.url:
        raise HTTPException(
            status_code=400,
            detail="Browser mode में वेबसाइट का URL देना ज़रूरी है।"
        )

    try:
        if request.mode == "chat":
            response = await client.messages.create(
                model=MODEL,
                max_tokens=1200,
                messages=[{
                    "role": "user",
                    "content": request.message,
                }],
            )
            reply = "\n".join(
                block.text
                for block in response.content
                if block.type == "text"
            )
            return {"reply": reply, "status": "success"}

        start_url = validate_url(request.url)
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()

            try:
                await page.goto(
                    start_url,
                    wait_until="domcontentloaded",
                    timeout=30000,
                )

                messages = [{
                    "role": "user",
                    "content": (
                        "आप एक browser automation agent हैं। यूज़र का काम "
                        "Playwright tools से वास्तव में पूरा करें। पहले पेज "
                        "inspect करें, फिर उचित कदम उठाएँ। हर कदम का परिणाम "
                        "जाँचें। यदि लॉगिन, OTP, CAPTCHA, भुगतान, कोई कानूनी "
                        "स्वीकृति या महत्वपूर्ण irreversible कार्रवाई चाहिए, "
                        "तो रुककर यूज़र से आवश्यक कार्रवाई करवाएँ। "
                        "अनुमति के बिना भुगतान या अंतिम submit न करें। "
                        "यदि जानकारी अपर्याप्त है तो स्पष्ट सवाल पूछें। "
                        "काम पूरा होने या आगे बढ़ना असंभव होने पर साफ बताएँ।\n\n"
                        f"वेबसाइट: {start_url}\n"
                        f"यूज़र का निर्देश: {request.message}"
                    ),
                }]

                final_reply = ""
                finished = False

                for _ in range(MAX_STEPS):
                    response = await client.messages.create(
                        model=MODEL,
                        max_tokens=1600,
                        tools=TOOLS,
                        messages=messages,
                    )
                    messages.append({
                        "role": "assistant",
                        "content": response.content,
                    })

                    tool_uses = [
                        block for block in response.content
                        if block.type == "tool_use"
                    ]

                    text_parts = [
                        block.text for block in response.content
                        if block.type == "text"
                    ]
                    if text_parts:
                        final_reply = "\n".join(text_parts)

                    if not tool_uses:
                        finished = True
                        break

                    tool_results = []
                    for tool in tool_uses:
                        result = await execute_tool(
                            page, tool.name, tool.input
                        )
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tool.id,
                            "content": result,
                        })

                    messages.append({
                        "role": "user",
                        "content": tool_results,
                    })

                if not finished:
                    final_reply = (
                        "सुरक्षा/स्टेप सीमा के कारण प्रक्रिया रोक दी गई। "
                        "कृपया काम को छोटे चरणों में बाँटकर दोबारा कोशिश करें।\n"
                        + final_reply
                    )

                return {
                    "reply": final_reply or "ब्राउज़र प्रक्रिया समाप्त हुई।",
                    "status": "success" if finished else "incomplete",
                    "url": page.url,
                    "session_id": request.session_id,
                }

            finally:
                await context.close()
                await browser.close()

    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except anthropic.APIError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Cloud AI API error: {str(exc)[:500]}"
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Server error: {str(exc)[:500]}"
        )
