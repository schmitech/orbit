import XCTest
@testable import OrbitClient

final class OrbitClientTests: XCTestCase {
    func testIntegration_NonStreaming() async throws {
        guard ProcessInfo.processInfo.environment["ORBIT_INTEGRATION"] == "1" else {
            throw XCTSkip("Set ORBIT_INTEGRATION=1 to run integration test")
        }
        let url = ProcessInfo.processInfo.environment["ORBIT_URL"] ?? "http://localhost:3000"
        let client = ApiClient(apiUrl: url)
        var allText = ""
        for try await chunk in client.streamChat(message: "ping", stream: false) {
            allText += chunk.text
        }
        XCTAssertFalse(allText.isEmpty)
    }
}

