#!/usr/bin/env node
// Example: call ORBIT with the official OpenAI Node.js SDK.
//
// ORBIT's /v1/chat/completions endpoint is OpenAI-compatible, so the
// standard `openai` client works unmodified — just point `baseURL` at
// your ORBIT server and pass your ORBIT API key.

const OpenAI = require("openai");
const { randomUUID } = require("crypto");

const ORBIT_API_URL = process.env.ORBIT_API_URL || "http://localhost:3000";
const ORBIT_API_KEY = process.env.ORBIT_API_KEY;

async function chat(message, stream = false) {
  if (!ORBIT_API_KEY) {
    console.error("Set the ORBIT_API_KEY environment variable");
    process.exit(1);
  }

  const client = new OpenAI({
    baseURL: `${ORBIT_API_URL}/v1`,
    apiKey: ORBIT_API_KEY,
    // ORBIT requires a session id per request by default
    // (config.yaml: chat_history.session.required).
    defaultHeaders: { "X-Session-ID": randomUUID() },
  });

  if (!stream) {
    const response = await client.chat.completions.create({
      model: process.env.ORBIT_MODEL || "gpt-oss:120b",
      messages: [{ role: "user", content: message }],
    });
    console.log(response.choices[0].message.content);
    return;
  }

  const response = await client.chat.completions.create({
    model: process.env.ORBIT_MODEL || "gpt-oss:120b",
    messages: [{ role: "user", content: message }],
    stream: true,
  });

  for await (const chunk of response) {
    const delta = chunk.choices[0].delta.content || "";
    process.stdout.write(delta);
  }
  console.log();
}

const args = process.argv.slice(2);
const stream = args.includes("--stream");
const message = args.filter((a) => a !== "--stream").join(" ");

if (!message) {
  console.error("Usage: node chat_completions.js <message> [--stream]");
  process.exit(1);
}

chat(message, stream).catch((err) => {
  console.error(err.message);
  process.exit(1);
});
