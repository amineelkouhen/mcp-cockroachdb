import asyncio
from agents import Agent, Runner
from agents.mcp import MCPServerStdio
from agents import Agent, Runner, trace


# Set up and create the agent
async def main():
    # Instanciate the CockroachDB MCP Server.
    async with MCPServerStdio(
        name="CockroachDB MCP Server",
        params={
            "command": "uv",
            "args": [
                "run", "src/main.py"
            ],
        "env": {
            "CRDB_HOST": "127.0.0.1",
            "CRDB_PORT": "26257",
            "CRDV_USERNAME": "root",
            "CRDB_PWD": "",
            "CRDB_DATABASE": "defaultdb",
            "CRDB_SSL_MODE": "disable"
        },
        }
    )as server:
        agent = Agent(
            name="CockroachDB Assistant",
            instructions="Use the tools to answer the user's questions",
            mcp_servers=[server],
        )
        with trace(workflow_name="Conversation"):
            conversation = []
            result = None
            while True:
                if result:
                    conversation = result.to_input_list()
                conversation.append({"role": "user", "content": input("User > ")})
                result = await Runner.run(agent, conversation)
                print(result.final_output)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExiting.")