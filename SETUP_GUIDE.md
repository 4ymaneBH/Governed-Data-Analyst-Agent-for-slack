# Setup & Deployment Guide

## 1. Slack App Configuration (Required)

To use the governed analyst agent, you need to create a Slack app and get three credentials.

### Step 1: Create the App
1. Go to [api.slack.com/apps](https://api.slack.com/apps?new_app=1)
2. Click **Create New App**
3. Select **From Scratch**
4. Name: `Data Analyst Agent`
5. Workspace: Select your development workspace

### Step 2: Enable Socket Mode
1. In the left sidebar, click **Socket Mode**
2. Toggle **Enable Socket Mode** to ON
3. Name the token: `socket-token`
4. Click **Generate**
5. Copy the token that starts with `xapp-...`
6. Save this as `SLACK_APP_TOKEN` in your `.env` file

### Step 3: Configure Permissions
1. In the left sidebar, click **OAuth & Permissions**
2. Scroll down to **Scopes** > **Bot Token Scopes**
3. Add the following scopes:
   - `app_mentions:read` (To hear "@Agent")
   - `chat:write` (To reply to messages)
   - `commands` (To use /slash commands)
   - `im:history` (Optional, for DM support)
   - `files:write` (To upload charts)

### Step 4: Install to Workspace
1. Scroll up to the top of **OAuth & Permissions**
2. Click **Install to Workspace**
3. Click **Allow**
4. Copy the **Bot User OAuth Token** (starts with `xoxb-...`)
5. Save this as `SLACK_BOT_TOKEN` in your `.env` file

### Step 5: Get Signing Secret
1. In the left sidebar, click **Basic Information**
2. Scroll down to **App Credentials**
3. Click **Show** next to **Signing Secret**
4. Copy the 32-character string
5. Save this as `SLACK_SIGNING_SECRET` in your `.env` file

### Step 6: Create Slash Command
1. In the left sidebar, click **Slash Commands**
2. Click **Create New Command**
3. Command: `/askdata`
4. Request URL: `http://localhost:3000/slack/events` (This is ignored in Socket Mode, but required field. Use any dummy URL)
5. Short Description: `Ask a data question`
6. Usage Hint: `[your question]`
7. Click **Save**

---

## 2. Environment Configuration

Create a `.env` file in the root directory:

```bash
# Slack Credentials (from above)
SLACK_BOT_TOKEN=xoxb-your-token
SLACK_SIGNING_SECRET=your-secret
SLACK_APP_TOKEN=xapp-your-token

# Database Config (Default for Docker)
POSTGRES_USER=analyst
POSTGRES_PASSWORD=analyst_secret
POSTGRES_DB=analyst_db
POSTGRES_HOST=postgres

# LLM Config (Ollama)
OLLAMA_BASE_URL=http://host.docker.internal:11434
OLLAMA_MODEL=llama3.2
```

## 3. Running the Stack

```bash
# Start all services
cd infra
docker compose up -d

# Initialize LLM (Run once)
docker exec -it analyst-ollama ollama pull llama3.2

# Check logs
docker compose logs -f
```

## 4. Verification

1. Go to your Slack workspace
2. Invite the bot to a channel: `/invite @Data Analyst Agent`
3. Type: `/askdata Show me the top 5 customers by revenue`
4. Check the **Admin UI** at [http://localhost:8080](http://localhost:8080) to see the audit log.
