import SwiftUI

struct ExecutionDetailView: View {
    @AppStorage("halo_base_url") private var baseURL: String = "http://127.0.0.1:8000"

    let executionId: String

    @State private var detail: ExecutionDetail? = nil
    @State private var errorText: String? = nil

    var body: some View {
        Group {
            if let detail {
                List {
                    Section("Summary") {
                        Text("\(detail.verb) · \(detail.status)")
                        Text("Started: \(detail.startedAt)")
                        if let finished = detail.finishedAt {
                            Text("Finished: \(finished)")
                        }
                        if let latency = detail.confirmationLatencyMs {
                            Text("Confirm latency: \(latency)ms")
                        }
                    }

                    Section("Command") {
                        Text(detail.rawCommandText)
                            .textSelection(.enabled)
                    }

                    Section("Receipts") {
                        if detail.receipts.isEmpty {
                            Text("No receipts")
                        }
                        ForEach(detail.receipts) { r in
                            VStack(alignment: .leading, spacing: 4) {
                                Text(r.type).font(.headline)
                                Text(r.contentText).font(.caption)
                                if let ext = r.externalReferenceId {
                                    Text("Ref: \(ext)").font(.caption2).foregroundStyle(.secondary)
                                }
                            }
                        }
                    }

                    if let err = detail.errorMessage {
                        Section("Error") {
                            Text(err)
                                .foregroundStyle(.red)
                        }
                    }
                }
            } else if let errorText {
                ContentUnavailableView("Couldn’t Load Execution", systemImage: "exclamationmark.triangle", description: Text(errorText))
            } else {
                ProgressView()
            }
        }
        .navigationTitle("Execution")
        .task { await load() }
    }

    private func load() async {
        guard let url = URL(string: baseURL) else {
            errorText = "Invalid Base URL"
            return
        }

        do {
            let api = HaloAPI(baseURL: url)
            detail = try await api.getExecution(executionId: executionId)
            errorText = nil
        } catch {
            errorText = String(describing: error)
        }
    }
}
