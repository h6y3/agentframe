# Deploying to GCP Cloud Run

This guide walks through deploying an AgentFrame application to Google Cloud Run, including setting up the Cloud Run MCP server so Claude Code can handle deployments directly.

## Overview

**Goal**: Enable Claude Code to deploy your app to Cloud Run with a single command.

**What you'll set up**:
1. Google Cloud SDK (gcloud CLI)
2. A GCP project with billing
3. Cloud Run MCP server for Claude Code
4. Your app deployed and running

**Time**: ~15-20 minutes (first time), ~2 minutes (subsequent deploys)

---

## Prerequisites

- macOS, Linux, or WSL on Windows
- Node.js 18+ (for MCP server)
- A Google account
- A payment method for GCP billing (free tier covers most small apps)

---

## Step 1: Install Google Cloud SDK

### macOS (Homebrew)
```bash
brew install google-cloud-sdk
```

### Other platforms
See: https://cloud.google.com/sdk/docs/install

### Verify installation
```bash
gcloud --version
```

---

## Step 2: Authenticate with Google Cloud

### 2.1 Login to gcloud CLI
```bash
gcloud auth login
```
This opens a browser. Sign in with your Google account.

### 2.2 Set up Application Default Credentials (ADC)
```bash
gcloud auth application-default login
```
This creates credentials that the MCP server uses.

### 2.3 Set the quota project

**Common Error**: After `application-default login`, you may see:
```
gcloud auth application-default set-quota-project - keeps saying I need a quota project
```

**What is a quota project?** It's the GCP project that gets billed for API calls when using Application Default Credentials.

**Fix**: Set it to your project (we'll create one in the next step if needed):
```bash
gcloud auth application-default set-quota-project YOUR_PROJECT_ID
```

---

## Step 3: Create a GCP Project

### 3.1 Try creating a project
```bash
gcloud projects create my-app-prod --name="My App Production"
```

### Common Error: Organization Permission Issues

If you're in a Google Workspace or Cloud Identity organization, you might see:
```
ERROR: [...] does not have permission to access projects instance [PROJECT_NUMBER:getIamPolicy]
The caller does not have permission.
```

**This can happen even if you're an org admin!** Organization policies can restrict project creation or IAM access.

### Fix: Create a project outside the organization

**Option A**: Via CLI with a unique ID
```bash
# Add timestamp to ensure unique project ID
gcloud projects create my-app-personal-$(date +%s) --name="My App"
```

**Option B**: Via Console (more control)
1. Go to [console.cloud.google.com/projectcreate](https://console.cloud.google.com/projectcreate)
2. Under "Organization" dropdown, select **"No organization"**
3. Create the project

**Why this works**: Personal projects outside an organization don't inherit restrictive org policies.

### 3.2 Set as default project
```bash
gcloud config set project YOUR_PROJECT_ID
```

---

## Step 4: Enable Billing

Cloud Run requires a billing account linked to your project.

### 4.1 List your billing accounts
```bash
gcloud billing accounts list
```

Output looks like:
```
ACCOUNT_ID            NAME                OPEN  MASTER_ACCOUNT_ID
01XXXX-XXXXXX-XXXXXX  My Billing Account  True
```

### 4.2 Link billing to your project
```bash
gcloud billing projects link YOUR_PROJECT_ID --billing-account=YOUR_BILLING_ACCOUNT_ID
```

Example:
```bash
gcloud billing projects link mindshift-personal-1773531818 --billing-account=007623-12198C-A54F12
```

### No billing account?
Create one at: [console.cloud.google.com/billing/create](https://console.cloud.google.com/billing/create)

---

## Step 5: Enable Required APIs

```bash
gcloud services enable run.googleapis.com artifactregistry.googleapis.com
```

### Common Error: Billing not linked
```
ERROR: FAILED_PRECONDITION: Billing account for project 'XXXXX' is not found.
Billing must be enabled for activation of service(s)...
```

**Fix**: Complete Step 4 first, then retry this command.

---

## Step 6: Add Cloud Run MCP to Claude Code

This is the magic step that lets Claude Code deploy directly.

```bash
claude mcp add --transport stdio --scope user cloud-run \
  --env GOOGLE_CLOUD_PROJECT=YOUR_PROJECT_ID \
  --env GOOGLE_CLOUD_REGION=us-central1 \
  -- npx -y @google-cloud/cloud-run-mcp
```

### What this does:
- Adds the official Google Cloud Run MCP server
- Sets your default project and region as environment variables
- Stores config in `~/.claude.json` (user scope = available in all projects)

### Verify installation
```bash
claude mcp list
```

You should see `cloud-run` in the list.

---

## Step 7: Restart Claude Code

Exit your current session:
```bash
exit
# or Ctrl+D
```

Start a new session:
```bash
claude
```

Claude now has access to these Cloud Run tools:
- `deploy_local_folder` — Deploy a directory to Cloud Run
- `deploy_file_contents` — Deploy files by content
- `list_services` — List all Cloud Run services
- `get_service` — Get service details
- `get_service_log` — Get logs for debugging
- `create_project` — Create new GCP projects
- `list_projects` — List available projects

---

## Step 8: Deploy Your App

Once Claude Code has the MCP configured, deployment is simple.

### Ask Claude to deploy:
```
Deploy the app in /path/to/your/project to Cloud Run
```

### Or deploy with specific options:
```
Deploy this folder to Cloud Run as service "my-app" in us-central1
```

### What happens:
1. Claude reads your project files
2. Cloud Run builds a container from your source
3. Container is deployed to Cloud Run
4. You get a public URL like `https://my-app-xxxxxxxxxx-uc.a.run.app`

---

## Environment Variables in Production

Your app likely needs secrets (API keys, database URLs). Set them via:

### Option A: During deployment
Claude can pass environment variables during deploy.

### Option B: After deployment (Cloud Console)
1. Go to [console.cloud.google.com/run](https://console.cloud.google.com/run)
2. Click your service
3. Edit & Deploy New Revision
4. Variables & Secrets → Add Variable

### Option C: Via gcloud CLI
```bash
gcloud run services update SERVICE_NAME \
  --region=us-central1 \
  --set-env-vars="API_KEY=xxx,DATABASE_URL=postgres://..."
```

### For sensitive secrets, use Secret Manager:
```bash
# Create a secret
echo -n "your-api-key" | gcloud secrets create MY_API_KEY --data-file=-

# Grant Cloud Run access
gcloud secrets add-iam-policy-binding MY_API_KEY \
  --member="serviceAccount:YOUR_PROJECT_NUMBER-compute@developer.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

# Reference in Cloud Run
gcloud run services update SERVICE_NAME \
  --set-secrets="API_KEY=MY_API_KEY:latest"
```

---

## Troubleshooting

### "Permission denied" on project operations
**Cause**: Org policies or IAM restrictions
**Fix**: Create a personal project outside the organization (Step 3)

### "Quota project required" for ADC
**Cause**: Application Default Credentials need a project for billing
**Fix**: `gcloud auth application-default set-quota-project YOUR_PROJECT_ID`

### "Billing must be enabled"
**Cause**: Project not linked to a billing account
**Fix**: Complete Step 4

### MCP tools not appearing in Claude Code
**Cause**: Session not restarted after adding MCP
**Fix**: Exit and restart Claude Code

### Deployment fails with container build errors
**Cause**: Missing Dockerfile or incorrect project structure
**Fix**: Ensure you have:
- `Dockerfile` in project root
- `requirements.txt` or `pyproject.toml` for dependencies
- Main entrypoint (e.g., `main.py` or `main_prod.py`)

### Service deployed but returns errors
**Cause**: Missing environment variables or runtime errors
**Fix**: Check logs with `gcloud run logs read --service=SERVICE_NAME`
  Or ask Claude: "Get the logs for my-service on Cloud Run"

---

## Quick Reference

### Full setup (copy-paste)
```bash
# Install gcloud (macOS)
brew install google-cloud-sdk

# Authenticate
gcloud auth login
gcloud auth application-default login

# Create project (use unique name)
gcloud projects create my-app-$(date +%s) --name="My App"
gcloud config set project my-app-XXXXXXXXXX  # use actual ID from above

# Set quota project
gcloud auth application-default set-quota-project my-app-XXXXXXXXXX

# Link billing
gcloud billing accounts list
gcloud billing projects link my-app-XXXXXXXXXX --billing-account=XXXXXX-XXXXXX-XXXXXX

# Enable APIs
gcloud services enable run.googleapis.com artifactregistry.googleapis.com

# Add MCP to Claude Code
claude mcp add --transport stdio --scope user cloud-run \
  --env GOOGLE_CLOUD_PROJECT=my-app-XXXXXXXXXX \
  --env GOOGLE_CLOUD_REGION=us-central1 \
  -- npx -y @google-cloud/cloud-run-mcp

# Restart Claude Code
exit
claude
```

### Useful commands
```bash
# List Cloud Run services
gcloud run services list

# Get service URL
gcloud run services describe SERVICE_NAME --format="value(status.url)"

# View logs
gcloud run logs read --service=SERVICE_NAME --limit=50

# Delete a service
gcloud run services delete SERVICE_NAME

# Update environment variables
gcloud run services update SERVICE_NAME --set-env-vars="KEY=value"
```

---

## Cost Considerations

Cloud Run pricing:
- **Free tier**: 2 million requests/month, 360,000 GB-seconds of memory
- **Pay-as-you-go**: ~$0.00002400 per vCPU-second, ~$0.00000250 per GB-second

For small apps with occasional traffic, you'll likely stay within free tier.

Set budget alerts at: [console.cloud.google.com/billing/budgets](https://console.cloud.google.com/billing/budgets)

---

## Next Steps

- Set up a custom domain: [Cloud Run domain mapping](https://cloud.google.com/run/docs/mapping-custom-domains)
- Configure CI/CD: Connect GitHub for automatic deploys
- Add monitoring: Cloud Run integrates with Cloud Monitoring automatically
