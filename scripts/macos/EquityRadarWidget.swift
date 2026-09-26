import AppIntents
import SwiftUI
import WidgetKit

struct EquityRadarTimelineEntry: TimelineEntry {
    let date: Date
    let snapshot: EquityRadarWidgetSnapshot
}

struct EquityRadarTimelineProvider: TimelineProvider {
    func placeholder(in context: Context) -> EquityRadarTimelineEntry {
        EquityRadarTimelineEntry(
            date: Date(),
            snapshot: EquityRadarWidgetSnapshot(
                running: true,
                message: "running",
                updatedAt: Date()
            )
        )
    }

    func getSnapshot(in context: Context, completion: @escaping (EquityRadarTimelineEntry) -> Void) {
        completion(EquityRadarTimelineEntry(date: Date(), snapshot: EquityRadarWidgetState.load()))
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<EquityRadarTimelineEntry>) -> Void) {
        let entry = EquityRadarTimelineEntry(date: Date(), snapshot: EquityRadarWidgetState.load())
        completion(Timeline(entries: [entry], policy: .after(Date().addingTimeInterval(300))))
    }
}

struct EquityRadarWidgetView: View {
    @Environment(\.widgetFamily) private var family
    let entry: EquityRadarTimelineEntry

    var body: some View {
        VStack(alignment: .leading, spacing: family == .systemLarge ? 18 : 12) {
            HStack(spacing: 10) {
                Image(systemName: "chart.xyaxis.line")
                    .font(.title2.weight(.semibold))
                    .foregroundStyle(.cyan)
                VStack(alignment: .leading, spacing: 2) {
                    Text("Equity Radar")
                        .font(.headline)
                    Text("Portfolio intelligence")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Circle()
                    .fill(entry.snapshot.running ? Color.green : Color.secondary)
                    .frame(width: 10, height: 10)
            }

            VStack(alignment: .leading, spacing: 4) {
                Text(entry.snapshot.running ? "Radar running" : "Radar stopped")
                    .font(family == .systemLarge ? .title3.bold() : .subheadline.bold())
                Text(entry.snapshot.message)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(family == .systemLarge ? 3 : 2)
            }

            Spacer(minLength: 0)

            HStack(spacing: 8) {
                Button(intent: StopEquityRadarIntent()) {
                    Label("Stop", systemImage: "stop.fill")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.bordered)

                Button(intent: StartEquityRadarIntent()) {
                    Label("Start", systemImage: "play.fill")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .tint(.cyan)
            }

            if family == .systemLarge, entry.snapshot.updatedAt != .distantPast {
                Text("Updated \(entry.snapshot.updatedAt, style: .relative)")
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }
        }
        .containerBackground(.fill.tertiary, for: .widget)
    }
}

@main
struct EquityRadarDesktopWidget: Widget {
    var body: some WidgetConfiguration {
        StaticConfiguration(kind: equityRadarWidgetKind, provider: EquityRadarTimelineProvider()) { entry in
            EquityRadarWidgetView(entry: entry)
        }
        .configurationDisplayName("Equity Radar")
        .description("Start or stop Equity Radar directly from the Desktop.")
        .supportedFamilies([.systemMedium, .systemLarge])
    }
}
