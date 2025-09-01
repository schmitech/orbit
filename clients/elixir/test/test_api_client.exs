ExUnit.start()

defmodule OrbitApiClientTest do
  use ExUnit.Case

  @tag :integration
  test "non-streaming returns response when server available" do
    if System.get_env("ORBIT_INTEGRATION") == "1" do
      client = Orbit.ApiClient.new(System.get_env("ORBIT_URL") || "http://localhost:3000")
      pid = self()
      # Use non-stream to get single chunk
      Orbit.ApiClient.stream_chat(client, "ping", false, fn %{text: t, done: d} ->
        send(pid, {:chunk, t, d})
      end)
      assert_receive {:chunk, text, true}, 5000
      assert is_binary(text)
    else
      IO.puts("Skipping integration test: set ORBIT_INTEGRATION=1 to enable")
      assert true
    end
  end
end

