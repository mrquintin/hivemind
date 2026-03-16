# Hivemind Admin

This is the control center for Hivemind. Use it to create AI agents, upload documents, define formulas, and manage who can use the system.

---

## 🚀 Quick Start

**Double-click `Hivemind Admin.app`** — that's it!

On first run, it will:
1. Install prerequisites (Node.js, Rust, npm deps) if needed
2. Connect to the Hivemind server automatically
3. Launch the Admin app

**New computer?** Run `First Run Setup.command` once in the HivemindSoftware folder to remove macOS quarantine flags and sign the apps.

---

## Manual Setup (For Developers)

**Hivemind Admin.app installs all of these automatically on first run!** But if you prefer manual setup:

| Requirement | Why | How to Get |
|-------------|-----|------------|
| **Xcode CLT** | Required for compilation | `xcode-select --install` |
| **Node.js 18+** | Builds the React frontend | https://nodejs.org |
| **Rust** | Builds the native backend | https://rustup.rs |
| **Cloud server running** | Admin connects to the API | Deploy it with `AWS_GUIDE.md` |

### Running from Source

```bash
cd admin
npm install
npm run tauri dev
```

The first run takes a few minutes (Rust compilation). A desktop window will open.

### Building Installers

```bash
npm run tauri build
```

Installers appear in `src-tauri/target/release/bundle/`:
- **macOS**: `.dmg` file
- **Windows**: `.msi` file

---

## Connecting to the Server

Point Admin at your hosted API URL. You can either set it in the app’s Settings UI or provide it at build/run time:

```bash
VITE_API_URL=https://your-server.com npm run tauri dev
```

---

## Creating an Agent

Agents are AI "personalities" that analyze problems from specific angles.

### Step 1: Open the Agent Editor

1. Launch Admin
2. Click **Agents** in the sidebar
3. Click **New Agent**

### Step 2: Fill in Basic Info

| Field | What to Enter |
|-------|---------------|
| **Name** | A clear name like "Game Theory Analyst" or "Financial Risk Evaluator" |
| **Type** | **Theory** (analyzes problems) or **Practicality** (scores recommendations) |
| **Description** | What this agent does (for your reference) |

### Step 3: Define the Agent's Expertise

For **Theory Agents**:

| Field | What to Enter |
|-------|---------------|
| **Framework** | The analytical approach: "Game Theory", "Porter's Five Forces", "Systems Thinking", etc. |
| **Principles** | Core beliefs that guide analysis. Example: "Always consider competitor reactions. Look for Nash equilibria." |
| **Analytical Style** | How the agent communicates: "Precise and data-driven" or "Narrative and strategic" |

For **Practicality Agents**:

| Field | What to Enter |
|-------|---------------|
| **Scoring Criteria** | What factors determine feasibility: "Cost, timeline, technical complexity, organizational readiness" |
| **Score Interpretation** | What scores mean: "90+: Low risk. 70-89: Manageable. Below 70: Major concerns." |

### Step 4: Attach Knowledge (Optional)

1. Click **Attach Knowledge Bases**
2. Select which document collections this agent can reference
3. Example: A "Pharmaceutical Regulations Agent" might have FDA guidelines

### Step 5: Attach Simulations (Optional)

1. Click **Attach Simulations**
2. Select which math formulas this agent can use
3. Example: A "Financial Analyst" might use break-even and ROI calculations

### Step 6: Test the Agent

1. Click **Test Agent**
2. Enter a sample problem: "Should we enter the European market?"
3. Review the response
4. Adjust the framework/principles if needed

### Step 7: Save and Publish

- **Save as Draft**: Agent is saved but not available to Client users
- **Publish**: Agent becomes available to everyone

---

## Creating a Knowledge Base

Knowledge bases are collections of documents that agents can reference.

### Step 1: Create the Knowledge Base

1. Click **Knowledge Bases** in the sidebar
2. Click **New Knowledge Base**
3. Enter a name: "Market Research Q4 2024"
4. Enter a description: "Analyst reports and market sizing documents"
5. Click **Create**

### Step 2: Upload Documents

1. Open the knowledge base
2. Click **Upload Documents**
3. Select files (PDF, DOCX, TXT, MD, HTML)
4. Wait for processing

**What happens during processing:**

1. Text is extracted from each document
2. The text is split into chunks (paragraphs/sections)
3. Each chunk gets an embedding (numerical representation for AI search)
4. Chunks are indexed in Qdrant for fast retrieval

### Step 3: Test Retrieval

1. Click **Test Retrieval**
2. Enter a query: "What is the market size in Europe?"
3. Review which chunks are returned
4. Check the relevance scores (higher = more relevant)

If wrong content is returned:
- The query might be too vague — try more specific terms
- The documents might not contain the information
- Consider splitting large documents into smaller, focused ones

### Step 4: View Statistics

Each knowledge base shows:
- **Document Count**: How many files uploaded
- **Chunk Count**: How many searchable pieces
- **Processing Status**: Complete, In Progress, or Failed

---

## Creating a Simulation

Simulations are math formulas that agents can use for precise calculations.

### Example: Profit Margin Calculator

**Name**: Profit Margin Calculator

**Description**: Calculates gross profit margin from revenue and costs

**Inputs**:
| Name | Description | Unit |
|------|-------------|------|
| revenue | Total revenue | USD |
| costs | Total costs | USD |

**Calculations**:
```
profit = revenue - costs
margin = (profit / revenue) * 100
```

**Outputs**:
| Name | Description | Unit |
|------|-------------|------|
| profit | Gross profit | USD |
| margin | Profit margin | percent |

### Testing Simulations

1. Click **Test Simulation**
2. Enter values: `revenue = 1000000`, `costs = 750000`
3. Click **Run**
4. Verify outputs: `profit = 250000`, `margin = 25.0`

If results are wrong:
- Check the calculation syntax
- Make sure variable names match
- Verify units are consistent

---

## Managing Users

The `CLEARED_USERNAMES` setting in the cloud controls who can log in.

To add a user:

1. Open `cloud/.env`
2. Add the username to `CLEARED_USERNAMES`:
   ```
   CLEARED_USERNAMES=alice,bob,charlie,newuser
   ```
3. Restart the cloud server

Users only need their username to log in — the API key is configured on the server.

---

## Publishing Updates

When you change agents, knowledge bases, or simulations:

1. Changes are saved but not immediately available to Client users
2. Click **Publish** on the specific item to make it live
3. Client apps will see the update on their next request

**Tip**: Test thoroughly before publishing. Use the Test functions for agents and simulations.

---

## File Structure

```
admin/
├── src/                         # React frontend
│   ├── App.tsx                 # Main application
│   ├── main.tsx                # Entry point
│   ├── styles.css              # Styling
│   │
│   ├── components/             # Reusable UI components
│   │   └── Sidebar.tsx
│   │
│   ├── pages/                  # Screen components
│   │   ├── Dashboard.tsx       # Home screen
│   │   ├── AgentList.tsx       # List of agents
│   │   ├── AgentEdit.tsx       # Create/edit agent
│   │   ├── KnowledgeBases.tsx  # Document management
│   │   ├── SimulationList.tsx  # List of formulas
│   │   └── SimulationEdit.tsx  # Create/edit formula
│   │
│   └── api/
│       └── client.ts           # API calls to cloud
│
├── src-tauri/                   # Native backend (Rust)
│   ├── src/
│   │   └── main.rs             # Native commands
│   ├── tauri.conf.json         # App configuration
│   └── bin/                    # Bundled binaries
│
├── index.html                   # HTML entry point
├── package.json                 # Node dependencies
├── vite.config.ts              # Vite configuration
└── README.md                    # This file
```

---

## Troubleshooting

### App won't start

**Check Rust**:
```bash
rustc --version
```
If not installed, get it from https://rustup.rs and restart your terminal.

**Check Node.js**:
```bash
node --version
```
Needs to be 18 or higher.

**Try a clean install**:
```bash
rm -rf node_modules
npm install
npm run tauri dev
```

### Can't connect to cloud

1. Is the hosted cloud server reachable?
   ```bash
   curl https://your-server.com/health
   ```
2. Check the API URL in the app Settings page or `VITE_API_URL`
3. Check firewall settings
4. The sidebar shows connection status — it checks every 30 seconds

### Testing Server Connection

Use the "Test Connection" button in the sidebar to verify the server is reachable. If connected:
- The status dot turns green
- The server dashboard shows a green ping indicator

### Documents not processing

- **Large files**: Processing takes time. Check the status indicator.
- **Unsupported format**: Only PDF, DOCX, TXT, MD, HTML are supported.
- **Cloud errors**: Check the server logs for details.

### Agent test not working

1. Make sure the cloud server is running
2. Check that knowledge bases are attached (if the agent needs them)
3. Verify the server's Anthropic API key is valid and has credits

### Changes not appearing in Client

1. Did you click **Publish** on the agent/knowledge base/simulation?
2. Try refreshing the Client app
3. Check that both apps connect to the same cloud server
