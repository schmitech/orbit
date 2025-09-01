# Rust Orbit API Client

Async streaming client for Orbit `/v1/chat` using `reqwest`.

## Example

```rust
use orbit_api::{ApiClient, StreamResponse};

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let client = ApiClient::new("http://localhost:3000", None, None)?;
    let mut stream = client.stream_chat("Hello from Rust!", true).await?;
    while let Some(chunk) = stream.next().await {
        let chunk = chunk?;
        print!("{}", chunk.text);
        if chunk.done { println!(); }
    }
    Ok(())
}
```

