import Foundation

// Minimal AnyCodable to decode dynamic JSON (Card body, params, etc).
public struct AnyCodable: Codable, Equatable {
    public let value: Any

    public init(_ value: Any) {
        self.value = value
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()

        if container.decodeNil() {
            self.value = NSNull()
            return
        }
        if let b = try? container.decode(Bool.self) {
            self.value = b
            return
        }
        if let i = try? container.decode(Int.self) {
            self.value = i
            return
        }
        if let d = try? container.decode(Double.self) {
            self.value = d
            return
        }
        if let s = try? container.decode(String.self) {
            self.value = s
            return
        }
        if let a = try? container.decode([AnyCodable].self) {
            self.value = a.map { $0.value }
            return
        }
        if let o = try? container.decode([String: AnyCodable].self) {
            var dict: [String: Any] = [:]
            dict.reserveCapacity(o.count)
            for (k, v) in o {
                dict[k] = v.value
            }
            self.value = dict
            return
        }

        throw DecodingError.dataCorruptedError(in: container, debugDescription: "Unsupported JSON")
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()

        switch value {
        case is NSNull:
            try container.encodeNil()
        case let b as Bool:
            try container.encode(b)
        case let i as Int:
            try container.encode(i)
        case let d as Double:
            try container.encode(d)
        case let s as String:
            try container.encode(s)
        case let a as [Any]:
            try container.encode(a.map { AnyCodable($0) })
        case let o as [String: Any]:
            var mapped: [String: AnyCodable] = [:]
            mapped.reserveCapacity(o.count)
            for (k, v) in o {
                mapped[k] = AnyCodable(v)
            }
            try container.encode(mapped)
        default:
            throw EncodingError.invalidValue(value, EncodingError.Context(codingPath: container.codingPath, debugDescription: "Unsupported value"))
        }
    }

    public static func == (lhs: AnyCodable, rhs: AnyCodable) -> Bool {
        // Good enough for tests/UI logic.
        String(describing: lhs.value) == String(describing: rhs.value)
    }
}
