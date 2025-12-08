"""CLI interface for FreshMart load generator."""

import asyncio
import logging
import signal
import sys

import click
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

from loadgen import __version__
from loadgen.config import PROFILES, get_profile, list_profiles
from loadgen.orchestrator import LoadOrchestrator

console = Console()


def setup_logging(verbose: bool = False):
    """Set up logging configuration.

    Args:
        verbose: Enable verbose logging
    """
    level = logging.DEBUG if verbose else logging.INFO

    # Configure rich handler
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True)],
    )

    # Silence noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


@click.group()
@click.version_option(version=__version__)
def cli():
    """FreshMart Load Generator - Generate realistic load for demonstration."""
    pass


@cli.command()
@click.option(
    "--profile",
    type=click.Choice(list(PROFILES.keys())),
    default="demo",
    help="Load profile to use",
)
@click.option(
    "--api-url",
    default="http://localhost:8080",
    help="FreshMart API base URL",
)
@click.option(
    "--duration",
    type=int,
    help="Duration in minutes (overrides profile default)",
)
@click.option(
    "--seed",
    type=int,
    help="Random seed for reproducibility",
)
@click.option(
    "--verbose",
    is_flag=True,
    help="Enable verbose logging",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show configuration without running",
)
def start(
    profile: str,
    api_url: str,
    duration: int,
    seed: int,
    verbose: bool,
    dry_run: bool,
):
    """Start load generation with specified profile."""
    setup_logging(verbose)

    # Get profile configuration
    try:
        load_profile = get_profile(profile)
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)

    # Show configuration
    console.print("\n[bold cyan]FreshMart Load Generator[/bold cyan]")
    console.print(f"Version: {__version__}\n")

    table = Table(title="Configuration")
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Profile", load_profile.name)
    table.add_row("Description", load_profile.description)
    table.add_row("Target Rate", f"{load_profile.orders_per_minute} orders/min")
    table.add_row("Concurrent Workflows", str(load_profile.concurrent_workflows))
    table.add_row(
        "Duration",
        f"{duration or load_profile.duration_minutes or 'unlimited'} minutes",
    )
    table.add_row("API URL", api_url)
    if seed:
        table.add_row("Random Seed", str(seed))

    console.print(table)
    console.print()

    if dry_run:
        console.print("[yellow]Dry run - not executing[/yellow]")
        return

    # Create orchestrator
    orchestrator = LoadOrchestrator(
        api_url=api_url,
        profile=load_profile,
        seed=seed,
    )

    # Set up signal handlers for graceful shutdown
    def signal_handler(sig, frame):
        console.print("\n[yellow]Interrupt received, stopping gracefully...[/yellow]")
        orchestrator.stop_requested = True

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Run orchestrator
    try:
        asyncio.run(orchestrator.run(duration_minutes=duration))
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
    except Exception as e:
        console.print(f"\n[red]Error: {e}[/red]")
        if verbose:
            console.print_exception()
        sys.exit(1)


@cli.command()
def profiles():
    """List available load profiles."""
    console.print("\n[bold cyan]Available Load Profiles[/bold cyan]\n")

    for profile in list_profiles():
        table = Table(title=f"{profile.name.upper()} Profile", show_header=False)
        table.add_column("Setting", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Description", profile.description)
        table.add_row("Orders/min", str(profile.orders_per_minute))
        table.add_row("Concurrent Workflows", str(profile.concurrent_workflows))
        table.add_row("Default Duration", f"{profile.duration_minutes} minutes")

        console.print(table)
        console.print()


@cli.command()
@click.argument("api_url", default="http://localhost:8080")
def health(api_url: str):
    """Check FreshMart API health."""
    from loadgen.api_client import FreshMartAPIClient

    setup_logging()

    async def check_health():
        async with FreshMartAPIClient(base_url=api_url) as client:
            try:
                result = await client.health_check()
                console.print(f"[green]✓ API is healthy at {api_url}[/green]")
                console.print(f"Response: {result}")
                return True
            except Exception as e:
                console.print(f"[red]✗ API health check failed: {e}[/red]")
                return False

    try:
        success = asyncio.run(check_health())
        sys.exit(0 if success else 1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


def main():
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()
