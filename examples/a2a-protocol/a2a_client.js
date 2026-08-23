#!/usr/bin/env node
// Call ORBIT through its Google Agent-to-Agent (A2A) protocol endpoint.

const { randomUUID } = require("crypto");

const ORBIT_API_URL = (process.env.ORBIT_API_URL || "http://localhost:3000").replace(/\/$/, "");
const ORBIT_API_KEY = process.env.ORBIT_API_KEY;
const ORBIT_USER_TOKEN = process.env.ORBIT_USER_TOKEN;
const ORBIT_A2A_ADAPTER = process.env.ORBIT_A2A_ADAPTER;

function headers() {
  const result = { "Content-Type": "application/json" };
  if (ORBIT_API_KEY) result.Authorization = `Bearer ${ORBIT_API_KEY}`;
  if (ORBIT_USER_TOKEN) {
    result["X-ORBIT-User-Authorization"] = `Bearer ${ORBIT_USER_TOKEN}`;
  }
  return result;
}

function rpcRequest(method, params) {
  return { jsonrpc: "2.0", id: randomUUID(), method, params };
}

async function responseJson(response) {
  if (response.ok) return response.json();
  throw new Error(`HTTP ${response.status}: ${await response.text()}`);
}

async function post(payload) {
  return responseJson(await fetch(`${ORBIT_API_URL}/a2a`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify(payload),
  }));
}

function taskParams(message, taskId) {
  const params = {};
  if (taskId) params.id = taskId;
  if (message !== undefined) {
    params.message = { role: "user", parts: [{ type: "text", text: message }] };
  }
  if (ORBIT_A2A_ADAPTER) params.metadata = { adapter: ORBIT_A2A_ADAPTER };
  return params;
}

async function discover() {
  const response = await fetch(`${ORBIT_API_URL}/.well-known/agent.json`);
  console.log(JSON.stringify(await responseJson(response), null, 2));
}

async function send(message) {
  console.log(JSON.stringify(
    await post(rpcRequest("tasks/send", taskParams(message))), null, 2,
  ));
}

async function sendSubscribe(message) {
  const response = await fetch(`${ORBIT_API_URL}/a2a`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify(rpcRequest("tasks/sendSubscribe", taskParams(message))),
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}: ${await response.text()}`);

  console.log("Streaming A2A events:");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  function printEvent(line) {
    line = line.trim();
    if (!line.startsWith("data: ")) return false;
    const event = JSON.parse(line.slice(6));
    console.log(JSON.stringify(event, null, 2));
    return event.result?.final === true;
  }

  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    let newline;
    while ((newline = buffer.indexOf("\n")) !== -1) {
      const line = buffer.slice(0, newline);
      buffer = buffer.slice(newline + 1);
      if (printEvent(line)) return;
    }
    if (done) break;
  }

  // SSE permits the last event to omit its trailing newline. Process it rather
  // than silently dropping a complete event when the connection closes.
  buffer += decoder.decode();
  if (buffer.trim()) {
    try {
      printEvent(buffer);
    } catch (error) {
      throw new Error(`Stream ended with an incomplete SSE event: ${error.message}`);
    }
  }
}

async function getOrCancel(method, taskId) {
  console.log(JSON.stringify(await post(rpcRequest(method, { id: taskId })), null, 2));
}

function usage() {
  console.error("Usage: node a2a_client.js <message> [--stream]");
  console.error("       node a2a_client.js --discover | --get <task-id> | --cancel <task-id>");
}

async function main() {
  const args = process.argv.slice(2);
  if (args[0] === "--discover") return discover();
  if (args[0] === "--get" || args[0] === "--cancel") {
    if (!args[1]) {
      usage();
      process.exitCode = 1;
      return;
    }
    return getOrCancel(args[0] === "--get" ? "tasks/get" : "tasks/cancel", args[1]);
  }

  const stream = args.includes("--stream");
  const message = args.filter((arg) => arg !== "--stream").join(" ");
  if (!message) {
    usage();
    process.exitCode = 1;
    return;
  }
  return stream ? sendSubscribe(message) : send(message);
}

main().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
