"""Monitor-safe Apollo startup geometry, independent of PySide6 for CI.

Never re-use off-screen positions from old UI state. Center on the display
under the cursor, or Qt's primary display; respect multi-monitor origins.
"""


def centered_window_geometry(screen, size, inset=16):
    """Return (x, y, width, height) inside screen's *available* rectangle.

    screen: x, y, width, height of Qt QScreen.availableGeometry()
    size: saved width and height (not the old saved x and y).
    """
    sx, sy, sw, sh = (int(v) for v in screen)
    if sw < 1 or sh < 1:
        raise ValueError("No usable display geometry")
    width, height = (int(v) for v in size)
    border = max(0, int(inset))
    width = max(1, min(max(1, width), max(1, sw - border * 2)))
    height = max(1, min(max(1, height), max(1, sh - border * 2)))
    x = sx + (sw - width) // 2
    y = sy + (sh - height) // 2
    return (x, y, width, height)
