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

                    Section("Normalized Intent JSON") {
                        Text(prettyJSON(detail.normalizedIntentJson))
                            .font(.system(.caption, design: .monospaced))
                            .textSelection(.enabled)
                    }

                    Section("Draft Payload JSON") {
                        Text(prettyJSON(detail.draftPayloadJson))
                            .font(.system(.caption, design: .monospaced))
                            .textSelection(.enabled)
                    }

                    Section("Execution Payload JSON") {
                        Text(prettyJSON(detail.executionPayloadJson))
                            .font(.system(.caption, design: .monospaced))
                            .textSelection(.enabled)
                    }

                    Section("Receipts") {
                        if detail.receipts.isEmpty {
                            Text("No receipts")
                        }
                        ForEach(detail.receipts) { receipt in
                            VStack(alignment: .leading, spacing: 4) {
                                Text(receipt.type).font(.headline)
                                Text(receipt.contentText).font(.caption)
                                if let ext = receipt.externalReferenceId {
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
                ContentUnavailableView(
                    "Couldn’t Load Execution",
                    systemImage: "exclamationmark.triangle",
                    description: Text(errorText)
                )
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

    private func prettyJSON(_ value: [String: AnyCodable]) -> String {
        let raw = value.mapValues { $0.value }
        guard JSONSerialization.isValidJSONObject(raw) else {
            return String(describing: raw)
        }

        do {
            let data = try JSONSerialization.data(withJSONObject: raw, options: [.prettyPrinted, .sortedKeys])
            return String(data: data, encoding: .utf8) ?? String(describing: raw)
        } catch {
            return String(describing: raw)
        }
    }
}
