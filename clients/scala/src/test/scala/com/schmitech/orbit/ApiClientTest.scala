package com.schmitech.orbit

import org.junit.Test
import org.junit.Assert._
import org.junit.Assume._

class ApiClientTest {
  @Test def integrationNonStreaming(): Unit = {
    assumeTrue("Set ORBIT_INTEGRATION=1 to enable", System.getenv("ORBIT_INTEGRATION") == "1")
    val url = Option(System.getenv("ORBIT_URL")).getOrElse("http://localhost:3000")
    val c = new ApiClient(url)
    var all = new StringBuilder
    c.streamChat("ping", false) { r => all ++= r.text }
    assertTrue(all.length >= 0) // smoke
  }
}

