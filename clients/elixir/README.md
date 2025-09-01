# Elixir Orbit Client

Streaming client for `/v1/chat` using Mint.

## Usage

```elixir
client = Orbit.ApiClient.new("http://localhost:3000")
Orbit.ApiClient.stream_chat(client, "Hello from Elixir!", true, fn %{text: text, done: done} ->
  IO.write(text)
  if done, do: IO.puts("")
end)
```

Install deps with `mix deps.get` before running.

