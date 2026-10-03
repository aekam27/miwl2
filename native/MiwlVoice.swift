import AppKit
import AVFoundation

// This accessory app is opened only by the explicit Record action. It never
// enumerates devices or asks for permission during the writing app's startup.
final class Recorder: NSObject, NSApplicationDelegate, AVAudioRecorderDelegate {
    let output: URL
    let control: URL
    let status: URL
    var recorder: AVAudioRecorder?
    var timer: Timer?
    var started: Date?
    var completed = false
    var ticks = 0

    init(output: String, control: String, status: String) {
        self.output = URL(fileURLWithPath: output)
        self.control = URL(fileURLWithPath: control)
        self.status = URL(fileURLWithPath: status)
    }

    func report(_ phase: String, error: String = "") {
        let value: [String: Any] = ["phase": phase, "pid": ProcessInfo.processInfo.processIdentifier,
                                  "elapsed": recorder?.currentTime ?? 0, "error": error]
        if let data = try? JSONSerialization.data(withJSONObject: value) {
            try? data.write(to: status, options: .atomic)
        }
    }

    func finish(_ phase: String, error: String = "") {
        guard !completed else { return }
        completed = true
        recorder?.stop()
        timer?.invalidate()
        report(phase, error: error)
        if phase != "finished" { try? FileManager.default.removeItem(at: output) }
        NSApplication.shared.terminate(nil)
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        guard FileManager.default.fileExists(atPath: output.deletingLastPathComponent().path),
              (try? String(contentsOf: control, encoding: .utf8)) != "cancel" else {
            finish("cancelled"); return
        }
        report("awaiting_permission")
        timer = Timer.scheduledTimer(withTimeInterval: 0.1, repeats: true) { [weak self] _ in
            guard let self, !self.completed else { return }
            self.ticks += 1
            let command = (try? String(contentsOf: self.control, encoding: .utf8)) ?? ""
            if command == "cancel" { self.finish("cancelled"); return }
            if command == "finish", self.recorder != nil { self.finish("finished"); return }
            if self.ticks >= 1800 { self.finish("error", error: "Microphone permission timed out."); return }
            if self.recorder != nil {
                if let started = self.started, Date().timeIntervalSince(started) >= 60 {
                    self.finish("finished")
                } else { self.report("recording") }
            }
        }
        switch AVCaptureDevice.authorizationStatus(for: .audio) {
        case .authorized: begin()
        case .notDetermined:
            AVCaptureDevice.requestAccess(for: .audio) { allowed in
                DispatchQueue.main.async {
                    guard !self.completed else { return }
                    if allowed { self.begin() }
                    else { self.finish("error", error: "Microphone access was denied. Typing and WAV import still work.") }
                }
            }
        default: finish("error", error: "Microphone access is denied or restricted. Typing and WAV import still work.")
        }
    }

    func begin() {
        guard !completed else { return }
        do {
            let settings: [String: Any] = [AVFormatIDKey: kAudioFormatLinearPCM,
                AVSampleRateKey: 16000, AVNumberOfChannelsKey: 1,
                AVLinearPCMBitDepthKey: 16, AVLinearPCMIsFloatKey: false,
                AVLinearPCMIsBigEndianKey: false]
            let audio = try AVAudioRecorder(url: output, settings: settings)
            recorder = audio
            audio.delegate = self
            guard audio.record(forDuration: 60) else {
                finish("error", error: "The microphone could not start recording."); return
            }
            started = Date()
            report("recording")
        } catch { finish("error", error: "The microphone recording could not be created.") }
    }

    func audioRecorderDidFinishRecording(_ recorder: AVAudioRecorder, successfully flag: Bool) {
        if flag { finish("finished") }
        else { finish("error", error: "The recording was interrupted.") }
    }

    func audioRecorderEncodeErrorDidOccur(_ recorder: AVAudioRecorder, error: Error?) {
        finish("error", error: "The recording format could not be encoded.")
    }
}

let arguments = CommandLine.arguments
guard arguments.count == 5, arguments[1] == "record" else { exit(2) }
let app = NSApplication.shared
app.setActivationPolicy(.accessory)
let delegate = Recorder(output: arguments[2], control: arguments[3], status: arguments[4])
app.delegate = delegate
app.run()
