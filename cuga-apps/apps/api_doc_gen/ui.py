_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>API Doc Generator</title>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  background:#0f1117;color:#e2e2e8;min-height:100vh;display:flex;flex-direction:column}

header{background:#1a1a2e;border-bottom:1px solid #2d2d4a;padding:14px 28px;
  display:flex;align-items:center;gap:12px;position:sticky;top:0;z-index:10;flex-shrink:0}
header h1{font-size:17px;font-weight:700;color:#fff}
.sub{font-size:12px;color:#6b6b7e}.sub span{color:#818cf8;font-weight:600}
.spacer{flex:1}
#specBadge{display:none;background:#1e2a1e;border:1px solid #2d4a2d;border-radius:6px;
  padding:4px 10px;font-size:11px;color:#6ee7b7;font-weight:600;gap:6px;align-items:center}
#specBadge.visible{display:flex}

.layout{display:grid;grid-template-columns:280px 1fr;flex:1;overflow:hidden;
  max-width:1600px;width:100%;margin:0 auto}
@media(max-width:760px){.layout{grid-template-columns:1fr}}

/* ── Sidebar ── */
.sidebar{padding:16px;overflow-y:auto;border-right:1px solid #2d2d4a;display:flex;flex-direction:column;gap:12px}
.card{background:#1a1a2e;border:1px solid #2d2d4a;border-radius:12px;padding:16px}
.slabel{font-size:11px;font-weight:700;color:#4a4a60;letter-spacing:.06em;
  text-transform:uppercase;margin-bottom:10px}

/* Spec loader */
.tab-row{display:flex;gap:4px;margin-bottom:12px}
.tab{background:none;border:1px solid #2d2d4a;border-radius:6px;
  padding:5px 10px;font-size:11px;color:#6b6b7e;cursor:pointer}
.tab.active{background:#6366f1;border-color:#6366f1;color:#fff}
.tab-panel{display:none}.tab-panel.active{display:block}

/* Drop zone */
#dropZone{border:2px dashed #2d2d4a;border-radius:8px;padding:20px;text-align:center;
  cursor:pointer;transition:border-color .15s;margin-bottom:8px}
#dropZone:hover,#dropZone.drag{border-color:#6366f1}
#dropZone p{font-size:12px;color:#4a4a60;line-height:1.6}
#dropZone strong{color:#818cf8}
#fileInput{display:none}

input[type=text],input[type=url]{width:100%;background:#0f1117;border:1px solid #2d2d4a;
  border-radius:7px;padding:8px 10px;font-size:12px;color:#e2e2e8;outline:none;
  font-family:inherit}
input:focus{border-color:#818cf8}
.btn{background:#6366f1;color:#fff;border:none;border-radius:7px;
  padding:7px 14px;font-size:12px;font-weight:600;cursor:pointer;width:100%;margin-top:8px}
.btn:hover{background:#4f46e5}
.btn:disabled{opacity:.4;cursor:default}
.btn-sm{width:auto;padding:5px 10px;font-size:11px;margin-top:0}
.btn-danger{background:#7f1d1d;color:#fca5a5}.btn-danger:hover{background:#991b1b}
.btn-ghost{background:#1f2937;border:1px solid #374151;color:#9ca3af;margin-top:0}
.btn-ghost:hover{background:#374151}

/* Sample cards */
.sample-grid{display:flex;flex-direction:column;gap:6px}
.sample-card{background:#0f1117;border:1px solid #2d2d4a;border-radius:8px;
  padding:10px 12px;cursor:pointer;transition:border-color .15s,background .15s}
.sample-card:hover{border-color:#6366f1;background:#12122a}
.sample-card.loaded{border-color:#2d4a2d;background:#0f1f0f}
.sample-name{font-size:12px;font-weight:600;color:#e2e2e8;margin-bottom:2px}
.sample-desc{font-size:11px;color:#4a4a60;line-height:1.4}
.sample-tag{display:inline-block;background:#1e1e3a;border:1px solid #2d2d4a;
  border-radius:4px;padding:1px 6px;font-size:10px;color:#818cf8;margin-top:4px;margin-right:3px}

/* Spec info */
#specInfo{display:none}
#specInfo.visible{display:block}
.info-row{display:flex;justify-content:space-between;align-items:center;
  margin-bottom:5px;font-size:12px}
.info-key{color:#6b6b7e}.info-val{color:#e2e2e8;font-weight:600;font-size:11px;
  text-align:right;max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.info-url{font-size:10px;color:#818cf8;word-break:break-all;margin-top:2px}

/* ── Main area ── */
.main{display:flex;flex-direction:column;overflow:hidden}

/* Docs panel */
#docsPanel{background:#1a1a2e;border-bottom:1px solid #2d2d4a;display:none;
  flex-shrink:0;max-height:45vh;overflow-y:auto}
#docsPanel.visible{display:block}
.docs-header{display:flex;align-items:center;gap:8px;padding:10px 20px;
  position:sticky;top:0;background:#1a1a2e;border-bottom:1px solid #2d2d4a;z-index:1}
.docs-title{font-size:11px;font-weight:700;color:#6b6b7e;letter-spacing:.08em;
  text-transform:uppercase;flex:1}
#docsContent{padding:16px 20px;font-size:13px;line-height:1.7;color:#d1d5db}
#docsContent h2{font-size:15px;font-weight:700;color:#fff;margin:16px 0 6px;
  border-bottom:1px solid #2d2d4a;padding-bottom:6px}
#docsContent h3{font-size:13px;font-weight:700;color:#c4b5fd;margin:14px 0 5px}
#docsContent h4{font-size:12px;font-weight:700;color:#a78bfa;margin:10px 0 4px}
#docsContent p{margin-bottom:8px}
#docsContent strong{color:#fff}
#docsContent code{background:#0f1117;padding:1px 5px;border-radius:3px;
  font-family:"SF Mono",Menlo,monospace;font-size:11px;color:#818cf8}
#docsContent pre{background:#0f1117;border:1px solid #2d2d4a;border-radius:8px;
  padding:12px 14px;overflow-x:auto;margin:8px 0}
#docsContent pre code{background:none;color:#d1d5db;font-size:12px;padding:0}
#docsContent table{width:100%;border-collapse:collapse;margin:8px 0;font-size:12px}
#docsContent th{background:#111827;color:#9ca3af;padding:6px 10px;
  text-align:left;font-weight:600;border:1px solid #1f2937}
#docsContent td{padding:6px 10px;border:1px solid #1f2937;color:#d1d5db}
#docsContent td:first-child{color:#c4b5fd;font-family:"SF Mono",Menlo,monospace;font-size:11px}
#docsContent hr{border:none;border-top:1px solid #2d2d4a;margin:16px 0}
#docsContent ul,#docsContent ol{padding-left:20px;margin:6px 0}
#docsContent li{margin:2px 0}
.copy-docs-btn{background:#1f2937;border:1px solid #374151;color:#9ca3af;
  border-radius:6px;padding:4px 10px;font-size:11px;cursor:pointer}
.copy-docs-btn:hover{background:#374151}

/* Chat */
#chatThread{flex:1;overflow-y:auto;padding:16px 20px;display:flex;flex-direction:column;gap:12px}
.msg{max-width:88%;animation:fadein .2s ease}
.msg-user{align-self:flex-end;background:#6366f1;color:#fff;border-radius:12px 12px 2px 12px;
  padding:10px 14px;font-size:13px;line-height:1.5}
.msg-agent{align-self:flex-start;background:#1a1a2e;border:1px solid #2d2d4a;
  border-radius:12px 12px 12px 2px;padding:12px 16px;font-size:13px;line-height:1.7;
  color:#d1d5db;max-width:100%}
.msg-agent strong{color:#fff}
.msg-agent code{background:#0f1117;padding:1px 5px;border-radius:3px;font-size:11px;color:#818cf8}
.msg-thinking{color:#6b6b7e;font-style:italic;font-size:13px;padding:10px 14px;align-self:flex-start}
.welcome{text-align:center;color:#4a4a60;padding:40px 20px;flex:1;display:flex;
  flex-direction:column;align-items:center;justify-content:center;gap:16px}
.welcome h2{font-size:18px;color:#6b6b7e;font-weight:600}
.chips{display:flex;flex-wrap:wrap;gap:6px;justify-content:center;max-width:620px}
.chip{background:#111827;border:1px solid #1e293b;border-radius:6px;
  padding:5px 10px;font-size:12px;color:#94a3b8;cursor:pointer;transition:all .15s}
.chip:hover{background:#6366f1;border-color:#6366f1;color:#fff}

/* Input */
.input-bar{padding:12px 20px;border-top:1px solid #2d2d4a;background:#1a1a2e;flex-shrink:0}
.input-row{display:flex;gap:8px;align-items:flex-end}
#chatInput{flex:1;background:#0f1117;border:1px solid #2d2d4a;border-radius:8px;
  padding:10px 14px;font-size:14px;color:#e2e2e8;outline:none;font-family:inherit;
  resize:none;min-height:44px;max-height:120px;line-height:1.4}
#chatInput:focus{border-color:#818cf8}
#chatInput::placeholder{color:#4a4a60}
#sendBtn{background:#6366f1;color:#fff;border:none;border-radius:8px;
  padding:10px 20px;font-size:14px;font-weight:600;cursor:pointer;height:44px;white-space:nowrap}
#sendBtn:hover{background:#4f46e5}
#sendBtn:disabled{opacity:.4;cursor:default}
.refine-chips{display:flex;flex-wrap:wrap;gap:5px;margin-top:8px}
.refine-chips .chip{font-size:11px;padding:3px 8px}

.toast{position:fixed;bottom:20px;right:20px;background:#10b981;color:#fff;
  padding:8px 16px;border-radius:8px;font-size:13px;font-weight:600;
  opacity:0;transition:opacity .3s;pointer-events:none;z-index:100}
.toast.show{opacity:1}

@keyframes fadein{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:none}}
@keyframes spin{to{transform:rotate(360deg)}}
.spinner{display:inline-block;animation:spin .7s linear infinite}
</style>
</head>
<body>

<header>
  <h1>API Doc Generator</h1>
  <p class="sub">Powered by <span>CugaAgent</span></p>
  <div class="spacer"></div>
  <div id="specBadge">
    <span>&#9679;</span>
    <span id="specBadgeText">No spec</span>
  </div>
</header>

<div class="layout">

<!-- ══ Sidebar ══ -->
<div class="sidebar">

  <div class="card">
    <div class="slabel">Load a spec</div>
    <div class="tab-row">
      <button class="tab active" onclick="switchTab('samples')">Samples</button>
      <button class="tab" onclick="switchTab('upload')">Upload</button>
      <button class="tab" onclick="switchTab('url')">URL</button>
    </div>

    <!-- Samples tab -->
    <div class="tab-panel active" id="tab-samples">
      <div class="sample-grid" id="sampleGrid"></div>
    </div>

    <!-- Upload tab -->
    <div class="tab-panel" id="tab-upload">
      <div id="dropZone" onclick="document.getElementById('fileInput').click()"
           ondragover="event.preventDefault();this.classList.add('drag')"
           ondragleave="this.classList.remove('drag')"
           ondrop="handleDrop(event)">
        <p><strong>Click or drag & drop</strong><br>JSON or YAML OpenAPI spec</p>
      </div>
      <input type="file" id="fileInput" accept=".json,.yaml,.yml"
             onchange="handleFileInput(this)">
    </div>

    <!-- URL tab -->
    <div class="tab-panel" id="tab-url">
      <input type="url" id="specUrl" placeholder="https://…/openapi.json"
             onkeydown="if(event.key==='Enter')loadFromUrl()">
      <button class="btn" onclick="loadFromUrl()">Load</button>
    </div>
  </div>

  <!-- Spec info (shown after load) -->
  <div class="card" id="specInfo">
    <div class="slabel">Loaded spec</div>
    <div class="info-row"><span class="info-key">Name</span><span class="info-val" id="infoTitle">—</span></div>
    <div class="info-row"><span class="info-key">Version</span><span class="info-val" id="infoVersion">—</span></div>
    <div class="info-row"><span class="info-key">Endpoints</span><span class="info-val" id="infoCount">—</span></div>
    <div class="info-url" id="infoUrl"></div>
  </div>

  <div class="card">
    <div class="slabel">Session</div>
    <button class="btn btn-danger" onclick="resetSession()">New session</button>
    <p style="font-size:10px;color:#4a4a60;margin-top:6px;line-height:1.4">
      Clears the conversation. The loaded spec stays in place.
    </p>
  </div>

</div>

<!-- ══ Main ══ -->
<div class="main">

  <!-- Docs output panel -->
  <div id="docsPanel">
    <div class="docs-header">
      <span class="docs-title">Generated docs</span>
      <button class="copy-docs-btn" onclick="copyDocs()">Copy Markdown</button>
    </div>
    <div id="docsContent"></div>
  </div>

  <!-- Chat -->
  <div id="chatThread">
    <div class="welcome" id="welcomeScreen">
      <h2>Select a spec to get started</h2>
      <p style="color:#4a4a60;font-size:13px;max-width:500px">
        Choose a sample API from the sidebar, upload your own OpenAPI spec,
        or point to a URL — then ask the agent to generate docs.
      </p>
      <div class="chips" id="starterChips">
        <span class="chip" onclick="ask(this.textContent)">Load Petstore and document all endpoints</span>
        <span class="chip" onclick="ask(this.textContent)">Load Stripe Payments and document the Charges API</span>
        <span class="chip" onclick="ask(this.textContent)">Load GitHub Issues and document the issue endpoints</span>
        <span class="chip" onclick="ask(this.textContent)">Load the Weather API and show me an example response</span>
        <span class="chip" onclick="ask(this.textContent)">Load Slack Messaging and document the channels endpoints</span>
      </div>
    </div>
  </div>

  <!-- Input bar -->
  <div class="input-bar">
    <div class="input-row">
      <textarea id="chatInput" rows="1"
        placeholder="Ask the agent to generate docs, explain an endpoint, add examples…"
        onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();ask()}"
        oninput="this.style.height='auto';this.style.height=Math.min(this.scrollHeight,120)+'px'"></textarea>
      <button id="sendBtn" onclick="ask()">Send</button>
    </div>
    <div class="refine-chips" id="refineChips" style="display:none">
      <span class="chip" onclick="ask(this.textContent)">Document all endpoints</span>
      <span class="chip" onclick="ask(this.textContent)">Show authentication details</span>
      <span class="chip" onclick="ask(this.textContent)">Add more realistic examples</span>
      <span class="chip" onclick="ask(this.textContent)">Document only POST endpoints</span>
      <span class="chip" onclick="ask(this.textContent)">Generate a Postman collection structure</span>
      <span class="chip" onclick="ask(this.textContent)">Explain the error response codes</span>
      <span class="chip" onclick="ask(this.textContent)">Show request/response schemas as tables</span>
    </div>
  </div>

</div>
</div>

<div class="toast" id="toast"></div>

<script>
// ── Sample OpenAPI specs ──────────────────────────────────────────────────

const SAMPLES = [
  {
    name: "Petstore API",
    desc: "Classic OpenAPI example — pets, orders, users",
    tags: ["REST", "CRUD", "Pets"],
    spec: {
      openapi: "3.0.3",
      info: { title: "Petstore API", version: "1.0.0",
        description: "A simple pet store REST API demonstrating CRUD operations." },
      servers: [{ url: "https://api.petstore.example.com/v1" }],
      components: {
        securitySchemes: {
          BearerAuth: { type: "http", scheme: "bearer", bearerFormat: "JWT" },
          ApiKeyAuth: { type: "apiKey", in: "header", name: "X-Api-Key" }
        },
        schemas: {
          Pet: {
            type: "object", required: ["name", "species"],
            properties: {
              id: { type: "integer", readOnly: true, example: 42 },
              name: { type: "string", example: "Biscuit" },
              species: { type: "string", enum: ["dog","cat","bird","rabbit"], example: "cat" },
              breed: { type: "string", example: "Maine Coon" },
              age: { type: "integer", example: 3 },
              status: { type: "string", enum: ["available","adopted","pending"], example: "available" },
              owner_id: { type: "integer", nullable: true, example: 7 },
              created_at: { type: "string", format: "date-time" }
            }
          },
          Order: {
            type: "object",
            properties: {
              id: { type: "integer", readOnly: true, example: 101 },
              pet_id: { type: "integer", example: 42 },
              user_id: { type: "integer", example: 7 },
              status: { type: "string", enum: ["pending","approved","delivered","cancelled"], example: "pending" },
              quantity: { type: "integer", example: 1 },
              ship_date: { type: "string", format: "date-time" },
              total_cents: { type: "integer", example: 4999 }
            }
          },
          User: {
            type: "object", required: ["username", "email"],
            properties: {
              id: { type: "integer", readOnly: true, example: 7 },
              username: { type: "string", example: "alice_chen" },
              email: { type: "string", format: "email", example: "alice@petstore.com" },
              first_name: { type: "string", example: "Alice" },
              last_name: { type: "string", example: "Chen" },
              phone: { type: "string", example: "+1-415-555-0100" },
              role: { type: "string", enum: ["customer","staff","admin"], example: "customer" }
            }
          },
          ApiError: {
            type: "object",
            properties: {
              code: { type: "integer", example: 404 },
              message: { type: "string", example: "Pet not found" }
            }
          }
        }
      },
      paths: {
        "/pets": {
          get: {
            summary: "List pets", operationId: "listPets", tags: ["Pets"],
            description: "Returns a paginated list of pets with optional filters.",
            parameters: [
              { name: "status", in: "query", schema: { type: "string", enum: ["available","adopted","pending"] }, description: "Filter by adoption status" },
              { name: "species", in: "query", schema: { type: "string" }, description: "Filter by species (dog, cat, bird, rabbit)" },
              { name: "limit", in: "query", schema: { type: "integer", default: 20, maximum: 100 }, description: "Max results per page" },
              { name: "offset", in: "query", schema: { type: "integer", default: 0 }, description: "Pagination offset" }
            ],
            responses: {
              "200": { description: "List of pets", content: { "application/json": { schema: { type: "array", items: { "$ref": "#/components/schemas/Pet" } } } } },
              "400": { description: "Invalid query parameters" }
            }
          },
          post: {
            summary: "Create a pet", operationId: "createPet", tags: ["Pets"],
            description: "Add a new pet to the store. Requires staff or admin role.",
            security: [{ BearerAuth: [] }],
            requestBody: { required: true, content: { "application/json": { schema: { "$ref": "#/components/schemas/Pet" } } } },
            responses: {
              "201": { description: "Pet created", content: { "application/json": { schema: { "$ref": "#/components/schemas/Pet" } } } },
              "400": { description: "Validation error" },
              "401": { description: "Unauthorised" },
              "403": { description: "Insufficient permissions" }
            }
          }
        },
        "/pets/{petId}": {
          get: {
            summary: "Get a pet", operationId: "getPet", tags: ["Pets"],
            parameters: [{ name: "petId", in: "path", required: true, schema: { type: "integer" }, description: "Pet ID" }],
            responses: {
              "200": { description: "Pet details", content: { "application/json": { schema: { "$ref": "#/components/schemas/Pet" } } } },
              "404": { description: "Pet not found" }
            }
          },
          put: {
            summary: "Update a pet", operationId: "updatePet", tags: ["Pets"],
            security: [{ BearerAuth: [] }],
            parameters: [{ name: "petId", in: "path", required: true, schema: { type: "integer" } }],
            requestBody: { required: true, content: { "application/json": { schema: { "$ref": "#/components/schemas/Pet" } } } },
            responses: {
              "200": { description: "Updated pet" },
              "401": { description: "Unauthorised" },
              "404": { description: "Pet not found" }
            }
          },
          delete: {
            summary: "Delete a pet", operationId: "deletePet", tags: ["Pets"],
            security: [{ BearerAuth: [] }],
            parameters: [{ name: "petId", in: "path", required: true, schema: { type: "integer" } }],
            responses: {
              "204": { description: "Deleted" },
              "401": { description: "Unauthorised" },
              "404": { description: "Pet not found" }
            }
          }
        },
        "/orders": {
          post: {
            summary: "Place an order", operationId: "placeOrder", tags: ["Orders"],
            security: [{ BearerAuth: [] }],
            requestBody: { required: true, content: { "application/json": { schema: { "$ref": "#/components/schemas/Order" } } } },
            responses: {
              "201": { description: "Order placed", content: { "application/json": { schema: { "$ref": "#/components/schemas/Order" } } } },
              "400": { description: "Pet unavailable or invalid request" },
              "401": { description: "Unauthorised" }
            }
          }
        },
        "/orders/{orderId}": {
          get: {
            summary: "Get an order", operationId: "getOrder", tags: ["Orders"],
            security: [{ BearerAuth: [] }],
            parameters: [{ name: "orderId", in: "path", required: true, schema: { type: "integer" } }],
            responses: {
              "200": { description: "Order details", content: { "application/json": { schema: { "$ref": "#/components/schemas/Order" } } } },
              "401": { description: "Unauthorised" },
              "404": { description: "Order not found" }
            }
          },
          delete: {
            summary: "Cancel an order", operationId: "cancelOrder", tags: ["Orders"],
            security: [{ BearerAuth: [] }],
            parameters: [{ name: "orderId", in: "path", required: true, schema: { type: "integer" } }],
            responses: {
              "204": { description: "Cancelled" },
              "400": { description: "Order already shipped" },
              "404": { description: "Order not found" }
            }
          }
        },
        "/users": {
          post: {
            summary: "Register a user", operationId: "createUser", tags: ["Users"],
            requestBody: { required: true, content: { "application/json": { schema: { "$ref": "#/components/schemas/User" } } } },
            responses: {
              "201": { description: "User created", content: { "application/json": { schema: { "$ref": "#/components/schemas/User" } } } },
              "409": { description: "Username or email already taken" }
            }
          }
        },
        "/users/login": {
          post: {
            summary: "Log in", operationId: "loginUser", tags: ["Users"],
            requestBody: { required: true, content: { "application/json": { schema: {
              type: "object", required: ["username","password"],
              properties: { username: { type: "string" }, password: { type: "string", format: "password" } }
            }}}},
            responses: {
              "200": { description: "JWT token", content: { "application/json": { schema: {
                type: "object", properties: { token: { type: "string" }, expires_at: { type: "string" } }
              }}}},
              "401": { description: "Bad credentials" }
            }
          }
        }
      }
    }
  },

  {
    name: "GitHub Issues API",
    desc: "Create and manage issues, labels, comments on repositories",
    tags: ["GitHub", "Issues", "Collaboration"],
    spec: {
      openapi: "3.0.3",
      info: { title: "GitHub Issues API", version: "2022-11-28",
        description: "Manage issues, labels, and comments on GitHub repositories. Requires a personal access token." },
      servers: [{ url: "https://api.github.com" }],
      components: {
        securitySchemes: {
          BearerAuth: { type: "http", scheme: "bearer", description: "GitHub personal access token" }
        },
        schemas: {
          Issue: {
            type: "object",
            properties: {
              id: { type: "integer", example: 1 },
              number: { type: "integer", example: 42 },
              title: { type: "string", example: "Bug: login fails with SSO enabled" },
              body: { type: "string", example: "When SSO is enabled, clicking 'Sign in' redirects to a blank page." },
              state: { type: "string", enum: ["open","closed"], example: "open" },
              labels: { type: "array", items: { "$ref": "#/components/schemas/Label" } },
              assignees: { type: "array", items: { "$ref": "#/components/schemas/User" } },
              user: { "$ref": "#/components/schemas/User" },
              comments: { type: "integer", example: 3 },
              created_at: { type: "string", format: "date-time" },
              updated_at: { type: "string", format: "date-time" },
              closed_at: { type: "string", format: "date-time", nullable: true },
              html_url: { type: "string", example: "https://github.com/acme/webapp/issues/42" }
            }
          },
          Label: {
            type: "object",
            properties: {
              id: { type: "integer", example: 208045946 },
              name: { type: "string", example: "bug" },
              color: { type: "string", example: "d73a4a", description: "6-digit hex without #" },
              description: { type: "string", example: "Something isn't working" }
            }
          },
          Comment: {
            type: "object",
            properties: {
              id: { type: "integer", example: 88 },
              body: { type: "string", example: "I can reproduce this on Firefox 124 + Windows 11." },
              user: { "$ref": "#/components/schemas/User" },
              created_at: { type: "string", format: "date-time" },
              updated_at: { type: "string", format: "date-time" },
              html_url: { type: "string" }
            }
          },
          User: {
            type: "object",
            properties: {
              login: { type: "string", example: "alice-chen" },
              id: { type: "integer", example: 1234567 },
              avatar_url: { type: "string" },
              html_url: { type: "string", example: "https://github.com/alice-chen" }
            }
          }
        }
      },
      paths: {
        "/repos/{owner}/{repo}/issues": {
          get: {
            summary: "List repository issues", operationId: "listIssues", tags: ["Issues"],
            security: [{ BearerAuth: [] }],
            parameters: [
              { name: "owner", in: "path", required: true, schema: { type: "string" }, description: "Repository owner (user or org)" },
              { name: "repo", in: "path", required: true, schema: { type: "string" }, description: "Repository name" },
              { name: "state", in: "query", schema: { type: "string", enum: ["open","closed","all"], default: "open" }, description: "Issue state filter" },
              { name: "labels", in: "query", schema: { type: "string" }, description: "Comma-separated label names" },
              { name: "assignee", in: "query", schema: { type: "string" }, description: "GitHub username or '*' for any" },
              { name: "per_page", in: "query", schema: { type: "integer", default: 30, maximum: 100 } },
              { name: "page", in: "query", schema: { type: "integer", default: 1 } }
            ],
            responses: {
              "200": { description: "List of issues", content: { "application/json": { schema: { type: "array", items: { "$ref": "#/components/schemas/Issue" } } } } },
              "401": { description: "Bad credentials" },
              "404": { description: "Repository not found" }
            }
          },
          post: {
            summary: "Create an issue", operationId: "createIssue", tags: ["Issues"],
            security: [{ BearerAuth: [] }],
            parameters: [
              { name: "owner", in: "path", required: true, schema: { type: "string" } },
              { name: "repo", in: "path", required: true, schema: { type: "string" } }
            ],
            requestBody: { required: true, content: { "application/json": { schema: {
              type: "object", required: ["title"],
              properties: {
                title: { type: "string", example: "Button alignment broken on mobile" },
                body: { type: "string", example: "The submit button overlaps the input field on screens < 375px." },
                assignees: { type: "array", items: { type: "string" }, example: ["alice-chen"] },
                labels: { type: "array", items: { type: "string" }, example: ["bug","needs-triage"] },
                milestone: { type: "integer", example: 3 }
              }
            }}}},
            responses: {
              "201": { description: "Issue created", content: { "application/json": { schema: { "$ref": "#/components/schemas/Issue" } } } },
              "403": { description: "Forbidden — no write access" },
              "422": { description: "Validation error" }
            }
          }
        },
        "/repos/{owner}/{repo}/issues/{issue_number}": {
          get: {
            summary: "Get an issue", operationId: "getIssue", tags: ["Issues"],
            security: [{ BearerAuth: [] }],
            parameters: [
              { name: "owner", in: "path", required: true, schema: { type: "string" } },
              { name: "repo", in: "path", required: true, schema: { type: "string" } },
              { name: "issue_number", in: "path", required: true, schema: { type: "integer" }, description: "Issue number (not ID)" }
            ],
            responses: {
              "200": { description: "Issue", content: { "application/json": { schema: { "$ref": "#/components/schemas/Issue" } } } },
              "404": { description: "Issue not found" }
            }
          },
          patch: {
            summary: "Update an issue", operationId: "updateIssue", tags: ["Issues"],
            security: [{ BearerAuth: [] }],
            parameters: [
              { name: "owner", in: "path", required: true, schema: { type: "string" } },
              { name: "repo", in: "path", required: true, schema: { type: "string" } },
              { name: "issue_number", in: "path", required: true, schema: { type: "integer" } }
            ],
            requestBody: { required: true, content: { "application/json": { schema: {
              type: "object",
              properties: {
                title: { type: "string" },
                body: { type: "string" },
                state: { type: "string", enum: ["open","closed"] },
                labels: { type: "array", items: { type: "string" } },
                assignees: { type: "array", items: { type: "string" } }
              }
            }}}},
            responses: {
              "200": { description: "Updated issue" },
              "403": { description: "Forbidden" },
              "404": { description: "Not found" }
            }
          }
        },
        "/repos/{owner}/{repo}/issues/{issue_number}/comments": {
          get: {
            summary: "List issue comments", operationId: "listComments", tags: ["Comments"],
            security: [{ BearerAuth: [] }],
            parameters: [
              { name: "owner", in: "path", required: true, schema: { type: "string" } },
              { name: "repo", in: "path", required: true, schema: { type: "string" } },
              { name: "issue_number", in: "path", required: true, schema: { type: "integer" } },
              { name: "per_page", in: "query", schema: { type: "integer", default: 30 } }
            ],
            responses: {
              "200": { description: "Comments", content: { "application/json": { schema: { type: "array", items: { "$ref": "#/components/schemas/Comment" } } } } }
            }
          },
          post: {
            summary: "Add a comment", operationId: "createComment", tags: ["Comments"],
            security: [{ BearerAuth: [] }],
            parameters: [
              { name: "owner", in: "path", required: true, schema: { type: "string" } },
              { name: "repo", in: "path", required: true, schema: { type: "string" } },
              { name: "issue_number", in: "path", required: true, schema: { type: "integer" } }
            ],
            requestBody: { required: true, content: { "application/json": { schema: {
              type: "object", required: ["body"],
              properties: { body: { type: "string", example: "Confirmed — I see the same issue on Chrome 124." } }
            }}}},
            responses: {
              "201": { description: "Comment created", content: { "application/json": { schema: { "$ref": "#/components/schemas/Comment" } } } }
            }
          }
        },
        "/repos/{owner}/{repo}/labels": {
          get: {
            summary: "List labels", operationId: "listLabels", tags: ["Labels"],
            security: [{ BearerAuth: [] }],
            parameters: [
              { name: "owner", in: "path", required: true, schema: { type: "string" } },
              { name: "repo", in: "path", required: true, schema: { type: "string" } }
            ],
            responses: {
              "200": { description: "Labels", content: { "application/json": { schema: { type: "array", items: { "$ref": "#/components/schemas/Label" } } } } }
            }
          },
          post: {
            summary: "Create a label", operationId: "createLabel", tags: ["Labels"],
            security: [{ BearerAuth: [] }],
            parameters: [
              { name: "owner", in: "path", required: true, schema: { type: "string" } },
              { name: "repo", in: "path", required: true, schema: { type: "string" } }
            ],
            requestBody: { required: true, content: { "application/json": { schema: {
              type: "object", required: ["name","color"],
              properties: {
                name: { type: "string", example: "performance" },
                color: { type: "string", example: "0075ca" },
                description: { type: "string", example: "Slow queries or rendering" }
              }
            }}}},
            responses: {
              "201": { description: "Label created" },
              "422": { description: "Label name already exists" }
            }
          }
        }
      }
    }
  },

  {
    name: "Stripe Payments API",
    desc: "Customers, charges, subscriptions, and refunds",
    tags: ["Payments", "Stripe", "Finance"],
    spec: {
      openapi: "3.0.3",
      info: { title: "Stripe Payments API", version: "2024-06-20",
        description: "Accept payments, manage customers, and handle subscriptions. All amounts are in the smallest currency unit (e.g. cents for USD)." },
      servers: [{ url: "https://api.stripe.com/v1" }],
      components: {
        securitySchemes: {
          BasicAuth: { type: "http", scheme: "basic", description: "Use your Stripe secret key as the username. Leave password blank." }
        },
        schemas: {
          Customer: {
            type: "object",
            properties: {
              id: { type: "string", example: "cus_Qk5fG2hJ8mPx3N" },
              object: { type: "string", enum: ["customer"], example: "customer" },
              email: { type: "string", example: "alice@acmecorp.com" },
              name: { type: "string", example: "Alice Chen" },
              phone: { type: "string", example: "+1-415-555-0100" },
              description: { type: "string", example: "Premium plan subscriber" },
              balance: { type: "integer", example: 0, description: "Account balance in cents. Negative = credit." },
              default_source: { type: "string", nullable: true, example: "card_1OxFkP2eZvKYlo2C8r3dU9mL" },
              metadata: { type: "object", example: { "company": "Acme Corp", "tier": "premium" } },
              created: { type: "integer", example: 1714000000, description: "Unix timestamp" }
            }
          },
          Charge: {
            type: "object",
            properties: {
              id: { type: "string", example: "ch_3OxFkP2eZvKYlo2C1QxKvNpA" },
              object: { type: "string", enum: ["charge"] },
              amount: { type: "integer", example: 4999, description: "Amount in smallest currency unit (cents)" },
              currency: { type: "string", example: "usd" },
              customer: { type: "string", example: "cus_Qk5fG2hJ8mPx3N" },
              description: { type: "string", example: "Pro plan — April 2026" },
              status: { type: "string", enum: ["succeeded","pending","failed"], example: "succeeded" },
              paid: { type: "boolean", example: true },
              receipt_url: { type: "string", example: "https://pay.stripe.com/receipts/..." },
              failure_message: { type: "string", nullable: true },
              created: { type: "integer", example: 1714003200 }
            }
          },
          Subscription: {
            type: "object",
            properties: {
              id: { type: "string", example: "sub_1OxFkP2eZvKYlo2CvNpA3Bcd" },
              object: { type: "string", enum: ["subscription"] },
              customer: { type: "string", example: "cus_Qk5fG2hJ8mPx3N" },
              status: { type: "string", enum: ["active","trialing","past_due","canceled","incomplete"], example: "active" },
              current_period_start: { type: "integer", example: 1714000000 },
              current_period_end: { type: "integer", example: 1716592000 },
              cancel_at_period_end: { type: "boolean", example: false },
              items: { type: "object", properties: { data: { type: "array", items: { type: "object" } } } }
            }
          },
          Refund: {
            type: "object",
            properties: {
              id: { type: "string", example: "re_3OxFkP2eZvKYlo2C0x2J8kNp" },
              amount: { type: "integer", example: 4999 },
              charge: { type: "string", example: "ch_3OxFkP2eZvKYlo2C1QxKvNpA" },
              currency: { type: "string", example: "usd" },
              reason: { type: "string", enum: ["duplicate","fraudulent","requested_by_customer"], nullable: true },
              status: { type: "string", enum: ["pending","succeeded","failed","canceled"], example: "succeeded" },
              created: { type: "integer", example: 1714009600 }
            }
          }
        }
      },
      paths: {
        "/customers": {
          get: {
            summary: "List customers", operationId: "listCustomers", tags: ["Customers"],
            security: [{ BasicAuth: [] }],
            parameters: [
              { name: "email", in: "query", schema: { type: "string" }, description: "Filter by exact email address" },
              { name: "limit", in: "query", schema: { type: "integer", default: 10, maximum: 100 } },
              { name: "starting_after", in: "query", schema: { type: "string" }, description: "Cursor for pagination (customer ID)" }
            ],
            responses: {
              "200": { description: "Paginated customer list", content: { "application/json": { schema: {
                type: "object",
                properties: {
                  data: { type: "array", items: { "$ref": "#/components/schemas/Customer" } },
                  has_more: { type: "boolean" }
                }
              }}}},
              "401": { description: "Invalid API key" }
            }
          },
          post: {
            summary: "Create a customer", operationId: "createCustomer", tags: ["Customers"],
            security: [{ BasicAuth: [] }],
            requestBody: { required: true, content: { "application/x-www-form-urlencoded": { schema: {
              type: "object",
              properties: {
                email: { type: "string", example: "alice@acmecorp.com" },
                name: { type: "string", example: "Alice Chen" },
                phone: { type: "string", example: "+14155550100" },
                description: { type: "string" },
                "metadata[company]": { type: "string", example: "Acme Corp" }
              }
            }}}},
            responses: {
              "200": { description: "Customer object", content: { "application/json": { schema: { "$ref": "#/components/schemas/Customer" } } } },
              "402": { description: "Card error" }
            }
          }
        },
        "/customers/{id}": {
          get: {
            summary: "Retrieve a customer", operationId: "getCustomer", tags: ["Customers"],
            security: [{ BasicAuth: [] }],
            parameters: [{ name: "id", in: "path", required: true, schema: { type: "string" }, example: "cus_Qk5fG2hJ8mPx3N" }],
            responses: {
              "200": { description: "Customer", content: { "application/json": { schema: { "$ref": "#/components/schemas/Customer" } } } },
              "404": { description: "No such customer" }
            }
          },
          post: {
            summary: "Update a customer", operationId: "updateCustomer", tags: ["Customers"],
            security: [{ BasicAuth: [] }],
            parameters: [{ name: "id", in: "path", required: true, schema: { type: "string" } }],
            requestBody: { required: true, content: { "application/x-www-form-urlencoded": { schema: {
              type: "object",
              properties: { email: { type: "string" }, name: { type: "string" }, description: { type: "string" } }
            }}}},
            responses: { "200": { description: "Updated customer" }, "404": { description: "Not found" } }
          },
          delete: {
            summary: "Delete a customer", operationId: "deleteCustomer", tags: ["Customers"],
            security: [{ BasicAuth: [] }],
            parameters: [{ name: "id", in: "path", required: true, schema: { type: "string" } }],
            responses: {
              "200": { description: "Deleted confirmation", content: { "application/json": { schema: {
                type: "object", properties: { id: { type: "string" }, deleted: { type: "boolean", example: true } }
              }}}},
              "404": { description: "Customer not found" }
            }
          }
        },
        "/charges": {
          get: {
            summary: "List charges", operationId: "listCharges", tags: ["Charges"],
            security: [{ BasicAuth: [] }],
            parameters: [
              { name: "customer", in: "query", schema: { type: "string" }, description: "Filter by customer ID" },
              { name: "limit", in: "query", schema: { type: "integer", default: 10 } }
            ],
            responses: { "200": { description: "Charge list" } }
          },
          post: {
            summary: "Create a charge", operationId: "createCharge", tags: ["Charges"],
            security: [{ BasicAuth: [] }],
            requestBody: { required: true, content: { "application/x-www-form-urlencoded": { schema: {
              type: "object", required: ["amount","currency"],
              properties: {
                amount: { type: "integer", example: 4999, description: "Amount in cents" },
                currency: { type: "string", example: "usd" },
                customer: { type: "string", example: "cus_Qk5fG2hJ8mPx3N" },
                source: { type: "string", example: "tok_visa", description: "Payment method token or ID" },
                description: { type: "string", example: "Pro plan — April 2026" },
                receipt_email: { type: "string", example: "alice@acmecorp.com" }
              }
            }}}},
            responses: {
              "200": { description: "Charge", content: { "application/json": { schema: { "$ref": "#/components/schemas/Charge" } } } },
              "400": { description: "Invalid request" },
              "402": { description: "Card declined" },
              "401": { description: "Invalid API key" }
            }
          }
        },
        "/refunds": {
          post: {
            summary: "Create a refund", operationId: "createRefund", tags: ["Refunds"],
            security: [{ BasicAuth: [] }],
            requestBody: { required: true, content: { "application/x-www-form-urlencoded": { schema: {
              type: "object", required: ["charge"],
              properties: {
                charge: { type: "string", example: "ch_3OxFkP2eZvKYlo2C1QxKvNpA" },
                amount: { type: "integer", example: 2500, description: "Partial refund amount in cents. Omit for full refund." },
                reason: { type: "string", enum: ["duplicate","fraudulent","requested_by_customer"] }
              }
            }}}},
            responses: {
              "200": { description: "Refund", content: { "application/json": { schema: { "$ref": "#/components/schemas/Refund" } } } },
              "400": { description: "Charge already fully refunded" }
            }
          }
        },
        "/subscriptions/{id}": {
          get: {
            summary: "Retrieve a subscription", operationId: "getSubscription", tags: ["Subscriptions"],
            security: [{ BasicAuth: [] }],
            parameters: [{ name: "id", in: "path", required: true, schema: { type: "string" }, example: "sub_1OxFkP2eZvKYlo2CvNpA3Bcd" }],
            responses: {
              "200": { description: "Subscription", content: { "application/json": { schema: { "$ref": "#/components/schemas/Subscription" } } } },
              "404": { description: "Not found" }
            }
          },
          delete: {
            summary: "Cancel a subscription", operationId: "cancelSubscription", tags: ["Subscriptions"],
            security: [{ BasicAuth: [] }],
            parameters: [{ name: "id", in: "path", required: true, schema: { type: "string" } }],
            requestBody: { content: { "application/x-www-form-urlencoded": { schema: {
              type: "object",
              properties: { cancel_at_period_end: { type: "boolean", example: true, description: "If true, cancel at end of billing period instead of immediately" } }
            }}}},
            responses: {
              "200": { description: "Cancelled subscription" },
              "404": { description: "Subscription not found" }
            }
          }
        }
      }
    }
  },

  {
    name: "Slack Messaging API",
    desc: "Post messages, manage channels, look up users",
    tags: ["Slack", "Messaging", "Collaboration"],
    spec: {
      openapi: "3.0.3",
      info: { title: "Slack Web API", version: "1.7.0",
        description: "The Slack Web API lets you build apps that interact with Slack workspaces — post messages, manage channels, react to events, and look up users." },
      servers: [{ url: "https://slack.com/api" }],
      components: {
        securitySchemes: {
          BearerAuth: { type: "http", scheme: "bearer", description: "Slack Bot OAuth token (xoxb-…)" }
        },
        schemas: {
          Channel: {
            type: "object",
            properties: {
              id: { type: "string", example: "C04NRTQVANE" },
              name: { type: "string", example: "general" },
              is_private: { type: "boolean", example: false },
              is_archived: { type: "boolean", example: false },
              topic: { type: "object", properties: { value: { type: "string", example: "Company-wide announcements" } } },
              purpose: { type: "object", properties: { value: { type: "string" } } },
              num_members: { type: "integer", example: 142 },
              created: { type: "integer", example: 1690000000 }
            }
          },
          Message: {
            type: "object",
            properties: {
              ts: { type: "string", example: "1714003200.123456", description: "Timestamp — also used as message ID" },
              text: { type: "string", example: "Deploy to production succeeded :rocket:" },
              user: { type: "string", example: "U04NR8VANEK", description: "User ID of the author" },
              channel: { type: "string", example: "C04NRTQVANE" },
              type: { type: "string", example: "message" },
              thread_ts: { type: "string", nullable: true, description: "Parent message ts if this is a thread reply" },
              blocks: { type: "array", items: { type: "object" }, description: "Rich Block Kit layout" }
            }
          },
          User: {
            type: "object",
            properties: {
              id: { type: "string", example: "U04NR8VANEK" },
              name: { type: "string", example: "alice.chen" },
              real_name: { type: "string", example: "Alice Chen" },
              is_bot: { type: "boolean", example: false },
              is_admin: { type: "boolean", example: false },
              profile: { type: "object", properties: {
                email: { type: "string", example: "alice@acmecorp.com" },
                display_name: { type: "string", example: "Alice" },
                title: { type: "string", example: "Senior Engineer" },
                image_72: { type: "string" }
              }}
            }
          }
        }
      },
      paths: {
        "/chat.postMessage": {
          post: {
            summary: "Post a message", operationId: "chatPostMessage", tags: ["Messaging"],
            security: [{ BearerAuth: [] }],
            requestBody: { required: true, content: { "application/json": { schema: {
              type: "object", required: ["channel"],
              properties: {
                channel: { type: "string", example: "C04NRTQVANE", description: "Channel ID or name" },
                text: { type: "string", example: "Deploy completed successfully :white_check_mark:" },
                thread_ts: { type: "string", description: "Reply to this thread timestamp" },
                blocks: { type: "array", items: { type: "object" }, description: "Block Kit rich message layout" },
                unfurl_links: { type: "boolean", default: true },
                username: { type: "string", description: "Override the bot username" },
                icon_emoji: { type: "string", example: ":robot_face:", description: "Override the bot icon" }
              }
            }}}},
            responses: {
              "200": { description: "Message sent", content: { "application/json": { schema: {
                type: "object",
                properties: {
                  ok: { type: "boolean", example: true },
                  ts: { type: "string", example: "1714003200.123456" },
                  message: { "$ref": "#/components/schemas/Message" }
                }
              }}}},
              "200_error": { description: "Slack always returns HTTP 200 — check `ok: false` for errors" }
            }
          }
        },
        "/conversations.list": {
          get: {
            summary: "List channels", operationId: "conversationsList", tags: ["Channels"],
            security: [{ BearerAuth: [] }],
            parameters: [
              { name: "types", in: "query", schema: { type: "string", default: "public_channel" }, description: "Channel types: public_channel, private_channel, mpim, im" },
              { name: "exclude_archived", in: "query", schema: { type: "boolean", default: true } },
              { name: "limit", in: "query", schema: { type: "integer", default: 100, maximum: 1000 } },
              { name: "cursor", in: "query", schema: { type: "string" }, description: "Pagination cursor from next_cursor" }
            ],
            responses: {
              "200": { description: "Channel list", content: { "application/json": { schema: {
                type: "object",
                properties: {
                  ok: { type: "boolean" },
                  channels: { type: "array", items: { "$ref": "#/components/schemas/Channel" } },
                  response_metadata: { type: "object", properties: { next_cursor: { type: "string" } } }
                }
              }}}}
            }
          }
        },
        "/conversations.history": {
          get: {
            summary: "Get channel message history", operationId: "conversationsHistory", tags: ["Channels"],
            security: [{ BearerAuth: [] }],
            parameters: [
              { name: "channel", in: "query", required: true, schema: { type: "string" }, example: "C04NRTQVANE" },
              { name: "limit", in: "query", schema: { type: "integer", default: 100 } },
              { name: "oldest", in: "query", schema: { type: "string" }, description: "Start of time range (Unix timestamp)" },
              { name: "latest", in: "query", schema: { type: "string" }, description: "End of time range (Unix timestamp)" }
            ],
            responses: {
              "200": { description: "Messages", content: { "application/json": { schema: {
                type: "object",
                properties: {
                  ok: { type: "boolean" },
                  messages: { type: "array", items: { "$ref": "#/components/schemas/Message" } },
                  has_more: { type: "boolean" }
                }
              }}}}
            }
          }
        },
        "/conversations.invite": {
          post: {
            summary: "Invite users to a channel", operationId: "conversationsInvite", tags: ["Channels"],
            security: [{ BearerAuth: [] }],
            requestBody: { required: true, content: { "application/json": { schema: {
              type: "object", required: ["channel","users"],
              properties: {
                channel: { type: "string", example: "C04NRTQVANE" },
                users: { type: "string", example: "U04NR8VANEK,U04NR8VANEM", description: "Comma-separated user IDs" }
              }
            }}}},
            responses: {
              "200": { description: "Invite result", content: { "application/json": { schema: {
                type: "object",
                properties: { ok: { type: "boolean" }, channel: { "$ref": "#/components/schemas/Channel" } }
              }}}}
            }
          }
        },
        "/users.info": {
          get: {
            summary: "Get user info", operationId: "usersInfo", tags: ["Users"],
            security: [{ BearerAuth: [] }],
            parameters: [
              { name: "user", in: "query", required: true, schema: { type: "string" }, example: "U04NR8VANEK", description: "User ID" }
            ],
            responses: {
              "200": { description: "User", content: { "application/json": { schema: {
                type: "object",
                properties: { ok: { type: "boolean" }, user: { "$ref": "#/components/schemas/User" } }
              }}}}
            }
          }
        },
        "/reactions.add": {
          post: {
            summary: "Add a reaction emoji to a message", operationId: "reactionsAdd", tags: ["Messaging"],
            security: [{ BearerAuth: [] }],
            requestBody: { required: true, content: { "application/json": { schema: {
              type: "object", required: ["channel","name","timestamp"],
              properties: {
                channel: { type: "string", example: "C04NRTQVANE" },
                name: { type: "string", example: "thumbsup", description: "Emoji name without colons" },
                timestamp: { type: "string", example: "1714003200.123456", description: "Message ts to react to" }
              }
            }}}},
            responses: {
              "200": { description: "Reaction added", content: { "application/json": { schema: {
                type: "object", properties: { ok: { type: "boolean", example: true } }
              }}}}
            }
          }
        }
      }
    }
  },

  {
    name: "OpenWeather API",
    desc: "Current conditions, forecasts, and air quality by location",
    tags: ["Weather", "Geo", "Public API"],
    spec: {
      openapi: "3.0.3",
      info: { title: "OpenWeather API", version: "2.5",
        description: "Retrieve current weather, 5-day forecasts, and air quality data for any location worldwide. Free tier available with an API key." },
      servers: [{ url: "https://api.openweathermap.org/data/2.5" }],
      components: {
        securitySchemes: {
          ApiKeyQuery: { type: "apiKey", in: "query", name: "appid", description: "Your OpenWeatherMap API key" }
        },
        schemas: {
          CurrentWeather: {
            type: "object",
            properties: {
              coord: { type: "object", properties: { lon: { type: "number", example: -122.4194 }, lat: { type: "number", example: 37.7749 } } },
              weather: { type: "array", items: { type: "object", properties: {
                id: { type: "integer", example: 800 },
                main: { type: "string", example: "Clear" },
                description: { type: "string", example: "clear sky" },
                icon: { type: "string", example: "01d" }
              }}},
              main: { type: "object", properties: {
                temp: { type: "number", example: 18.4, description: "Temperature in °C (or °F if units=imperial)" },
                feels_like: { type: "number", example: 17.8 },
                humidity: { type: "integer", example: 62 },
                pressure: { type: "integer", example: 1013, description: "hPa" },
                temp_min: { type: "number", example: 15.2 },
                temp_max: { type: "number", example: 21.0 }
              }},
              wind: { type: "object", properties: {
                speed: { type: "number", example: 4.1, description: "Wind speed in m/s" },
                deg: { type: "integer", example: 280, description: "Wind direction in degrees" }
              }},
              clouds: { type: "object", properties: { all: { type: "integer", example: 0, description: "Cloudiness %" } } },
              visibility: { type: "integer", example: 10000, description: "Visibility in metres, max 10000" },
              name: { type: "string", example: "San Francisco" },
              dt: { type: "integer", example: 1714003200, description: "Unix UTC timestamp of measurement" },
              sys: { type: "object", properties: {
                country: { type: "string", example: "US" },
                sunrise: { type: "integer", example: 1713969742 },
                sunset: { type: "integer", example: 1714017621 }
              }}
            }
          },
          Forecast: {
            type: "object",
            properties: {
              cnt: { type: "integer", example: 40, description: "Number of 3-hour forecast entries" },
              list: { type: "array", items: { type: "object", properties: {
                dt: { type: "integer", description: "Unix UTC timestamp" },
                main: { type: "object" },
                weather: { type: "array", items: { type: "object" } },
                wind: { type: "object" },
                dt_txt: { type: "string", example: "2026-04-23 15:00:00" }
              }}},
              city: { type: "object", properties: {
                name: { type: "string", example: "San Francisco" },
                country: { type: "string", example: "US" },
                coord: { type: "object", properties: { lat: { type: "number" }, lon: { type: "number" } } }
              }}
            }
          },
          AirQuality: {
            type: "object",
            properties: {
              list: { type: "array", items: { type: "object", properties: {
                main: { type: "object", properties: { aqi: { type: "integer", example: 2,
                  description: "Air Quality Index: 1=Good, 2=Fair, 3=Moderate, 4=Poor, 5=Very Poor" } } },
                components: { type: "object", properties: {
                  co: { type: "number", example: 203.6, description: "CO μg/m³" },
                  no2: { type: "number", example: 2.3, description: "NO₂ μg/m³" },
                  o3: { type: "number", example: 68.7, description: "O₃ μg/m³" },
                  pm2_5: { type: "number", example: 3.7, description: "PM2.5 μg/m³" },
                  pm10: { type: "number", example: 6.2, description: "PM10 μg/m³" }
                }},
                dt: { type: "integer" }
              }}}
            }
          }
        }
      },
      paths: {
        "/weather": {
          get: {
            summary: "Current weather", operationId: "getCurrentWeather", tags: ["Weather"],
            security: [{ ApiKeyQuery: [] }],
            description: "Returns current weather conditions for a city name, zip code, or coordinates.",
            parameters: [
              { name: "q", in: "query", schema: { type: "string" }, example: "San Francisco,US", description: "City name, optionally with country code: 'London,GB'" },
              { name: "lat", in: "query", schema: { type: "number" }, example: 37.7749, description: "Latitude (use with lon)" },
              { name: "lon", in: "query", schema: { type: "number" }, example: -122.4194, description: "Longitude (use with lat)" },
              { name: "zip", in: "query", schema: { type: "string" }, example: "94105,US", description: "ZIP/postal code with country" },
              { name: "units", in: "query", schema: { type: "string", enum: ["standard","metric","imperial"], default: "metric" }, description: "metric=°C, imperial=°F, standard=Kelvin" },
              { name: "lang", in: "query", schema: { type: "string", default: "en" }, description: "Language for description text" }
            ],
            responses: {
              "200": { description: "Current weather data", content: { "application/json": { schema: { "$ref": "#/components/schemas/CurrentWeather" } } } },
              "401": { description: "Invalid or missing API key" },
              "404": { description: "City not found" },
              "429": { description: "Rate limit exceeded" }
            }
          }
        },
        "/forecast": {
          get: {
            summary: "5-day / 3-hour forecast", operationId: "getForecast", tags: ["Forecast"],
            security: [{ ApiKeyQuery: [] }],
            description: "Returns a 5-day forecast in 3-hour intervals (40 data points total).",
            parameters: [
              { name: "q", in: "query", schema: { type: "string" }, example: "Tokyo,JP" },
              { name: "lat", in: "query", schema: { type: "number" } },
              { name: "lon", in: "query", schema: { type: "number" } },
              { name: "units", in: "query", schema: { type: "string", enum: ["standard","metric","imperial"], default: "metric" } },
              { name: "cnt", in: "query", schema: { type: "integer", maximum: 40 }, description: "Limit number of forecast entries returned" }
            ],
            responses: {
              "200": { description: "Forecast data", content: { "application/json": { schema: { "$ref": "#/components/schemas/Forecast" } } } },
              "401": { description: "Invalid API key" },
              "404": { description: "Location not found" }
            }
          }
        },
        "/air_pollution": {
          get: {
            summary: "Current air quality", operationId: "getAirQuality", tags: ["Air Quality"],
            security: [{ ApiKeyQuery: [] }],
            description: "Returns current air quality index and pollutant concentrations for given coordinates.",
            parameters: [
              { name: "lat", in: "query", required: true, schema: { type: "number" }, example: 37.7749 },
              { name: "lon", in: "query", required: true, schema: { type: "number" }, example: -122.4194 }
            ],
            responses: {
              "200": { description: "Air quality data", content: { "application/json": { schema: { "$ref": "#/components/schemas/AirQuality" } } } },
              "401": { description: "Invalid API key" }
            }
          }
        },
        "/air_pollution/forecast": {
          get: {
            summary: "Air quality forecast", operationId: "getAirQualityForecast", tags: ["Air Quality"],
            security: [{ ApiKeyQuery: [] }],
            description: "Returns hourly air quality forecast for up to 4 days ahead.",
            parameters: [
              { name: "lat", in: "query", required: true, schema: { type: "number" } },
              { name: "lon", in: "query", required: true, schema: { type: "number" } }
            ],
            responses: {
              "200": { description: "Forecast air quality data" },
              "401": { description: "Invalid API key" }
            }
          }
        }
      }
    }
  }
]

// ── State ──────────────────────────────────────────────────────────────────

let _loadedSampleIdx = -1
let _hasMessages = false
let _lastDocsMarkdown = ''

// ── Tab switching ──────────────────────────────────────────────────────────

function switchTab(name) {
  document.querySelectorAll('.tab').forEach((t, i) => {
    const panels = ['samples','upload','url']
    t.classList.toggle('active', panels[i] === name)
  })
  document.querySelectorAll('.tab-panel').forEach(p => {
    p.classList.toggle('active', p.id === 'tab-' + name)
  })
}

// ── Render sample cards ────────────────────────────────────────────────────

function renderSamples() {
  const grid = document.getElementById('sampleGrid')
  grid.innerHTML = ''
  SAMPLES.forEach((s, i) => {
    const card = document.createElement('div')
    card.className = 'sample-card' + (_loadedSampleIdx === i ? ' loaded' : '')
    card.id = 'sample-' + i
    card.onclick = () => loadSample(i)
    card.innerHTML = `
      <div class="sample-name">${esc(s.name)}</div>
      <div class="sample-desc">${esc(s.desc)}</div>
      <div>${s.tags.map(t => `<span class="sample-tag">${esc(t)}</span>`).join('')}</div>`
    grid.appendChild(card)
  })
}

// ── Load spec ──────────────────────────────────────────────────────────────

async function loadSample(idx) {
  const s = SAMPLES[idx]
  await loadSpecRaw(JSON.stringify(s.spec))
  _loadedSampleIdx = idx
  renderSamples()
}

async function loadFromUrl() {
  const url = document.getElementById('specUrl').value.trim()
  if (!url) return
  try {
    const r = await fetch('/load-spec-url', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url })
    })
    const d = await r.json()
    if (d.error) { showToast(d.error, 'error'); return }
    await refreshSpecInfo()
    showToast(`Loaded: ${d.title}`)
  } catch(e) {
    showToast('Failed: ' + e.message, 'error')
  }
}

async function handleFileInput(input) {
  const file = input.files[0]
  if (!file) return
  const raw = await file.text()
  await loadSpecRaw(raw)
}

function handleDrop(e) {
  e.preventDefault()
  document.getElementById('dropZone').classList.remove('drag')
  const file = e.dataTransfer.files[0]
  if (!file) return
  const reader = new FileReader()
  reader.onload = ev => loadSpecRaw(ev.target.result)
  reader.readAsText(file)
}

async function loadSpecRaw(raw) {
  try {
    const r = await fetch('/load-spec', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ raw })
    })
    const d = await r.json()
    if (d.error) { showToast(d.error, 'error'); return }
    await refreshSpecInfo()
    showToast(`Loaded: ${d.title}`)
  } catch(e) {
    showToast('Failed to load spec', 'error')
  }
}

async function refreshSpecInfo() {
  const r = await fetch('/spec-info')
  const d = await r.json()
  if (!d.loaded) return
  document.getElementById('specInfo').classList.add('visible')
  document.getElementById('infoTitle').textContent = d.title
  document.getElementById('infoVersion').textContent = d.version || '—'
  document.getElementById('infoCount').textContent = d.endpoint_count + ' endpoints'
  document.getElementById('infoUrl').textContent = d.base_url
  const badge = document.getElementById('specBadge')
  badge.classList.add('visible')
  document.getElementById('specBadgeText').textContent = d.title
  // Update starter chips to suggest using this spec
  const chips = document.getElementById('starterChips')
  if (chips) {
    chips.innerHTML = `
      <span class="chip" onclick="ask('Document all endpoints in this API')">Document all endpoints</span>
      <span class="chip" onclick="ask('Show me the authentication details and how to get started')">Authentication & setup</span>
      <span class="chip" onclick="ask('Document the GET endpoints with example responses')">GET endpoints with examples</span>
      <span class="chip" onclick="ask('Document the POST and PUT endpoints with example request bodies')">POST/PUT with request bodies</span>
      <span class="chip" onclick="ask('Generate a quick-start guide for a new developer')">Quick-start guide</span>
      <span class="chip" onclick="ask('List all endpoints with a one-line description of each')">Endpoint overview table</span>`
  }
}

// ── Chat ───────────────────────────────────────────────────────────────────

async function ask(question) {
  const inp = document.getElementById('chatInput')
  const btn = document.getElementById('sendBtn')
  const thread = document.getElementById('chatThread')
  const q = question || inp.value.trim()
  if (!q) return
  inp.value = ''
  inp.style.height = 'auto'

  const welcome = document.getElementById('welcomeScreen')
  if (welcome) welcome.remove()
  document.getElementById('refineChips').style.display = 'flex'
  _hasMessages = true

  const userEl = document.createElement('div')
  userEl.className = 'msg msg-user'
  userEl.textContent = q
  thread.appendChild(userEl)

  const thinkEl = document.createElement('div')
  thinkEl.className = 'msg msg-thinking'
  thinkEl.innerHTML = '<span class="spinner">&#10227;</span> Generating docs…'
  thread.appendChild(thinkEl)
  thread.scrollTop = thread.scrollHeight
  btn.disabled = true

  try {
    const r = await fetch('/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: q })
    })
    if (!r.ok) {
      const e = await r.json()
      throw new Error(e.error || r.statusText)
    }
    const data = await r.json()
    thinkEl.remove()

    const agentEl = document.createElement('div')
    agentEl.className = 'msg msg-agent'
    agentEl.innerHTML = renderMd(data.answer)
    thread.appendChild(agentEl)
    thread.scrollTop = thread.scrollHeight

    // Mirror long docs responses into the pinned panel
    if (data.answer.length > 400) {
      _lastDocsMarkdown = data.answer
      showDocsPanel(data.answer)
    }
  } catch(err) {
    thinkEl.remove()
    const errEl = document.createElement('div')
    errEl.className = 'msg msg-agent'
    errEl.innerHTML = '<span style="color:#f87171">Error: ' + esc(err.message) + '</span>'
    thread.appendChild(errEl)
  } finally {
    btn.disabled = false
  }
}

// ── Docs panel ─────────────────────────────────────────────────────────────

function showDocsPanel(markdown) {
  const panel = document.getElementById('docsPanel')
  const content = document.getElementById('docsContent')
  panel.classList.add('visible')
  content.innerHTML = renderMd(markdown)
}

function copyDocs() {
  if (!_lastDocsMarkdown) return
  navigator.clipboard.writeText(_lastDocsMarkdown).then(() => {
    const btn = document.querySelector('.copy-docs-btn')
    const orig = btn.textContent
    btn.textContent = 'Copied!'
    setTimeout(() => btn.textContent = orig, 1500)
  })
}

// ── Session reset ──────────────────────────────────────────────────────────

async function resetSession() {
  await fetch('/reset', { method: 'POST' })
  _hasMessages = false
  _lastDocsMarkdown = ''
  document.getElementById('docsPanel').classList.remove('visible')
  document.getElementById('docsContent').innerHTML = ''
  document.getElementById('refineChips').style.display = 'none'
  document.getElementById('chatThread').innerHTML = `
    <div class="welcome" id="welcomeScreen">
      <h2>Session cleared</h2>
      <p style="color:#4a4a60;font-size:13px">The spec is still loaded. Ask the agent to generate docs.</p>
      <div class="chips" id="starterChips">
        <span class="chip" onclick="ask('Document all endpoints in this API')">Document all endpoints</span>
        <span class="chip" onclick="ask('Show me the authentication details and how to get started')">Authentication & setup</span>
        <span class="chip" onclick="ask('Generate a quick-start guide for a new developer')">Quick-start guide</span>
      </div>
    </div>`
}

// ── Markdown renderer ──────────────────────────────────────────────────────

function renderMd(text) {
  let html = text
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')

  // Fenced code blocks
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) =>
    `<pre><code class="lang-${lang}">${code.replace(/&amp;/g,'&').replace(/&lt;/g,'<').replace(/&gt;/g,'>')}</code></pre>`)

  // Headings
  html = html.replace(/^#### (.+)$/gm, '<h4>$1</h4>')
  html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>')
  html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>')
  html = html.replace(/^# (.+)$/gm, '<h2>$1</h2>')

  // HR
  html = html.replace(/^---+$/gm, '<hr>')

  // Bold / inline code
  html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
  html = html.replace(/`([^`\n]+)`/g, '<code>$1</code>')

  // Tables
  html = html.replace(/((\|.+\|\n)+)/g, block => {
    const rows = block.trim().split('\n')
    let out = '<table>'
    rows.forEach((row, i) => {
      if (/^\|[-| :]+\|$/.test(row.trim())) return
      const cells = row.split('|').filter((_, ci) => ci > 0 && ci < row.split('|').length - 1)
      const tag = i === 0 ? 'th' : 'td'
      out += '<tr>' + cells.map(c => `<${tag}>${c.trim()}</${tag}>`).join('') + '</tr>'
    })
    return out + '</table>'
  })

  // Lists
  html = html.replace(/^- (.+)$/gm, '<li>$1</li>')
  html = html.replace(/(<li>.*<\/li>\n?)+/g, m => '<ul>' + m + '</ul>')

  // Paragraphs — lines not already wrapped
  html = html.replace(/^(?!<[a-z]|$)(.+)$/gm, '<p>$1</p>')

  // Clean up double-escaped HTML inside pre blocks
  return html
}

function esc(s) {
  return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
}

// ── Toast ──────────────────────────────────────────────────────────────────

function showToast(msg, type) {
  const t = document.getElementById('toast')
  t.textContent = msg
  t.style.background = type === 'error' ? '#dc2626' : '#10b981'
  t.classList.add('show')
  setTimeout(() => t.classList.remove('show'), 2800)
}

// ── Init ───────────────────────────────────────────────────────────────────

async function init() {
  renderSamples()
  await refreshSpecInfo().catch(() => {})

  try {
    const convo = await fetch('/conversation').then(r => r.json())
    if (convo && convo.length > 0) {
      document.getElementById('welcomeScreen')?.remove()
      document.getElementById('refineChips').style.display = 'flex'
      _hasMessages = true
      const thread = document.getElementById('chatThread')
      for (const msg of convo) {
        const el = document.createElement('div')
        if (msg.role === 'user') {
          el.className = 'msg msg-user'
          el.textContent = msg.text
        } else {
          el.className = 'msg msg-agent'
          el.innerHTML = renderMd(msg.text)
          if (msg.text.length > 400) {
            _lastDocsMarkdown = msg.text
            showDocsPanel(msg.text)
          }
        }
        thread.appendChild(el)
      }
      thread.scrollTop = thread.scrollHeight
    }
  } catch(e) {}
}

init()
</script>
</body>
</html>"""
