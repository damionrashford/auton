# MCP (Model Context Protocol)

Zero-dependency Model Context Protocol client with multiple transport options. Enables LLM applications to call tools, read resources, and use prompts from MCP servers.

## Transports

| Transport | Use Case |
|-----------|----------|
| **Streamable HTTP** | Standard HTTP with Streamable HTTP protocol |
| **stdio** | Local subprocess (e.g., `npx mcp-server`) |
| **SSE** | Legacy HTTP + Server-Sent Events |

## Usage

```typescript
import {
  MCPClient,
  connectWithAutoDetect,
  MCPStreamableHTTPTransport,
  MCPStdioTransport,
  MCPSSETransport,
} from "auton";

// Auto-detect from URL
const client = await connectWithAutoDetect({
  url: "http://localhost:3000/mcp",
  // or stdio: { command: "npx", args: ["-y", "my-mcp-server"] }
});

// Or explicit transport
const transport = new MCPStreamableHTTPTransport({
  url: "http://localhost:3000/mcp",
});
const client = new MCPClient({ transport });

await client.connect();

// List tools
const tools = await client.listTools();

// Call tool
const result = await client.callTool("search", { query: "delegation" });

// List resources
const resources = await client.listResources();

// Read resource
const content = await client.readResource("file:///path/to/file");

// Get prompt
const prompt = await client.getPrompt("summary", { context: "..." });

await client.close();
```

## Streamable HTTP

```typescript
const transport = new MCPStreamableHTTPTransport({
  url: "https://api.example.com/mcp",
  headers: { Authorization: "Bearer ..." },
});
```

## stdio (Node.js)

```typescript
const transport = new MCPStdioTransport({
  command: "npx",
  args: ["-y", "@modelcontextprotocol/server-filesystem", "/path"],
});
```

## SSE (Legacy)

```typescript
const transport = new MCPSSETransport({
  url: "http://localhost:3000/sse",
  headers: {},
});
```

## MCPClientConfig

```typescript
interface MCPClientConfig {
  transport: MCPTransport;
}
```

## connectWithAutoDetect

Infers transport from config:

- `url` (http/https) → Streamable HTTP
- `url` (sse path) → SSE
- `stdio` → stdio

## See Also

- [Model Context Protocol](https://modelcontextprotocol.io/) — Official spec
- [MCP Type Definitions](../api-reference.md#mcp-types) — MCPTool, MCPResource, etc.
