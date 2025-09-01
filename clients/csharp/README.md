# C# Orbit API Client

Async streaming client for Orbit `/v1/chat`.

## Example

```csharp
using System;
using System.Threading.Tasks;
using SchmiTech.Orbit;

class Program {
  static async Task Main() {
    var client = new ApiClient("http://localhost:3000");
    await foreach (var chunk in client.StreamChatAsync("Hello from C#!", true)) {
      Console.Write(chunk.Text);
      if (chunk.Done) Console.WriteLine();
    }
  }
}
```

