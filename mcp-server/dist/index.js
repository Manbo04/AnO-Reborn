#!/usr/bin/env node
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { CallToolRequestSchema, ListToolsRequestSchema, ListResourcesRequestSchema, ReadResourceRequestSchema, } from "@modelcontextprotocol/sdk/types.js";
import pg from "pg";
const { Pool } = pg;
// Database connection (uses environment variable)
const pool = new Pool({
    connectionString: process.env.DATABASE_PUBLIC_URL || process.env.DATABASE_URL,
});
// Create the MCP server
const server = new Server({
    name: "ano-mcp-server",
    version: "1.0.0",
}, {
    capabilities: {
        tools: {},
        resources: {},
    },
});
// Define available tools
server.setRequestHandler(ListToolsRequestSchema, async () => {
    return {
        tools: [
            {
                name: "get_nation_info",
                description: "Get information about a nation/country by name or ID",
                inputSchema: {
                    type: "object",
                    properties: {
                        identifier: {
                            type: "string",
                            description: "Nation name or ID",
                        },
                    },
                    required: ["identifier"],
                },
            },
            {
                name: "get_nation_resources",
                description: "Get resources for a specific nation",
                inputSchema: {
                    type: "object",
                    properties: {
                        nation_id: {
                            type: "number",
                            description: "Nation ID",
                        },
                    },
                    required: ["nation_id"],
                },
            },
            {
                name: "query_database",
                description: "Run a read-only SQL query against the game database (SELECT only)",
                inputSchema: {
                    type: "object",
                    properties: {
                        query: {
                            type: "string",
                            description: "SQL SELECT query to execute",
                        },
                    },
                    required: ["query"],
                },
            },
            {
                name: "get_table_schema",
                description: "Get the schema of a database table",
                inputSchema: {
                    type: "object",
                    properties: {
                        table_name: {
                            type: "string",
                            description: "Name of the table",
                        },
                    },
                    required: ["table_name"],
                },
            },
            {
                name: "list_tables",
                description: "List all tables in the database",
                inputSchema: {
                    type: "object",
                    properties: {},
                    required: [],
                },
            },
            {
                name: "get_market_prices",
                description: "Get current market prices for resources",
                inputSchema: {
                    type: "object",
                    properties: {
                        resource: {
                            type: "string",
                            description: "Optional: specific resource name (e.g., 'oil', 'iron', 'food')",
                        },
                    },
                },
            },
            {
                name: "get_war_status",
                description: "Get active wars for a nation",
                inputSchema: {
                    type: "object",
                    properties: {
                        nation_id: {
                            type: "number",
                            description: "Nation ID to check wars for",
                        },
                    },
                    required: ["nation_id"],
                },
            },
            {
                name: "get_coalition_info",
                description: "Get information about a coalition",
                inputSchema: {
                    type: "object",
                    properties: {
                        coalition_name: {
                            type: "string",
                            description: "Name of the coalition",
                        },
                    },
                    required: ["coalition_name"],
                },
            },
        ],
    };
});
// Handle tool calls
server.setRequestHandler(CallToolRequestSchema, async (request) => {
    const { name, arguments: args } = request.params;
    try {
        switch (name) {
            case "get_nation_info": {
                const identifier = args?.identifier;
                const query = isNaN(Number(identifier))
                    ? `SELECT * FROM countries WHERE LOWER(name) = LOWER($1) LIMIT 1`
                    : `SELECT * FROM countries WHERE id = $1 LIMIT 1`;
                const result = await pool.query(query, [identifier]);
                return {
                    content: [
                        {
                            type: "text",
                            text: result.rows.length > 0
                                ? JSON.stringify(result.rows[0], null, 2)
                                : "Nation not found",
                        },
                    ],
                };
            }
            case "get_nation_resources": {
                const nationId = args?.nation_id;
                const result = await pool.query(`SELECT * FROM resources WHERE country_id = $1`, [nationId]);
                return {
                    content: [
                        {
                            type: "text",
                            text: result.rows.length > 0
                                ? JSON.stringify(result.rows[0], null, 2)
                                : "No resources found for this nation",
                        },
                    ],
                };
            }
            case "query_database": {
                const query = (args?.query).trim();
                // Security: Only allow SELECT queries
                if (!query.toLowerCase().startsWith("select")) {
                    return {
                        content: [
                            {
                                type: "text",
                                text: "Error: Only SELECT queries are allowed for safety",
                            },
                        ],
                        isError: true,
                    };
                }
                const result = await pool.query(query);
                return {
                    content: [
                        {
                            type: "text",
                            text: JSON.stringify(result.rows, null, 2),
                        },
                    ],
                };
            }
            case "get_table_schema": {
                const tableName = args?.table_name;
                const result = await pool.query(`SELECT column_name, data_type, is_nullable, column_default
           FROM information_schema.columns
           WHERE table_name = $1
           ORDER BY ordinal_position`, [tableName]);
                return {
                    content: [
                        {
                            type: "text",
                            text: result.rows.length > 0
                                ? JSON.stringify(result.rows, null, 2)
                                : `Table '${tableName}' not found`,
                        },
                    ],
                };
            }
            case "list_tables": {
                const result = await pool.query(`SELECT table_name
           FROM information_schema.tables
           WHERE table_schema = 'public'
           ORDER BY table_name`);
                return {
                    content: [
                        {
                            type: "text",
                            text: JSON.stringify(result.rows.map((r) => r.table_name), null, 2),
                        },
                    ],
                };
            }
            case "get_market_prices": {
                const resource = args?.resource;
                let query = `SELECT * FROM market_listings ORDER BY created_at DESC LIMIT 50`;
                let params = [];
                if (resource) {
                    query = `SELECT * FROM market_listings WHERE LOWER(resource_type) = LOWER($1) ORDER BY created_at DESC LIMIT 20`;
                    params = [resource];
                }
                const result = await pool.query(query, params);
                return {
                    content: [
                        {
                            type: "text",
                            text: JSON.stringify(result.rows, null, 2),
                        },
                    ],
                };
            }
            case "get_war_status": {
                const nationId = args?.nation_id;
                const result = await pool.query(`SELECT * FROM wars
           WHERE (attacker_id = $1 OR defender_id = $1)
           AND status = 'active'`, [nationId]);
                return {
                    content: [
                        {
                            type: "text",
                            text: result.rows.length > 0
                                ? JSON.stringify(result.rows, null, 2)
                                : "No active wars found",
                        },
                    ],
                };
            }
            case "get_coalition_info": {
                const coalitionName = args?.coalition_name;
                const result = await pool.query(`SELECT * FROM coalitions WHERE LOWER(name) = LOWER($1) LIMIT 1`, [coalitionName]);
                if (result.rows.length === 0) {
                    return {
                        content: [
                            {
                                type: "text",
                                text: "Coalition not found",
                            },
                        ],
                    };
                }
                // Also get members
                const members = await pool.query(`SELECT c.id, c.name FROM countries c
           JOIN coalition_members cm ON c.id = cm.country_id
           WHERE cm.coalition_id = $1`, [result.rows[0].id]);
                return {
                    content: [
                        {
                            type: "text",
                            text: JSON.stringify({
                                ...result.rows[0],
                                members: members.rows,
                            }, null, 2),
                        },
                    ],
                };
            }
            default:
                return {
                    content: [
                        {
                            type: "text",
                            text: `Unknown tool: ${name}`,
                        },
                    ],
                    isError: true,
                };
        }
    }
    catch (error) {
        const errorMessage = error instanceof Error ? error.message : "Unknown error";
        return {
            content: [
                {
                    type: "text",
                    text: `Error: ${errorMessage}`,
                },
            ],
            isError: true,
        };
    }
});
// Define available resources
server.setRequestHandler(ListResourcesRequestSchema, async () => {
    return {
        resources: [
            {
                uri: "ano://game/overview",
                name: "Game Overview",
                description: "Overview of the AnO nation game",
                mimeType: "text/plain",
            },
            {
                uri: "ano://database/schema",
                name: "Database Schema",
                description: "Full database schema overview",
                mimeType: "application/json",
            },
        ],
    };
});
// Handle resource reads
server.setRequestHandler(ReadResourceRequestSchema, async (request) => {
    const { uri } = request.params;
    if (uri === "ano://game/overview") {
        return {
            contents: [
                {
                    uri,
                    mimeType: "text/plain",
                    text: `AnO Nation Game Overview
=========================

AnO is a browser-based nation simulation game where players:
- Build and manage their own nation
- Trade resources on the market
- Form coalitions with other players
- Engage in military conflicts
- Manage economy and policies

Key Features:
- Province management with resource production
- Military units and combat system
- Coalition diplomacy
- Real-time market trading
- Policy system affecting nation development

Database Tables:
- countries: Player nations
- resources: Nation resources
- provinces: Nation provinces
- wars: Active and historical conflicts
- coalitions: Player alliances
- market_listings: Trade offers
- units: Military forces
`,
                },
            ],
        };
    }
    if (uri === "ano://database/schema") {
        try {
            const result = await pool.query(`
        SELECT
          t.table_name,
          array_agg(c.column_name || ' (' || c.data_type || ')' ORDER BY c.ordinal_position) as columns
        FROM information_schema.tables t
        JOIN information_schema.columns c ON t.table_name = c.table_name
        WHERE t.table_schema = 'public'
        GROUP BY t.table_name
        ORDER BY t.table_name
      `);
            return {
                contents: [
                    {
                        uri,
                        mimeType: "application/json",
                        text: JSON.stringify(result.rows, null, 2),
                    },
                ],
            };
        }
        catch (error) {
            return {
                contents: [
                    {
                        uri,
                        mimeType: "text/plain",
                        text: "Error fetching database schema",
                    },
                ],
            };
        }
    }
    throw new Error(`Unknown resource: ${uri}`);
});
// Start the server
async function main() {
    const transport = new StdioServerTransport();
    await server.connect(transport);
    console.error("AnO MCP Server running on stdio");
}
main().catch(console.error);
//# sourceMappingURL=index.js.map
