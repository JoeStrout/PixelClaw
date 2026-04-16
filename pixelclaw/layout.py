from agentcore.panel import Panel

HEADER_HEIGHT = 64
DOCK_WIDTH    = 128
CHAT_FRACTION = 0.20


class LayoutManager:
    """
    Owns the top-level panel layout rules for PixelClaw.

    Call update(w, h) whenever the window size changes to reposition and
    resize all managed panels.  Rules are hard-coded for now.
    """

    def __init__(
        self,
        header: Panel,
        dock:   Panel,
        main:   Panel,
        chat:   Panel,
    ) -> None:
        self.header = header
        self.dock   = dock
        self.main   = main
        self.chat   = chat

    def update(self, width: int, height: int) -> None:
        chat_w = int(width * CHAT_FRACTION)
        body_h = height - HEADER_HEIGHT
        main_w = width - DOCK_WIDTH - chat_w

        self.header.x, self.header.y      = 0, 0
        self.header.width                  = width
        self.header.height                 = HEADER_HEIGHT

        self.dock.x, self.dock.y          = 0, HEADER_HEIGHT
        self.dock.width                    = DOCK_WIDTH
        self.dock.height                   = body_h

        self.main.x, self.main.y          = DOCK_WIDTH, HEADER_HEIGHT
        self.main.width                    = main_w
        self.main.height                   = body_h

        self.chat.x, self.chat.y          = DOCK_WIDTH + main_w, HEADER_HEIGHT
        self.chat.width                    = chat_w
        self.chat.height                   = body_h
