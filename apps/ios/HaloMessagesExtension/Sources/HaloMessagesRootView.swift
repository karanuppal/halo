import SwiftUI

struct HaloMessagesRootView: View {
    @AppStorage("halo_base_url") private var baseURL: String = "http://127.0.0.1:8000"
    @AppStorage("halo_household_id") private var householdId: String = "hh-1"
    @AppStorage("halo_user_id") private var userId: String = "u-1"

    @State private var commandText: String = ""
    @State private var card: CardV1? = nil
    @State private var errorText: String? = nil
    @State private var isBusy = false

    let sendMessage: (String) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Halo")
                .font(.title2)
                .bold()

            VStack(alignment: .leading, spacing: 8) {
                TextField("What should Halo do?", text: $commandText)
                    .textInputAutocapitalization(.sentences)
                    .textFieldStyle(.roundedBorder)

                HStack {
                    Button("Reorder usual") { commandText = "reorder the usual" }
                    Button("Cancel Netflix") { commandText = "cancel Netflix" }
                    Button("Book cleaning") { commandText = "book cleaner next week" }
                }
                .buttonStyle(.bordered)
                .font(.caption)
            }

            HStack {
                Button("Draft") { Task { await draft() } }
                    .buttonStyle(.borderedProminent)
                    .disabled(commandText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || isBusy)

                if let card, card.type == "DRAFT", let draftId = card.draftId {
                    Button("Confirm") { Task { await confirm(draftId: draftId) } }
                        .buttonStyle(.bordered)
                        .disabled(isBusy)

                    Button("Modify") { Task { await modifyExample(draftId: draftId) } }
                        .buttonStyle(.bordered)
                        .disabled(isBusy)
                }
            }

            if isBusy {
                ProgressView()
            }

            if let errorText {
                Text(errorText)
                    .font(.caption)
                    .foregroundStyle(.red)
            }

            if let card {
                Divider()
                Text(card.title).font(.headline)
                Text(card.summary).font(.subheadline)

                if !card.warnings.isEmpty {
                    ForEach(card.warnings, id: \.self) { w in
                        Text(w).font(.caption).foregroundStyle(.orange)
                    }
                }

                if card.type == "CLARIFY" {
                    ClarifyView(card: card) { qid, answer in
                        Task { await draft(clarification: [qid: answer]) }
                    }
                }

                Button("Send to Thread") {
                    sendMessage("Halo: \(card.title)\n\(card.summary)")
                }
                .buttonStyle(.bordered)
            }

            Spacer()

            DisclosureGroup("Settings") {
                VStack(alignment: .leading, spacing: 8) {
                    TextField("Base URL", text: $baseURL)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled(true)
                    TextField("Household ID", text: $householdId)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled(true)
                    TextField("User ID", text: $userId)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled(true)
                }
                .font(.caption)
            }
            .font(.caption)
        }
        .padding()
    }

    private func api() throws -> HaloAPI {
        guard let url = URL(string: baseURL) else { throw HaloAPIError.invalidURL }
        return HaloAPI(baseURL: url)
    }

    private func draft(clarification: [String: String]? = nil) async {
        isBusy = true
        defer { isBusy = false }

        do {
            let req = CommandRequest(
                householdId: householdId,
                userId: userId,
                rawCommandText: commandText,
                channel: "IMESSAGE",
                clarificationAnswers: clarification
            )
            let c = try await api().submitCommand(req)
            card = c
            errorText = nil
        } catch {
            errorText = String(describing: error)
        }
    }

    private func confirm(draftId: String) async {
        isBusy = true
        defer { isBusy = false }

        do {
            let c = try await api().confirmDraft(draftId: draftId, userId: userId)
            card = c
            errorText = nil
            sendMessage("Halo: \(c.title)\n\(c.summary)")
        } catch {
            errorText = String(describing: error)
        }
    }

    private func modifyExample(draftId: String) async {
        // Minimal demo: for booking drafts, select option 2.
        isBusy = true
        defer { isBusy = false }

        do {
            let c = try await api().modifyDraft(
                draftId: draftId,
                modifications: ["selected_time_window_index": AnyCodable(1)]
            )
            card = c
            errorText = nil
        } catch {
            errorText = String(describing: error)
        }
    }
}

struct ClarifyView: View {
    let card: CardV1
    let onAnswer: (String, String) -> Void

    var body: some View {
        if let qs = card.body["questions"]?.value as? [Any] {
            VStack(alignment: .leading, spacing: 8) {
                ForEach(Array(qs.enumerated()), id: \.offset) { idx, qAny in
                    if let q = qAny as? [String: Any] {
                        let qid = (q["id"] as? String) ?? "q\(idx)"
                        let prompt = (q["prompt"] as? String) ?? "Clarify"
                        Text(prompt).font(.caption)

                        if let choices = q["choices"] as? [Any] {
                            HStack {
                                ForEach(choices.compactMap { $0 as? String }, id: \.self) { choice in
                                    Button(choice) {
                                        onAnswer(qid, choice)
                                    }
                                    .buttonStyle(.bordered)
                                    .font(.caption2)
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
