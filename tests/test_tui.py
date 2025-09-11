import pre_nixos.tui as tui


def test_tui_exposes_run():
    assert callable(tui.run)


def test_draw_plan_displays_ip(monkeypatch):
    class FakeWin:
        def __init__(self):
            self.lines = {}

        def clear(self):
            pass

        def getmaxyx(self):
            return (25, 80)

        def addstr(self, y, x, s):
            self.lines[y] = s

        def refresh(self):
            pass

    win = FakeWin()
    monkeypatch.setattr(tui.network, "get_lan_status", lambda: "203.0.113.7")
    tui._draw_plan(win, {"a": 1})
    assert "203.0.113.7" in win.lines[0]


def test_draw_plan_displays_messages(monkeypatch):
    class FakeWin:
        def __init__(self):
            self.lines = {}

        def clear(self):
            pass

        def getmaxyx(self):
            return (25, 80)

        def addstr(self, y, x, s):
            self.lines[y] = s

        def refresh(self):
            pass

    win = FakeWin()
    monkeypatch.setattr(tui.network, "get_lan_status", lambda: "missing SSH public key")
    tui._draw_plan(win, {"a": 1})
    assert "missing SSH public key" in win.lines[0]
