import AppKit
import Foundation

struct Configuration: Decodable {
    let projectRoot: String
    let python: String
    let dataDirectory: String?
}

// A local source launcher, not a self-contained distributed Python application.
// Configuration is generated locally and never contains credentials.
let application = NSApplication.shared
application.setActivationPolicy(.accessory)
func fail(_ message: String) -> Never {
    let alert = NSAlert()
    alert.messageText = "Miwl 2 could not start"
    alert.informativeText = message
    alert.alertStyle = .warning
    alert.runModal()
    exit(1)
}
guard let resource = Bundle.main.url(forResource: "launcher", withExtension: "json") else {
    fail("Rebuild this local launcher from the Miwl checkout.")
}
let configuration: Configuration
do {
    configuration = try JSONDecoder().decode(Configuration.self, from: Data(contentsOf: resource))
} catch {
    fail("The local launcher configuration is unreadable. Rebuild it from the checkout.")
}
let root = URL(fileURLWithPath: configuration.projectRoot, isDirectory: true)
let python = URL(fileURLWithPath: configuration.python)
guard FileManager.default.isExecutableFile(atPath: python.path),
      FileManager.default.fileExists(atPath: root.appendingPathComponent("src/miwl2/app.py").path) else {
    fail("The checkout or prepared Python environment has moved. Rebuild the local launcher.")
}
let process = Process()
process.executableURL = python
process.currentDirectoryURL = root
process.arguments = ["-m", "miwl2"]
if let directory = configuration.dataDirectory {
    process.arguments! += ["--data-dir", directory]
}
var environment = ProcessInfo.processInfo.environment
// The selected checkout must win over another editable installation.
environment["PYTHONPATH"] = root.appendingPathComponent("src").path
environment["PYTHONNOUSERSITE"] = "1"
environment.removeValue(forKey: "QT_QPA_PLATFORM")
environment.removeValue(forKey: "QT_QUICK_BACKEND")
process.environment = environment
let diagnostics = Pipe()
process.standardError = diagnostics
// Drain continuously: a full pipe must never block the application on exit.
let outputLock = NSLock()
var output = Data()
diagnostics.fileHandleForReading.readabilityHandler = { handle in
    let chunk = handle.availableData
    guard !chunk.isEmpty else { return }
    outputLock.lock()
    output.append(chunk)
    if output.count > 8192 { output = Data(output.suffix(8192)) }
    outputLock.unlock()
}
do {
    try process.run()
} catch {
    fail("Python could not be launched: \(error.localizedDescription)")
}
process.waitUntilExit()
diagnostics.fileHandleForReading.readabilityHandler = nil
let tail = diagnostics.fileHandleForReading.readDataToEndOfFile()
outputLock.lock()
output.append(tail)
let message = String(data: output.suffix(8192), encoding: .utf8) ?? ""
outputLock.unlock()
if process.terminationStatus != 0 {
    fail(message.isEmpty ? "The app exited before opening. Verify the prepared Python environment." : message)
}
