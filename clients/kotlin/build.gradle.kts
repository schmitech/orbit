plugins {
    kotlin("jvm") version "1.9.10"
    application
}

repositories { mavenCentral() }

dependencies {
    implementation("com.squareup.okhttp3:okhttp:4.11.0")
    testImplementation("org.junit.jupiter:junit-jupiter:5.9.3")
}

kotlin { jvmToolchain(11) }

tasks.test {
    useJUnitPlatform()
}

application {
    mainClass.set("com.schmitech.orbit.ExampleKt")
}
