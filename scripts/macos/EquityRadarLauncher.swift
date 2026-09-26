import AppKit
import Darwin
import SwiftUI

@MainActor
private final class EquityRadarApplicationGuard {
    static let shared = EquityRadarApplicationGuard()

    private let bundleIdentifier = "com.rgferreira.EquityRadarLauncher"
    private let canonicalAppURL = FileManager.default.homeDirectoryForCurrentUser
        .appendingPathComponent("Applications/Equity Radar.app", isDirectory: true)
        .resolvingSymlinksInPath()
        .standardizedFileURL
    private var lockFileDescriptor: Int32 = -1

    private init() {}

    func acquire() -> Bool {
        let runningAppURL = Bundle.main.bundleURL
            .resolvingSymlinksInPath()
            .standardizedFileURL
        guard runningAppURL == canonicalAppURL else {
            activateCanonicalInstance()
            return false
        }

        let supportDirectory = FileManager.default.urls(
            for: .applicationSupportDirectory,
            in: .userDomainMask
        )[0]
        .appendingPathComponent("EquityRadar", isDirectory: true)
        do {
            try FileManager.default.createDirectory(
                at: supportDirectory,
                withIntermediateDirectories: true
            )
        } catch {
            activateCanonicalInstance()
            return false
        }

        let lockURL = supportDirectory
            .appendingPathComponent("equity-radar-ui.lock", isDirectory: false)
        let descriptor = Darwin.open(
            lockURL.path,
            O_CREAT | O_RDWR,
            S_IRUSR | S_IWUSR
        )
        guard descriptor >= 0 else {
            activateCanonicalInstance()
            return false
        }
        guard Darwin.lockf(descriptor, F_TLOCK, 0) == 0 else {
            Darwin.close(descriptor)
            activateCanonicalInstance()
            return false
        }

        lockFileDescriptor = descriptor
        return true
    }

    private func activateCanonicalInstance() {
        DispatchQueue.main.async {
            let currentPID = ProcessInfo.processInfo.processIdentifier
            if let primary = NSRunningApplication.runningApplications(
                withBundleIdentifier: self.bundleIdentifier
            ).first(where: {
                $0.processIdentifier != currentPID
                    && $0.bundleURL?
                        .resolvingSymlinksInPath()
                        .standardizedFileURL == self.canonicalAppURL
            }) {
                primary.activate(options: [.activateAllWindows])
            }
            NSApplication.shared.terminate(nil)
        }
    }

    deinit {
        guard lockFileDescriptor >= 0 else { return }
        Darwin.lockf(lockFileDescriptor, F_ULOCK, 0)
        Darwin.close(lockFileDescriptor)
    }
}

struct LauncherView: View {
    @AppStorage("startServerOnLaunch") private var startServerOnLaunch = true
    @State private var status = "Checking server status…"
    @State private var isRunning = false
    @State private var isBusy = false
    @State private var didHandleLaunch = false
    @State private var autoStartTask: Task<Void, Never>?

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
            Toggle("Start server on launch", isOn: $startServerOnLaunch)
                .toggleStyle(.switch)
                .onChange(of: startServerOnLaunch) { _, enabled in
                    if !enabled {
                        cancelAutomaticStart(
                            statusMessage: "Automatic server start disabled."
                        )
                    }
                }
            Text("Quit normally from the app menu or press ⌘Q.")
                .font(.caption)
                .foregroundStyle(.tertiary)
        }
        .padding(28)
        .frame(width: 440, height: 320)
        .task { await handleLaunch() }
    }

    private func run(_ action: String) {
        cancelAutomaticStart()
        isBusy = true
        status = action == "start" ? "Starting Equity Radar…" : "Stopping Equity Radar…"
        Task {
            let result = await Task.detached(priority: .userInitiated) { executeControl(action) }.value
            EquityRadarWidgetState.save(result)
            status = result.message
            isRunning = result.running
            isBusy = false
        }
    }

    private func handleLaunch() async {
        guard !didHandleLaunch else { return }
        didHandleLaunch = true
        if startServerOnLaunch {
            beginAutomaticStart()
        } else {
            await refreshStatus()
        }
    }

    private func beginAutomaticStart() {
        guard autoStartTask == nil else { return }
        isBusy = true
        status = "Starting Equity Radar automatically…"
        autoStartTask = Task {
            await startAutomaticallyUntilReady()
        }
    }

    private func startAutomaticallyUntilReady() async {
        var retryDelaySeconds: UInt64 = 2
        var attempt = 1

        while !Task.isCancelled {
            let result = await Task.detached(priority: .userInitiated) {
                executeControl("start")
            }.value
            guard !Task.isCancelled else { return }

            EquityRadarWidgetState.save(result)
            status = result.message
            isRunning = result.running
            if result.running {
                isBusy = false
                autoStartTask = nil
                return
            }

            status = "Waiting for ZeroTier or dependencies… retrying in \(retryDelaySeconds)s."
            do {
                try await Task.sleep(for: .seconds(retryDelaySeconds))
            } catch {
                return
            }
            retryDelaySeconds = min(retryDelaySeconds * 2, 30)
            attempt += 1
            status = "Automatic start attempt \(attempt)…"
        }
    }

    private func cancelAutomaticStart(statusMessage: String? = nil) {
        autoStartTask?.cancel()
        autoStartTask = nil
        isBusy = false
        if let statusMessage {
            status = statusMessage
        }
    }

    private func refreshStatus() async {
        let result = await Task.detached(priority: .utility) { executeControl("status") }.value
        EquityRadarWidgetState.save(result)
        status = result.message
        isRunning = result.running
    }
}

@main
struct EquityRadarLauncherApp: App {
    private let isPrimaryInstance: Bool

    init() {
        let isPrimaryInstance = EquityRadarApplicationGuard.shared.acquire()
        self.isPrimaryInstance = isPrimaryInstance
        guard isPrimaryInstance else { return }

        if
            let iconURL = Bundle.main.url(
                forResource: "EquityRadar",
                withExtension: "icns"
            ),
            let icon = NSImage(contentsOf: iconURL)
        {
            icon.isTemplate = false
            NSApplication.shared.applicationIconImage = icon
        }
    }

    var body: some Scene {
        Window("Equity Radar", id: "equity-radar-main") {
            if isPrimaryInstance {
                LauncherView()
            } else {
                EmptyView()
            }
        }
        .windowResizability(.contentSize)
        .commands {
            CommandGroup(replacing: .newItem) { }
        }
    }
}
