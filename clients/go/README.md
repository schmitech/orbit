# Go Orbit API Client

Streaming client for Orbit `/v1/chat` using Go stdlib.

## Example

```go
package main

import (
  "context"
  "fmt"
  orbit "github.com/example/orbit-go"
)

func main() {
  client := orbit.NewApiClient("http://localhost:3000", "", "")
  ctx := context.Background()
  ch, err := client.StreamChat(ctx, "Hello from Go!", true)
  if err != nil { panic(err) }
  for resp := range ch {
    if resp.Err != nil { panic(resp.Err) }
    fmt.Print(resp.Text)
    if resp.Done { fmt.Println() }
  }
}
```

