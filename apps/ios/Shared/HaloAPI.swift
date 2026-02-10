import Foundation

public enum HaloAPIError: Error {
    case invalidURL
    case httpError(Int, String)
}

public struct HaloAPI {
    public let baseURL: URL

    public init(baseURL: URL) {
        self.baseURL = baseURL
    }

    public func submitCommand(_ req: CommandRequest) async throws -> CardV1 {
        try await post(path: "/v1/command", body: req)
    }

    public func modifyDraft(draftId: String, modifications: [String: AnyCodable]) async throws -> CardV1 {
        let req = DraftModifyRequest(draftId: draftId, modifications: modifications)
        return try await post(path: "/v1/draft/modify", body: req)
    }

    public func confirmDraft(draftId: String, userId: String) async throws -> CardV1 {
        let req = DraftConfirmRequest(draftId: draftId, userId: userId)
        return try await post(path: "/v1/draft/confirm", body: req)
    }

    public func listExecutions(householdId: String) async throws -> [ExecutionListItem] {
        var comps = URLComponents(url: baseURL, resolvingAgainstBaseURL: false)
        comps?.path = "/v1/executions"
        comps?.queryItems = [URLQueryItem(name: "household_id", value: householdId)]
        guard let url = comps?.url else { throw HaloAPIError.invalidURL }
        return try await get(url: url)
    }

    public func getExecution(executionId: String) async throws -> ExecutionDetail {
        try await get(path: "/v1/executions/\(executionId)")
    }

    public func getReceipts(executionId: String) async throws -> [ReceiptArtifactOut] {
        try await get(path: "/v1/receipts/\(executionId)")
    }

    private func get<T: Decodable>(path: String) async throws -> T {
        let url = baseURL.appendingPathComponent(_clean(path))
        return try await get(url: url)
    }

    private func get<T: Decodable>(url: URL) async throws -> T {
        var request = URLRequest(url: url)
        request.httpMethod = "GET"

        let (data, resp) = try await URLSession.shared.data(for: request)
        try validate(resp: resp, data: data)
        return try JSONDecoder().decode(T.self, from: data)
    }

    private func post<T: Decodable, B: Encodable>(path: String, body: B) async throws -> T {
        let url = baseURL.appendingPathComponent(_clean(path))
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(body)

        let (data, resp) = try await URLSession.shared.data(for: request)
        try validate(resp: resp, data: data)
        return try JSONDecoder().decode(T.self, from: data)
    }

    private func _clean(_ path: String) -> String {
        if path.hasPrefix("/") {
            return String(path.dropFirst())
        }
        return path
    }

    private func validate(resp: URLResponse, data: Data) throws {
        guard let http = resp as? HTTPURLResponse else { return }
        if (200..<300).contains(http.statusCode) { return }

        let body = String(data: data, encoding: .utf8) ?? ""
        throw HaloAPIError.httpError(http.statusCode, body)
    }
}
