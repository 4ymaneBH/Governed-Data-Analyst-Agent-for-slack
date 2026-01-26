"""
Slack App Service - Governed Data Analyst Agent
Slack Bolt application for handling /askdata command and interactive components.
"""

import asyncio
import logging
import os
from typing import Optional

import httpx
import structlog
from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

# Environment configuration
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET")
SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN")
AGENT_URL = os.getenv("AGENT_URL", "http://localhost:8002")
ADMIN_CHANNEL = os.getenv("ADMIN_CHANNEL", "#data-approvals")

# User role mapping (in production, this would be from database)
USER_ROLES = {
    "U001INTERN": {"role": "intern", "region": None},
    "U002MARKETING": {"role": "marketing", "region": None},
    "U003SALES_NA": {"role": "sales", "region": "NA"},
    "U004SALES_EMEA": {"role": "sales", "region": "EMEA"},
    "U005SALES_APAC": {"role": "sales", "region": "APAC"},
    "U006ANALYST": {"role": "data_analyst", "region": None},
    "U007ADMIN": {"role": "admin", "region": None},
}

# Initialize Slack app
app = AsyncApp(
    token=SLACK_BOT_TOKEN,
    signing_secret=SLACK_SIGNING_SECRET
)

# HTTP client for agent service
http_client = httpx.AsyncClient(timeout=120.0)


# =============================================================================
# Chart Upload Helper
# =============================================================================

async def upload_chart_to_slack(
    client, 
    channel_id: str, 
    file_path: str, 
    title: str,
    thread_ts: str = None
) -> Optional[str]:
    """Upload chart image to Slack and return the file permalink."""
    try:
        if not file_path or not os.path.exists(file_path):
            logger.warning("Chart file not found", path=file_path)
            return None
        
        result = await client.files_upload_v2(
            channel=channel_id,
            file=file_path,
            title=title,
            initial_comment="📊 Here's your chart!",
            thread_ts=thread_ts
        )
        
        if result.get("ok"):
            permalink = result.get("file", {}).get("permalink", "")
            logger.info("Chart uploaded to Slack", permalink=permalink)
            return permalink
        else:
            logger.error("Slack file upload failed", error=result.get("error"))
            return None
            
    except Exception as e:
        logger.error("Chart upload failed", error=str(e))
        return None


# =============================================================================
# Block Kit Templates
# =============================================================================

def build_response_blocks(
    answer_text: str,
    question: str,
    request_id: str,
    evidence: list = None,
    tool_calls: list = None,
    confidence: float = 0.0,
    requires_approval: bool = False,
    approval_reason: str = None
) -> list:
    """Build Block Kit blocks for the response message."""
    
    blocks = []
    
    # Header
    blocks.append({
        "type": "header",
        "text": {
            "type": "plain_text",
            "text": "📊 Data Analyst Response",
            "emoji": True
        }
    })
    
    # Original question
    blocks.append({
        "type": "context",
        "elements": [
            {
                "type": "mrkdwn",
                "text": f"*Question:* {question[:200]}"
            }
        ]
    })
    
    blocks.append({"type": "divider"})
    
    # Handle approval required
    if requires_approval:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"⚠️ *Approval Required*\n\n{approval_reason}\n\nYour request has been sent to an admin for approval."
            }
        })
        return blocks
    
    # Main answer
    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": answer_text[:3000]  # Slack limit
        }
    })
    
    # Confidence indicator
    confidence_emoji = "🟢" if confidence >= 0.8 else "🟡" if confidence >= 0.5 else "🔴"
    blocks.append({
        "type": "context",
        "elements": [
            {
                "type": "mrkdwn",
                "text": f"{confidence_emoji} Confidence: {confidence:.0%}"
            }
        ]
    })
    
    # Sources section
    if evidence and len(evidence) > 0:
        blocks.append({"type": "divider"})
        
        source_text = "*Sources:*\n"
        for i, e in enumerate(evidence[:5], 1):
            source_text += f"• [{e.get('type', 'unknown')}] {e.get('source', 'Unknown')}\n"
        
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": source_text
            }
        })
    
    blocks.append({"type": "divider"})
    
    # Action buttons
    blocks.append({
        "type": "actions",
        "elements": [
            {
                "type": "button",
                "text": {
                    "type": "plain_text",
                    "text": "📋 Show SQL",
                    "emoji": True
                },
                "action_id": "show_sql",
                "value": request_id
            },
            {
                "type": "button",
                "text": {
                    "type": "plain_text",
                    "text": "📚 Show Sources",
                    "emoji": True
                },
                "action_id": "show_sources",
                "value": request_id
            },
            {
                "type": "button",
                "text": {
                    "type": "plain_text",
                    "text": "🔄 Replay",
                    "emoji": True
                },
                "action_id": "show_replay",
                "value": request_id
            }
        ]
    })
    
    # Footer with request ID
    blocks.append({
        "type": "context",
        "elements": [
            {
                "type": "mrkdwn",
                "text": f"Request ID: `{request_id[:8]}...`"
            }
        ]
    })
    
    return blocks


def build_approval_request_blocks(
    request_id: str,
    user_id: str,
    user_name: str,
    question: str,
    reason: str
) -> list:
    """Build Block Kit blocks for approval request."""
    
    return [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "🔐 Approval Request",
                "emoji": True
            }
        },
        {
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": f"*Requester:*\n<@{user_id}>"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Request ID:*\n`{request_id[:8]}...`"
                }
            ]
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Question:*\n{question[:500]}"
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Reason for Approval:*\n{reason}"
            }
        },
        {"type": "divider"},
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "✅ Approve",
                        "emoji": True
                    },
                    "style": "primary",
                    "action_id": "approve_request",
                    "value": json.dumps({"request_id": request_id, "user_id": user_id})
                },
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "❌ Deny",
                        "emoji": True
                    },
                    "style": "danger",
                    "action_id": "deny_request",
                    "value": json.dumps({"request_id": request_id, "user_id": user_id})
                }
            ]
        }
    ]


def build_replay_blocks(replay_data: dict) -> list:
    """Build Block Kit blocks for replay timeline."""
    
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "🔄 Request Replay",
                "emoji": True
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Question:* {replay_data.get('question', 'N/A')[:200]}"
            }
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*Timeline:*"
            }
        }
    ]
    
    for i, step in enumerate(replay_data.get("steps", []), 1):
        decision_emoji = "✅" if step.get("decision") == "ALLOW" else "❌" if step.get("decision") == "DENY" else "⏳"
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"{i}. {decision_emoji} *{step.get('tool', 'unknown')}* - {step.get('decision', 'N/A')} ({step.get('latency_ms', 0)}ms)"
                }
            ]
        })
    
    blocks.append({"type": "divider"})
    blocks.append({
        "type": "context",
        "elements": [
            {
                "type": "mrkdwn",
                "text": f"Total latency: {replay_data.get('total_latency_ms', 0)}ms"
            }
        ]
    })
    
    return blocks


def build_error_blocks(error_message: str, request_id: str = None) -> list:
    """Build Block Kit blocks for error messages."""
    
    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"❌ *Error*\n\n{error_message}"
            }
        }
    ]
    
    if request_id:
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"Request ID: `{request_id[:8]}...`"
                }
            ]
        })
    
    return blocks


# =============================================================================
# Helper Functions
# =============================================================================

def get_user_context(user_id: str) -> dict:
    """Get user context including role and region."""
    user_info = USER_ROLES.get(user_id, {"role": "intern", "region": None})
    return {
        "user_id": user_id,
        "slack_user_id": user_id,
        "role": user_info["role"],
        "region": user_info.get("region")
    }


async def call_agent(question: str, context: dict, request_id: str) -> dict:
    """Call the agent service."""
    try:
        response = await http_client.post(
            f"{AGENT_URL}/ask",
            json={
                "text": question,
                "context": context,
                "request_id": request_id
            }
        )
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as e:
        logger.error("Agent call failed", error=str(e))
        return {"error": str(e)}


async def get_replay(request_id: str) -> dict:
    """Get replay data from agent service."""
    try:
        response = await http_client.get(f"{AGENT_URL}/replay/{request_id}")
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as e:
        logger.error("Replay fetch failed", error=str(e))
        return {"error": str(e)}


async def send_approval_callback(request_id: str, approved: bool, approver_id: str, reason: str = None):
    """Send approval decision to agent service."""
    try:
        response = await http_client.post(
            f"{AGENT_URL}/approval/callback",
            params={
                "request_id": request_id,
                "approved": approved,
                "approver_id": approver_id,
                "reason": reason
            }
        )
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as e:
        logger.error("Approval callback failed", error=str(e))
        return {"error": str(e)}


# =============================================================================
# Slack Event Handlers
# =============================================================================

@app.command("/askdata")
async def handle_askdata_command(ack, command, client, respond):
    """Handle the /askdata slash command."""
    await ack()
    
    user_id = command["user_id"]
    question = command["text"]
    channel_id = command["channel_id"]
    
    if not question.strip():
        await respond("Please provide a question. Usage: `/askdata What was our CAC last month?`")
        return
    
    logger.info("Received askdata command", user_id=user_id, question=question[:50])
    
    # Get user context
    context = get_user_context(user_id)
    
    # Generate request ID
    import uuid
    request_id = str(uuid.uuid4())
    
    # Send initial response
    await respond({
        "text": "🔄 Processing your question...",
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"🔄 Processing: _{question[:100]}_..."
                }
            }
        ]
    })
    
    # Call agent
    result = await call_agent(question, context, request_id)
    
    if "error" in result and not result.get("answer_text"):
        blocks = build_error_blocks(result["error"], request_id)
        await client.chat_postMessage(
            channel=channel_id,
            blocks=blocks,
            text=f"Error: {result['error']}"
        )
        return
    
    # Check if approval is required
    if result.get("requires_approval"):
        # Send response to user
        blocks = build_response_blocks(
            answer_text="",
            question=question,
            request_id=request_id,
            requires_approval=True,
            approval_reason=result.get("approval_reason", "This request requires admin approval")
        )
        await client.chat_postMessage(
            channel=channel_id,
            blocks=blocks,
            text="Your request requires approval"
        )
        
        # Send approval request to admin channel
        try:
            user_info = await client.users_info(user=user_id)
            user_name = user_info["user"]["real_name"]
        except:
            user_name = user_id
        
        approval_blocks = build_approval_request_blocks(
            request_id=request_id,
            user_id=user_id,
            user_name=user_name,
            question=question,
            reason=result.get("approval_reason", "Sensitive data access")
        )
        
        # Post to admin channel (you'd configure this channel)
        # await client.chat_postMessage(
        #     channel=ADMIN_CHANNEL,
        #     blocks=approval_blocks,
        #     text=f"Approval request from {user_name}"
        # )
        
        return
    
    # Build and send response
    blocks = build_response_blocks(
        answer_text=result.get("answer_text", "No answer generated"),
        question=question,
        request_id=request_id,
        evidence=result.get("evidence", []),
        tool_calls=result.get("tool_calls", []),
        confidence=result.get("confidence", 0.0)
    )
    
    # Send main response
    response_msg = await client.chat_postMessage(
        channel=channel_id,
        blocks=blocks,
        text=result.get("answer_text", "Data analysis complete")[:200]
    )
    
    # Upload chart if available
    chart_path = result.get("chart_url")
    if chart_path:
        await upload_chart_to_slack(
            client=client,
            channel_id=channel_id,
            file_path=chart_path,
            title=question[:50] + ("..." if len(question) > 50 else ""),
            thread_ts=response_msg.get("ts")  # Reply in thread
        )


@app.action("show_sql")
async def handle_show_sql(ack, body, client):
    """Handle Show SQL button click."""
    await ack()
    
    request_id = body["actions"][0]["value"]
    channel_id = body["channel"]["id"]
    
    # Get replay data to find SQL
    replay = await get_replay(request_id)
    
    if "error" in replay:
        await client.chat_postEphemeral(
            channel=channel_id,
            user=body["user"]["id"],
            text=f"Could not retrieve SQL: {replay['error']}"
        )
        return
    
    # Find SQL from steps
    sql_found = False
    for step in replay.get("steps", []):
        if step.get("tool") == "run_sql":
            sql_found = True
            await client.chat_postEphemeral(
                channel=channel_id,
                user=body["user"]["id"],
                blocks=[
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*SQL Query:*\n```sql\n{step.get('inputs', {}).get('query', 'N/A')}\n```"
                        }
                    }
                ],
                text="SQL Query"
            )
            break
    
    if not sql_found:
        await client.chat_postEphemeral(
            channel=channel_id,
            user=body["user"]["id"],
            text="No SQL query was executed for this request."
        )


@app.action("show_sources")
async def handle_show_sources(ack, body, client):
    """Handle Show Sources button click."""
    await ack()
    
    request_id = body["actions"][0]["value"]
    channel_id = body["channel"]["id"]
    
    replay = await get_replay(request_id)
    
    if "error" in replay:
        await client.chat_postEphemeral(
            channel=channel_id,
            user=body["user"]["id"],
            text=f"Could not retrieve sources: {replay['error']}"
        )
        return
    
    # Build sources text
    sources_text = "*Sources Used:*\n\n"
    for step in replay.get("steps", []):
        tool = step.get("tool", "")
        if tool == "search_docs":
            sources_text += "📚 *Documents searched*\n"
        elif tool == "explain_metric":
            sources_text += "📊 *Metric definitions retrieved*\n"
        elif tool == "run_sql":
            sources_text += "🗄️ *Database queried*\n"
    
    await client.chat_postEphemeral(
        channel=channel_id,
        user=body["user"]["id"],
        text=sources_text
    )


@app.action("show_replay")
async def handle_show_replay(ack, body, client):
    """Handle Replay button click."""
    await ack()
    
    request_id = body["actions"][0]["value"]
    channel_id = body["channel"]["id"]
    
    replay = await get_replay(request_id)
    
    if "error" in replay:
        await client.chat_postEphemeral(
            channel=channel_id,
            user=body["user"]["id"],
            text=f"Could not retrieve replay: {replay['error']}"
        )
        return
    
    blocks = build_replay_blocks(replay)
    
    await client.chat_postEphemeral(
        channel=channel_id,
        user=body["user"]["id"],
        blocks=blocks,
        text="Request Replay"
    )


@app.action("approve_request")
async def handle_approve_request(ack, body, client):
    """Handle Approve button click."""
    await ack()
    
    action_data = json.loads(body["actions"][0]["value"])
    request_id = action_data["request_id"]
    original_user_id = action_data["user_id"]
    approver_id = body["user"]["id"]
    channel_id = body["channel"]["id"]
    
    # Send approval to agent
    result = await send_approval_callback(request_id, True, approver_id)
    
    if "error" in result:
        await client.chat_postMessage(
            channel=channel_id,
            text=f"Failed to process approval: {result['error']}"
        )
        return
    
    # Update the original message
    await client.chat_update(
        channel=channel_id,
        ts=body["message"]["ts"],
        blocks=[
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"✅ *Approved* by <@{approver_id}>"
                }
            }
        ],
        text="Request approved"
    )
    
    # Notify the original user
    await client.chat_postMessage(
        channel=original_user_id,
        text=f"Your data request has been approved by <@{approver_id}>. Processing now..."
    )


@app.action("deny_request")
async def handle_deny_request(ack, body, client):
    """Handle Deny button click."""
    await ack()
    
    action_data = json.loads(body["actions"][0]["value"])
    request_id = action_data["request_id"]
    original_user_id = action_data["user_id"]
    approver_id = body["user"]["id"]
    channel_id = body["channel"]["id"]
    
    # Send denial to agent
    result = await send_approval_callback(request_id, False, approver_id, "Request denied by admin")
    
    # Update the original message
    await client.chat_update(
        channel=channel_id,
        ts=body["message"]["ts"],
        blocks=[
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"❌ *Denied* by <@{approver_id}>"
                }
            }
        ],
        text="Request denied"
    )
    
    # Notify the original user
    await client.chat_postMessage(
        channel=original_user_id,
        text=f"Your data request was denied by <@{approver_id}>."
    )


@app.event("app_mention")
async def handle_app_mention(event, say, client):
    """Handle @mentions of the bot."""
    text = event.get("text", "")
    user_id = event.get("user")
    
    # Remove the bot mention from the text
    question = text.split(">", 1)[-1].strip() if ">" in text else text
    
    if not question:
        await say("Hi! You can ask me data questions. Try: `@DataAnalyst What was our revenue last month?`")
        return
    
    # Process like /askdata
    context = get_user_context(user_id)
    import uuid
    request_id = str(uuid.uuid4())
    
    result = await call_agent(question, context, request_id)
    
    if "error" in result and not result.get("answer_text"):
        await say(f"Sorry, I encountered an error: {result['error']}")
        return
    
    blocks = build_response_blocks(
        answer_text=result.get("answer_text", "No answer generated"),
        question=question,
        request_id=request_id,
        evidence=result.get("evidence", []),
        tool_calls=result.get("tool_calls", []),
        confidence=result.get("confidence", 0.0),
        requires_approval=result.get("requires_approval", False),
        approval_reason=result.get("approval_reason")
    )
    
    await say(blocks=blocks, text=result.get("answer_text", "")[:200])


# =============================================================================
# Main Entry Point
# =============================================================================

async def main():
    """Start the Slack app in socket mode."""
    logger.info("Starting Slack App Service")
    
    if not SLACK_APP_TOKEN:
        logger.error("SLACK_APP_TOKEN not set")
        return
    
    handler = AsyncSocketModeHandler(app, SLACK_APP_TOKEN)
    await handler.start_async()


if __name__ == "__main__":
    asyncio.run(main())
