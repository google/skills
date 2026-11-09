# Genkit MCP (`genkit_mcp`)

MCP (Model Context Protocol) integration for Genkit Dart, built on `mcp_dart`.
It prefers the stateless MCP 2026-07-28 protocol and falls back to
initialization-based peers automatically.

> **Namespaced tool names are shortened on the wire.** A tool like
> `my-server/weatherTool` is presented to the model as `weatherTool`; the full
> name is preserved in `metadata.originalName` and tool requests still resolve
> correctly.

- [MCP Host (Recommended)](#mcp-host-recommended): Lines 18-74
- [MCP Client (Advanced or Single Server)](#mcp-client-advanced-or-single-server): Lines 76-110
- [MCP Server](#mcp-server): Lines 112-165

---

## MCP Host (Recommended)
Connect to one or more MCP servers and aggregate their capabilities into the
Genkit registry automatically.

```dart
import 'package:genkit/genkit.dart';
import 'package:genkit_mcp/genkit_mcp.dart';

void main() async {
  final ai = Genkit();

  final host = defineMcpHost(
    ai,
    McpHostOptionsWithCache(
      name: 'my-host',
      mcpServers: {
        'fs': McpServerConfig(
          command: 'npx',
          args: ['-y', '@modelcontextprotocol/server-filesystem', '.'],
        ),
      },
    ),
  );

  // Tools can be discovered and executed dynamically using a wildcard...
  final response = await ai.generate(
    model: googleAI.gemini('gemini-flash-latest'),
    prompt: 'Summarize the contents of README.md',
    toolNames: ['my-host:tool/fs/*'],
  );
  
  // ...or by specifying the exact tool name
  final exactResponse = await ai.generate(
    model: googleAI.gemini('gemini-flash-latest'),
    prompt: 'Read README.md',
    toolNames: ['my-host:tool/fs/read_file'],
  );
}
```

### Connect over Streamable HTTP

Point `McpServerConfig` at a URL instead of a command to connect over Streamable
HTTP. (There is no public `StreamableHttpClientTransport` to construct directly;
custom client transports implement the `McpClientTransport` interface.)

```dart
final host = defineMcpHost(
  ai,
  McpHostOptionsWithCache(
    name: 'my-host',
    mcpServers: {
      'remote': McpServerConfig(url: Uri.parse('https://mcp.example.com/mcp')),
    },
  ),
);
```

## MCP Client (Advanced or Single Server)
Connecting to a single MCP server with a client object is an advanced usecase
for when you need manual control over the client lifecycle. Standalone clients
do not automatically register tools into the registry, so they must be passed
into `generate` or `defineDynamicActionProvider` manually.

```dart
import 'package:genkit/genkit.dart';
import 'package:genkit_mcp/genkit_mcp.dart';

void main() async {
  final ai = Genkit();

  final client = createMcpClient(
    McpClientOptions(
      name: 'my-client',
      mcpServer: McpServerConfig(
        command: 'npx',
        args: ['-y', '@modelcontextprotocol/server-filesystem', '.'],
      ),
    ),
  );
  
  await client.ready();

  // Retrieve the tools from the connected client
  final tools = await client.getActiveTools(ai);
  
  final response = await ai.generate(
    model: googleAI.gemini('gemini-flash-latest'),
    prompt: 'Read the contents of README.md',
    tools: tools,
  );
}
```

## MCP Server
Expose Genkit actions (tools, prompts, resources) over MCP.

```dart
import 'package:genkit/genkit.dart';
import 'package:genkit_mcp/genkit_mcp.dart';

void main() async {
  final ai = Genkit();

  ai.defineTool(
    name: 'add',
    description: 'Add two numbers together',
    inputSchema: .map(.string(), .dynamicSchema()),
    fn: (input, _) async => .response((input['a'] + input['b']).toString()),
  );

  ai.defineResource(
    name: 'my-resource',
    uri: 'my://resource',
    fn: (_, _) async => ResourceOutput(content: [TextPart(text: 'my resource')]),
  );

  // Stdio transport by default
  final server = createMcpServer(ai, McpServerOptions(name: 'my-server'));
  await server.start();
}
```

### Streamable HTTP Transport
```dart
import 'dart:io';

final transport = await StreamableHttpServerTransport.bind(
  address: InternetAddress.loopbackIPv4,
  port: 3000,
);
await server.start(transport);
```

> **DNS-rebinding protection and batch rejection are on by default.** Loopback
> hosts work unconfigured, but a non-loopback deployment must set `allowedHosts`
> (and should set `allowedOrigins`) or requests are rejected. Legacy clients
> that
> send JSON-RPC batches can opt out with `rejectBatchJsonRpcPayloads: false`.
>
> ```dart
> final transport = await StreamableHttpServerTransport.bind(
>   address: InternetAddress.anyIPv4,
>   port: 3000,
>   allowedHosts: ['mcp.example.com'],
>   allowedOrigins: ['https://app.example.com'],
> );
> ```
