import SwiftUI

private let projectRoot = ProcessInfo.processInfo.environment["EQUITY_RADAR_PROJECT_ROOT"]
    ?? FileManager.default.homeDirectoryForCurrentUser
        .appendingPathComponent("Documents/PersonalEquityRadar").path
private let controlScript = URL(fileURLWithPath: projectRoot)
    .appendingPathComponent("scripts/macos/equity-radar-control.zsh").path

private struct ControlResult: Sendable {
    let message: String
    let running: Bool
}

private func executeControl(_ action: String) -> ControlResult {
    let process = Process()
    let output = Pipe()
    let errors = Pipe()
    process.executableURL = URL(fileURLWithPath: controlScript)
    process.arguments = [action]
    process.standardOutput = output
    process.standardError = errors
    do {
        try process.run()
        process.waitUntilExit()
        let stdout = String(data: output.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
        let stderr = String(data: errors.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
        let message = (stdout.isEmpty ? stderr : stdout).trimmingCharacters(in: .whitespacesAndNewlines)
        let running = action == "start" || (action == "status" && process.terminationStatus == 0)
        return ControlResult(
            message: message.isEmpty ? "No status message was returned." : message,
            running: action == "stop" ? false : running
        )
    } catch {
        return ControlResult(message: "Could not run Equity Radar: \(error.localizedDescription)", running: false)
    }
}

struct LauncherView: View {
    @State private var status = "Checking server status…"
    @State private var isRunning = false
    @State private var isBusy = false

    var body: some View {
        VStack(spacing: 20) {
            Image(systemName: "chart.xyaxis.line")
                .font(.system(size: 38, weight: .medium))
                .foregroundStyle(.cyan)
            VStack(spacing: 7) {
                Text("Equity Radar")
                    .font(.title.bold())
                HStack(spacing: 7) {
                    Circle()
                        .fill(isRunning ? Color.green : Color.secondary)
                        .frame(width: 9, height: 9)
                    Text(status)
                        .font(.callout)
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                        .multilineTextAlignment(.center)
                }
            }
            HStack(spacing: 12) {
                Button("Stop everything", role: .destructive) { run("stop") }
                    .keyboardShortcut(".", modifiers: [.command])
                Button("Start everything") { run("start") }
                    .keyboardShortcut(.defaultAction)
                    .buttonStyle(.borderedProminent)
            }
            .disabled(isBusy)
            Text("Quit normally from the app menu or press ⌘Q.")
                .font(.caption)
                .foregroundStyle(.tertiary)
        }
        .padding(28)
        .frame(width: 440, height: 265)
        .task { await refreshStatus() }
    }

    private func run(_ action: String) {
        isBusy = true
        status = action == "start" ? "Starting Equity Radar…" : "Stopping Equity Radar…"
        Task {
            let result = await Task.detached(priority: .userInitiated) { executeControl(action) }.value
            status = result.message
            isRunning = result.running
            isBusy = false
        }
    }

    private func refreshStatus() async {
        let result = await Task.detached(priority: .utility) { executeControl("status") }.value
        status = result.message
        isRunning = result.running
    }
}

@main
struct EquityRadarLauncherApp: App {
    var body: some Scene {
        WindowGroup("Equity Radar Launcher") {
            LauncherView()
        }
        .windowResizability(.contentSize)
        .commands {
            CommandGroup(replacing: .newItem) { }
        }
    }
}
