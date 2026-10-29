"""Interactive Grill-Me and Alignment Engine for Natasha and Taghi."""

from __future__ import annotations

import sys
from typing import Any, Callable
from rich.console import Console
from rich.panel import Panel
from rich.markup import escape
from contracts import ClarificationOption, ClarificationQuestion
from tools.ui import _get_theme, console


def format_grill_answers_for_prompt(
    answers: dict[str, str],
    questions: list[ClarificationQuestion] | None = None,
) -> str:
    """Format answered questions into structured prompt context for agent realignment."""
    if not answers:
        return ""

    q_map: dict[str, ClarificationQuestion] = {}
    if questions:
        for q in questions:
            q_map[q.id] = q

    lines: list[str] = ["User Confirmed Decisions & Specifications:"]
    for q_id, answer in answers.items():
        q_obj = q_map.get(q_id)
        label = q_obj.question if q_obj else q_id
        category = f"[{q_obj.category}] " if q_obj and q_obj.category else ""
        lines.append(f"- {category}{label}: {answer}")
    return "\n".join(lines)


def has_non_default_answers(
    questions: list[ClarificationQuestion],
    answers: dict[str, str],
) -> bool:
    """Return True if any question received a custom answer or a non-default option selection."""
    if not answers:
        return False
    for q in questions:
        if getattr(q, "custom_response", None):
            return True
        if q.id in answers:
            def_opt: ClarificationOption | None = None
            for opt in q.options:
                if opt.is_default:
                    def_opt = opt
                    break
            if not def_opt and q.options:
                def_opt = q.options[0]

            if def_opt:
                # If selected key doesn't match default key and label doesn't match default label
                if q.selected_option and q.selected_option != def_opt.key:
                    return True
                if answers[q.id] != def_opt.label:
                    return True
    return False


def run_grill_session(
    questions: list[ClarificationQuestion],
    agent_name: str = "natasha",
    title: str | None = None,
    auto: bool = False,
    input_func: Callable[[str], str] | None = None,
    max_questions: int = 10,
) -> tuple[dict[str, str], bool]:
    """
    Run an interactive multi-choice & open-response alignment interview.

    Args:
        questions: List of clarification/grill questions (up to max_questions).
        agent_name: Lead asking the questions ('natasha', 'taghi', etc.).
        title: Custom title for the panel header.
        auto: If True, automatically accept all recommended defaults.
        input_func: Custom input function for testability (defaults to input).
        max_questions: Maximum number of questions to ask in this session (default 10).

    Returns:
        tuple[answers, quit_requested]:
          answers: dict mapping question id -> confirmed answer text
          quit_requested: True if user opted to cancel execution
    """
    if not questions:
        return {}, False

    theme = _get_theme(agent_name.lower())
    active_questions = questions[:max_questions]
    answers: dict[str, str] = {}

    # Helper to find default option for a question
    def get_default_option(q: ClarificationQuestion) -> ClarificationOption | None:
        for opt in q.options:
            if opt.is_default:
                return opt
        return q.options[0] if q.options else None

    # Automated or non-interactive headless execution: resolve all defaults immediately
    ask = input_func or input
    is_headless = auto or (input_func is None and not sys.stdin.isatty())
    if is_headless:
        for q in active_questions:
            def_opt = get_default_option(q)
            if def_opt:
                q.selected_option = def_opt.key
                answers[q.id] = def_opt.label
            else:
                answers[q.id] = "Default"
        return answers, False

    # Interactive Grill Session
    header_title = title or f"🎯 {theme['name']} Alignment & Architecture Grill"
    banner_text = (
        f"[{theme['color']}][bold]{theme['icon']} {theme['name']}[/bold] ({theme['role']})[/] "
        f"wants to clarify [cyan]{len(active_questions)} specifications[/cyan] to ensure the build matches your intent.\n"
        "[dim]Controls: [green][Enter][/green] Accept Default | [cyan][1, 2...][/cyan] Select | [yellow][c][/yellow] Custom text | [magenta][a][/magenta] Accept all remaining | [red][q][/red] Quit[/dim]"
    )
    console.print()
    console.print(
        Panel(
            banner_text,
            title=f"[bold {theme['color']}]{header_title}[/bold {theme['color']}]",
            title_align="left",
            border_style=theme.get("border", theme["color"]),
            padding=(0, 2),
        )
    )

    accept_all_remaining = False

    for idx, q in enumerate(active_questions, start=1):
        def_opt = get_default_option(q)

        if accept_all_remaining:
            if def_opt:
                q.selected_option = def_opt.key
                answers[q.id] = def_opt.label
            continue

        cat_badge = f" [dim]({q.category})[/dim]" if q.category else ""
        console.print(f"\n[bold {theme['color']}][{idx}/{len(active_questions)}][/bold {theme['color']}] [bold white]{escape(q.question)}[/bold white]{cat_badge}")

        for opt in q.options:
            is_def = opt.is_default or (def_opt and opt.key == def_opt.key)
            tag = " [bold green](Recommended)[/bold green]" if is_def else ""
            desc = f" [dim]— {escape(opt.description)}[/dim]" if opt.description else ""
            console.print(f"     [bold cyan]\\[{escape(str(opt.key))}][/bold cyan] {escape(opt.label)}{tag}{desc}")

        while True:
            try:
                prompt_label = f"[{theme['name']}] > "
                user_choice = ask(prompt_label).strip()
            except (EOFError, KeyboardInterrupt):
                console.print("\n[yellow]Session interrupted by user.[/yellow]")
                return answers, True

            low = user_choice.lower()

            # Empty enter: choose default
            if low == "":
                if def_opt:
                    q.selected_option = def_opt.key
                    answers[q.id] = def_opt.label
                    console.print(f"   [bold green]✔ Accepted default: {escape(def_opt.label)}[/bold green]")
                else:
                    answers[q.id] = "Accepted"
                break

            # Quit
            if low in ("q", "quit", "exit"):
                return answers, True

            # Accept all remaining defaults
            if low in ("a", "all", "accept-all"):
                accept_all_remaining = True
                if def_opt:
                    q.selected_option = def_opt.key
                    answers[q.id] = def_opt.label
                    console.print(f"   [bold green]✔ Accepted default: {escape(def_opt.label)}[/bold green]")
                    console.print("   [dim]↳ Accepting all remaining defaults...[/dim]")
                break

            # Custom freeform prompt
            if low in ("c", "custom"):
                try:
                    custom_text = ask("   📝 Enter custom specification / answer: ").strip()
                except (EOFError, KeyboardInterrupt):
                    return answers, True
                if custom_text:
                    q.custom_response = custom_text
                    q.selected_option = "custom"
                    answers[q.id] = custom_text
                    console.print(f"   [bold yellow]✔ Recorded custom answer: {escape(custom_text)}[/bold yellow]")
                    break
                else:
                    console.print("   [dim]No input provided; please choose an option or enter text.[/dim]")
                    continue

            # Check if user entered one of the option keys (e.g. "1", "2")
            matched_opt = None
            for opt in q.options:
                if str(opt.key).strip().lower() == low:
                    matched_opt = opt
                    break

            if matched_opt:
                q.selected_option = matched_opt.key
                answers[q.id] = matched_opt.label
                console.print(f"   [bold green]✔ Selected option \\[{matched_opt.key}]: {escape(matched_opt.label)}[/bold green]")
                break

            # Freeform text typed directly at choice prompt
            q.custom_response = user_choice
            q.selected_option = "custom"
            answers[q.id] = user_choice
            console.print(f"   [bold yellow]✔ Recorded specification: {escape(user_choice)}[/bold yellow]")
            break

    console.print()
    return answers, False
