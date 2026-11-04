Import os
import json
import ipaddress
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError


app = FastAPI(title="AI Browser Agent - OpenRouter")

# CORS settings
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

# OpenRouter settings
API_KEY = os.getenv("OPENROUTER_API_KEY")
MODEL = os.getenv "OPENROUTER_MODEL", "Anthropic Claude Haiku 5.5"
MAX_STEPS = int(os.getenv("MAX_AGENT_STEPS", "12"))

OPENROUTER API Key = "Sk-live-bd64a7c7666be2cfb521b52644fec258f9a6460965f7cbd51b24069bae8b0f14"


class ChatRequest(BaseModel):
    mode: str
    message: str = Field(min_length=1, max_length=10000)
    url: str | None = None
    session_id: str | None = None


def validate_url(url: str) -> str:
    """Validate a public HTTP/HTTPS website URL."""
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

        try:
            ip = ipaddress.ip_address(host)
            if not ip.is_global:
                raise ValueError()
        except ValueError:
            if host.replace(".", "").isdigit():
                raise ValueError()

        return url

    except Exception:
        raise ValueError(
            "कृपया सही public वेबसाइट URL दें (http:// या https://)।"
        )


async def openrouter_request(messages, tools=None, max_tokens=1600):
    if not API_KEY:
        raise HTTPException(
            status_code=503,
            detail="Render Environment Variables में OPENROUTER_API_KEY सेट नहीं है।"
        )

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "X-Title": "AI Browser Agent",
    }

    payload = {
        "model": MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
    }

    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            OPENROUTER_URL,
            headers=headers,
            json=payload,
        )

        response.raise_for_status()
        data = response.json()

    choices = data.get("choices", [])

    if not choices:
        raise RuntimeError("OpenRouter से कोई जवाब नहीं मिला।")

    return choices[0]["message"]


# Browser tools
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "open_website",
            "description": "Open a public website URL in the browser.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"}
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "inspect_page",
            "description": (
                "Read the current page title, visible text, links, buttons "
                "and form fields."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "click_element",
            "description": "Click a page element using a CSS selector.",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string"}
                },
                "required": ["selector"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fill_field",
            "description": "Fill a form field using a CSS selector.",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string"},
                    "value": {"type": "string"},
                },
                "required": ["selector", "value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "press_key",
            "description": "Press a keyboard key on a page element.",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string"},
                    "key": {"type": "string"},
                },
                "required": ["selector", "key"],
            },
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
            page_text = await page.locator("body").inner_text(
                timeout=10000
            )

            details = await page.locator(
                "a, button, input, textarea, select, [role='button']"
            ).evaluate_all("""
                els => els.slice(0, 100).map((e, i) => ({
                    index: i,
                    tag: e.tagName,
                    text: (e.innerText ||
                        e.getAttribute('aria-label') ||
                        e.getAttribute('placeholder') || '').slice(0, 200),
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
                "text": page_text[:12000],
                "elements": details,
            }, ensure_ascii=False)

        if name == "click_element":
            selector = args["selector"]

            await page.locator(selector).first.click(
                timeout=10000
            )

            await page.wait_for_timeout(700)

            return json.dumps({
                "ok": True,
                "url": page.url,
                "title": await page.title(),
            }, ensure_ascii=False)

        if name == "fill_field":
            await page.locator(args["selector"]).first.fill(
                args["value"],
                timeout=10000,
            )

            return json.dumps({
                "ok": True,
                "action": "field filled",
            })

        if name == "press_key":
            allowed_keys = {
                "Enter",
                "Tab",
                "Escape",
                "ArrowDown",
                "ArrowUp",
                "ArrowLeft",
                "ArrowRight",
            }

            key = args["key"]

            if key not in allowed_keys:
                return json.dumps({
                    "ok": False,
                    "error": "यह key अनुमति प्राप्त सूची में नहीं है।",
                }, ensure_ascii=False)

            await page.locator(args["selector"]).first.press(
                key,
                timeout=10000,
            )

            return json.dumps({
                "ok": True,
                "key": key,
            })

        return json.dumps({
            "ok": False,
            "error": "Unknown tool",
        })

    except PlaywrightTimeoutError:
        return json.dumps({
            "ok": False,
            "error": "Element नहीं मिला या समय समाप्त हो गया। पेज दोबारा inspect करें।",
        }, ensure_ascii=False)

    except Exception as exc:
        return json.dumps({
            "ok": False,
            "error": str(exc)[:1000],
        }, ensure_ascii=False)


@app.get("/")
async def home():
    return {
        "status": "Backend is running successfully!",
        "provider": "OpenRouter",
    }


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "openrouter_configured": bool(API_KEY),
        "model": MODEL,
    }


@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):

    if not API_KEY:
        raise HTTPException(
            status_code=503,
            detail="Render में OPENROUTER_API_KEY सेट नहीं है।",
        )

    if request.mode not in ("chat", "browser"):
        raise HTTPException(
            status_code=400,
            detail="mode 'chat' या 'browser' होना चाहिए।",
        )

    if request.mode == "browser" and not request.url:
        raise HTTPException(
            status_code=400,
            detail="Browser mode में वेबसाइट का URL देना ज़रूरी है।",
        )

    try:

        # CHAT MODE
        if request.mode == "chat":

            messages = [{
                "role": "user",
                "content": request.message,
            }]

            response = await openrouter_request(
                messages,
                max_tokens=1200,
            )

            reply = response.get("content") or "AI से कोई जवाब नहीं मिला।"

            return {
                "reply": reply,
                "status": "success",
            }

        # BROWSER MODE
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

                    response = await openrouter_request(
                        messages,
                        tools=TOOLS,
                        max_tokens=1600,
                    )

                    # Assistant response
                    messages.append(response)

                    content = response.get("content") or ""
                    if content:
                        final_reply = content

                    tool_calls = response.get("tool_calls") or []

                    if not tool_calls:
                        finished = True
                        break

                    # Execute browser tools
                    for tool_call in tool_calls:

                        function = tool_call.get("function", {})
                        tool_name = function.get("name", "")

                        try:
                            arguments = json.loads(
                                function.get("arguments") or "{}"
                            )
                        except json.JSONDecodeError:
                            arguments = {}

                        result = await execute_tool(
                            page,
                            tool_name,
                            arguments,
                        )

                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call["id"],
                            "content": result,
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
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )

    except httpx.HTTPStatusError as exc:
        error_text = exc.response.text[:500]

        raise HTTPException(
            status_code=502,
            detail=f"OpenRouter API error: {error_text}",
        )

    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"OpenRouter connection error: {str(exc)[:500]}",
        )

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Server error: {str(exc)[:500]}",
