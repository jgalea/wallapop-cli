import json
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from . import client

app = typer.Typer(add_completion=False, no_args_is_help=True, help="Search Wallapop (Spain and Portugal) from the terminal.")
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


def main():
    app()
