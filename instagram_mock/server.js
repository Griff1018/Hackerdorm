// Minimal demo server: serves the static pages and proxies OpenAI calls
// so the API key stays in .env and never reaches the browser.
// Run: node server.js  →  http://localhost:3000
const http = require("http");
const fs = require("fs");
const path = require("path");

try { process.loadEnvFile(path.join(__dirname, ".env")); } catch { /* no .env */ }

const PORT = process.env.PORT || 3000;
const API_KEY = process.env.OPENAI_API_KEY;
const MIME = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".png": "image/png", ".jpg": "image/jpeg", ".svg": "image/svg+xml" };

if (!API_KEY) console.warn("⚠ OPENAI_API_KEY is not set in .env");

http.createServer(async (req, res) => {
  // Proxy: POST /api/openai/<path> → https://api.openai.com/v1/<path>
  if (req.method === "POST" && req.url.startsWith("/api/openai/")) {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    try {
      const upstream = await fetch(`https://api.openai.com/v1/${req.url.slice("/api/openai/".length)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${API_KEY}` },
        body: Buffer.concat(chunks)
      });
      res.writeHead(upstream.status, { "Content-Type": "application/json" });
      res.end(Buffer.from(await upstream.arrayBuffer()));
    } catch (err) {
      res.writeHead(502, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ error: { message: err.message } }));
    }
    return;
  }

  // Static files (dotfiles such as .env are never served)
  const urlPath = decodeURIComponent(req.url.split("?")[0]);
  const file = path.join(__dirname, urlPath === "/" ? "index.html" : urlPath);
  if (!file.startsWith(__dirname) || path.basename(file).startsWith(".") || file === __filename) {
    res.writeHead(404); return res.end("Not found");
  }
  fs.readFile(file, (err, data) => {
    if (err) { res.writeHead(404); return res.end("Not found"); }
    res.writeHead(200, { "Content-Type": MIME[path.extname(file)] || "application/octet-stream" });
    res.end(data);
  });
}).listen(PORT, () => {
  console.log(`Instagram mock:        http://localhost:${PORT}/index.html`);
  console.log(`Content Agent Console: http://localhost:${PORT}/create.html`);
});
