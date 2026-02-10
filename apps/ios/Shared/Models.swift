import Foundation

public struct CardActionV1: Codable {
    public let type: String
    public let label: String
    public let payload: [String: AnyCodable]?
}

public struct CardV1: Codable {
    public let version: String?
    public let type: String

    public let title: String
    public let summary: String

    public let householdId: String
    public let userId: String

    public let draftId: String?
    public let executionId: String?

    public let vendor: String?
    public let estimatedCostCents: Int?

    public let body: [String: AnyCodable]
    public let actions: [CardActionV1]
    public let warnings: [String]

    enum CodingKeys: String, CodingKey {
        case version
        case type
        case title
        case summary
        case householdId = "household_id"
        case userId = "user_id"
        case draftId = "draft_id"
        case executionId = "execution_id"
        case vendor
        case estimatedCostCents = "estimated_cost_cents"
        case body
        case actions
        case warnings
    }
}

public struct CommandRequest: Codable {
    public let householdId: String
    public let userId: String
    public let rawCommandText: String
    public let channel: String?
    public let clarificationAnswers: [String: String]?

    public init(householdId: String, userId: String, rawCommandText: String, channel: String? = nil, clarificationAnswers: [String: String]? = nil) {
        self.householdId = householdId
        self.userId = userId
        self.rawCommandText = rawCommandText
        self.channel = channel
        self.clarificationAnswers = clarificationAnswers
    }

    enum CodingKeys: String, CodingKey {
        case householdId = "household_id"
        case userId = "user_id"
        case rawCommandText = "raw_command_text"
        case channel
        case clarificationAnswers = "clarification_answers"
    }
}

public struct DraftModifyRequest: Codable {
    public let draftId: String
    public let modifications: [String: AnyCodable]

    enum CodingKeys: String, CodingKey {
        case draftId = "draft_id"
        case modifications
    }
}

public struct DraftConfirmRequest: Codable {
    public let draftId: String
    public let userId: String

    enum CodingKeys: String, CodingKey {
        case draftId = "draft_id"
        case userId = "user_id"
    }
}

public struct ExecutionListItem: Codable, Identifiable {
    public var id: String { executionId }

    public let executionId: String
    public let draftId: String
    public let verb: String
    public let status: String
    public let startedAt: String
    public let finishedAt: String?

    public let vendor: String
    public let finalCostCents: Int?

    enum CodingKeys: String, CodingKey {
        case executionId = "execution_id"
        case draftId = "draft_id"
        case verb
        case status
        case startedAt = "started_at"
        case finishedAt = "finished_at"
        case vendor
        case finalCostCents = "final_cost_cents"
    }
}

public struct ReceiptArtifactOut: Codable, Identifiable {
    public let id: String
    public let type: String
    public let contentText: String
    public let externalReferenceId: String?
    public let createdAt: String

    enum CodingKeys: String, CodingKey {
        case id
        case type
        case contentText = "content_text"
        case externalReferenceId = "external_reference_id"
        case createdAt = "created_at"
    }
}

public struct ExecutionDetail: Codable {
    public let executionId: String
    public let draftId: String
    public let verb: String
    public let status: String

    public let startedAt: String
    public let finishedAt: String?

    public let rawCommandText: String
    public let normalizedIntentJson: [String: AnyCodable]
    public let draftPayloadJson: [String: AnyCodable]
    public let confirmationLatencyMs: Int?

    public let executionPayloadJson: [String: AnyCodable]
    public let errorMessage: String?

    public let receipts: [ReceiptArtifactOut]

    enum CodingKeys: String, CodingKey {
        case executionId = "execution_id"
        case draftId = "draft_id"
        case verb
        case status
        case startedAt = "started_at"
        case finishedAt = "finished_at"
        case rawCommandText = "raw_command_text"
        case normalizedIntentJson = "normalized_intent_json"
        case draftPayloadJson = "draft_payload_json"
        case confirmationLatencyMs = "confirmation_latency_ms"
        case executionPayloadJson = "execution_payload_json"
        case errorMessage = "error_message"
        case receipts
    }
}
