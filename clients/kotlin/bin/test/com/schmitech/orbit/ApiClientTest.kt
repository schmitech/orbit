package com.schmitech.orbit

import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assumptions.assumeTrue
import org.junit.jupiter.api.Test

class ApiClientTest {
    @Test
    fun integrationNonStreaming() {
        assumeTrue(System.getenv("ORBIT_INTEGRATION") == "1", "Set ORBIT_INTEGRATION=1 to enable")
        val url = System.getenv("ORBIT_URL") ?: "http://localhost:3000"
        val client = ApiClient(url)
        var all = StringBuilder()
        client.streamChat("ping", false) { chunk -> all.append(chunk.text) }
        Thread.sleep(1000) // allow async callback to complete in simple demo
        assertFalse(all.isEmpty())
    }
}

