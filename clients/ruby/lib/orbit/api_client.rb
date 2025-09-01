require 'net/http'
require 'json'
require 'uri'

module Orbit
  class ApiClient
    def initialize(api_url, api_key = nil, session_id = nil)
      @api_url = api_url
      @api_key = api_key
      @session_id = session_id
    end

    def endpoint
      return @api_url if @api_url.end_with?('/v1/chat')
      @api_url.gsub(%r{/+$}, '') + '/v1/chat'
    end

    def stream_chat(message, stream = true)
      uri = URI.parse(endpoint)
      http = Net::HTTP.new(uri.host, uri.port)
      http.use_ssl = (uri.scheme == 'https')
      http.read_timeout = nil

      req = Net::HTTP::Post.new(uri.request_uri)
      req['Content-Type'] = 'application/json'
      req['Accept'] = stream ? 'text/event-stream' : 'application/json'
      req['X-Request-ID'] = Time.now.to_i.to_s(36)
      req['X-API-Key'] = @api_key if @api_key
      req['X-Session-ID'] = @session_id if @session_id
      req.body = JSON.dump({ messages: [{ role: 'user', content: message }], stream: stream })

      http.request(req) do |response|
        unless response.is_a?(Net::HTTPSuccess)
          raise "HTTP error: #{response.code} #{response.body}"
        end

        if !stream
          data = JSON.parse(response.body) rescue { 'response' => response.body }
          yield({ text: data['response'].to_s, done: true }) if block_given?
          return
        end

        buffer = ''
        response.read_body do |chunk|
          buffer << chunk
          while (idx = buffer.index("\n"))
            line = buffer.slice!(0..idx).strip
            next if line.empty?
            if line.start_with?('data: ')
              json = line[6..-1].strip
              if json.empty? || json == '[DONE]'
                yield({ text: '', done: true }) if block_given?
                return
              end
              begin
                data = JSON.parse(json)
                if data['error']
                  msg = data['error']['message'] rescue 'Server error'
                  raise msg
                end
                if data['response']
                  yield({ text: data['response'], done: data['done'] || false }) if block_given?
                end
                if data['done']
                  yield({ text: '', done: true }) if block_given?
                  return
                end
              rescue StandardError
                yield({ text: json, done: false }) if block_given?
              end
            else
              yield({ text: line, done: false }) if block_given?
            end
          end
        end
      end
    end
  end
end

