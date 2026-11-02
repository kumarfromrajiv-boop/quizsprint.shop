const http = require("http");

const PORT = process.env.PORT || 3000;

const server = http.createServer(async (req, res) => {

  // CORS settings
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");

  if (req.method === "OPTIONS") {
    res.writeHead(204);
    return res.end();
  }

  res.setHeader("Content-Type", "application/json; charset=utf-8");

  // Health check
  if (req.method === "GET" && req.url === "/") {
    res.writeHead(200);
    return res.end(JSON.stringify({
      status: "online",
      message: "OpenRouter AI Server is running"
    }));
  }

  // Chat API
  if (req.method === "POST" && req.url === "/api/chat") {

    try {
      let body = "";

      for await (const chunk of req) {
        body += chunk;

        if (body.length > 1000000) {
          throw new Error("Request too large");
        }
      }

      const data = JSON.parse(body);

      const message = data.message;
      const mode = data.mode || "chat";
      const url = data.url || "";

      if (!message || !message.trim()) {
        res.writeHead(400);
        return res.end(JSON.stringify({
          error: "Message is required"
        }));
      }

      // Get API Key from Render Environment
      const API_KEY = process.env.OPENROUTER_API_KEY;

      if (!API_KEY) {
        res.writeHead(500);
        return res.end(JSON.stringify({
          error: "Render में OPENROUTER_API_KEY सेट नहीं है।"
        }));
      }

      // AI instructions
      let systemPrompt =
        "You are a helpful AI assistant. Reply in the user's language. Be clear and useful.";

      if (mode === "browser") {
        systemPrompt =
          "You are a website task assistant. You can explain how to perform tasks on websites, but you do not have direct browser access or the ability to click buttons, log in, or interact with websites. Never claim that you performed an action.";
      }

      const userMessage = mode === "browser"
        ? "Website URL: " + url + "\n\nTask: " + message
        : message;

      // OpenRouter API request
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
            model: "openai/gpt-4o-mini",
            messages: [
              {
                role: "system",
                content: systemPrompt
              },
              {
                role: "user",
                content: userMessage
              }
            ]
          })
        }
      );

      const result = await response.json();

      if (!response.ok) {
        res.writeHead(response.status);
        return res.end(JSON.stringify({
          error: result.error?.message || "OpenRouter API Error"
        }));
      }

      const reply =
        result.choices?.[0]?.message?.content;

      if (!reply) {
        throw new Error("AI से जवाब प्राप्त नहीं हुआ।");
      }

      res.writeHead(200);

      return res.end(JSON.stringify({
        reply: reply,
        type: "success"
      }));

    } catch (error) {
      console.error("Server Error:", error);

      res.writeHead(500);

      return res.end(JSON.stringify({
        error: error.message || "Internal Server Error"
      }));
    }
  }

  res.writeHead(404);

  res.end(JSON.stringify({
    error: "Route not found"
  }));

});

// Start server
server.listen(PORT, "0.0.0.0", () => {
  console.log("OpenRouter AI Server running on port " + PORT);
});
