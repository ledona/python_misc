"""container aware top for CPU/MEMORY usage created mostly with claudecode"""

import argparse
import curses
import getpass
import os
import socket
import time
from typing import Optional

_CGROUP_V1_CPUACCT = "/sys/fs/cgroup/cpuacct/cpuacct.usage_percpu"
_CGROUP_V1_CPUSET = "/sys/fs/cgroup/cpuset/cpuset.cpus"
_CGROUP_V1_MEM_USAGE = "/sys/fs/cgroup/memory/memory.usage_in_bytes"
_CGROUP_V1_MEM_LIMIT = "/sys/fs/cgroup/memory/memory.limit_in_bytes"
_CGROUP_V2_CPUSET_EFF = "/sys/fs/cgroup/cpuset.cpus.effective"
_CGROUP_V2_CPUSET = "/sys/fs/cgroup/cpuset.cpus"
_CGROUP_V2_MEM_CURR = "/sys/fs/cgroup/memory.current"
_CGROUP_V2_MEM_MAX = "/sys/fs/cgroup/memory.max"

# EMA smoothing factor (higher = more responsive, lower = smoother)
_EMA_ALPHA = 0.3

# Color pair indices
_CP_DIM = 1  # gray:   <5%
_CP_GREEN = 2  # green:  5-40%
_CP_YELLOW = 3  # yellow: 40-90%
_CP_RED = 4  # red:    >90%

_SPARK_CHARS = "▁▂▃▄▅▆▇█"


def _parse_cpuset(s: str) -> list[int]:
    """Parse cpuset string like '0-3,6' into sorted list of core indices."""
    cores = []
    for part in s.strip().split(","):
        if "-" in part:
            a, b = part.split("-")
            cores.extend(range(int(a), int(b) + 1))
        else:
            cores.append(int(part))
    return sorted(cores)


def _fmt_cores(cores: list[int]) -> str:
    """Format sorted core list as compact ranges, e.g. [0,1,2,3,6] -> '0-3,6'."""
    if not cores:
        return ""
    parts = []
    start = end = cores[0]
    for c in cores[1:]:
        if c == end + 1:
            end = c
        else:
            parts.append(f"{start}-{end}" if start != end else str(start))
            start = end = c
    parts.append(f"{start}-{end}" if start != end else str(start))
    return ",".join(parts)


def _fmt_bytes(n: int, decimals: int = 1) -> str:
    v: float = n
    if n == 0:
        return "0.0"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if v < 1024:
            return f"{v:.{decimals}f}{unit}"
        v /= 1024
    return f"{v:.{decimals}f}PB"


def _fmt_pct(pct: float) -> str:
    if 0.2 <= pct < 1:
        return " <1%"
    return f"{round(pct):3d}%"


def _bar(pct: float, width: int) -> str:
    filled = int(pct / 100 * width)
    return "|" * filled + "." * (width - filled)


def _color_attr(pct: float) -> int:
    if pct < 5:
        return curses.color_pair(_CP_DIM) | curses.A_DIM
    if pct < 40:
        return curses.color_pair(_CP_GREEN)
    if pct < 90:
        return curses.color_pair(_CP_YELLOW)
    return curses.color_pair(_CP_RED)


def _draw_bar(stdscr: curses.window, row: int, col: int, label: str, bar_width: int, pct: float):
    """Draw: LABEL [BAR] NNN%  with bar colored by pct threshold."""
    try:
        stdscr.addstr(row, col, f"{label} [")
        stdscr.addstr(_bar(pct, bar_width), _color_attr(pct))
        stdscr.addstr(f"] {_fmt_pct(pct)}")
    except curses.error:
        pass


def _spark_chars(values: list[float], bar_width: int, max_history: int) -> list[tuple[str, float]]:
    """Map history values onto bar_width sparkline characters.

    The full history window is max_history seconds wide. Characters on the left
    are blank until enough samples have been collected to fill that window.
    When max_history > bar_width multiple samples are averaged per character;
    when max_history < bar_width each sample is stretched across multiple characters.
    """
    n = len(values)
    # how many leading time-slots in the history window have no data yet
    empty_slots = max_history - n
    result = []
    for i in range(bar_width):
        # time-slot range [t0, t1) this character covers within the history window
        t0 = i * max_history / bar_width
        t1 = (i + 1) * max_history / bar_width
        # convert to indices into values[] (which holds the newest n slots)
        si = int(t0) - empty_slots
        ei = int(t1) - empty_slots
        if ei <= si:
            ei = si + 1
        if ei <= 0 or si >= n:
            result.append((" ", 0.0))
            continue
        chunk = values[max(0, si) : min(n, ei)]
        pct = sum(chunk) / len(chunk) if chunk else 0.0
        idx = min(len(_SPARK_CHARS) - 1, round(pct / 100 * (len(_SPARK_CHARS) - 1)))
        result.append((_SPARK_CHARS[idx], pct))
    return result


def _fmt_uptime_secs(secs: int) -> str:
    days, rem = divmod(secs, 86400)
    hours, rem = divmod(rem, 3600)
    mins = rem // 60
    if days:
        return f"up {days}d {hours}h {mins}m"
    if hours:
        return f"up {hours}h {mins}m"
    return f"up {mins}m"


def _fmt_uptime() -> str:
    try:
        with open("/proc/uptime") as f:
            secs = int(float(f.read().split()[0]))
    except OSError:
        return "up ?"
    return _fmt_uptime_secs(secs)


def _fmt_container_uptime() -> str:
    """Estimate container uptime from PID 1 start time relative to host boot."""
    try:
        with open("/proc/uptime") as f:
            host_uptime = float(f.read().split()[0])
        with open("/proc/1/stat") as f:
            content = f.read()
        # comm field (field 2) may contain spaces/parens; find last ')' to safely split
        fields_after = content[content.rfind(")") + 2:].split()
        # starttime is field 22 in /proc/pid/stat (1-indexed), index 19 after comm+state
        starttime_ticks = int(fields_after[19])
        clk_tck = os.sysconf("SC_CLK_TCK")
        secs = max(0, int(host_uptime - starttime_ticks / clk_tck))
    except (OSError, IndexError, ValueError):
        return _fmt_uptime()
    return _fmt_uptime_secs(secs)


def _ruler(bar_width: int, max_history: int) -> str:
    """Build a dash-filled time axis of length bar_width with quarter-interval tick labels."""
    secs = sorted(
        {max_history, max_history * 3 // 4, max_history // 2, max_history // 4, 0}, reverse=True
    )
    ticks = []
    for s in secs:
        label = "now" if s == 0 else f"{s}s"
        pos = bar_width - len(label) if s == 0 else int((max_history - s) / max_history * bar_width)
        ticks.append((pos, label))
    ticks.sort()

    buf = ["-"] * bar_width
    last_end = -1
    for pos, label in ticks:
        if pos <= last_end or pos + len(label) > bar_width:
            continue
        for j, ch in enumerate(label):
            buf[pos + j] = ch
        last_end = pos + len(label)
    return "".join(buf)


def _draw_sparkline(
    stdscr: curses.window,
    row: int,
    col: int,
    label: str,
    values: list[float],
    bar_width: int,
    max_history: int,
):
    """Draw: LABEL [sparkline]"""
    try:
        stdscr.addstr(row, col, f"{label} [")
        spark_col = col + len(label) + 2
        for i, (ch, pct) in enumerate(_spark_chars(values, bar_width, max_history)):
            stdscr.addstr(row, spark_col + i, ch, _color_attr(pct))
        stdscr.addstr(row, spark_col + bar_width, "]")
    except curses.error:
        pass


def _read_proc_stat() -> dict[int, tuple[int, int]]:
    """Read /proc/stat, return {core_id: (idle_jiffies, total_jiffies)}."""
    result = {}
    with open("/proc/stat") as f:
        for line in f:
            if line.startswith("cpu") and len(line) > 3 and line[3].isdigit():
                parts = line.split()
                core_id = int(parts[0][3:])
                vals = [int(x) for x in parts[1:]]
                idle = vals[3] + (vals[4] if len(vals) > 4 else 0)  # idle + iowait
                result[core_id] = (idle, sum(vals))
    return result


class _Monitor:
    def __init__(self, history_seconds: int):
        self.cgroup_ver: Optional[int] = self._detect_cgroup()
        self.assigned_cores = self._get_assigned_cores()
        self._smoothed: dict[int, float] = {}
        self.hostname = socket.gethostname()
        self.username = getpass.getuser()
        self.max_history = history_seconds
        self._cpu_history: list[float] = []
        self._mem_history: list[float] = []

    def _detect_cgroup(self) -> Optional[int]:
        if os.path.exists(_CGROUP_V1_CPUACCT):
            return 1
        if os.path.exists(_CGROUP_V2_MEM_CURR) or os.path.exists(_CGROUP_V2_CPUSET_EFF):
            return 2
        return None

    def _get_assigned_cores(self) -> list[int]:
        if self.cgroup_ver == 1:
            with open(_CGROUP_V1_CPUSET) as f:
                return _parse_cpuset(f.read())
        if self.cgroup_ver == 2:
            for path in (_CGROUP_V2_CPUSET_EFF, _CGROUP_V2_CPUSET):
                if os.path.exists(path):
                    with open(path) as f:
                        content = f.read().strip()
                        if content:
                            return _parse_cpuset(content)
        return sorted(_read_proc_stat().keys())

    def _sample_cpu(self):
        if self.cgroup_ver == 1:
            with open(_CGROUP_V1_CPUACCT) as f:
                return [int(x) for x in f.read().split()]
        return _read_proc_stat()

    def _calc_pct(self, s1, s2, elapsed_ns: float) -> dict[int, float]:
        pcts = {}
        if self.cgroup_ver == 1:
            for core in self.assigned_cores:
                if core < len(s1) and core < len(s2):
                    pcts[core] = max(0.0, min(100.0, (s2[core] - s1[core]) / elapsed_ns * 100))
        else:
            for core in self.assigned_cores:
                if core not in s1 or core not in s2:
                    continue
                d_total = s2[core][1] - s1[core][1]
                d_idle = s2[core][0] - s1[core][0]
                if d_total <= 0:
                    pcts[core] = 0.0
                else:
                    pcts[core] = max(0.0, min(100.0, (1 - d_idle / d_total) * 100))
        return pcts

    def _smooth(self, pcts: dict[int, float]) -> dict[int, float]:
        for core, pct in pcts.items():
            if core in self._smoothed:
                self._smoothed[core] = _EMA_ALPHA * pct + (1 - _EMA_ALPHA) * self._smoothed[core]
            else:
                self._smoothed[core] = pct
        return self._smoothed

    def _record_history(self, avg_cpu: float, mem_pct: float):
        self._cpu_history.append(avg_cpu)
        if len(self._cpu_history) > self.max_history:
            self._cpu_history = self._cpu_history[-self.max_history :]
        self._mem_history.append(mem_pct)
        if len(self._mem_history) > self.max_history:
            self._mem_history = self._mem_history[-self.max_history :]

    @staticmethod
    def _system_mem_total() -> Optional[int]:
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        return int(line.split()[1]) * 1024
        except OSError:
            pass
        return None

    @staticmethod
    def _system_swap() -> tuple[int, int]:
        """Returns (swap_used, swap_total) from /proc/meminfo."""
        total = free = 0
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    parts = line.split()
                    if parts[0] == "SwapTotal:":
                        total = int(parts[1]) * 1024
                    elif parts[0] == "SwapFree:":
                        free = int(parts[1]) * 1024
        except OSError:
            pass
        return total - free, total

    def _get_swap(self) -> tuple[int, int]:
        """Returns (swap_used_bytes, swap_total_bytes)."""
        try:
            if self.cgroup_ver == 2 and os.path.exists("/sys/fs/cgroup/memory.swap.current"):
                with open("/sys/fs/cgroup/memory.swap.current") as f:
                    used = int(f.read().strip())
                total = None
                if os.path.exists("/sys/fs/cgroup/memory.swap.max"):
                    with open("/sys/fs/cgroup/memory.swap.max") as f:
                        content = f.read().strip()
                        if content != "max":
                            total = int(content)
                _, sys_total = self._system_swap()
                return used, total or sys_total or 1
            if self.cgroup_ver == 1 and os.path.exists(
                "/sys/fs/cgroup/memory/memory.memsw.usage_in_bytes"
            ):
                with open("/sys/fs/cgroup/memory/memory.memsw.usage_in_bytes") as f:
                    memsw_used = int(f.read().strip())
                with open(_CGROUP_V1_MEM_USAGE) as f:
                    mem_used = int(f.read().strip())
                _, sys_total = self._system_swap()
                return max(0, memsw_used - mem_used), sys_total or 1
        except OSError:
            pass
        return self._system_swap()

    @staticmethod
    def _get_disk() -> tuple[int, int]:
        """Returns (used_bytes, total_bytes) for the root filesystem."""
        try:
            st = os.statvfs("/")
            total = st.f_blocks * st.f_frsize
            used = (st.f_blocks - st.f_bfree) * st.f_frsize
            return used, total
        except OSError:
            return 0, 1

    def _get_memory(self) -> tuple[int, int]:
        """Returns (used_bytes, limit_bytes); limit falls back to system total."""
        try:
            if self.cgroup_ver == 1:
                with open(_CGROUP_V1_MEM_USAGE) as f:
                    used = int(f.read().strip())
                with open(_CGROUP_V1_MEM_LIMIT) as f:
                    limit_val = int(f.read().strip())
                limit = None if limit_val >= (1 << 62) else limit_val
            elif self.cgroup_ver == 2:
                if not os.path.exists(_CGROUP_V2_MEM_CURR):
                    return 0, self._system_mem_total() or 1
                with open(_CGROUP_V2_MEM_CURR) as f:
                    used = int(f.read().strip())
                limit = None
                if os.path.exists(_CGROUP_V2_MEM_MAX):
                    with open(_CGROUP_V2_MEM_MAX) as f:
                        content = f.read().strip()
                        if content != "max":
                            limit = int(content)
            else:
                with open("/proc/meminfo") as f:
                    info = {}
                    for line in f:
                        parts = line.split()
                        if parts[0] in ("MemTotal:", "MemAvailable:"):
                            info[parts[0]] = int(parts[1]) * 1024
                total = info.get("MemTotal:", 1)
                avail = info.get("MemAvailable:", 0)
                return total - avail, total
        except OSError:
            return 0, self._system_mem_total() or 1
        return used, limit or self._system_mem_total() or 1

    def run(self, stdscr: curses.window):
        curses.curs_set(0)
        stdscr.nodelay(True)
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(_CP_DIM, curses.COLOR_WHITE, -1)
        curses.init_pair(_CP_GREEN, curses.COLOR_GREEN, -1)
        curses.init_pair(_CP_YELLOW, curses.COLOR_YELLOW, -1)
        curses.init_pair(_CP_RED, curses.COLOR_RED, -1)

        s1 = self._sample_cpu()
        t1 = time.monotonic()
        force_clear = False

        while True:
            time.sleep(1)
            t2 = time.monotonic()
            s2 = self._sample_cpu()

            pcts = self._calc_pct(s1, s2, (t2 - t1) * 1e9)
            smoothed = self._smooth(pcts)
            mem_used, mem_limit = self._get_memory()
            swap_used, swap_total = self._get_swap()
            disk_used, disk_total = self._get_disk()
            s1, t1 = s2, t2

            avg_cpu = sum(smoothed.values()) / len(smoothed) if smoothed else 0.0
            mem_pct = mem_used / mem_limit * 100
            swap_pct = swap_used / swap_total * 100 if swap_total else 0.0
            disk_pct = disk_used / disk_total * 100 if disk_total else 0.0
            self._record_history(avg_cpu, mem_pct)

            if force_clear:
                stdscr.clear()
                force_clear = False
            else:
                stdscr.erase()
            height, width = stdscr.getmaxyx()

            # Row 0: title left, datetime right
            now = time.strftime("%Y-%m-%d %H:%M:%S")
            try:
                stdscr.addstr(0, 0, "contop - container aware cpu/memory usage", curses.A_BOLD)
                if width > len(now) + 8:
                    stdscr.addstr(0, width - len(now) - 1, now)
            except curses.error:
                pass

            # Row 1: hostname left, uptime right
            uptime = ("ctr " + _fmt_container_uptime()) if self.cgroup_ver else ("host " + _fmt_uptime())
            try:
                stdscr.addstr(1, 0, f"{self.username}@{self.hostname}")
                if width > len(uptime) + 2:
                    stdscr.addstr(1, width - len(uptime) - 1, uptime)
            except curses.error:
                pass

            # Row 2: separator
            try:
                stdscr.addstr(2, 0, "╌" * (width - 1))
            except curses.error:
                pass

            # Row 3+: info section — labels in default color, values color-coded by threshold.
            # Each chunk (label + value) wraps to the next row if it won't fit.
            cgroup_str = f"cgroup v{self.cgroup_ver}" if self.cgroup_ver else "host"
            has_swap = swap_total >= 100 * 1024
            if has_swap:
                swap_val = f"{_fmt_bytes(swap_used)}/{_fmt_bytes(swap_total)} ({_fmt_pct(swap_pct)})"
                swap_attr: int | None = _color_attr(swap_pct)
            else:
                swap_val, swap_attr = "0 Swp", None
            # each chunk: list of (text, attr) drawn atomically — no wrapping mid-chunk
            chunks: list[list[tuple[str, int | None]]] = [
                [(f"{cgroup_str}  |  {len(self.assigned_cores)} cores", None)],
                [("  |  CPU: ", None), (_fmt_pct(avg_cpu), _color_attr(avg_cpu))],
                [("  |  Mem: ", None), (f"{_fmt_bytes(mem_used)}/{_fmt_bytes(mem_limit)}", _color_attr(mem_pct))],
                [("  |  Swap: ", None), (swap_val, swap_attr)],
                [("  |  Disk: ", None), (f"{_fmt_bytes(disk_used, 0)}/{_fmt_bytes(disk_total, 0)}", _color_attr(disk_pct))],
            ]
            cur_row, cur_col = 3, 0
            for chunk in chunks:
                chunk_len = sum(len(text) for text, _ in chunk)
                if cur_col > 0 and cur_col + chunk_len >= width - 1:
                    cur_row += 1
                    cur_col = 0
                for i, (text, attr) in enumerate(chunk):
                    if i == 0 and cur_col == 0 and text.startswith("  |  "):
                        text = text[5:]
                    try:
                        clipped = text[: max(0, width - 1 - cur_col)]
                        if attr is not None:
                            stdscr.addstr(cur_row, cur_col, clipped, attr)
                        else:
                            stdscr.addstr(cur_row, cur_col, clipped)
                        cur_col += len(clipped)
                    except curses.error:
                        pass

            # separator after info (moves down if info wrapped)
            sep_row = cur_row + 1
            try:
                stdscr.addstr(sep_row, 0, "╌" * (width - 1))
            except curses.error:
                pass

            row = sep_row + 1

            # Sparklines — same width as the memory bar below
            # label "CPU " (4) + " [" (2) + "]" (1) = 7 overhead
            bar_w_spark = max(10, width - 8)
            _draw_sparkline(
                stdscr, row, 0, "CPU ", self._cpu_history, bar_w_spark, self.max_history
            )
            row += 1
            _draw_sparkline(
                stdscr, row, 0, "Mem ", self._mem_history, bar_w_spark, self.max_history
            )
            row += 1
            # ruler indented to align with bar content: label (4) + " [" (2) = 6
            try:
                stdscr.addstr(row, 6, _ruler(bar_w_spark, self.max_history))
            except curses.error:
                pass
            row += 2

            # Memory bar — full width
            # label "Mem " (4) + " [" (2) + "] NNN%" (6) = 12 overhead
            bar_w_mem = max(10, width - 13)
            _draw_bar(stdscr, row, 0, "Mem ", bar_w_mem, mem_pct)
            row += 2

            # CPU bars — row-major so all rows are full except possibly the last.
            # Maximize columns from terminal width to minimize rows.
            # min col width: label (3) + " [" (2) + "] NNN%" (6) + 1 gap + 5 min bar = 17
            n_cores = len(self.assigned_cores)
            n_cols = max(1, min(n_cores, width // 17))
            n_rows = (n_cores + n_cols - 1) // n_cols
            col_width = width // n_cols
            bar_w_cpu = max(5, col_width - 12)

            for r in range(n_rows):
                if row + r >= height - 2:
                    break
                for c in range(n_cols):
                    core_idx = r * n_cols + c
                    if core_idx >= n_cores:
                        break
                    core = self.assigned_cores[core_idx]
                    _draw_bar(stdscr, row + r, c * col_width, f"{core_idx:3d}", bar_w_cpu, smoothed.get(core, 0.0))
            row += n_rows

            try:
                stdscr.addstr(min(height - 1, row + 1), 0, "q: quit  r: refresh")
            except curses.error:
                pass
            stdscr.refresh()

            key = stdscr.getch()
            if key in (ord("q"), ord("Q")):
                break
            if key in (ord("r"), ord("R")):
                force_clear = True


def main():
    parser = argparse.ArgumentParser(description="Container-aware top with per-core CPU bars")
    parser.add_argument(
        "--history",
        type=int,
        default=120,
        metavar="SECONDS",
        help="seconds of history shown in sparklines (default: 120)",
    )
    args = parser.parse_args()

    monitor = _Monitor(history_seconds=args.history)
    try:
        curses.wrapper(monitor.run)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
