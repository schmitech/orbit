# Ruby Orbit API Client

Simple Ruby client for Orbit `/v1/chat` using Net::HTTP.

## Example

```ruby
require_relative 'lib/orbit/api_client'

client = Orbit::ApiClient.new('http://localhost:3000')
client.stream_chat('Hello from Ruby!', true) do |chunk|
  print chunk[:text]
  puts if chunk[:done]
end
```

