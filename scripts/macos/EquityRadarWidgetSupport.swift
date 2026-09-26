import Foundation
import WidgetKit

let equityRadarAppGroup = "3Z35427AND.com.rgferreira.EquityRadarLauncher"
let equityRadarWidgetKind = "com.rgferreira.EquityRadarLauncher.widget"

struct ControlResult: Sendable {
    let message: String
    let running: Bool
}

struct EquityRadarWidgetSnapshot: Codable, Sendable {
    let running: Bool
    let message: String
    let updatedAt: Date
}

enum EquityRadarWidgetState {
    private static let stateKey = "widget.snapshot"

    static func load() -> EquityRadarWidgetSnapshot {
        guard
            let defaults = UserDefaults(suiteName: equityRadarAppGroup),
            let data = defaults.data(forKey: stateKey),
            let snapshot = try? JSONDecoder().decode(EquityRadarWidgetSnapshot.self, from: data)
        else {
            return EquityRadarWidgetSnapshot(
                running: false,
                message: "Open Equity Radar to check its status",
                updatedAt: .distantPast
            )
        }
        return snapshot
    }

    static func save(_ result: ControlResult) {
        let snapshot = EquityRadarWidgetSnapshot(
            running: result.running,
            message: result.message,
            updatedAt: Date()
        )
        guard
            let defaults = UserDefaults(suiteName: equityRadarAppGroup),
            let data = try? JSONEncoder().encode(snapshot)
        else { return }
        defaults.set(data, forKey: stateKey)
        WidgetCenter.shared.reloadTimelines(ofKind: equityRadarWidgetKind)
    }
}

private func equityRadarControlScript() -> String {
    let bundle = Bundle.main
    if let direct = bundle.resourceURL?.appendingPathComponent("equity-radar-control.zsh"),
       FileManager.default.fileExists(atPath: direct.path) {
        return direct.path
    }

    let appContents = bundle.bundleURL
        .deletingLastPathComponent()
        .deletingLastPathComponent()
    return appContents.appendingPathComponent("Resources/equity-radar-control.zsh").path
}

private func materializedEquityRadarControlScript() throws -> String {
    let fileManager = FileManager.default
    let source = URL(fileURLWithPath: equityRadarControlScript())
    let supportRoot = try fileManager.url(
        for: .applicationSupportDirectory,
        in: .userDomainMask,
        appropriateFor: nil,
        create: true
    )
    let controllerDirectory = supportRoot
        .appendingPathComponent("EquityRadar", isDirectory: true)
        .appendingPathComponent("controller", isDirectory: true)
    try fileManager.createDirectory(
        at: controllerDirectory, withIntermediateDirectories: true
    )
    let destination = controllerDirectory.appendingPathComponent("equity-radar-control.zsh")
    let sourceData = try Data(contentsOf: source)
    let destinationData = try? Data(contentsOf: destination)
    if destinationData != sourceData {
        try sourceData.write(to: destination, options: .atomic)
    }
    return destination.path
}

private func verifyEquityRadarProjectAccess() throws {
    let projectRoot = ProcessInfo.processInfo.environment["EQUITY_RADAR_PROJECT_ROOT"]
        ?? FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Documents/PersonalEquityRadar").path
    let marker = URL(fileURLWithPath: projectRoot).appendingPathComponent("app.py")
    _ = try Data(contentsOf: marker, options: .mappedIfSafe)
}

func executeControl(_ action: String) -> ControlResult {
    let process = Process()
    let output = Pipe()
    let errors = Pipe()
    process.standardOutput = output
    process.standardError = errors

    do {
        if action == "start" {
            try verifyEquityRadarProjectAccess()
        }
        let controller = try materializedEquityRadarControlScript()
        process.executableURL = URL(fileURLWithPath: "/bin/zsh")
        process.arguments = [controller, action]
        try process.run()
        process.waitUntilExit()
        let stdout = String(data: output.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
        let stderr = String(data: errors.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
        let message = (stdout.isEmpty ? stderr : stdout).trimmingCharacters(in: .whitespacesAndNewlines)
        let running = (action == "start" && process.terminationStatus == 0)
            || (action == "status" && process.terminationStatus == 0)
        return ControlResult(
            message: message.isEmpty ? "No status message was returned." : message,
            running: action == "stop" ? false : running
        )
    } catch {
        return ControlResult(
            message: "Could not access or run Equity Radar: \(error.localizedDescription)",
            running: false
        )
    }
}
