import SwiftUI

private struct ReorderDraftItem: Identifiable {
    let id: String
    let name: String
    var quantity: Int
}

private enum DraftKind {
    case reorder
    case cancel
    case book
    case unknown
}

struct HaloMessagesRootView: View {
    @AppStorage("halo_base_url") private var baseURL: String = "http://127.0.0.1:8000"
    @AppStorage("halo_household_id") private var householdId: String = "hh-1"
    @AppStorage("halo_user_id") private var userId: String = "u-1"

    @State private var commandText: String = ""
    @State private var card: CardV1? = nil
    @State private var errorText: String? = nil
    @State private var isBusy = false

    // Modify state
    @State private var reorderItems: [ReorderDraftItem] = []
    @State private var selectedSubscriptionName: String = ""
    @State private var selectedBookingWindowIndex: Int = 0

    let threadPayload: HaloThreadPayload?
    let sendCardToThread: (CardV1) -> Void
    let sendTextToThread: (String) -> Void

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

                    Button("Apply Modify") { Task { await applyModify(draftId: draftId, card: card) } }
                        .buttonStyle(.bordered)
                        .disabled(isBusy)

                    Button("Cancel") {
                        self.card = nil
                        errorText = nil
                    }
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
                    ForEach(card.warnings, id: \.self) { warning in
                        Text(warning).font(.caption).foregroundStyle(.orange)
                    }
                }

                if card.type == "CLARIFY" {
                    ClarifyView(card: card) { qid, answer in
                        Task { await draft(clarification: [qid: answer]) }
                    }
                }

                if card.type == "DRAFT" {
                    DraftModifyView(
                        card: card,
                        reorderItems: $reorderItems,
                        selectedSubscriptionName: $selectedSubscriptionName,
                        selectedBookingWindowIndex: $selectedBookingWindowIndex
                    )
                }

                Button("Send to Thread") {
                    sendCardToThread(card)
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
        .task(id: threadPayload?.stableKey ?? "") {
            await rehydrateFromThreadPayload()
        }
        .onChange(of: card?.draftId ?? "") { _ in
            syncModifyStateFromCard()
        }
    }

    private func api() throws -> HaloAPI {
        guard let url = URL(string: baseURL) else { throw HaloAPIError.invalidURL }
        return HaloAPI(baseURL: url)
    }

    private func rehydrateFromThreadPayload() async {
        guard let payload = threadPayload else { return }

        isBusy = true
        defer { isBusy = false }

        do {
            if let draftId = payload.draftId {
                let fetched = try await api().getDraft(draftId: draftId)
                card = fetched
                errorText = nil
                syncModifyStateFromCard()
                return
            }

            if let executionId = payload.executionId {
                let execution = try await api().getExecution(executionId: executionId)
                card = cardFromExecution(execution)
                errorText = nil
                return
            }
        } catch {
            errorText = String(describing: error)
        }
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
            syncModifyStateFromCard()
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
            sendCardToThread(c)
        } catch {
            errorText = String(describing: error)
        }
    }

    private func applyModify(draftId: String, card: CardV1) async {
        isBusy = true
        defer { isBusy = false }

        do {
            var modifications: [String: AnyCodable] = [:]
            switch detectDraftKind(card) {
            case .reorder:
                let items = reorderItems.map { ["name": $0.name, "quantity": $0.quantity] as [String: Any] }
                modifications["items"] = AnyCodable(items)
            case .cancel:
                if !selectedSubscriptionName.isEmpty {
                    modifications["subscription_name"] = AnyCodable(selectedSubscriptionName)
                }
            case .book:
                modifications["selected_time_window_index"] = AnyCodable(selectedBookingWindowIndex)
            case .unknown:
                break
            }

            let c = try await api().modifyDraft(draftId: draftId, modifications: modifications)
            self.card = c
            errorText = nil
            syncModifyStateFromCard()
        } catch {
            errorText = String(describing: error)
        }
    }

    private func detectDraftKind(_ card: CardV1) -> DraftKind {
        if card.body["items"] != nil {
            return .reorder
        }
        if card.body["time_windows"] != nil {
            return .book
        }
        if card.body["available_subscriptions"] != nil || card.body["monthly_cost_cents"] != nil {
            return .cancel
        }
        return .unknown
    }

    private func syncModifyStateFromCard() {
        guard let card else { return }

        switch detectDraftKind(card) {
        case .reorder:
            reorderItems = extractReorderItems(from: card)
        case .cancel:
            selectedSubscriptionName = extractCurrentSubscriptionName(from: card)
        case .book:
            selectedBookingWindowIndex = extractCurrentBookingIndex(from: card)
        case .unknown:
            break
        }
    }

    private func extractReorderItems(from card: CardV1) -> [ReorderDraftItem] {
        guard let itemsAny = card.body["items"]?.value as? [Any] else {
            return []
        }

        var out: [ReorderDraftItem] = []
        for item in itemsAny {
            guard let dict = item as? [String: Any] else { continue }
            let name = (dict["name"] as? String) ?? "item"
            let qty = max(1, (dict["quantity"] as? Int) ?? 1)
            out.append(ReorderDraftItem(id: name, name: name, quantity: qty))
        }
        return out
    }

    private func extractCurrentSubscriptionName(from card: CardV1) -> String {
        if let direct = card.body["name"]?.value as? String {
            return direct
        }

        guard let optionsAny = card.body["available_subscriptions"]?.value as? [Any],
              let first = optionsAny.first as? [String: Any],
              let name = first["name"] as? String
        else {
            return ""
        }
        return name
    }

    private func extractCurrentBookingIndex(from card: CardV1) -> Int {
        guard let idx = card.body["selected_time_window_index"]?.value as? Int else {
            return 0
        }
        return max(0, idx)
    }

    private func cardFromExecution(_ detail: ExecutionDetail) -> CardV1 {
        let type = detail.status == "DONE" ? "DONE" : "FAILED"
        let summary = detail.receipts.first?.contentText
            ?? detail.errorMessage
            ?? "Execution \(detail.status)"

        return CardV1(
            version: "1",
            type: type,
            title: "\(type): \(detail.verb)",
            summary: summary,
            householdId: householdId,
            userId: userId,
            draftId: detail.draftId,
            executionId: detail.executionId,
            vendor: nil,
            estimatedCostCents: nil,
            body: [
                "execution_payload_json": AnyCodable(detail.executionPayloadJson),
                "normalized_intent_json": AnyCodable(detail.normalizedIntentJson)
            ],
            actions: [],
            warnings: []
        )
    }
}

private struct DraftModifyView: View {
    let card: CardV1
    @Binding var reorderItems: [ReorderDraftItem]
    @Binding var selectedSubscriptionName: String
    @Binding var selectedBookingWindowIndex: Int

    var body: some View {
        switch detectDraftKind(card) {
        case .reorder:
            reorderView
        case .cancel:
            cancelView
        case .book:
            bookingView
        case .unknown:
            EmptyView()
        }
    }

    private var reorderView: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Modify items")
                .font(.caption)
                .bold()

            ForEach($reorderItems) { $item in
                Stepper("\(item.name): \(item.quantity)", value: $item.quantity, in: 1...20)
                    .font(.caption)
            }
        }
    }

    private var cancelView: some View {
        let names = subscriptionNames(from: card)
        return VStack(alignment: .leading, spacing: 8) {
            Text("Select subscription")
                .font(.caption)
                .bold()

            Picker("Subscription", selection: $selectedSubscriptionName) {
                ForEach(names, id: \.self) { name in
                    Text(name).tag(name)
                }
            }
            .pickerStyle(.menu)
            .font(.caption)
        }
    }

    private var bookingView: some View {
        let labels = bookingLabels(from: card)
        return VStack(alignment: .leading, spacing: 8) {
            Text("Select time window")
                .font(.caption)
                .bold()

            Picker("Window", selection: $selectedBookingWindowIndex) {
                ForEach(Array(labels.enumerated()), id: \.offset) { idx, label in
                    Text(label).tag(idx)
                }
            }
            .pickerStyle(.menu)
            .font(.caption)
        }
    }

    private func detectDraftKind(_ card: CardV1) -> DraftKind {
        if card.body["items"] != nil {
            return .reorder
        }
        if card.body["time_windows"] != nil {
            return .book
        }
        if card.body["available_subscriptions"] != nil || card.body["monthly_cost_cents"] != nil {
            return .cancel
        }
        return .unknown
    }

    private func subscriptionNames(from card: CardV1) -> [String] {
        guard let options = card.body["available_subscriptions"]?.value as? [Any] else {
            if let current = card.body["name"]?.value as? String {
                return [current]
            }
            return []
        }

        var out: [String] = []
        for option in options {
            guard let dict = option as? [String: Any], let name = dict["name"] as? String else {
                continue
            }
            out.append(name)
        }
        return out
    }

    private func bookingLabels(from card: CardV1) -> [String] {
        guard let windows = card.body["time_windows"]?.value as? [Any] else {
            return ["Option 1", "Option 2", "Option 3"]
        }

        var labels: [String] = []
        for window in windows {
            guard let dict = window as? [String: Any] else { continue }
            if let label = dict["label"] as? String, !label.isEmpty {
                labels.append(label)
                continue
            }
            let start = (dict["start"] as? String) ?? ""
            labels.append(start.isEmpty ? "Time option" : start)
        }

        if labels.isEmpty {
            return ["Option 1", "Option 2", "Option 3"]
        }
        return labels
    }
}

private struct ClarifyView: View {
    let card: CardV1
    let onAnswer: (String, String) -> Void

    var body: some View {
        if let questions = card.body["questions"]?.value as? [Any] {
            VStack(alignment: .leading, spacing: 8) {
                ForEach(Array(questions.enumerated()), id: \.offset) { idx, questionAny in
                    if let question = questionAny as? [String: Any] {
                        let qid = (question["id"] as? String) ?? "q\(idx)"
                        let prompt = (question["prompt"] as? String) ?? "Clarify"
                        Text(prompt).font(.caption)

                        if let choices = question["choices"] as? [Any] {
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
