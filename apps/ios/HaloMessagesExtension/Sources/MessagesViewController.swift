import Messages
import SwiftUI

final class MessagesViewController: MSMessagesAppViewController {
    private var hostingController: UIHostingController<HaloMessagesRootView>?

    override func willBecomeActive(with conversation: MSConversation) {
        super.willBecomeActive(with: conversation)
        mountOrUpdateUI(conversation: conversation)
    }

    override func didSelect(_ message: MSMessage, conversation: MSConversation) {
        super.didSelect(message, conversation: conversation)
        mountOrUpdateUI(conversation: conversation)
    }

    private func mountOrUpdateUI(conversation: MSConversation) {
        let selectedPayload = HaloThreadPayload(conversation.selectedMessage?.url)

        let root = HaloMessagesRootView(
            threadPayload: selectedPayload,
            sendCardToThread: { [weak self] card in
                self?.insertCardMessage(card)
            },
            sendTextToThread: { [weak self] text in
                self?.activeConversation?.insertText(text, completionHandler: nil)
            }
        )

        if let host = hostingController {
            host.rootView = root
            return
        }

        let host = UIHostingController(rootView: root)
        host.view.translatesAutoresizingMaskIntoConstraints = false
        addChild(host)
        view.addSubview(host.view)
        NSLayoutConstraint.activate([
            host.view.leadingAnchor.constraint(equalTo: view.leadingAnchor),
            host.view.trailingAnchor.constraint(equalTo: view.trailingAnchor),
            host.view.topAnchor.constraint(equalTo: view.topAnchor),
            host.view.bottomAnchor.constraint(equalTo: view.bottomAnchor),
        ])
        host.didMove(toParent: self)

        hostingController = host
    }

    private func insertCardMessage(_ card: CardV1) {
        guard let conversation = activeConversation else { return }

        let layout = MSMessageTemplateLayout()
        layout.caption = card.title
        layout.subcaption = card.summary
        if let warning = card.warnings.first, !warning.isEmpty {
            layout.trailingSubcaption = warning
        }

        let session = conversation.selectedMessage?.session ?? MSSession()
        let message = MSMessage(session: session)
        message.layout = layout
        message.url = HaloThreadPayload(card: card).asURL()

        conversation.insert(message, completionHandler: nil)
    }
}
