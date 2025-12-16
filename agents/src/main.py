"""Agent CLI - Main entry point."""

import asyncio
import logging
import sys
import uuid

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from src.config import get_settings
from src.graphs.ops_assistant_graph import run_assistant

# Configure logging
settings = get_settings()
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

# Suppress HTTP client logging while keeping agent thinking logs
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("requests").setLevel(logging.WARNING)

# Suppress other verbose loggers (keep agent reasoning visible)
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("anthropic").setLevel(logging.WARNING)

app = typer.Typer(help="FreshMart Operations Assistant CLI")
console = Console()


@app.command()
def chat(
    message: str = typer.Argument(None, help="Message to send to the assistant"),
    thread_id: str = typer.Option(None, "--thread-id", "-t", help="Conversation thread ID for memory persistence"),
):
    """
    Chat with the FreshMart Operations Assistant.

    Examples:
        python -m src.main "Show all OUT_FOR_DELIVERY orders"
        python -m src.main "Find orders for customer Alex"
        python -m src.main "Mark order FM-1001 as DELIVERED"

        # Continue a conversation:
        python -m src.main --thread-id my-session "Find orders for Lisa"
        python -m src.main --thread-id my-session "Show me her orders"
    """
    if not message:
        # Interactive mode with persistent event loop and session memory
        # Generate a unique thread_id for this interactive session
        session_thread_id = thread_id or f"session-{uuid.uuid4().hex[:8]}"

        console.print(Panel.fit(
            "[bold green]FreshMart Operations Assistant[/bold green]\n"
            "Type your questions about orders, stores, and couriers.\n"
            f"Session ID: [cyan]{session_thread_id}[/cyan]\n"
            "Type 'quit' or 'exit' to leave.",
            title="Welcome",
        ))

        async def interactive_loop():
            while True:
                try:
                    user_input = console.input("\n[bold blue]You:[/bold blue] ")
                    if user_input.lower() in ("quit", "exit", "q"):
                        console.print("[yellow]Goodbye![/yellow]")
                        break

                    if not user_input.strip():
                        continue

                    # Stream events to show what the agent is doing
                    console.print()  # Blank line before thinking output
                    final_response = None
                    async for event_type, data in run_assistant(user_input, thread_id=session_thread_id, stream_events=True):
                        if event_type == "tool_call":
                            tool_name = data.get("name", "unknown")
                            args_str = ", ".join(f"{k}={repr(v)}" for k, v in data.get("args", {}).items())
                            console.print(f"[dim]Calling {tool_name}({args_str})[/dim]")
                        elif event_type == "tool_result":
                            content = data.get("content", "")
                            if len(content) > 80:
                                content = content[:77] + "..."
                            console.print(f"[dim]Tool returned: {content}[/dim]")
                        elif event_type == "response":
                            final_response = data

                    # Display final response
                    if final_response:
                        console.print("\n[bold green]Assistant:[/bold green]")
                        console.print(Markdown(final_response))
                    else:
                        console.print("[red]No response received[/red]")

                except KeyboardInterrupt:
                    console.print("\n[yellow]Goodbye![/yellow]")
                    break
                except Exception as e:
                    console.print(f"[red]Error: {e}[/red]")
                    import traceback
                    console.print(f"[dim]{traceback.format_exc()}[/dim]")

        # Run with a single event loop for the entire session
        try:
            asyncio.run(interactive_loop())
        except KeyboardInterrupt:
            console.print("\n[yellow]Goodbye![/yellow]")
    else:
        # Single message mode
        # Use provided thread_id or generate a one-time ID
        msg_thread_id = thread_id or f"oneshot-{uuid.uuid4().hex[:8]}"

        async def run_once():
            console.print()
            final_response = None
            async for event_type, data in run_assistant(message, thread_id=msg_thread_id, stream_events=True):
                if event_type == "tool_call":
                    tool_name = data.get("name", "unknown")
                    args_str = ", ".join(f"{k}={repr(v)}" for k, v in data.get("args", {}).items())
                    console.print(f"[dim]Calling {tool_name}({args_str})[/dim]")
                elif event_type == "tool_result":
                    content = data.get("content", "")
                    if len(content) > 80:
                        content = content[:77] + "..."
                    console.print(f"[dim]Tool returned: {content}[/dim]")
                elif event_type == "response":
                    final_response = data

            if final_response:
                console.print()
                console.print(Panel(Markdown(final_response), title="Response"))
            else:
                console.print("[red]No response received[/red]")

        try:
            asyncio.run(run_once())
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            import traceback
            console.print(f"[dim]{traceback.format_exc()}[/dim]")
            sys.exit(1)


@app.command()
def check():
    """Check agent configuration and connectivity."""
    console.print("[bold]Checking agent configuration...[/bold]\n")

    settings = get_settings()

    # Check LLM
    console.print("LLM Configuration:")
    if settings.anthropic_api_key:
        console.print("  [green]Anthropic API key configured[/green]")
    elif settings.openai_api_key:
        console.print("  [green]OpenAI API key configured[/green]")
    else:
        console.print("  [red]No LLM API key found![/red]")
        console.print("  Set ANTHROPIC_API_KEY or OPENAI_API_KEY")

    # Check API
    console.print(f"\nAPI Base: {settings.agent_api_base}")
    console.print(f"OpenSearch: {settings.agent_os_base}")
    console.print(f"Materialize: {settings.mz_host}:{settings.mz_port}")


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", help="Host to bind to"),
    port: int = typer.Option(8081, help="Port to bind to"),
):
    """
    Run the agent as a simple HTTP service.

    POST /chat with JSON {"message": "your question"} to interact with the assistant.
    """
    from http.server import HTTPServer, BaseHTTPRequestHandler
    import json

    class AgentHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/health":
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "healthy"}).encode())
            else:
                self.send_response(404)
                self.end_headers()

        def do_POST(self):
            if self.path == "/chat":
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length)
                try:
                    data = json.loads(body)
                    message = data.get("message", "")
                    thread_id = data.get("thread_id", f"api-{uuid.uuid4().hex[:8]}")

                    if not message:
                        self.send_response(400)
                        self.send_header("Content-type", "application/json")
                        self.end_headers()
                        self.wfile.write(json.dumps({"error": "message required"}).encode())
                        return

                    response = asyncio.run(run_assistant(message, thread_id=thread_id))
                    self.send_response(200)
                    self.send_header("Content-type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        "response": response,
                        "thread_id": thread_id
                    }).encode())

                except Exception as e:
                    self.send_response(500)
                    self.send_header("Content-type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": str(e)}).encode())
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format, *args):
            logging.info("%s - %s", self.address_string(), format % args)

    console.print(f"[bold green]Starting agent server on {host}:{port}[/bold green]")
    console.print("POST /chat with {\"message\": \"your question\"}")
    console.print("GET /health for health check")

    server = HTTPServer((host, port), AgentHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        console.print("\n[yellow]Shutting down...[/yellow]")
        server.shutdown()


if __name__ == "__main__":
    app()
