import Foundation

public struct HaloThreadPayload: Equatable {
    public let draftId: String?
    public let executionId: String?
    public let householdId: String?
    public let userId: String?
    public let cardType: String?

    public init(card: CardV1) {
        self.draftId = card.draftId
        self.executionId = card.executionId
        self.householdId = card.householdId
        self.userId = card.userId
        self.cardType = card.type
    }

    public init?(_ url: URL?) {
        guard let url else { return nil }
        guard let components = URLComponents(url: url, resolvingAgainstBaseURL: false) else {
            return nil
        }

        var map: [String: String] = [:]
        for item in components.queryItems ?? [] {
            map[item.name] = item.value
        }

        self.draftId = map["draft_id"]
        self.executionId = map["execution_id"]
        self.householdId = map["household_id"]
        self.userId = map["user_id"]
        self.cardType = map["card_type"]

        if draftId == nil && executionId == nil {
            return nil
        }
    }

    public var stableKey: String {
        [draftId ?? "", executionId ?? "", cardType ?? ""].joined(separator: ":")
    }

    public func asURL() -> URL? {
        var components = URLComponents()
        components.scheme = "halo"
        components.host = "card"

        var items: [URLQueryItem] = []
        if let draftId {
            items.append(URLQueryItem(name: "draft_id", value: draftId))
        }
        if let executionId {
            items.append(URLQueryItem(name: "execution_id", value: executionId))
        }
        if let householdId {
            items.append(URLQueryItem(name: "household_id", value: householdId))
        }
        if let userId {
            items.append(URLQueryItem(name: "user_id", value: userId))
        }
        if let cardType {
            items.append(URLQueryItem(name: "card_type", value: cardType))
        }
        components.queryItems = items

        return components.url
    }
}
