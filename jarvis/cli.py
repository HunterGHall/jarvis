import json
import time
from datetime import datetime

from rich.align import Align
from rich.console import Console, Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

from jarvis.models.default.default_model import UTILITY_TOOLS, model_version, send_message, show_cost, user_name
from jarvis.pricing import estimate_cost, format_cost, format_tokens

# The utility folders are added to the path by the model module imported above.
import file_operations  # noqa: E402

console = Console()
_active_status = None


def _confirm(message):
    """Asks before a destructive action, pausing the spinner so the prompt is readable."""
    if _active_status:
        _active_status.stop()
    try:
        answer = console.input(Text.assemble(("\n  ⚠  ", "bold yellow"), (message, "yellow"), ("  [y/N] ", "bold")))
    except EOFError:
        answer = ""
    finally:
        if _active_status:
            _active_status.start()
    return answer.strip().lower() in {"y", "yes"}


file_operations.CONFIRM = _confirm

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
    "get_headlines": ("📰", "bright_white"),
    "search_news": ("📰", "bright_white"),
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
    "delete_file": ("🗑 ", "red"),
    "move_file": ("📦", "bright_yellow"),
    "copy_file": ("📄", "bright_yellow"),
    "rename_file": ("✏ ", "bright_yellow"),
    "create_folder": ("📁", "bright_yellow"),
    "search_recipes": ("🍳", "orange3"),
    "get_recipe": ("🍳", "orange3"),
    "random_recipe": ("🎲", "orange3"),
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
        self.tokens_in = 0
        self.tokens_out = 0
        self.searches = 0
        # None once any call is on a model without known prices.
        self.cost_in = 0.0
        self.cost_out = 0.0

    def _add_usage(self, event):
        usage = event["usage"]
        self.tokens_in += sum(
            usage.get(key) or 0 for key in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
        )
        self.tokens_out += usage.get("output_tokens") or 0
        self.searches += (usage.get("server_tool_use") or {}).get("web_search_requests") or 0
        call_cost = estimate_cost(event["model"], usage)
        if call_cost is None or self.cost_in is None:
            self.cost_in = self.cost_out = None
        else:
            self.cost_in += call_cost[0]
            self.cost_out += call_cost[1]

    def cost_summary(self):
        if self.cost_in is None:
            parts = [f"{format_tokens(self.tokens_in)} in / {format_tokens(self.tokens_out)} out"]
        else:
            parts = [
                f"{format_tokens(self.tokens_in)} in {format_cost(self.cost_in)}",
                f"{format_tokens(self.tokens_out)} out {format_cost(self.cost_out)}",
                f"{format_cost(self.cost_in + self.cost_out)} total",
            ]
        if self.searches:
            # Web searches are billed per search, on top of the token cost.
            parts.append(f"+{self.searches} web search{'es' if self.searches != 1 else ''}")
        return " · ".join(parts)

    def handle(self, event):
        if event["type"] == "usage":
            self._add_usage(event)
            return
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
    global _active_status
    started = time.perf_counter()
    with console.status(Text("Thinking...", style="cyan"), spinner="dots12") as status:
        _active_status = status
        session = _Session(status)
        try:
            reply = send_message(message, "default", on_event=session.handle)
        finally:
            _active_status = None
    elapsed = time.perf_counter() - started

    calls = f"{session.calls} tool call{'s' if session.calls != 1 else ''}" if session.calls else "no tools"
    console.print(
        Panel(
            Markdown(reply.strip() or "*(no response)*"),
            title="[bold cyan]JARVIS[/]",
            title_align="left",
            subtitle=Text(f"{elapsed:.1f}s · {calls}", style="dim"),
            subtitle_align="right",
            border_style="cyan",
            padding=(1, 2),
        )
    )
    if show_cost:
        # Its own line, since a panel subtitle gets cut off on a narrow terminal.
        console.print(Align.right(Text(session.cost_summary(), style="dim yellow")))


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
