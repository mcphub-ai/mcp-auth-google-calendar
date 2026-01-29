import argparse
import asyncio
import os
import json
import logging
import shutil
from pathlib import Path
from typing import List, Any

from fastmcp import Client
from fastmcp.client.auth.oauth import OAuth, ClientNotFoundError
from key_value.aio.stores.disk import DiskStore
from openai import AsyncOpenAI
from dotenv import load_dotenv

# Load OpenAI Key and Config
load_dotenv()
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL", "http://localhost:8000/sse")

if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY not found in.env")

client_openai = AsyncOpenAI(api_key=OPENAI_API_KEY)

async def convert_mcp_to_openai_tools(mcp_tools: List[Any]) -> List:
    """Adapts MCP Tool schema to OpenAI Tool schema."""
    openai_tools = []
    for tool in mcp_tools:
        openai_tools.append({
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.inputSchema
            }
        })
    return openai_tools

async def run_chat_loop(profile: str = "default"):
    print(f"--- Connecting to MCP Server at {MCP_SERVER_URL} ---")
    print(f"--- Using profile: {profile} ---")

    storage_dir = Path(".client_storage") / profile
    storage_dir.mkdir(parents=True, exist_ok=True)
    
    max_retries = 2
    for attempt in range(max_retries):
        # We use a persistent DiskStore for auth tokens so we don't have to login every time
        disk_store = DiskStore(directory=str(storage_dir))

        try:
            async with disk_store:
                # Create OAuth provider with persistent storage
                auth_provider = OAuth(
                    mcp_url=MCP_SERVER_URL,
                    token_storage=disk_store
                )
                
                async with Client(MCP_SERVER_URL, auth=auth_provider) as mcp_client:
                    print("✓ Connected to Server & Authenticated")
                    
                    mcp_tools = await mcp_client.list_tools()
                    openai_tools = await convert_mcp_to_openai_tools(mcp_tools)
                    print(f"✓ Discovered tools: {[t['function']['name'] for t in openai_tools]}")

                    messages = []
                    print("\n--- GPT-4o Calendar Assistant (Type 'quit' to exit) ---")

                    while True:
                        try:
                            user_input = input("\nUser: ")
                            if user_input.lower() in ['quit', 'exit']:
                                return
                            
                            messages.append({"role": "user", "content": user_input})
                            
                            # 1. Ask OpenAI
                            response = await client_openai.chat.completions.create(
                                model="gpt-4o",
                                messages=messages,
                                tools=openai_tools,
                                tool_choice="auto" 
                            )
                            
                            response_msg = response.choices[0].message
                            
                            # 2. Check for tool calls
                            if response_msg.tool_calls:
                                messages.append(response_msg)
                                
                                for tool_call in response_msg.tool_calls:
                                    name = tool_call.function.name
                                    args = json.loads(tool_call.function.arguments)
                                    
                                    print(f" > Executing tool: {name}...")
                                    
                                    try:
                                        # 3. Execute tool on MCP Server
                                        result = await mcp_client.call_tool(name, args)
                                        output = result.content[0].text if result.content else "Success"
                                    except Exception as e:
                                        output = f"Error: {str(e)}"
                                        
                                    print(f" > Result: {output}")

                                    messages.append({
                                        "tool_call_id": tool_call.id,
                                        "role": "tool",
                                        "name": name,
                                        "content": str(output)
                                    })
                                
                                # 4. Final response after tool execution
                                final = await client_openai.chat.completions.create(
                                    model="gpt-4o", messages=messages
                                )
                                final_text = final.choices[0].message.content
                                print(f"\nAssistant: {final_text}")
                                messages.append({"role": "assistant", "content": final_text})
                                
                            else:
                                print(f"\nAssistant: {response_msg.content}")
                                messages.append(response_msg)
                        except KeyboardInterrupt:
                            return
                        except Exception as e:
                            print(f"Error: {e}")
            # If we exit the context naturally, return
            return
            
        except ClientNotFoundError:
            print("! Client credentials rejected by server (likely server storage reset).")
            print("! Clearing local cache and re-authenticating...")
            
            # Close/Remove local storage to force new registration
            if storage_dir.exists():
                shutil.rmtree(str(storage_dir))
                storage_dir.mkdir(parents=True, exist_ok=True)
            
            if attempt == max_retries - 1:
                print("x Failed to authenticate after cleaning cache.")
                raise

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MCP Client")
    parser.add_argument("--profile", default="default", help="Client profile name for separate auth")
    args = parser.parse_args()

    try:
        asyncio.run(run_chat_loop(profile=args.profile))
    except KeyboardInterrupt:
        print("\nGoodbye!")
    except Exception as e:
        print(f"\nError: {e}")