# Java Orbit API Client

Minimal streaming client for the Orbit `/v1/chat` endpoint.

## Usage

```java
import com.schmitech.orbit.ApiClient;
import com.schmitech.orbit.StreamResponse;

public class Example {
  public static void main(String[] args) throws Exception {
    ApiClient client = new ApiClient("http://localhost:3000", null, null);

    client.streamChat("Hello from Java!", true, (StreamResponse resp) -> {
      System.out.print(resp.text());
      if (resp.done()) System.out.println();
    });
  }
}
```

Build with Java 11+ (uses `java.net.http.HttpClient`).

