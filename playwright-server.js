const http = require("http");
const { chromium } = require("playwright");

const PORT = process.env.PORT || 3000;
const SHARED_SECRET = process.env.BROWSER_SHARED_SECRET;

function send(res, status, data) {
  res.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization"
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

// Playwright Browser Automation
async function runBrowser(url, steps) {
  let browser;

  try {
    const parsed = new URL(url);

    if (!["http:", "https:"].includes(parsed.protocol)) {
      throw new Error("Only HTTP and HTTPS URLs are allowed.");
    }

    if (
      parsed.hostname === "localhost" ||
      parsed.hostname === "127.0.0.1" ||
      parsed.hostname === "::1" ||
      parsed.hostname.endsWith(".local")
    ) {
      throw new Error("Local addresses are not allowed.");
    }

    browser = await chromium.launch({
      headless: true,
      args: ["--no-sandbox"]
    });

    const page = await browser.newPage();

    await page.goto(url, {
      waitUntil: "domcontentloaded",
      timeout: 60000
    });

    const results = [];

    for (const step of steps) {
      if (!step || typeof step !== "object") {
        throw new Error("Invalid browser step.");
      }

      switch (step.action) {

        case "click":
          if (!step.selector) {
            throw new Error("Selector required.");
          }

          await page.locator(step.selector).first().click({
            timeout: 15000
          });

          results.push({
            action: "click",
            success: true
          });
          break;

        case "fill":
          if (!step.selector) {
            throw new Error("Selector required.");
          }

          await page.locator(step.selector).first().fill(
            String(step.value ?? ""),
            { timeout: 15000 }
          );

          results.push({
            action: "fill",
            success: true
          });
          break;

        case "wait":
          await page.waitForTimeout(
            Math.min(Math.max(Number(step.ms) || 1000, 0), 10000)
          );

          results.push({
            action: "wait",
            success: true
          });
          break;

        case "read":
          results.push({
            action: "read",
            text: (await page.locator("body").innerText()).slice(0, 5000)
          });
          break;

        default:
          throw new Error("Unsupported action: " + step.action);
      }
    }

    return {
      success: true,
      title: await page.title(),
      url: page.url(),
      text: (await page.locator("body").innerText()).slice(0, 5000),
      results
    };

  } finally {
    if (browser) {
      await browser.close();
    }
  }
}

// HTTP Server
const server = http.createServer(async (req, res) => {

  if (req.method === "OPTIONS") {
    res.writeHead(204, {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type, Authorization"
    });

    return res.end();
  }

  // Health Check
  if (req.method === "GET" && req.url === "/") {
    return send(res, 200, {
      status: "online",
      message: "Playwright JavaScript Server is running"
    });
  }

  // Browser API
  if (req.method !== "POST" || req.url !== "/api/run") {
    return send(res, 404, {
      error: "Route not found"
    });
  }

  // Security Check
  if (!SHARED_SECRET) {
    return send(res, 500, {
      error: "BROWSER_SHARED_SECRET is not configured."
    });
  }

  if (req.headers.authorization !== "Bearer " + SHARED_SECRET) {
    return send(res, 401, {
      error: "Unauthorized"
    });
  }

  try {
    const data = await readBody(req);

    if (!data.url || !Array.isArray(data.steps)) {
      return send(res, 400, {
        error: "URL and steps are required."
      });
    }

    const result = await runBrowser(data.url, data.steps);

    return send(res, 200, result);

  } catch (error) {
    console.error("Playwright Error:", error);

    return send(res, 500, {
      success: false,
      error: error.message || "Browser execution failed."
    });
  }
});

// Start Server
server.listen(PORT, "0.0.0.0", () => {
  console.log("Playwright Server running on port " + PORT);
});
