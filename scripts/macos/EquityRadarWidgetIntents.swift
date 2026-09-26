import AppIntents

struct StartEquityRadarIntent: AppIntent {
    static let title: LocalizedStringResource = "Start Equity Radar"
    static let description = IntentDescription("Starts the local Equity Radar server and opens its dashboard.")
    static var supportedModes: IntentModes { [.background, .foreground(.dynamic)] }

    func perform() async throws -> some IntentResult {
        let result = await Task.detached(priority: .userInitiated) {
            executeControl("start")
        }.value
        EquityRadarWidgetState.save(result)
        return .result()
    }
}

struct StopEquityRadarIntent: AppIntent {
    static let title: LocalizedStringResource = "Stop Equity Radar"
    static let description = IntentDescription("Stops the local Equity Radar server.")
    static var supportedModes: IntentModes { [.background, .foreground(.dynamic)] }

    func perform() async throws -> some IntentResult {
        let result = await Task.detached(priority: .userInitiated) {
            executeControl("stop")
        }.value
        EquityRadarWidgetState.save(result)
        return .result()
    }
}

@available(macOSApplicationExtension, unavailable)
extension StartEquityRadarIntent: ForegroundContinuableIntent {}

@available(macOSApplicationExtension, unavailable)
extension StopEquityRadarIntent: ForegroundContinuableIntent {}
