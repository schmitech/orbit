package com.schmitech.orbit

object Example {
  def main(args: Array[String]): Unit = {
    val url = sys.env.getOrElse("ORBIT_URL", "http://localhost:3000")
    val c = new ApiClient(url)
    c.streamChat("Hello from Scala!", true) { r =>
      print(r.text)
      if (r.done) println()
    }
  }
}

