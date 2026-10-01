import json
import sys
from datetime import datetime
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from . import account, client

app = typer.Typer(add_completion=False, no_args_is_help=True, help="Search, message and make offers on Wallapop (Spain and Portugal) from the terminal.")
console = Console()


def _fail(e):
    console.print(f"[red]{e}[/red]")
    raise typer.Exit(1)


@app.command()
def search(
    query: str,
    min_price: Optional[float] = typer.Option(None, "--min", help="Minimum price in EUR"),
    max_price: Optional[float] = typer.Option(None, "--max", help="Maximum price in EUR"),
    near: Optional[str] = typer.Option(None, "--near", "-n", help="Town to search around, e.g. Madrid or Lisboa"),
    radius: Optional[float] = typer.Option(None, "--radius", "-r", help="Km around --near (sorts by distance)"),
    sort: Optional[str] = typer.Option(None, "--sort", "-s", help="relevance, new, near, cheap or dear"),
    ships: bool = typer.Option(False, "--ships", help="Only items the seller will ship"),
    limit: int = typer.Option(40, "--limit", "-l"),
    loose: bool = typer.Option(False, "--loose", help="Keep Wallapop's fuzzy matches instead of requiring every word in the title"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Search listings."""
    if sort and sort not in client.SORTS:
        raise typer.BadParameter(f"--sort must be one of {', '.join(client.SORTS)}")
    if radius and not near:
        raise typer.BadParameter("--radius needs --near")
    try:
        rows, where = client.search(query, min_price=min_price, max_price=max_price, near=near, radius_km=radius,
                                    sort=sort, limit=limit, strict=not loose, ships_only=ships)
    except client.WallapopError as e:
        _fail(e)
    if as_json:
        print(json.dumps([{k: v for k, v in r.items() if k != "description"} for r in rows], ensure_ascii=False, indent=2))
        return
    if not rows:
        console.print(f"No listings with “{query}” in the title" + ("" if loose else " (try --loose)") + ".")
        return
    title = f"{len(rows)} listings for “{query}”" + (f" near {where}" if where else "") + (f" (≤{radius:g} km)" if radius else "")
    t = Table(title=title)
    t.add_column("Price", no_wrap=True, justify="right")
    t.add_column("Title", overflow="fold")
    t.add_column("Where", overflow="fold", max_width=22)
    t.add_column("Listed", no_wrap=True)
    t.add_column("ID", no_wrap=True, style="dim")
    for r in rows:
        flags = (" [green]ship[/green]" if r["ships"] else "") + (" [yellow]reserved[/yellow]" if r["reserved"] else "")
        t.add_row(f"€{r['price']:g}", f"[link={r['url']}]{r['title']}[/link]{flags}",
                  f"{r['city'] or '-'} {r['country'] or ''}".strip(), r["created"], r["id"])
    console.print(t)


@app.command()
def show(ref: str = typer.Argument(..., help="Item id or URL"), as_json: bool = typer.Option(False, "--json")):
    """Show one listing in full."""
    try:
        r = client.item(ref)
    except client.WallapopError as e:
        _fail(e)
    if as_json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return
    console.print(f"[bold]{r['title']}[/bold]  €{r['price']:g}")
    console.print(" · ".join(x for x in [r["condition"], f"{r['city']}, {r['country']}", "ships" if r["ships"] else "pickup only",
                                         f"{r['views']} views, {r['favorites']} favourites", f"updated {r['modified']}"] if x))
    console.print(r["url"], style="dim")
    console.print()
    console.print(r["description"].strip())


@app.command()
def login(cookie: Optional[str] = typer.Option(None, "--cookie", help=f"Paste the {account.COOKIE} value instead of reading Chrome")):
    """Log in by reusing your Chrome session (log in at es.wallapop.com first)."""
    try:
        name = account.login(cookie or account.cookie_from_chrome())
    except client.WallapopError as e:
        _fail(e)
    console.print(f"Logged in as {name}. Session saved to {account.STORE}")


@app.command()
def inbox(limit: int = typer.Option(20, "--limit", "-l"), as_json: bool = typer.Option(False, "--json")):
    """List your conversations, newest first."""
    try:
        convs = account.Session().inbox(limit)
    except client.WallapopError as e:
        _fail(e)
    if as_json:
        print(json.dumps(convs, ensure_ascii=False, indent=2))
        return
    t = Table(title=f"{len(convs)} conversations")
    t.add_column("With", overflow="fold")
    t.add_column("Item", overflow="fold")
    t.add_column("Last message", overflow="fold")
    t.add_column("Conversation", no_wrap=True, style="dim")
    for c in convs:
        msgs = (c.get("messages") or {}).get("messages") or []
        last = msgs[0] if msgs else {}
        text = ("you: " if last.get("from_self") else "") + (last.get("text") or "")
        unread = f" [yellow]({c['unread_messages']} new)[/yellow]" if c.get("unread_messages") else ""
        t.add_row(c["with_user"]["name"] + unread, (c.get("item") or {}).get("title", ""), text[:80], c["hash"])
    console.print(t)


def _print_conv(conv):
    it = conv.get("item") or {}
    console.print(f"[bold]{conv['with_user']['name']}[/bold] · {it.get('title', '')}", highlight=False)
    msgs = (conv.get("messages") or {}).get("messages") or []
    for m in sorted(msgs, key=lambda m: m.get("timestamp", 0)):
        when = datetime.fromtimestamp(m.get("timestamp", 0) / 1000).strftime("%d %b %H:%M")
        who = "[cyan]you[/cyan]" if m.get("from_self") else conv["with_user"]["name"]
        console.print(f"[dim]{when}[/dim] {who}: {m.get('text') or '[' + m.get('type', '?') + ']'}", highlight=False)


@app.command()
def chat(ref: str = typer.Argument(..., help="Conversation id, or an item id/URL you've messaged about")):
    """Show a conversation."""
    try:
        conv = account.Session().conversation_for(ref)
    except client.WallapopError as e:
        _fail(e)
    if not conv:
        _fail(f"no conversation about {ref} yet. Start one with: wallapop send {ref} \"...\"")
    _print_conv(conv)


@app.command()
def send(ref: str = typer.Argument(..., help="Conversation id, or an item id/URL"),
         text: str = typer.Argument(..., help="Message text, or - to read stdin")):
    """Message a seller. Starts the conversation if there isn't one yet."""
    if text == "-":
        text = sys.stdin.read().strip()
    if not text:
        raise typer.BadParameter("empty message")
    try:
        s = account.Session()
        conv = s.conversation_for(ref) or s.start(client.item(ref)["id"])
        s.send(conv, text)
        conv = s.conversation(conv["hash"])
    except client.WallapopError as e:
        _fail(e)
    _print_conv(conv)


@app.command()
def offer(ref: str = typer.Argument(..., help="Item id or URL"),
          amount: float = typer.Argument(..., help="Offer in EUR"),
          dry_run: bool = typer.Option(False, "--dry-run", help="Check the terms without sending")):
    """Make a formal Wallapop offer on a listing."""
    try:
        s = account.Session()
        it = client.item(ref)
        terms = s.offer_terms(it["id"])
    except client.WallapopError as e:
        _fail(e)
    console.print(f"{it['title']}: asking €{terms['price']:g}, lowest offer Wallapop accepts €{terms['min']:g}, "
                  f"{terms['remaining']} of {terms['per_day']} offers left today", highlight=False)
    if amount < terms["min"]:
        _fail(f"€{amount:g} is below Wallapop's floor of €{terms['min']:g} for this listing. Not sent.")
    if amount >= terms["price"]:
        _fail(f"€{amount:g} isn't below the asking price. Not sent.")
    if not terms["remaining"]:
        _fail("no offers left today. Not sent.")
    if dry_run:
        console.print(f"€{amount:g} would be accepted. Not sent (--dry-run).")
        return
    try:
        s.offer(it["id"], round(amount, 2), terms["currency"])
    except client.WallapopError as e:
        _fail(e)
    console.print(f"[green]Offer of €{amount:g} sent.[/green]")


def main():
    app()
