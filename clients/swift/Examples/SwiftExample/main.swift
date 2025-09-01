import OrbitClient
import Foundation

let url = ProcessInfo.processInfo.environment["ORBIT_URL"] ?? "http://localhost:3000"
let client = ApiClient(apiUrl: url)

let stream = client.streamChat(message: "Hello from Swift!", stream: true)

let sem = DispatchSemaphore(value: 0)
Task {
    do {
        for try await chunk in stream {
            print(chunk.text, terminator: "")
            if chunk.done { print(); break }
        }
    } catch {
        print("Error: \(error)")
    }
    sem.signal()
}
sem.wait()

