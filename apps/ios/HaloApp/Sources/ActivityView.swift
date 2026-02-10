import SwiftUI

struct ActivityView: View {
    @AppStorage("halo_base_url") private var baseURL: String = "http://127.0.0.1:8000"
    @AppStorage("halo_household_id") private var householdId: String = "hh-1"

    @State private var items: [ExecutionListItem] = []
    @State private var errorText: String? = nil
    @State private var isLoading = false

    var body: some View {
        NavigationStack {
            Group {
                if let errorText {
                    ContentUnavailableView("Couldn’t Load Activity", systemImage: "exclamationmark.triangle", description: Text(errorText))
                } else if items.isEmpty && !isLoading {
                    ContentUnavailableView("No Executions Yet", systemImage: "clock", description: Text("Run a command via the iMessage extension or curl."))
                } else {
                    List(items) { item in
                        NavigationLink {
                            ExecutionDetailView(executionId: item.executionId)
                        } label: {
                            VStack(alignment: .leading, spacing: 4) {
                                Text("\(item.verb) · \(item.status)")
                                    .font(.headline)
                                Text(item.startedAt)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                if let cents = item.finalCostCents {
                                    Text("$\(Double(cents) / 100.0, specifier: "%.2f")")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                            }
                        }
                    }
                }
            }
            .navigationTitle("Activity")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        Task { await load() }
                    } label: {
                        Image(systemName: "arrow.clockwise")
                    }
                }
            }
            .task { await load() }
            .refreshable { await load() }
        }
    }

    private func load() async {
        isLoading = true
        defer { isLoading = false }

        guard let url = URL(string: baseURL) else {
            errorText = "Invalid Base URL"
            return
        }

        do {
            let api = HaloAPI(baseURL: url)
            items = try await api.listExecutions(householdId: householdId)
            errorText = nil
        } catch {
            errorText = String(describing: error)
        }
    }
}
