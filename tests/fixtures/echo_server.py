from mcp.server.mcpserver import MCPServer

server = MCPServer("echo")


@server.tool()
def shout(text: str) -> str:
    """Return the text in capitals."""
    return text.upper()


@server.tool()
def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b


if __name__ == "__main__":
    server.run("stdio")
