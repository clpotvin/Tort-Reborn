"""
Tasks/loop_lag.py
Event-loop scheduling drift monitor.

A 1-second loop that measures how late it actually wakes up. Drift is a direct
measure of how long the event loop was blocked, which is the discriminator for
the hypothesis that commands queue behind blocking work in the background tasks.

Individual excursions over the threshold are emitted as they happen; everything
else is folded into a once-a-minute summary, which keeps this at roughly 1,400
lines a day rather than 86,000.
"""

import time

from discord.ext import commands, tasks

from Helpers import telemetry

INTERVAL_S = 1.0
LAG_THRESHOLD_MS = 250.0
SUMMARY_INTERVAL_S = 60.0


def _percentile(sorted_samples, q):
    """Nearest-rank percentile over an already-sorted list."""
    if not sorted_samples:
        return 0.0
    idx = int(round(q * (len(sorted_samples) - 1)))
    idx = max(0, min(len(sorted_samples) - 1, idx))
    return sorted_samples[idx]


class LoopLag(commands.Cog):
    def __init__(self, client):
        self.client = client
        self._last = None
        self._samples = []
        self._window_started = time.perf_counter()
        self.loop_lag.start()

    def cog_unload(self):
        self.loop_lag.cancel()

    @tasks.loop(seconds=INTERVAL_S)
    async def loop_lag(self):
        now = time.perf_counter()
        if self._last is not None:
            drift_ms = (now - self._last - INTERVAL_S) * 1000.0
            if drift_ms > 0:
                self._samples.append(drift_ms)
                if drift_ms >= LAG_THRESHOLD_MS:
                    telemetry.emit({"type": "loop_lag", "drift_ms": round(drift_ms, 2)})
            if now - self._window_started >= SUMMARY_INTERVAL_S:
                self._emit_summary(now)
        self._last = now

    def _emit_summary(self, now):
        # Emit every window, even one with no positive-drift samples, so the
        # summary is a reliable once-a-minute heartbeat: absence of a line then
        # means the monitor (or the loop) is dead, not merely a quiet window.
        samples = sorted(self._samples)
        telemetry.emit({
            "type": "loop_lag_summary",
            "window_s": round(now - self._window_started, 1),
            "n": len(samples),
            "p50_ms": round(_percentile(samples, 0.50), 2),
            "p95_ms": round(_percentile(samples, 0.95), 2),
            "max_ms": round(samples[-1], 2) if samples else 0.0,
        })
        self._samples = []
        self._window_started = now

    @loop_lag.before_loop
    async def before_loop_lag(self):
        await self.client.wait_until_ready()


def setup(client):
    client.add_cog(LoopLag(client))
