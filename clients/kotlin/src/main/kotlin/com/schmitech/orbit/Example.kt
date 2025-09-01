package com.schmitech.orbit

fun main() {
    val url = System.getenv("ORBIT_URL") ?: "http://localhost:3000"
    val client = ApiClient(url)
    client.streamChat("Hello from Kotlin!", true) { chunk ->
        print(chunk.text)
        if (chunk.done) println()
    }
    Thread.sleep(3000)
}

