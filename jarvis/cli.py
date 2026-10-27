import json
import time
from datetime import datetime

from rich.align import Align
from rich.console import Console, Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

from jarvis.models.default.default_model import UTILITY_TOOLS, model_version, send_message, user_name

console = Console()

BANNER = [
    "     ██╗ █████╗ ██████╗ ██╗   ██╗██╗███████╗",
    "     ██║██╔══██╗██╔══██╗██║   ██║██║██╔════╝",
    "     ██║███████║██████╔╝██║   ██║██║███████╗",
    "██   ██║██╔══██║██╔══██╗╚██╗ ██╔╝██║╚════██║",
    "╚█████╔╝██║  ██║██║  ██║ ╚████╔╝ ██║███████║",
    " ╚════╝ ╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚═╝╚══════╝",
]
# Top to bottom fade from cyan into blue.
BANNER_COLORS = ["#00ffff", "#00e5ff", "#00c8ff", "#00a8ff", "#0088ff", "#0066ff"]

# Icon and color per tool; anything not listed gets the default.
TOOL_STYLES = {
    "web_search": ("🔍", "yellow"),
    "web_fetch": ("🌐", "yellow"),
    "get_weather": ("🌤 ", "bright_blue"),
    "get_daily_forecast": ("🌤 ", "bright_blue"),
    "get_hourly_forecast": ("🌤 ", "bright_blue"),
    "get_air_quality": ("🌫 ", "bright_blue"),
    "get_sun_and_moon": ("🌙", "bright_blue"),
    "get_stock_price": ("📈", "green"),
    "get_crypto_price": ("🪙", "green"),
    "convert_currency": ("💱", "green"),
    "get_scores": ("🏆", "green"),
    "define": ("📖", "bright_cyan"),
    "media_control": ("🎵", "magenta"),
    "get_now_playing": ("🎵", "magenta"),
    "set_timer": ("⏱ ", "bright_red"),
    "list_timers": ("⏱ ", "bright_red"),
    "cancel_timer": ("⏱ ", "bright_red"),
    "calculate": ("🧮", "bright_cyan"),
    "convert_units": ("📐", "bright_cyan"),
    "search_files": ("📂", "bright_yellow"),
    "open_app": ("🚀", "bright_magenta"),
    "close_app": ("🚪", "bright_magenta"),
    "read_clipboard": ("📋", "bright_yellow"),
    "write_clipboard": ("📋", "bright_yellow"),
    "get_network_status": ("📡", "bright_blue"),
    "ping_host": ("📡", "bright_blue"),
    "get_system_status": ("🖥 ", "bright_green"),
    "get_system_specifications": ("🖥 ", "bright_green"),
    "set_do_not_disturb": ("🔕", "bright_magenta"),
    "get_do_not_disturb": ("🔕", "bright_magenta"),
}
DEFAULT_TOOL_STYLE = ("⚙ ", "bright_magenta")


def _greeting():
    hour = datetime.now().hour
    period = "morning" if hour < 12 else "afternoon" if hour < 18 else "evening"
    first_name = user_name.split()[0] if user_name else ""
    return f"Good {period}, {first_name}." if first_name else f"Good {period}."


def _print_banner():
    banner = Text("\n".join(BANNER))
    for index, color in enumerate(BANNER_COLORS):
        banner.stylize(color, sum(len(line) + 1 for line in BANNER[:index]), sum(len(line) + 1 for line in BANNER[: index + 1]) - 1)

    status = Text.assemble(
        ("● ", "bold green"),
        ("online", "green"),
        ("   ·   ", "dim"),
        (model_version, "cyan"),
        ("   ·   ", "dim"),
        (f"{len(UTILITY_TOOLS)} tools + web", "cyan"),
    )
    console.print(
        Panel(
            Group(
                Align.center(banner),
                Text(""),
                Align.center(Text(_greeting(), style="bold white")),
                Align.center(status),
            ),
            border_style="bright_blue",
            padding=(1, 4),
            subtitle="[dim]Ctrl+C or 'exit' to quit[/dim]",
        )
    )


def _format_input(tool_input):
    parts = []
    for key, value in tool_input.items():
        text = json.dumps(value, ensure_ascii=False)
        if len(text) > 60:
            text = text[:57] + "..."
        parts.append(f"{key}={text}")
    return ", ".join(parts)


def _preview(output):
    text = " ".join(str(output).split())
    return text if len(text) <= 100 else text[:97] + "..."


class _Session:
    """Prints each tool call and result as they happen, and tracks the spinner."""

    def __init__(self, status):
        self.status = status
        self.calls = 0
        self.started = {}

    def handle(self, event):
        name = event["name"]
        icon, color = TOOL_STYLES.get(name, DEFAULT_TOOL_STYLE)
        if event["type"] == "tool_call":
            self.calls += 1
            self.started[name] = time.perf_counter()
            kind = "server" if event.get("server") else "local"
            console.print(
                Text.assemble(
                    (f"  {icon} ", color),
                    (name, f"bold {color}"),
                    (f"  {_format_input(event['input'])}", "dim"),
                    (f"  [{kind}]", "dim italic"),
                )
            )
            self.status.update(Text(f"Running {name}...", style=color))
        else:
            seconds = event.get("seconds")
            if seconds is None:
                seconds = time.perf_counter() - self.started.get(name, time.perf_counter())
            mark, style = ("✗", "red") if event["is_error"] else ("✓", "green")
            console.print(
                Text.assemble(
                    ("     ╰─ ", "dim"),
                    (f"{mark} ", style),
                    (f"{seconds:.1f}s", style),
                    (f"  {_preview(event['output'])}", "dim"),
                )
            )
            self.status.update(Text("Thinking...", style="cyan"))


def _ask(message):
    started = time.perf_counter()
    with console.status(Text("Thinking...", style="cyan"), spinner="dots12") as status:
        session = _Session(status)
        reply = send_message(message, "default", on_event=session.handle)
    elapsed = time.perf_counter() - started

    calls = f"{session.calls} tool call{'s' if session.calls != 1 else ''}" if session.calls else "no tools"
    console.print(
        Panel(
            Markdown(reply.strip() or "*(no response)*"),
            title="[bold cyan]JARVIS[/]",
            title_align="left",
            subtitle=f"[dim]{elapsed:.1f}s · {calls}[/dim]",
            subtitle_align="right",
            border_style="cyan",
            padding=(1, 2),
        )
    )


def run():
    _print_banner()
    try:
        while True:
            console.print()
            message = console.input("[bold cyan]>[/] ").strip()
            if not message:
                continue
            if message.lower() in {"exit", "quit"}:
                break
            try:
                _ask(message)
            except KeyboardInterrupt:
                raise
            except Exception as error:
                console.print(
                    Panel(
                        Text(f"{type(error).__name__}: {error}"),
                        title="[bold red]Error[/]",
                        title_align="left",
                        border_style="red",
                    )
                )
    except (KeyboardInterrupt, EOFError):
        console.print()
    console.print("[dim]Goodbye sir.[/dim]")
