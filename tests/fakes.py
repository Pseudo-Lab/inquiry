"""Deterministic adapter fixture with no network, sleeps, or model SDK."""


class FakeAdapter:
    def __init__(self, signals, on_signal=None):
        self.signals = list(signals)
        self.on_signal = on_signal
        self.calls = []
        self.closed = False

    def run(self, request):
        self.calls.append(request)
        self.closed = False
        try:
            for index, signal in enumerate(self.signals):
                if self.on_signal is not None:
                    self.on_signal(index, request)
                if isinstance(signal, BaseException):
                    raise signal
                yield signal
        finally:
            self.closed = True
