"""Commands for connecting ChatGPT plan usage to the local CLI."""

import typer
from rich.console import Console
from rich.table import Table

from tradingagents.chatgpt_plan_auth import (
    ChatGPTAuthError,
    connect_chatgpt,
    connection_status,
    disconnect_chatgpt,
    list_account_models,
)

auth_app = typer.Typer(
    name="auth",
    help="Connect the local CLI to an eligible ChatGPT plan.",
    no_args_is_help=True,
)
console = Console()


@auth_app.command("connect")
def connect() -> None:
    """Authorize TradingAgents to use ChatGPT plan inference."""
    console.print("Opening a browser for Sign in with ChatGPT...")
    try:
        account = connect_chatgpt()
    except ChatGPTAuthError as exc:
        console.print(f"[red]{exc}[/red]", stderr=True)
        raise typer.Exit(code=1) from None
    identity = account["email"] or "ChatGPT account"
    console.print(f"[green]Connected to ChatGPT plan usage for {identity}.[/green]")


@auth_app.command("status")
def status() -> None:
    """Show whether a local ChatGPT plan connection exists."""
    try:
        account = connection_status()
    except ChatGPTAuthError as exc:
        console.print(f"[red]{exc}[/red]", stderr=True)
        raise typer.Exit(code=1) from None
    if account is None:
        console.print("ChatGPT plan usage is not connected.")
        return
    identity = account["email"] or "ChatGPT account"
    console.print(f"ChatGPT plan usage is connected for {identity}.")


@auth_app.command("models")
def models() -> None:
    """List models available to the connected ChatGPT account."""
    try:
        available = list_account_models()
    except ChatGPTAuthError as exc:
        console.print(f"[red]{exc}[/red]", stderr=True)
        raise typer.Exit(code=1) from None
    table = Table("Model", "Model ID")
    for display_name, slug in available:
        table.add_row(display_name, slug)
    console.print(table)


@auth_app.command("disconnect")
def disconnect() -> None:
    """Revoke the renewable session when possible and remove local tokens."""
    try:
        remote_revoked = disconnect_chatgpt()
    except ChatGPTAuthError as exc:
        console.print(f"[red]{exc}[/red]", stderr=True)
        raise typer.Exit(code=1) from None
    console.print("Local ChatGPT credentials were removed.")
    if remote_revoked:
        console.print("The renewable session was revoked.")
    else:
        console.print(
            "Remote revocation was not confirmed. You can also disconnect the app in ChatGPT Settings."
        )
