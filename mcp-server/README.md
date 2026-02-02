# AnO MCP Server

A Model Context Protocol (MCP) server for the AnO Nation Game. This server provides tools and resources for AI assistants to interact with the game database and understand game mechanics.

## Features

### Tools

- **get_nation_info** - Get information about a nation by name or ID
- **get_nation_resources** - Get resources for a specific nation
- **query_database** - Run read-only SQL queries (SELECT only)
- **get_table_schema** - Get the schema of a database table
- **list_tables** - List all database tables
- **get_market_prices** - Get current market prices
- **get_war_status** - Get active wars for a nation
- **get_coalition_info** - Get coalition information and members

### Resources

- **ano://game/overview** - Overview of the game mechanics
- **ano://database/schema** - Full database schema

## Installation

```bash
cd mcp-server
npm install
npm run build
```

## Configuration

Set the database URL environment variable:

```bash
export DATABASE_PUBLIC_URL="postgresql://..."
# or
export DATABASE_URL="postgresql://..."
```

## Usage

### With VS Code / Copilot

Add to your `.vscode/mcp.json`:

```json
{
  "servers": {
    "ano": {
      "command": "node",
      "args": ["/path/to/AnO/mcp-server/dist/index.js"],
      "env": {
        "DATABASE_PUBLIC_URL": "your-database-url"
      }
    }
  }
}
```

### Development

```bash
npm run dev  # Watch mode with tsx
```

### Testing with MCP Inspector

```bash
npm run inspector
```

## Extending the Server

To add new tools:

1. Add the tool definition in `ListToolsRequestSchema` handler
2. Add the tool implementation in `CallToolRequestSchema` handler

Example:

```typescript
// In ListToolsRequestSchema handler
{
  name: "my_new_tool",
  description: "Description of what it does",
  inputSchema: {
    type: "object",
    properties: {
      param1: { type: "string", description: "..." }
    },
    required: ["param1"]
  }
}

// In CallToolRequestSchema handler
case "my_new_tool": {
  const param1 = args?.param1 as string;
  // Implementation
  return { content: [{ type: "text", text: "result" }] };
}
```

## License

MIT
