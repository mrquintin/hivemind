# Hivemind Client

This is the end-user app for running AI-powered strategic analyses. You describe a problem, AI agents analyze it from multiple angles, and you get recommendations with full reasoning.

---

## 🚀 Quick Start

**Double-click `Hivemind Client.app`** — that's it!

On first run, it will:
1. Install prerequisites (Node.js, Rust, npm deps) if needed
2. Use the saved or configured Hivemind server URL
3. Launch the Client app

**New computer?** Run `First Run Setup.command` once in the HivemindSoftware folder to remove macOS quarantine flags and sign the apps.

---

## For End Users

### Logging In

When you open the app, you'll see a login screen:

**Username**: Enter your assigned username. This must be on the "cleared" list maintained by The Nash Lab.

Click **Log in**. If successful, you'll see the main terminal-style interface.

### Running an Analysis

1. **Type your problem** in the input area. Be specific:
   - Good: "Should we acquire CompanyX? They have strong IP but declining revenue."
   - Less good: "What should we do?"

2. **Select agents** from the available list. Each agent analyzes from a different angle (Game Theory, Financial Risk, etc.)

3. **Click Run Analysis** and watch the real-time progress

4. **Review the results**:
   - Each recommendation has a title, content, and reasoning
   - Feasibility scores show how practical each recommendation is
   - The audit trail shows exactly how conclusions were reached

### Understanding Results

**Feasibility Scores**:
| Score | Meaning |
|-------|---------|
| 90-100 | Highly feasible, low risk |
| 70-89 | Feasible with manageable challenges |
| 50-69 | Possible but significant obstacles |
| Below 50 | Major concerns (usually filtered out) |

**The Audit Trail**:
Every recommendation shows:
- Which agents contributed
- What documents were referenced
- What simulations were run
- How long each step took

This provides full transparency — you can see exactly why the AI reached its conclusions.

### Logging Out

Click **Log out** in the top-right corner. This clears your session and API key from the app.

---

## The Interface

The Client uses a Bloomberg Terminal-inspired design:

```
┌─ HIVEMIND TERMINAL ─────────────────────────────────────────────────────┐
│                                                                          │
│  ┌─ INPUT ────────────────┐  ┌─ AGENT RESPONSES ───────────────────────┐│
│  │                        │  │                                          ││
│  │  Type your problem     │  │  Theory Agent 1: [response]             ││
│  │  here...               │  │  Theory Agent 2: [response]             ││
│  │                        │  │                                          ││
│  └────────────────────────┘  └──────────────────────────────────────────┘│
│                                                                          │
│  ┌─ DEBATE FEED ──────────┐  ┌─ RECOMMENDATIONS ───────────────────────┐│
│  │                        │  │                                          ││
│  │  Agent dialogues and   │  │  Final recommendations with scores      ││
│  │  critiques appear here │  │                                          ││
│  │                        │  │                                          ││
│  └────────────────────────┘  └──────────────────────────────────────────┘│
│                                                                          │
│  ┌─ SIMULATIONS ──────────┐  ┌─ AUDIT TRAIL ───────────────────────────┐│
│  │                        │  │                                          ││
│  │  Math calculations     │  │  Step-by-step record of the analysis    ││
│  │                        │  │                                          ││
│  └────────────────────────┘  └──────────────────────────────────────────┘│
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## For Developers

### Prerequisites

**Hivemind Client.app installs all of these automatically on first run!** But if you prefer manual setup:

| Requirement | Why | How to Get |
|-------------|-----|------------|
| **Xcode CLT** | Required for compilation | `xcode-select --install` |
| **Node.js 18+** | Builds the React frontend | https://nodejs.org |
| **Rust** | Builds the native backend | https://rustup.rs |
| **Cloud server running** | Client connects to the API | Deploy it with `AWS_GUIDE.md` |

### Running from Source

```bash
cd client
npm install
npm run tauri dev
```

The first run takes a few minutes (Rust compilation). A desktop window will open.

### Building Installers

```bash
npm run tauri build
```

Outputs appear in `src-tauri/target/release/bundle/`:
- **macOS**: `.dmg` in `dmg/`
- **Windows**: `.msi` in `msi/`

### Connecting to a Different Server

Point the Client at your hosted API URL. Set the environment variable before running:
```bash
VITE_API_URL=https://your-server.com npm run tauri dev
```

Or change the server URL in the app UI if that build supports runtime configuration.

---

## File Structure

```
client/
├── src/                         # React frontend
│   ├── App.tsx                 # Main component with login + terminal UI
│   ├── main.tsx                # Entry point
│   ├── styles.css              # Bloomberg terminal styling
│   │
│   └── api/
│       └── client.ts           # API calls to cloud
│
├── src-tauri/                   # Native backend (Rust)
│   ├── src/
│   │   └── main.rs             # Native commands
│   ├── tauri.conf.json         # App configuration
│   └── Cargo.toml              # Rust dependencies
│
├── index.html                   # HTML entry point
├── package.json                 # Node dependencies
├── vite.config.ts              # Vite configuration
└── README.md                    # This file
```

### Key Files

**`src/App.tsx`**

The main React component. It handles:
- Login screen (`EnterMenu` component)
- Authentication state
- The main terminal UI with all the panels
- Real-time progress display

**`src/styles.css`**

All the styling. Uses:
- CSS variables for colors (`--bg`, `--text`, `--accent`, etc.)
- Terminal-inspired aesthetic
- Bloomberg-style data panels

**`src/api/client.ts`**

API client functions:
- `enterSystem()` — Login with username + API key
- `logout()` — Clear the session
- `getAuthToken()` — Get the current JWT token
- API URL configuration

---

## How Authentication Works

1. User enters their username
2. Client sends it to `POST /auth/login`
3. Server checks if username is in `CLEARED_USERNAMES`
4. Server returns a JWT token
5. Client stores the token and uses it for all subsequent requests
6. AI calls use the server's API key (configured during Cloud Setup)

**Local storage**: The Client stores the username in localStorage for convenience. Users stay logged in across app restarts until they explicitly log out.

---

## Troubleshooting

### "Username is not cleared"

Your username isn't in the `CLEARED_USERNAMES` list on the server. Contact The Nash Lab to get added.

### "Cannot connect to server"

1. Is the cloud server running?
2. Check your internet connection
3. Check if a firewall is blocking the connection

### Connection status shows "Disconnected"

The app checks server connection every 30 seconds. If disconnected:
1. Verify the server is running
2. Check your network connection
3. The app will reconnect automatically when the server is available

### Analysis is slow

This is normal. AI analysis takes time:
- Simple problems: 30-60 seconds
- Multiple agents: 1-3 minutes
- Each agent adds ~15-30 seconds

### App crashes on startup

**Mac**:
1. Right-click the app → "Open" (bypasses Gatekeeper)
2. System Settings → Privacy & Security → Allow the app

**Windows**:
1. Run as administrator
2. Check Windows Defender didn't quarantine it
3. Try reinstalling

### Lost my login

Your username is stored locally. If you:
- Clicked **Log out**: Enter your username again
- Cleared browser/app data: Enter your username again

---

## For IT Administrators

### System Requirements

| | Minimum | Recommended |
|--|---------|-------------|
| **macOS** | 10.15 (Catalina) | 12.0+ (Monterey) |
| **Windows** | Windows 10 | Windows 11 |
| **RAM** | 4 GB | 8 GB |
| **Storage** | 500 MB | 1 GB |

### Network Requirements

The app needs outbound HTTPS (port 443) to:
- The Hivemind Cloud server
- api.anthropic.com (for AI calls)

No inbound connections required.

### Silent Installation

**Windows**:
```bash
msiexec /i "Hivemind Client.msi" /quiet
```

**macOS**:
Deploy via MDM (Jamf, Kandji, etc.)

### Data Storage Locations

**macOS**: `~/Library/Application Support/com.thenashlab.hivemind.client/`

**Windows**: `%APPDATA%\com.thenashlab.hivemind.client\`

Contains:
- Session tokens
- Cached data
- App preferences

### Privacy

What stays local:
- Username (in localStorage)
- Session tokens
- App preferences

What goes to the server:
- Problem statements you submit
- Agent configurations you select

What we don't collect:
- Files on your computer
- System information
- Data from other apps
