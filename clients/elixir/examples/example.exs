client = Orbit.ApiClient.new(System.get_env("ORBIT_URL") || "http://localhost:3000")
IO.puts("Streaming example (Ctrl+C to stop if server not running):")
Orbit.ApiClient.stream_chat(client, "Hello from Elixir!", true, fn %{text: t, done: d} ->
  IO.write(t)
  if d, do: IO.puts("")
end)

