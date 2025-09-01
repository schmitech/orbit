defmodule Orbit.ApiClient do
  @moduledoc """
  Minimal Elixir client for Orbit /v1/chat with SSE streaming using Mint.
  """

  defstruct [:api_url, :api_key, :session_id]

  @type t :: %__MODULE__{api_url: String.t(), api_key: String.t() | nil, session_id: String.t() | nil}

  def new(api_url, api_key \\ nil, session_id \\ nil) when is_binary(api_url) do
    %__MODULE__{api_url: api_url, api_key: api_key, session_id: session_id}
  end

  defp endpoint(%__MODULE__{api_url: url}) do
    if String.ends_with?(url, "/v1/chat"), do: url, else: String.trim_trailing(url, "/") <> "/v1/chat"
  end

  @doc """
  Stream chat via SSE. Invokes `on_chunk.(%{text: binary, done: boolean})` for each data chunk.
  """
  def stream_chat(%__MODULE__{} = client, message, stream \\ true, on_chunk) when is_function(on_chunk, 1) do
    uri = URI.parse(endpoint(client))
    scheme = (uri.scheme || "http") |> String.to_atom()
    host = uri.host || "localhost"
    port = uri.port || (if scheme == :https, do: 443, else: 80)

    transport_opts = if scheme == :https, do: [transport_opts: [cacertfile: CAStore.file_path()]], else: []
    {:ok, conn} = Mint.HTTP.connect(scheme, host, port, transport_opts)

    body = Jason.encode!(%{
      messages: [%{role: "user", content: message}],
      stream: stream
    })

    headers = [
      {"content-type", "application/json"},
      {"accept", if(stream, do: "text/event-stream", else: "application/json")},
      {"x-request-id", :erlang.unique_integer([:positive]) |> Integer.to_string()}
    ]

    headers =
      headers
      |> maybe_add("x-api-key", client.api_key)
      |> maybe_add("x-session-id", client.session_id)

    {:ok, conn, ref} = Mint.HTTP.request(conn, "POST", uri.path || "/v1/chat", headers, body)
    loop(conn, ref, on_chunk, "")
  end

  defp maybe_add(headers, _k, nil), do: headers
  defp maybe_add(headers, k, v), do: [{k, v} | headers]

  defp loop(conn, ref, on_chunk, buffer) do
    receive do
      message ->
        case Mint.HTTP.stream(conn, message) do
          {:ok, conn, responses} ->
            {buffer, done?} = handle_responses(responses, ref, on_chunk, buffer)
            if done?, do: :ok, else: loop(conn, ref, on_chunk, buffer)
          {:error, _conn, reason, _responses} ->
            raise "HTTP error: #{inspect(reason)}"
          :unknown ->
            loop(conn, ref, on_chunk, buffer)
        end
    after
      60_000 -> raise "Connection timed out"
    end
  end

  defp handle_responses(responses, ref, on_chunk, buffer) do
    Enum.reduce(responses, {buffer, false}, fn
      {:status, ^ref, _code}, acc -> acc
      {:headers, ^ref, _hdrs}, acc -> acc
      {:data, ^ref, data}, {buf, _} -> process_sse(buf <> data, on_chunk)
      {:done, ^ref}, {buf, _} ->
        # flush leftover as done
        on_chunk.(%{text: "", done: true})
        {buf, true}
      _, acc -> acc
    end)
  end

  defp process_sse(buffer, on_chunk) do
    {lines, rest} = split_lines(buffer)
    done =
      Enum.reduce(lines, false, fn line, d ->
        line = String.trim(line)
        cond do
          line == "" -> d
          String.starts_with?(line, "data: ") ->
            payload = String.trim_leading(line, "data: ") |> String.trim()
            cond do
              payload == "" or payload == "[DONE]" ->
                on_chunk.(%{text: "", done: true})
                true
              true ->
                case Jason.decode(payload) do
                  {:ok, %{"response" => text} = m} ->
                    on_chunk.(%{text: text, done: Map.get(m, "done", false)})
                    d or Map.get(m, "done", false)
                  _ ->
                    on_chunk.(%{text: payload, done: false})
                    d
                end
            end
          true ->
            on_chunk.(%{text: line, done: false})
            d
        end
      end)

    {rest, done}
  end

  defp split_lines(buffer) do
    case :binary.matches(buffer, "\n") do
      [] -> {[], buffer}
      matches ->
        last = List.last(matches)
        {idx, _len} = last
        complete = :binary.part(buffer, 0, idx + 1)
        rest = :binary.part(buffer, idx + 1, byte_size(buffer) - idx - 1)
        {String.split(complete, "\n", trim: true), rest}
    end
  end
end

