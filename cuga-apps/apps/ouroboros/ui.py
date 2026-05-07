"""
HTML UI for the Ouroboros demo app — exported as _HTML and served at GET /.

Layout:
  Left  — Chat panel: prompt chips, message log, input
  Right — Lead board: location header + ranked business cards + next steps
"""

_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>Ouroboros — CUGA finds its next client</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;600&display=swap');

  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg:        #07080c;
    --bg-soft:   #0c0e15;
    --card:      #11131d;
    --card2:     #171a26;
    --card3:     #1d2030;
    --border:    #232739;
    --border-strong: #2e3349;
    --accent:    #34d399;   /* emerald — money */
    --accent-glow: rgba(52,211,153,0.45);
    --accent2:   #a78bfa;   /* violet — agentic */
    --accent2-glow: rgba(167,139,250,0.45);
    --accent3:   #fbbf24;   /* warm gold — top picks */
    --accent3-glow: rgba(251,191,36,0.45);
    --text:      #ecf0fa;
    --text-soft: #c4cbdc;
    --muted:     #7c8499;
    --muted-2:   #5b6378;
    --danger:    #f87171;
    --success:   #4ade80;

    --shadow-sm: 0 1px 2px rgba(0,0,0,0.4);
    --shadow-md: 0 4px 20px rgba(0,0,0,0.35), 0 1px 2px rgba(0,0,0,0.4);
    --shadow-lg: 0 18px 48px rgba(0,0,0,0.5), 0 2px 6px rgba(0,0,0,0.4);
    --shadow-glow-emerald: 0 0 0 1px rgba(52,211,153,0.18), 0 8px 32px rgba(52,211,153,0.12);
    --shadow-glow-gold:    0 0 0 1px rgba(251,191,36,0.30), 0 10px 36px rgba(251,191,36,0.14);
  }

  html, body { height: 100%; }

  body {
    /* Layered background:
       1. subtle dot-grid texture
       2-4. soft color glows (violet top-right, emerald bottom-left, gold center)
       5. base color */
    background-image:
      radial-gradient(rgba(255,255,255,0.022) 1px, transparent 1px),
      radial-gradient(1100px 620px at 82% -8%, rgba(167,139,250,0.14), transparent 62%),
      radial-gradient(900px 520px at -4% 108%, rgba(52,211,153,0.10), transparent 60%),
      radial-gradient(700px 420px at 50% 50%, rgba(251,191,36,0.04), transparent 70%);
    background-size: 28px 28px, auto, auto, auto;
    background-color: var(--bg);
    background-attachment: fixed;
    color: var(--text);
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    font-size: 14px;
    font-feature-settings: 'cv11', 'ss01', 'ss03';
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
    text-rendering: optimizeLegibility;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    letter-spacing: -0.005em;
  }

  ::selection { background: rgba(52,211,153,0.28); color: #fff; }

  header {
    position: sticky; top: 0; z-index: 100;
    background: linear-gradient(180deg, rgba(13,15,22,0.85), rgba(13,15,22,0.65));
    backdrop-filter: saturate(160%) blur(14px);
    -webkit-backdrop-filter: saturate(160%) blur(14px);
    border-bottom: 1px solid var(--border);
    padding: 12px 24px;
    display: flex; align-items: center; gap: 14px;
    box-shadow: 0 1px 0 rgba(255,255,255,0.02) inset, 0 6px 24px rgba(0,0,0,0.25);
  }
  .logo {
    width: 32px; height: 32px; border-radius: 10px;
    background: conic-gradient(from 90deg, var(--accent), var(--accent2), var(--accent3), var(--accent));
    display: grid; place-items: center; color: #07080c;
    font-weight: 900; font-size: 18px; letter-spacing: -1px;
    box-shadow:
      0 0 0 1px rgba(255,255,255,0.06),
      0 6px 18px rgba(167,139,250,0.30),
      0 2px 6px rgba(52,211,153,0.18);
    animation: spin-slow 18s linear infinite;
  }
  @keyframes spin-slow { to { transform: rotate(360deg); } }

  header h1 {
    font-size: 18px; font-weight: 800; letter-spacing: -0.02em;
    background: linear-gradient(180deg, #ffffff 0%, #c8d0e3 100%);
    -webkit-background-clip: text; background-clip: text;
    -webkit-text-fill-color: transparent;
  }
  header h1 span {
    background: linear-gradient(135deg, var(--accent) 0%, var(--accent2) 100%);
    -webkit-background-clip: text; background-clip: text;
    -webkit-text-fill-color: transparent;
  }
  header .tag {
    font-size: 11px; color: var(--muted); font-weight: 500;
    border-left: 1px solid var(--border);
    padding-left: 14px; margin-left: 6px;
    letter-spacing: 0.01em;
  }
  .status-badge {
    display: inline-flex; align-items: center; gap: 8px;
    font-size: 11.5px; color: var(--muted); margin-left: auto;
    background: rgba(255,255,255,0.02);
    border: 1px solid var(--border);
    padding: 5px 11px 5px 9px; border-radius: 999px;
    font-weight: 500; letter-spacing: 0.01em;
  }
  .status-dot {
    width: 8px; height: 8px; border-radius: 50%;
    background: var(--success);
    box-shadow: 0 0 0 3px rgba(74,222,128,0.18), 0 0 8px rgba(74,222,128,0.6);
    animation: pulse 2.4s ease-in-out infinite;
  }
  .status-dot.busy {
    background: var(--accent2);
    box-shadow: 0 0 0 3px rgba(167,139,250,0.22), 0 0 10px rgba(167,139,250,0.7);
    animation: pulse 1.2s ease-in-out infinite;
  }
  @keyframes pulse {
    0%, 100% { opacity: 1; transform: scale(1); }
    50%      { opacity: 0.55; transform: scale(0.85); }
  }

  /* Reusable header pill-buttons (replace old inline-styled ones) */
  .header-pill {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 6px 13px; border-radius: 999px;
    background: rgba(255,255,255,0.025);
    border: 1px solid var(--border);
    color: var(--text-soft);
    font-size: 12px; font-weight: 600; letter-spacing: 0.01em;
    text-decoration: none; cursor: pointer;
    transition: border-color 0.18s, color 0.18s, background 0.18s, transform 0.18s;
  }
  .header-pill:hover {
    color: var(--text);
    border-color: var(--border-strong);
    background: rgba(255,255,255,0.05);
    transform: translateY(-1px);
  }

  main {
    display: grid;
    grid-template-columns: 460px 1fr;
    gap: 0; flex: 1; overflow: hidden;
    height: calc(100vh - 65px);
  }

  /* Chat panel */
  .chat-panel {
    background: linear-gradient(180deg, var(--card) 0%, var(--bg-soft) 100%);
    border-right: 1px solid var(--border);
    display: flex; flex-direction: column; overflow: hidden;
  }
  .panel-title {
    padding: 14px 20px; font-size: 10.5px; font-weight: 700;
    text-transform: uppercase; letter-spacing: 1.4px;
    color: var(--muted); border-bottom: 1px solid var(--border);
    display: flex; align-items: center; gap: 8px;
    background: rgba(255,255,255,0.012);
  }
  .panel-title .runs-btn {
    margin-left: auto;
    background: rgba(255,255,255,0.025);
    border: 1px solid var(--border); color: var(--muted);
    border-radius: 999px; padding: 4px 11px; font-size: 10px;
    text-transform: uppercase; letter-spacing: 1px;
    cursor: pointer; font-weight: 700;
    transition: color 0.18s, border-color 0.18s, background 0.18s;
  }
  .panel-title .runs-btn:hover {
    color: var(--accent); border-color: rgba(52,211,153,0.55);
    background: rgba(52,211,153,0.06);
  }

  .runs-drawer {
    position: absolute; right: 14px; top: 60px; z-index: 25;
    width: 400px; max-height: 70vh; overflow-y: auto;
    background: linear-gradient(180deg, var(--card2), var(--card));
    border: 1px solid var(--border-strong);
    border-radius: 14px;
    box-shadow: var(--shadow-lg);
    display: none;
    backdrop-filter: blur(14px);
    animation: drawer-in 0.18s ease-out;
  }
  @keyframes drawer-in {
    from { opacity: 0; transform: translateY(-6px); }
    to   { opacity: 1; transform: translateY(0); }
  }
  .runs-drawer.open { display: block; }
  .runs-drawer .head {
    padding: 13px 16px; font-size: 10.5px; font-weight: 700;
    text-transform: uppercase; letter-spacing: 1.4px;
    color: var(--muted); border-bottom: 1px solid var(--border);
    display: flex; align-items: center; gap: 8px;
    position: sticky; top: 0;
    background: linear-gradient(180deg, var(--card2), rgba(23,26,38,0.96));
    backdrop-filter: blur(10px);
  }
  .runs-drawer .empty { padding: 20px; color: var(--muted); font-size: 12px; line-height: 1.6; }
  .run-item {
    padding: 13px 16px; border-bottom: 1px solid var(--border);
    cursor: pointer; transition: background 0.15s, border-left-color 0.15s;
    border-left: 3px solid transparent;
  }
  .run-item:hover { background: rgba(255,255,255,0.025); border-left-color: var(--accent); }
  /* Loop-fired runs get a colored left edge so they're scannable in the list */
  .run-item.run-item-loop {
    border-left-color: var(--accent2);
    background: rgba(167,139,250,0.05);
  }
  .run-item.run-item-loop:hover { background: rgba(167,139,250,0.10); }
  .src-badge {
    font-size: 10px; font-weight: 700; padding: 2px 8px;
    border-radius: 999px; text-decoration: none;
    display: inline-flex; align-items: center; gap: 4px;
    letter-spacing: 0.02em;
  }
  .src-badge.src-user {
    background: rgba(148,163,184,0.10); color: #a8b2c5;
    border: 1px solid rgba(148,163,184,0.25);
  }
  .src-badge.src-loop {
    background: rgba(167,139,250,0.18); color: #c4b5fd;
    border: 1px solid rgba(167,139,250,0.45);
    box-shadow: 0 0 0 0 rgba(167,139,250,0.35);
    transition: box-shadow 0.18s, background 0.18s;
  }
  .src-badge.src-loop:hover {
    background: rgba(167,139,250,0.28);
    box-shadow: 0 0 14px -4px rgba(167,139,250,0.55);
  }
  .run-item .row {
    display: flex; align-items: center; gap: 8px; margin-bottom: 6px;
  }
  .run-item .ts {
    font-size: 11px; color: var(--accent2); font-weight: 700;
    font-family: 'JetBrains Mono', ui-monospace, monospace;
    letter-spacing: -0.01em;
  }
  .run-item .elapsed {
    font-size: 10px; color: var(--accent3); font-weight: 600;
    background: rgba(251,191,36,0.10); padding: 2px 7px; border-radius: 999px;
    border: 1px solid rgba(251,191,36,0.22);
  }
  .run-item .leads-pill {
    font-size: 10px; color: var(--accent); font-weight: 700;
    margin-left: auto; letter-spacing: 0.01em;
  }
  .run-item .question {
    font-size: 13px; color: var(--text); line-height: 1.45;
    overflow: hidden; text-overflow: ellipsis;
    display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
  }
  .run-item .trace-row {
    display: flex; flex-wrap: wrap; gap: 5px; margin-top: 8px;
  }
  .agent-pill {
    background: rgba(255,255,255,0.025);
    border: 1px solid var(--border);
    border-radius: 999px; padding: 2px 9px; font-size: 10px;
    color: var(--accent2); font-weight: 600;
    font-family: 'JetBrains Mono', ui-monospace, monospace;
    letter-spacing: 0.01em;
  }
  .agent-pill.scout      { color: var(--accent);  border-color: rgba(52,211,153,0.40); background: rgba(52,211,153,0.06); }
  .agent-pill.writer     { color: var(--accent3); border-color: rgba(251,191,36,0.40); background: rgba(251,191,36,0.06); }
  .agent-pill.no-output  { opacity: 0.45; text-decoration: line-through; }

  .trace-modal-backdrop {
    position: fixed; inset: 0;
    background: rgba(7,8,12,0.72);
    backdrop-filter: blur(6px);
    display: none; z-index: 50; align-items: center; justify-content: center;
    animation: fade-in 0.18s ease-out;
  }
  @keyframes fade-in { from { opacity: 0; } to { opacity: 1; } }
  .trace-modal-backdrop.open { display: flex; }
  .trace-modal {
    background: linear-gradient(180deg, var(--card2), var(--card));
    border: 1px solid var(--border-strong);
    border-radius: 16px; width: min(720px, 92vw); max-height: 85vh;
    display: flex; flex-direction: column; overflow: hidden;
    box-shadow: var(--shadow-lg);
    animation: pop-in 0.22s cubic-bezier(0.16,1,0.3,1);
  }
  @keyframes pop-in {
    from { opacity: 0; transform: scale(0.96) translateY(8px); }
    to   { opacity: 1; transform: scale(1) translateY(0); }
  }
  .trace-modal-head {
    padding: 16px 20px; border-bottom: 1px solid var(--border);
    display: flex; align-items: center; gap: 10px;
    background: rgba(255,255,255,0.012);
  }
  .trace-modal-head h3 {
    margin: 0; font-size: 14px; color: var(--text); font-weight: 700;
    letter-spacing: -0.01em;
  }
  .trace-modal-body {
    flex: 1; overflow-y: auto; padding: 16px 20px;
  }
  .trace-step {
    display: flex; align-items: flex-start; gap: 12px;
    padding: 11px 0; border-bottom: 1px dashed var(--border);
    font-size: 12px;
  }
  .trace-step:last-child { border-bottom: none; }
  .trace-step .num {
    color: var(--muted); font-variant-numeric: tabular-nums;
    min-width: 28px; text-align: right; font-weight: 700;
    font-family: 'JetBrains Mono', ui-monospace, monospace;
  }
  .trace-step .agent {
    color: var(--accent); font-weight: 700;
    min-width: 140px;
    font-family: 'JetBrains Mono', ui-monospace, monospace;
    font-size: 11.5px; letter-spacing: -0.01em;
  }
  .trace-step .preview {
    color: var(--text-soft); flex: 1; white-space: pre-wrap;
    overflow-wrap: anywhere; line-height: 1.55;
    max-height: 4.6em; overflow: hidden; text-overflow: ellipsis;
  }
  .trace-step .badge {
    background: rgba(248,113,113,0.12); border: 1px solid var(--danger);
    color: var(--danger); padding: 1px 9px; border-radius: 999px;
    font-size: 10px; font-weight: 700; letter-spacing: 0.02em;
  }

  .msg .meta {
    display: block; margin-top: 6px;
    font-size: 10px; color: var(--muted); opacity: 0.75;
    text-transform: uppercase; letter-spacing: 1px;
    font-weight: 600;
  }
  /* Inline "schedule this as a recurring loop" affordance under user
     messages. Discreet on purpose — afterthought, not the main action. */
  .msg .sched {
    display: flex; align-items: center; gap: 6px;
    margin-top: 8px; padding-top: 6px;
    border-top: 1px dashed rgba(0,0,0,0.18);
    font-size: 11px; opacity: 0.75; transition: opacity 0.15s;
  }
  .msg.user:hover .sched { opacity: 1; }
  .msg .sched-label { font-weight: 600; }
  .msg .sched select, .msg .sched button {
    background: rgba(0,0,0,0.15); color: inherit;
    border: 1px solid rgba(0,0,0,0.25);
    border-radius: 4px; padding: 1px 6px; font: inherit; font-size: 11px;
    cursor: pointer;
  }
  .msg .sched button:hover { background: rgba(0,0,0,0.28); }
  .msg .sched.done {
    color: #07201a; font-weight: 600;
    border-top-color: rgba(0,0,0,0.25);
  }
  .msg .sched.err  { color: #7a1f1f; }
  .msg .sched a {
    color: #1e3a8a; text-decoration: underline; cursor: pointer;
  }
  .chips {
    display: flex; flex-wrap: wrap; gap: 6px;
    padding: 12px 16px; border-bottom: 1px solid var(--border);
    background: rgba(255,255,255,0.008);
  }
  .chip {
    background: rgba(255,255,255,0.025);
    border: 1px solid var(--border);
    border-radius: 999px; padding: 6px 12px;
    font-size: 11.5px; color: var(--muted); cursor: pointer;
    transition: color 0.18s, border-color 0.18s, background 0.18s, transform 0.18s;
    white-space: nowrap; font-weight: 500;
  }
  .chip:hover {
    border-color: rgba(52,211,153,0.55);
    color: var(--text);
    background: rgba(52,211,153,0.07);
    transform: translateY(-1px);
  }

  .messages {
    flex: 1; overflow-y: auto; padding: 18px 16px;
    display: flex; flex-direction: column; gap: 12px;
    scrollbar-width: thin;
    scrollbar-color: var(--border) transparent;
  }
  .messages::-webkit-scrollbar { width: 6px; }
  .messages::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
  .messages::-webkit-scrollbar-thumb:hover { background: var(--border-strong); }

  .msg {
    max-width: 92%; padding: 11px 15px; border-radius: 14px;
    line-height: 1.65; white-space: pre-wrap;
    word-break: break-word; font-size: 13px;
    animation: msg-in 0.22s cubic-bezier(0.16,1,0.3,1);
  }
  @keyframes msg-in {
    from { opacity: 0; transform: translateY(6px); }
    to   { opacity: 1; transform: translateY(0); }
  }
  .msg.user {
    background: linear-gradient(135deg, var(--accent) 0%, #2bbd87 100%);
    color: #042118;
    align-self: flex-end; border-bottom-right-radius: 4px;
    font-weight: 600;
    box-shadow: 0 8px 24px -6px rgba(52,211,153,0.45),
                0 1px 0 rgba(255,255,255,0.18) inset;
  }
  .msg.agent {
    background: rgba(255,255,255,0.02);
    border: 1px solid var(--border);
    align-self: flex-start; border-bottom-left-radius: 4px;
    color: var(--text-soft);
    box-shadow: var(--shadow-sm);
  }
  .msg.error {
    background: rgba(248,113,113,0.10); border: 1px solid var(--danger);
    color: var(--danger); align-self: flex-start;
  }
  .msg.thinking {
    color: var(--muted); font-style: italic;
    border: 1px dashed var(--border-strong);
    background: rgba(255,255,255,0.012);
    align-self: flex-start;
    position: relative;
  }
  .msg.thinking::after {
    content: '';
    display: inline-block;
    width: 4px; height: 4px; margin-left: 4px;
    border-radius: 50%; background: var(--accent2);
    animation: thinking-blink 1.4s infinite;
    vertical-align: middle;
  }
  @keyframes thinking-blink {
    0%, 100% { opacity: 0.3; transform: scale(0.85); }
    50%      { opacity: 1;   transform: scale(1.1); }
  }

  .input-row {
    display: flex; gap: 8px;
    padding: 14px 16px;
    border-top: 1px solid var(--border);
    background: linear-gradient(180deg, transparent, rgba(0,0,0,0.18));
  }
  .input-row input {
    flex: 1; background: var(--bg-soft);
    border: 1px solid var(--border);
    border-radius: 12px; padding: 11px 16px; color: var(--text);
    font-size: 14px; outline: none;
    font-family: inherit; font-weight: 500;
    transition: border-color 0.18s, box-shadow 0.18s, background 0.18s;
  }
  .input-row input:focus {
    border-color: rgba(52,211,153,0.55);
    background: rgba(52,211,153,0.04);
    box-shadow: 0 0 0 4px rgba(52,211,153,0.10);
  }
  .input-row input::placeholder { color: var(--muted-2); }

  .btn {
    background: linear-gradient(135deg, var(--accent) 0%, #2bbd87 100%);
    color: #042118; border: none;
    border-radius: 12px; padding: 11px 20px;
    font-size: 13px; font-weight: 700;
    letter-spacing: -0.005em;
    cursor: pointer;
    transition: transform 0.15s, box-shadow 0.18s, opacity 0.15s;
    box-shadow: 0 6px 18px -4px rgba(52,211,153,0.55),
                0 1px 0 rgba(255,255,255,0.20) inset;
  }
  .btn:hover {
    transform: translateY(-1px);
    box-shadow: 0 10px 24px -6px rgba(52,211,153,0.65),
                0 1px 0 rgba(255,255,255,0.28) inset;
  }
  .btn:active { transform: translateY(0); }
  .btn:disabled {
    opacity: 0.4; cursor: not-allowed; transform: none;
    box-shadow: none;
  }
  .btn-secondary {
    background: rgba(255,255,255,0.03);
    color: var(--text);
    border: 1px solid var(--border);
    font-weight: 600;
    box-shadow: none;
  }
  .btn-secondary:hover {
    background: rgba(255,255,255,0.06);
    border-color: var(--border-strong);
    box-shadow: none;
  }
  .input-cadence {
    background: var(--bg-soft); color: var(--text);
    border: 1px solid var(--border); border-radius: 12px;
    padding: 11px 10px; font-size: 12.5px;
    outline: none; cursor: pointer;
    font-family: inherit; font-weight: 500;
    transition: border-color 0.18s;
  }
  .input-cadence:focus { border-color: var(--accent); }

  /* Right data panel */
  .data-panel { display: flex; flex-direction: column; overflow: hidden; }
  .data-panel-header {
    padding: 14px 26px; font-size: 10.5px; font-weight: 700;
    text-transform: uppercase; letter-spacing: 1.4px;
    color: var(--muted); border-bottom: 1px solid var(--border);
    display: flex; align-items: center; gap: 10px;
    background: rgba(255,255,255,0.012);
  }
  .refresh-badge {
    margin-left: auto; font-size: 11px; color: var(--muted);
    background: rgba(255,255,255,0.025);
    border: 1px solid var(--border);
    border-radius: 999px; padding: 4px 11px; cursor: pointer;
    text-transform: none; letter-spacing: 0; font-weight: 600;
    transition: color 0.18s, border-color 0.18s, background 0.18s;
    font-family: inherit;
  }
  .refresh-badge:hover {
    color: var(--accent); border-color: rgba(52,211,153,0.55);
    background: rgba(52,211,153,0.06);
  }
  .data-scroll {
    flex: 1; overflow-y: auto; padding: 26px;
    display: flex; flex-direction: column; gap: 20px;
    scrollbar-width: thin;
    scrollbar-color: var(--border) transparent;
  }
  .data-scroll::-webkit-scrollbar { width: 6px; }
  .data-scroll::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
  .data-scroll::-webkit-scrollbar-thumb:hover { background: var(--border-strong); }

  .empty-state {
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    height: 100%; color: var(--muted); gap: 18px;
    text-align: center; padding: 48px 32px;
  }
  .empty-state .icon {
    font-size: 88px; line-height: 1;
    background: linear-gradient(135deg, var(--accent) 0%, var(--accent2) 50%, var(--accent3) 100%);
    -webkit-background-clip: text; background-clip: text;
    -webkit-text-fill-color: transparent;
    filter: drop-shadow(0 8px 28px rgba(167,139,250,0.30));
    animation: spin-slow 16s linear infinite;
    opacity: 0.85;
  }
  .empty-state p {
    font-size: 14px; max-width: 440px; line-height: 1.75;
    color: var(--text-soft); font-weight: 400;
  }
  .empty-state .hint {
    font-size: 12px; color: var(--accent);
    border: 1px dashed rgba(52,211,153,0.55);
    background: rgba(52,211,153,0.05);
    padding: 7px 18px; border-radius: 999px;
    font-weight: 600; letter-spacing: 0.005em;
  }

  /* Hero */
  .hero {
    background:
      radial-gradient(800px 220px at 100% 0%, rgba(167,139,250,0.16), transparent 65%),
      radial-gradient(600px 200px at 0% 100%, rgba(52,211,153,0.10), transparent 65%),
      linear-gradient(135deg, var(--card2), var(--card));
    border: 1px solid var(--border);
    border-radius: 18px; padding: 22px 26px;
    position: relative; overflow: hidden;
    box-shadow: var(--shadow-md);
  }
  .hero::before {
    content: ''; position: absolute; right: -60px; top: -60px;
    width: 220px; height: 220px; border-radius: 50%;
    background: radial-gradient(closest-side, rgba(167,139,250,0.18), transparent 72%);
    pointer-events: none;
    animation: drift 12s ease-in-out infinite;
  }
  .hero::after {
    content: ''; position: absolute; left: -40px; bottom: -50px;
    width: 180px; height: 180px; border-radius: 50%;
    background: radial-gradient(closest-side, rgba(52,211,153,0.12), transparent 72%);
    pointer-events: none;
    animation: drift 14s ease-in-out infinite reverse;
  }
  @keyframes drift {
    0%, 100% { transform: translate(0,0); }
    50%      { transform: translate(-12px, 8px); }
  }
  .hero .label {
    font-size: 10.5px; text-transform: uppercase; letter-spacing: 1.6px;
    color: var(--muted); margin-bottom: 8px; font-weight: 700;
  }
  .hero .place {
    font-size: 26px; font-weight: 800; line-height: 1.15;
    letter-spacing: -0.02em;
    background: linear-gradient(180deg, #ffffff 0%, #aab3c7 100%);
    -webkit-background-clip: text; background-clip: text;
    -webkit-text-fill-color: transparent;
  }
  .hero .place .accent {
    background: linear-gradient(135deg, var(--accent) 0%, #6ee7b7 100%);
    -webkit-background-clip: text; background-clip: text;
    -webkit-text-fill-color: transparent;
  }
  .hero .display {
    font-size: 12.5px; color: var(--muted); margin-top: 6px;
    font-weight: 500;
  }
  .hero .summary {
    font-size: 13.5px; color: var(--text-soft); line-height: 1.65;
    margin-top: 14px;
  }
  .hero .meta-row {
    display: flex; flex-wrap: wrap; gap: 7px; margin-top: 16px;
  }
  .pill {
    background: rgba(255,255,255,0.025);
    border: 1px solid var(--border);
    border-radius: 999px; padding: 4px 11px; font-size: 11px;
    color: var(--text); font-weight: 600;
    letter-spacing: 0.005em;
    backdrop-filter: blur(6px);
  }
  .pill.lat   {
    color: var(--accent2);
    border-color: rgba(167,139,250,0.4);
    background: rgba(167,139,250,0.08);
    font-family: 'JetBrains Mono', ui-monospace, monospace;
    font-size: 10.5px;
  }
  .pill.focus {
    color: var(--accent3);
    border-color: rgba(251,191,36,0.4);
    background: rgba(251,191,36,0.08);
  }
  .pill.cat   {
    color: var(--accent);
    border-color: rgba(52,211,153,0.4);
    background: rgba(52,211,153,0.08);
  }

  .section-title {
    font-size: 10.5px; font-weight: 700;
    text-transform: uppercase; letter-spacing: 1.4px;
    color: var(--muted); margin: 6px 0 -8px 0;
    display: flex; align-items: center; gap: 10px;
  }
  .section-title::after {
    content: ''; flex: 1; height: 1px;
    background: linear-gradient(90deg, var(--border), transparent);
  }

  /* Lead cards */
  .lead {
    background:
      radial-gradient(400px 120px at 100% 0%, rgba(255,255,255,0.025), transparent 70%),
      var(--card);
    border: 1px solid var(--border);
    border-radius: 16px; padding: 18px 20px;
    display: flex; flex-direction: column; gap: 12px;
    transition: border-color 0.2s, transform 0.2s, box-shadow 0.2s;
    box-shadow: var(--shadow-sm);
    position: relative;
  }
  .lead:hover {
    border-color: rgba(52,211,153,0.45);
    transform: translateY(-2px);
    box-shadow: 0 10px 32px -10px rgba(52,211,153,0.20),
                0 4px 12px rgba(0,0,0,0.35);
  }
  .lead.top {
    border-color: rgba(251,191,36,0.55);
    background:
      radial-gradient(500px 160px at 100% 0%, rgba(251,191,36,0.10), transparent 65%),
      var(--card);
    box-shadow: var(--shadow-glow-gold);
  }
  .lead.top:hover {
    border-color: rgba(251,191,36,0.75);
    box-shadow: 0 0 0 1px rgba(251,191,36,0.45),
                0 14px 38px -8px rgba(251,191,36,0.28);
  }

  .lead-head {
    display: flex; align-items: flex-start; gap: 14px;
  }
  .lead-rank {
    flex-shrink: 0; width: 40px; height: 40px;
    border-radius: 12px;
    background: rgba(255,255,255,0.025);
    border: 1px solid var(--border);
    display: grid; place-items: center;
    font-size: 16px; font-weight: 800; color: var(--accent);
    font-variant-numeric: tabular-nums;
    box-shadow: 0 1px 0 rgba(255,255,255,0.04) inset;
  }
  .lead.top .lead-rank {
    background: linear-gradient(135deg, rgba(251,191,36,0.18), rgba(251,191,36,0.08));
    border-color: rgba(251,191,36,0.5);
    color: var(--accent3);
    box-shadow: 0 0 0 1px rgba(251,191,36,0.10) inset,
                0 4px 12px -2px rgba(251,191,36,0.30);
  }
  .lead-title { flex: 1; min-width: 0; }
  .lead-title .name {
    font-size: 16px; font-weight: 700; line-height: 1.3;
    letter-spacing: -0.015em;
    display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
  }
  .lead-title .cat  {
    font-size: 10.5px; color: var(--accent2); margin-top: 4px;
    text-transform: uppercase; letter-spacing: 1px; font-weight: 700;
  }
  .lead-score {
    flex-shrink: 0;
    background: rgba(255,255,255,0.025);
    border: 1px solid var(--border);
    border-radius: 12px; padding: 7px 13px;
    font-size: 10.5px; color: var(--muted); text-align: center;
    line-height: 1.15; font-weight: 600;
    text-transform: uppercase; letter-spacing: 1px;
  }
  .lead-score b {
    display: block; font-size: 19px; color: var(--accent);
    font-weight: 800; letter-spacing: -0.02em;
    font-variant-numeric: tabular-nums;
    margin-top: 2px;
  }
  .lead.top .lead-score {
    background: rgba(251,191,36,0.08);
    border-color: rgba(251,191,36,0.4);
  }
  .lead.top .lead-score b { color: var(--accent3); }

  .lead-use {
    background: rgba(52,211,153,0.05);
    border: 1px solid rgba(52,211,153,0.20);
    border-radius: 12px; padding: 10px 13px;
    font-size: 12.5px; color: var(--text-soft);
    line-height: 1.55;
  }
  .lead-use .lbl {
    color: var(--accent); font-weight: 800; margin-right: 8px;
    text-transform: uppercase; letter-spacing: 1px; font-size: 10.5px;
  }

  .lead-pitch {
    font-size: 13.5px; line-height: 1.65; color: var(--text-soft);
  }

  .lead-meta { display: flex; flex-wrap: wrap; gap: 6px; }
  .lead-meta a, .lead-meta span {
    background: rgba(255,255,255,0.025);
    border: 1px solid var(--border);
    border-radius: 999px; padding: 4px 11px;
    font-size: 11px; color: var(--text-soft); text-decoration: none;
    font-weight: 500;
    transition: color 0.18s, border-color 0.18s, background 0.18s;
  }
  .lead-meta a:hover {
    border-color: rgba(52,211,153,0.55);
    color: var(--accent);
    background: rgba(52,211,153,0.08);
  }

  .lead-evidence {
    display: flex; flex-direction: column; gap: 6px;
    border-top: 1px dashed var(--border); padding-top: 12px;
  }
  .lead-evidence .lbl {
    font-size: 10px; color: var(--muted);
    text-transform: uppercase; letter-spacing: 1.2px; font-weight: 700;
  }
  .lead-evidence a {
    font-size: 12px; color: var(--accent2); text-decoration: none;
    word-break: break-word;
    transition: color 0.15s;
  }
  .lead-evidence a:hover { color: #c4b5fd; text-decoration: underline; }

  /* Deep-dive: website signals */
  .signals {
    display: flex; flex-direction: column; gap: 8px;
    border-top: 1px dashed var(--border); padding-top: 12px;
  }
  .signals .lbl {
    font-size: 10px; color: var(--muted);
    text-transform: uppercase; letter-spacing: 1.2px; font-weight: 700;
  }
  .signal-chips { display: flex; flex-wrap: wrap; gap: 5px; }
  .signal-chip {
    font-size: 11px; padding: 3px 10px; border-radius: 999px;
    border: 1px solid var(--border); background: rgba(255,255,255,0.025);
    color: var(--muted);
    display: inline-flex; align-items: center; gap: 5px;
    font-weight: 500;
  }
  .signal-chip.yes {
    color: var(--success);
    border-color: rgba(74,222,128,0.40);
    background: rgba(74,222,128,0.07);
  }
  .signal-chip.no  {
    color: var(--danger);
    border-color: rgba(248,113,113,0.40);
    background: rgba(248,113,113,0.07);
  }
  .signal-chip .glyph { font-weight: 800; }
  .unblock-pill {
    font-size: 10.5px; padding: 3px 10px; border-radius: 999px;
    background: linear-gradient(135deg, rgba(251,191,36,0.14), rgba(251,191,36,0.06));
    color: var(--accent3);
    border: 1px solid rgba(251,191,36,0.42);
    margin-left: auto; font-weight: 700;
    letter-spacing: 0.005em;
    box-shadow: 0 4px 10px -4px rgba(251,191,36,0.30);
  }

  /* Deep-dive: review friction */
  .friction {
    display: flex; flex-direction: column; gap: 9px;
    border-top: 1px dashed var(--border); padding-top: 12px;
  }
  .friction .lbl {
    font-size: 10px; color: var(--muted);
    text-transform: uppercase; letter-spacing: 1.2px; font-weight: 700;
  }
  .friction-item {
    background: rgba(248,113,113,0.04);
    border-left: 3px solid var(--danger);
    border-radius: 8px; padding: 9px 13px;
    display: flex; flex-direction: column; gap: 4px;
  }
  .friction-item .pat {
    font-size: 10.5px; color: var(--danger);
    text-transform: uppercase; letter-spacing: 0.8px; font-weight: 700;
  }
  .friction-item .qt {
    font-size: 12.5px; color: var(--text-soft);
    line-height: 1.55; font-style: italic;
  }
  .friction-item .src {
    font-size: 11px; color: var(--muted);
  }
  .friction-item .src a { color: var(--accent2); text-decoration: none; }
  .friction-item .src a:hover { text-decoration: underline; }

  .deep-dive-flag {
    font-size: 9.5px; padding: 2px 8px; border-radius: 999px;
    background: linear-gradient(135deg, rgba(167,139,250,0.20), rgba(167,139,250,0.08));
    color: var(--accent2);
    border: 1px solid rgba(167,139,250,0.45);
    text-transform: uppercase; letter-spacing: 0.8px; font-weight: 700;
  }
  .outdated-flag {
    font-size: 9.5px; padding: 2px 8px; border-radius: 999px;
    background: rgba(248,113,113,0.10); color: var(--danger);
    border: 1px solid rgba(248,113,113,0.4);
    text-transform: uppercase; letter-spacing: 0.8px; font-weight: 700;
  }

  /* Freshness — separate from capability chips so the user reads them as
     "site health" rather than "feature presence". */
  .freshness-chips { display: flex; flex-wrap: wrap; gap: 5px; }
  .fresh-chip {
    font-size: 11px; padding: 3px 10px; border-radius: 999px;
    border: 1px solid var(--border); background: rgba(255,255,255,0.025);
    color: var(--muted); font-weight: 500;
  }
  .fresh-chip.bad {
    color: var(--danger);
    border-color: rgba(248,113,113,0.5);
    background: rgba(248,113,113,0.06);
  }
  .fresh-chip.ok  {
    color: var(--success);
    border-color: rgba(74,222,128,0.40);
    background: rgba(74,222,128,0.06);
  }

  /* Email button + modal */
  .lead-actions {
    display: flex; gap: 8px; margin-top: 6px;
  }
  .btn-ghost {
    background: rgba(52,211,153,0.06);
    color: var(--accent);
    border: 1px solid rgba(52,211,153,0.42);
    border-radius: 10px; padding: 7px 14px;
    font-size: 12px; font-weight: 700;
    cursor: pointer; text-decoration: none;
    display: inline-flex; align-items: center;
    transition: background 0.18s, border-color 0.18s, transform 0.15s;
  }
  .btn-ghost:hover {
    background: rgba(52,211,153,0.14);
    border-color: rgba(52,211,153,0.65);
    transform: translateY(-1px);
  }
  .btn-ghost.violet {
    color: var(--accent2);
    border-color: rgba(167,139,250,0.42);
    background: rgba(167,139,250,0.06);
  }
  .btn-ghost.violet:hover {
    background: rgba(167,139,250,0.14);
    border-color: rgba(167,139,250,0.65);
  }

  .modal-backdrop {
    position: fixed; inset: 0;
    background: rgba(7,8,12,0.74);
    backdrop-filter: blur(8px);
    -webkit-backdrop-filter: blur(8px);
    display: none; align-items: center; justify-content: center;
    z-index: 1000; padding: 24px;
    animation: fade-in 0.18s ease-out;
  }
  .modal-backdrop.open { display: flex; }
  .modal {
    background: linear-gradient(180deg, var(--card2), var(--card));
    border: 1px solid var(--border-strong);
    border-radius: 18px;
    width: min(640px, 100%);
    max-height: 90vh;
    display: flex; flex-direction: column;
    overflow: hidden;
    box-shadow: var(--shadow-lg);
    animation: pop-in 0.22s cubic-bezier(0.16,1,0.3,1);
  }
  .modal-head {
    display: flex; align-items: center; gap: 12px;
    padding: 16px 20px; border-bottom: 1px solid var(--border);
    background: rgba(255,255,255,0.012);
  }
  .modal-head h3 {
    font-size: 14px; font-weight: 700; flex: 1;
    letter-spacing: -0.01em;
  }
  .modal-head h3 small {
    color: var(--muted); font-weight: 500; font-size: 12px; margin-left: 8px;
  }
  .modal-close {
    background: transparent; color: var(--muted); border: none;
    font-size: 22px; cursor: pointer; line-height: 1; padding: 4px 10px;
    border-radius: 8px;
    transition: color 0.15s, background 0.15s;
  }
  .modal-close:hover {
    color: var(--text);
    background: rgba(255,255,255,0.04);
  }
  .modal-body {
    flex: 1; overflow-y: auto; padding: 18px 20px;
    display: flex; flex-direction: column; gap: 12px;
  }
  .modal-body label {
    font-size: 10.5px; font-weight: 700; color: var(--muted);
    text-transform: uppercase; letter-spacing: 1.2px;
  }
  .modal-body input[type="text"],
  .modal-body textarea {
    background: var(--bg-soft);
    border: 1px solid var(--border);
    border-radius: 10px; padding: 11px 14px;
    color: var(--text); font-size: 13px;
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    width: 100%; outline: none; resize: vertical;
    transition: border-color 0.18s, box-shadow 0.18s;
  }
  .modal-body input[type="text"]:focus,
  .modal-body textarea:focus {
    border-color: rgba(52,211,153,0.55);
    box-shadow: 0 0 0 4px rgba(52,211,153,0.10);
  }
  .modal-body textarea { min-height: 280px; line-height: 1.6; }
  .modal-foot {
    display: flex; gap: 8px; padding: 14px 20px;
    border-top: 1px solid var(--border);
    background: rgba(0,0,0,0.18);
  }
  .modal-foot .spacer { flex: 1; }
  .modal-foot .copy-toast {
    color: var(--success); font-size: 12px; font-weight: 600;
    align-self: center; opacity: 0; transition: opacity 0.15s;
  }
  .modal-foot .copy-toast.show { opacity: 1; }

  /* Next steps */
  .next-steps {
    background:
      radial-gradient(500px 160px at 0% 0%, rgba(251,191,36,0.06), transparent 70%),
      var(--card);
    border: 1px solid var(--border);
    border-radius: 16px; padding: 18px 20px;
    box-shadow: var(--shadow-sm);
  }
  .next-steps h3 {
    font-size: 11px; font-weight: 800; color: var(--accent3);
    text-transform: uppercase; letter-spacing: 1.4px;
    margin-bottom: 12px;
    display: flex; align-items: center; gap: 8px;
  }
  .next-steps h3::before {
    content: '→';
    font-size: 14px;
    line-height: 1;
  }
  .next-steps ol { padding-left: 22px; }
  .next-steps li {
    font-size: 13px; line-height: 1.7; color: var(--text-soft);
    margin-bottom: 6px;
  }
  .next-steps li::marker {
    color: var(--accent3); font-weight: 700;
  }
</style>
</head>
<body>

<header>
  <div class="logo">∞</div>
  <h1>Ouro<span>boros</span></h1>
  <span class="tag">CUGA finds its next client</span>
  <div class="status-badge">
    <div class="status-dot" id="statusDot"></div>
    <span id="statusText">Ready</span>
  </div>
  <button class="header-pill" onclick="openEmailCfgModal()"
          title="Configure per-run email notifications">
    ✉ Email
  </button>
  <a class="header-pill" href="/cuga/loops/" target="_blank"
     title="View all CUGA loops scheduled by this and other apps">
    🔁 Loops
  </a>
</header>

<!-- Email-config modal (NB: distinct from the per-lead "draft email" modal
     elsewhere in this UI; that one is #emailBackdrop / closeEmail()) -->
<div id="emailCfgBackdrop" onclick="if(event.target===this)closeEmailCfgModal()"
     style="display:none;position:fixed;inset:0;background:rgba(0,0,0,0.6);
            z-index:1000;align-items:center;justify-content:center">
  <div style="background:#161b22;border:1px solid #30363d;border-radius:8px;
              padding:24px;max-width:560px;width:92%;max-height:90vh;overflow-y:auto;
              color:#e6edf3;font-family:-apple-system,system-ui,sans-serif;font-size:14px">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
      <h2 style="margin:0;font-size:16px">✉️ Email notifications</h2>
      <button onclick="closeEmailCfgModal()" style="background:none;border:none;
              color:#8b949e;font-size:20px;cursor:pointer">×</button>
    </div>
    <p style="margin:0 0 14px;color:#8b949e;font-size:12px">
      Set a recipient + SMTP creds and emails will be sent automatically after
      every run. Leave SMTP fields blank to use the env vars instead.
    </p>
    <div id="emailCfgStatus" style="font-size:11px;
         padding:8px 10px;background:#0d1117;border-radius:4px;margin-bottom:14px"></div>

    <label style="display:block;margin-top:8px">
      <span style="display:block;margin-bottom:4px;font-size:12px;color:#8b949e">
        Recipient email <span style="color:#f85149">*</span>
        <span style="color:#666"> — emails are off when this is empty</span>
      </span>
      <input type="email" id="ecRecipient" placeholder="you@example.com"
        style="width:100%;padding:7px 10px;background:#0d1117;border:1px solid #30363d;
               border-radius:4px;color:#e6edf3;font:inherit;box-sizing:border-box" />
    </label>

    <label style="display:block;margin-top:12px">
      <span style="display:block;margin-bottom:4px;font-size:12px;color:#8b949e">
        Minimum leads to send (skip noisy runs)
      </span>
      <input type="number" id="ecMinLeads" min="0" max="10" value="0"
        style="width:80px;padding:7px 10px;background:#0d1117;border:1px solid #30363d;
               border-radius:4px;color:#e6edf3;font:inherit" />
    </label>

    <fieldset style="margin-top:14px;border:1px solid #30363d;border-radius:4px;
                     padding:8px 12px;color:#8b949e">
      <legend style="font-size:11px;text-transform:uppercase;letter-spacing:0.5px;
                     padding:0 6px">Send for</legend>
      <label style="display:inline-block;margin-right:16px">
        <input type="checkbox" id="ecIncludeUser" /> 👤 user requests
      </label>
      <label style="display:inline-block">
        <input type="checkbox" id="ecIncludeLoop" /> 🔁 loop fires
      </label>
    </fieldset>

    <fieldset style="margin-top:14px;border:1px solid #30363d;border-radius:4px;
                     padding:8px 12px">
      <legend style="font-size:11px;text-transform:uppercase;letter-spacing:0.5px;
                     padding:0 6px;color:#8b949e">SMTP credentials</legend>
      <div style="display:grid;grid-template-columns:1fr 80px;gap:8px 10px">
        <label>Host
          <input type="text" id="ecSmtpHost" placeholder="smtp.gmail.com"
            style="width:100%;padding:6px 8px;background:#0d1117;border:1px solid #30363d;
                   border-radius:4px;color:#e6edf3;font:inherit;box-sizing:border-box" />
        </label>
        <label>Port
          <input type="number" id="ecSmtpPort" placeholder="587"
            style="width:100%;padding:6px 8px;background:#0d1117;border:1px solid #30363d;
                   border-radius:4px;color:#e6edf3;font:inherit;box-sizing:border-box" />
        </label>
        <label style="grid-column:1/3">Username
          <input type="text" id="ecSmtpUsername" placeholder="you@gmail.com"
            style="width:100%;padding:6px 8px;background:#0d1117;border:1px solid #30363d;
                   border-radius:4px;color:#e6edf3;font:inherit;box-sizing:border-box" />
        </label>
        <label style="grid-column:1/3">
          Password
          <span id="ecPwState" style="font-size:11px;font-weight:normal;margin-left:6px"></span>
          <input type="password" id="ecSmtpPassword" autocomplete="new-password"
            style="width:100%;padding:6px 8px;background:#0d1117;border:2px solid #30363d;
                   border-radius:4px;color:#e6edf3;font:inherit;box-sizing:border-box" />
        </label>
        <label style="grid-column:1/3">From address
          <input type="email" id="ecSmtpFrom" placeholder="(defaults to username)"
            style="width:100%;padding:6px 8px;background:#0d1117;border:1px solid #30363d;
                   border-radius:4px;color:#e6edf3;font:inherit;box-sizing:border-box" />
        </label>
      </div>
    </fieldset>

    <div style="margin-top:18px;display:flex;gap:8px;justify-content:flex-end">
      <button onclick="emailCfgTest()" id="ecTestBtn"
              style="padding:8px 14px;background:transparent;border:1px solid #30363d;
                     border-radius:4px;color:#aaa;cursor:pointer">
        Send test email
      </button>
      <button onclick="emailCfgSave()" id="ecSaveBtn"
              style="padding:8px 14px;background:#238636;border:1px solid #2ea043;
                     border-radius:4px;color:white;cursor:pointer;font-weight:600">
        Save
      </button>
    </div>
    <div id="emailCfgMsg" style="margin-top:12px;font-size:12px;min-height:18px"></div>
  </div>
</div>

<main>
  <div class="chat-panel" style="position: relative;">
    <div class="panel-title">
      <span>Hunt with the agent</span>
      <button class="runs-btn" id="runsBtn" onclick="toggleRunsDrawer()">Past runs ▾</button>
    </div>

    <div class="runs-drawer" id="runsDrawer">
      <div class="head">
        <span id="runsScopeLabel">Saved turns · this thread</span>
        <button class="runs-btn" id="scopeToggleBtn"
          style="margin-left:auto" onclick="toggleRunsScope()">All threads</button>
        <button class="runs-btn" onclick="refreshRunsList()">Refresh</button>
      </div>
      <div id="runsList" class="empty">No runs yet — ask a question first.</div>
    </div>

    <div class="chips">
      <div class="chip" onclick="sendChip(this)">Find leads in Westchester, NY</div>
      <div class="chip" onclick="sendChip(this)">Restaurants in HSR Layout, Bangalore — pitch order bots</div>
      <div class="chip" onclick="sendChip(this)">Salons in Brooklyn that need appointment booking</div>
      <div class="chip" onclick="sendChip(this)">Independent hotels in Lisbon — concierge agent angle</div>
      <div class="chip" onclick="sendChip(this)">Clinics in Austin — patient FAQ + intake</div>
      <div class="chip" onclick="sendChip(this)">Real estate offices in San Mateo — lead capture pitch</div>
      <div class="chip" onclick="sendChip(this)">Boutiques in Williamsburg — product Q&A</div>
      <div class="chip" onclick="sendChip(this)">Veterinary clinics near Berkeley — appointment + reminders</div>
      <div class="chip" onclick="sendChip(this)">Tutoring centers in Mumbai Andheri — enrollment funnel</div>
    </div>

    <div class="messages" id="messages"></div>

    <div class="input-row">
      <input type="text" id="userInput"
        placeholder="Try: 'Find restaurants in HSR Layout that need an order bot'"
        onkeydown="if(event.key==='Enter') sendMessage()" />
      <select id="inputCadence" class="input-cadence" title="Cadence for Schedule">
        <option value="5m">every 5 min</option>
        <option value="30m">every 30 min</option>
        <option value="1h">hourly</option>
        <option value="6h">every 6 hours</option>
        <option value="daily" selected>daily</option>
        <option value="weekly">weekly</option>
      </select>
      <button class="btn btn-secondary" id="scheduleBtn" onclick="scheduleFromInput()" title="Register the typed question as a recurring loop">Schedule</button>
      <button class="btn" id="sendBtn" onclick="sendMessage()" title="Run the typed question once now">Hunt</button>
    </div>
  </div>

  <div class="data-panel">
    <div class="data-panel-header">
      <span>Lead board</span>
      <button class="refresh-badge" id="refreshBadge" onclick="fetchSession()" title="Reload the lead board">↻ Refresh</button>
    </div>
    <div class="data-scroll" id="dataScroll">
      <div class="empty-state" id="emptyState">
        <div class="icon">∞</div>
        <p>Name a location — neighborhood, city, or region. Optionally add a category ("salons", "restaurants") and a CUGA pitch focus ("appointment booking", "order bot"). The agent will scout OSM + the live web and hand back a ranked board with tailored pitches.</p>
        <div class="hint">Try: "Find restaurants in HSR Layout — order bot pitch"</div>
      </div>
    </div>
  </div>
</main>

<div class="trace-modal-backdrop" id="traceBackdrop" onclick="if(event.target===this) closeTrace()">
  <div class="trace-modal" role="dialog" aria-modal="true" aria-labelledby="traceTitle">
    <div class="trace-modal-head">
      <h3 id="traceTitle">Agent trace</h3>
      <span id="traceMeta" style="color: var(--muted); font-size: 11px; margin-left: auto;"></span>
      <button class="modal-close" onclick="closeTrace()" aria-label="Close" style="background:none;border:none;color:var(--muted);font-size:22px;cursor:pointer;">×</button>
    </div>
    <div class="trace-modal-body" id="traceBody"></div>
  </div>
</div>

<div class="modal-backdrop" id="emailBackdrop" onclick="if(event.target===this) closeEmail()">
  <div class="modal" role="dialog" aria-modal="true" aria-labelledby="emailModalTitle">
    <div class="modal-head">
      <h3 id="emailModalTitle">Draft email <small id="emailModalLead"></small></h3>
      <button class="modal-close" onclick="closeEmail()" aria-label="Close">×</button>
    </div>
    <div class="modal-body">
      <label for="emailTo">To</label>
      <input type="text" id="emailTo" placeholder="recipient@example.com" />

      <label for="emailSubject">Subject</label>
      <input type="text" id="emailSubject" />

      <label for="emailBody">Body</label>
      <textarea id="emailBody" spellcheck="true"></textarea>
    </div>
    <div class="modal-foot">
      <button class="btn-ghost" onclick="copyEmail()">Copy</button>
      <button class="btn-ghost violet" onclick="openInMail()">Open in mail app</button>
      <span class="copy-toast" id="copyToast">Copied</span>
      <span class="spacer"></span>
      <button class="btn" onclick="closeEmail()">Done</button>
    </div>
  </div>
</div>

<script>
  // Persist the thread_id in localStorage (NOT sessionStorage) so the
  // user's runs survive tab close, browser restart, and server restart.
  // sessionStorage was clearing on every new tab — meaning every new tab
  // got a fresh thread_id and the past-runs drawer looked empty even
  // though the JSON files were still on disk under the old thread.
  let SESSION_ID = localStorage.getItem('ouroboros_session');
  if (!SESSION_ID) {
    SESSION_ID = (crypto.randomUUID
      ? crypto.randomUUID()
      : 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
          const r = Math.random() * 16 | 0;
          return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
        }));
    localStorage.setItem('ouroboros_session', SESSION_ID);
  }

  const messagesEl = document.getElementById('messages');
  const inputEl    = document.getElementById('userInput');
  const sendBtn    = document.getElementById('sendBtn');
  const scheduleBtn = document.getElementById('scheduleBtn');
  const inputCadence = document.getElementById('inputCadence');
  const statusDot  = document.getElementById('statusDot');
  const statusText = document.getElementById('statusText');
  const dataScroll = document.getElementById('dataScroll');
  const emptyState = document.getElementById('emptyState');

  function setStatus(busy, label) {
    statusDot.className = 'status-dot' + (busy ? ' busy' : '');
    statusText.textContent = label;
  }

  function addMessage(text, cls, meta) {
    const div = document.createElement('div');
    div.className = 'msg ' + cls;
    div.textContent = text;
    if (meta) {
      const span = document.createElement('span');
      span.className = 'meta';
      span.textContent = meta;
      div.appendChild(span);
    }
    // Discreet inline scheduler under each USER message: pick a cadence,
    // click Set, and the message is registered as a recurring loop fired
    // by the supervisor. Existing chat behavior is unchanged — this is
    // an afterthought, not a replacement for /ask.
    if (cls === 'user' && text && text.trim()) {
      div.appendChild(_buildScheduleControl(text.trim()));
    }
    messagesEl.appendChild(div);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return div;
  }

  function _buildScheduleControl(promptText) {
    const row = document.createElement('div');
    row.className = 'sched';
    row.innerHTML =
      '<span class="sched-label">🔁 Schedule this</span>'
    + '<select class="sched-cadence" title="How often to re-run this question">'
    +   '<option value="5m">every 5 min</option>'
    +   '<option value="30m">every 30 min</option>'
    +   '<option value="1h">hourly</option>'
    +   '<option value="6h">every 6 hours</option>'
    +   '<option value="daily" selected>daily</option>'
    +   '<option value="weekly">weekly</option>'
    + '</select>'
    + '<button type="button" class="sched-set">Set</button>';
    const btn = row.querySelector('.sched-set');
    btn.addEventListener('click', () => {
      const cadence = row.querySelector('.sched-cadence').value;
      _scheduleMessage(row, promptText, cadence);
    });
    return row;
  }

  async function _scheduleMessage(row, promptText, cadence) {
    const setBtn = row.querySelector('.sched-set');
    setBtn.disabled = true; setBtn.textContent = '…';
    try {
      const r = await fetch('/cuga/loops/api/create', {
        method: 'POST',
        headers: {'content-type': 'application/json'},
        body: JSON.stringify({
          agent_name: 'ouroboros_supervisor',
          thread_id:  SESSION_ID,
          prompt:     promptText,
          cadence:    cadence,
          metadata:   {source: 'chat_inline'},
        }),
      });
      const j = await r.json();
      if (!r.ok) throw new Error(j.error || j.detail?.[0]?.msg || ('HTTP ' + r.status));
      const lid = j.loop?.id || '';
      row.className = 'sched done';
      row.innerHTML =
        '🔁 Scheduled ' + esc(cadence) + ' · '
      + '<a href="/cuga/loops/" target="_blank" title="' + esc(lid)
      +   '">' + esc(lid.slice(0, 16)) + '</a> · '
      + '<a class="sched-cancel">Cancel</a>';
      row.querySelector('.sched-cancel').addEventListener('click', async () => {
        try {
          await fetch('/cuga/loops/api/' + encodeURIComponent(lid), {method: 'DELETE'});
          row.className = 'sched';
          row.appendChild(document.createTextNode(' (cancelled)'));
        } catch (e) {
          row.className = 'sched err';
          row.appendChild(document.createTextNode(' cancel failed: ' + e.message));
        }
      });
    } catch (err) {
      row.className = 'sched err';
      row.innerHTML = '🔁 Schedule failed: ' + esc(err.message);
      setBtn.disabled = false; setBtn.textContent = 'Set';
    }
  }

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function host(url) {
    try { return new URL(url).hostname; } catch (_) { return ''; }
  }

  let _lastHash = '';

  function renderHero(b, state) {
    const lat = (b.lat != null && b.lon != null)
      ? '<span class="pill lat">' +
        esc((b.lat.toFixed ? b.lat.toFixed(3) : b.lat) + ', ' + (b.lon.toFixed ? b.lon.toFixed(3) : b.lon)) +
        '</span>'
      : '';
    const focusPills = (state.categories || []).map(c =>
      '<span class="pill cat">' + esc(c) + '</span>'
    ).join('');
    const pitch = state.pitch_focus
      ? '<span class="pill focus">pitch: ' + esc(state.pitch_focus) + '</span>'
      : '';
    return (
      '<div class="hero">' +
        '<div class="label">Hunting in</div>' +
        '<div class="place"><span class="accent">' + esc(b.location || '?') + '</span></div>' +
        (b.display_name ? '<div class="display">' + esc(b.display_name) + '</div>' : '') +
        (b.summary ? '<div class="summary">' + esc(b.summary) + '</div>' : '') +
        '<div class="meta-row">' + lat + focusPills + pitch + '</div>' +
      '</div>'
    );
  }

  // Human labels for the website-signal keys returned by analyze_business_website.
  // The "good" column says whether the chip should render green (yes) or red (no)
  // when the underlying boolean is true. Phone-first / appointment-required are
  // examples where TRUE is bad — they're CUGA opportunities.
  const SIGNAL_LABELS = [
    { key: 'has_online_ordering',  label: 'Online ordering',  goodWhenTrue: true  },
    { key: 'has_online_booking',   label: 'Online booking',   goodWhenTrue: true  },
    { key: 'has_chat_widget',      label: 'Live chat',        goodWhenTrue: true  },
    { key: 'has_contact_form',     label: 'Contact form',     goodWhenTrue: true  },
    { key: 'has_faq',              label: 'FAQ page',         goodWhenTrue: true  },
    { key: 'has_response_promise', label: 'Response SLA',     goodWhenTrue: true  },
    { key: 'phone_first',          label: 'Phone-first',      goodWhenTrue: false },
    { key: 'appointment_required', label: 'Appt-only',        goodWhenTrue: false },
  ];

  function renderSignalChips(signals) {
    if (!signals) return '';
    const chips = SIGNAL_LABELS.map(s => {
      const v = !!signals[s.key];
      // The chip's green/red follows whether the *current* state is good or bad
      // for the business — TRUE for "phone_first" is bad, so it renders red.
      const isGood = v === s.goodWhenTrue;
      const cls = isGood ? 'yes' : 'no';
      const glyph = v ? '✓' : '✗';
      return '<span class="signal-chip ' + cls + '"><span class="glyph">' +
        glyph + '</span> ' + esc(s.label) + '</span>';
    }).join('');
    const unblock = (signals.agent_unblock_score != null)
      ? '<span class="unblock-pill">CUGA opportunity ' + esc(signals.agent_unblock_score) + '/4</span>'
      : '';
    return (
      '<div class="signals">' +
        '<div class="lbl" style="display:flex;align-items:center;gap:6px;">' +
          '<span>Website signals</span>' + unblock +
        '</div>' +
        '<div class="signal-chips">' + chips + '</div>' +
        renderFreshnessChips(signals) +
      '</div>'
    );
  }

  function renderFreshnessChips(s) {
    if (!s) return '';
    const chips = [];
    // SSL — red if bare http
    chips.push('<span class="fresh-chip ' + (s.is_https ? 'ok' : 'bad') + '">' +
               (s.is_https ? '🔒 HTTPS' : '⚠ No HTTPS') + '</span>');
    // Mobile viewport
    chips.push('<span class="fresh-chip ' + (s.mobile_responsive ? 'ok' : 'bad') + '">' +
               (s.mobile_responsive ? '📱 Mobile-ready' : '⚠ Not mobile-friendly') + '</span>');
    // Copyright year
    if (s.copyright_year != null) {
      const stale = s.years_stale != null && s.years_stale >= 3;
      chips.push('<span class="fresh-chip ' + (stale ? 'bad' : 'ok') + '">©' +
                 esc(s.copyright_year) +
                 (stale ? ' · ' + esc(s.years_stale) + 'y stale' : '') + '</span>');
    }
    // SEO meta
    if (s.has_meta_description === false) {
      chips.push('<span class="fresh-chip bad">⚠ No SEO meta</span>');
    }
    if (s.has_og_tags === false) {
      chips.push('<span class="fresh-chip bad">⚠ No social meta</span>');
    }
    // Tech smells — render each as its own chip so the user can scan them
    (s.tech_smells || []).forEach(t => {
      chips.push('<span class="fresh-chip bad">⚠ ' + esc(t) + '</span>');
    });
    if (!chips.length) return '';
    return (
      '<div class="lbl" style="margin-top:6px;">Site health</div>' +
      '<div class="freshness-chips">' + chips.join('') + '</div>'
    );
  }

  function renderFriction(items) {
    if (!items || !items.length) return '';
    const blocks = items.map(f => {
      const src = f.source_url
        ? '<div class="src"><a href="' + esc(f.source_url) + '" target="_blank" rel="noopener">' +
          esc(host(f.source_url) || f.source_url) + '</a></div>'
        : '';
      return (
        '<div class="friction-item">' +
          (f.pattern ? '<div class="pat">' + esc(f.pattern) + '</div>' : '') +
          (f.quote ? '<div class="qt">"' + esc(f.quote) + '"</div>' : '') +
          src +
        '</div>'
      );
    }).join('');
    return (
      '<div class="friction">' +
        '<div class="lbl">What people complain about</div>' +
        blocks +
      '</div>'
    );
  }

  function renderLead(lead, idx) {
    const score = lead.fit_score != null ? Math.max(1, Math.min(10, lead.fit_score)) : 0;
    const top = score >= 8 ? ' top' : '';
    const meta = [];
    if (lead.address) meta.push('<span>📍 ' + esc(lead.address) + '</span>');
    if (lead.phone)   meta.push('<span>📞 ' + esc(lead.phone) + '</span>');
    if (lead.email)   meta.push('<span>✉ ' + esc(lead.email) + '</span>');
    if (lead.website) meta.push('<a href="' + esc(lead.website) + '" target="_blank" rel="noopener">🌐 ' + esc(host(lead.website) || lead.website) + '</a>');
    if (lead.osm)     meta.push('<a href="' + esc(lead.osm) + '" target="_blank" rel="noopener">🗺️ OSM</a>');

    const evidence = (lead.evidence || []).map(e =>
      '<a href="' + esc(e.url) + '" target="_blank" rel="noopener">' +
        esc(e.title || e.url) +
      '</a>'
    ).join('');

    const flags = [];
    if (lead.deep_dive) {
      flags.push('<span class="deep-dive-flag">deep-dive</span>');
    }
    if (lead.website_signals && lead.website_signals.looks_outdated) {
      flags.push('<span class="outdated-flag">site stale</span>');
    }

    // Only stash + render the email button when the agent actually generated
    // a draft (deep-dive leads only). Lower-ranked candidates get no button —
    // the user can ask "deep-dive lead #N" to spend tokens on a focused pass.
    const hasDraft = lead.email_draft &&
                     (lead.email_draft.subject || lead.email_draft.body);
    let emailButton = '';
    if (hasDraft) {
      const draftKey = 'lead-' + idx;
      EMAIL_DRAFTS[draftKey] = {
        to:      lead.email || '',
        subject: lead.email_draft.subject || ('Idea for ' + (lead.name || '')),
        body:    lead.email_draft.body || '',
        name:    lead.name || '',
      };
      emailButton =
        '<button class="btn-ghost" onclick="openEmail(\'' + draftKey + '\')">' +
        '✉ Draft email</button>';
    }
    const websiteButton = lead.website
      ? '<a class="btn-ghost violet" href="' + esc(lead.website) +
        '" target="_blank" rel="noopener">View site</a>'
      : '';
    const actionsHtml = (emailButton || websiteButton)
      ? '<div class="lead-actions">' + emailButton + websiteButton + '</div>'
      : '';

    return (
      '<div class="lead' + top + '">' +
        '<div class="lead-head">' +
          '<div class="lead-rank">' + (idx + 1) + '</div>' +
          '<div class="lead-title">' +
            '<div class="name">' + esc(lead.name || 'Unknown business') +
              ' ' + flags.join(' ') + '</div>' +
            (lead.category ? '<div class="cat">' + esc(lead.category) + '</div>' : '') +
          '</div>' +
          '<div class="lead-score">fit<b>' + score + '/10</b></div>' +
        '</div>' +
        (lead.use_case ? '<div class="lead-use"><span class="lbl">Use case</span>' + esc(lead.use_case) + '</div>' : '') +
        (lead.pitch ? '<div class="lead-pitch">' + esc(lead.pitch) + '</div>' : '') +
        (meta.length ? '<div class="lead-meta">' + meta.join('') + '</div>' : '') +
        renderSignalChips(lead.website_signals) +
        renderFriction(lead.review_friction) +
        (evidence ? '<div class="lead-evidence"><span class="lbl">Evidence</span>' + evidence + '</div>' : '') +
        actionsHtml +
      '</div>'
    );
  }

  // ── Email draft modal ────────────────────────────────────────────────
  const EMAIL_DRAFTS = {};
  let _activeDraftKey = null;

  const emailBackdrop = document.getElementById('emailBackdrop');
  const emailTo       = document.getElementById('emailTo');
  const emailSubject  = document.getElementById('emailSubject');
  const emailBody     = document.getElementById('emailBody');
  const emailModalLeadEl = document.getElementById('emailModalLead');
  const copyToast     = document.getElementById('copyToast');

  function openEmail(key) {
    const d = EMAIL_DRAFTS[key];
    if (!d) return;
    _activeDraftKey = key;
    emailTo.value      = d.to || '';
    emailSubject.value = d.subject || '';
    emailBody.value    = d.body || '';
    emailModalLeadEl.textContent = d.name ? '· ' + d.name : '';
    emailBackdrop.classList.add('open');
    setTimeout(() => emailSubject.focus(), 50);
  }
  function closeEmail() {
    emailBackdrop.classList.remove('open');
    copyToast.classList.remove('show');
    _activeDraftKey = null;
  }
  function copyEmail() {
    const text = 'Subject: ' + emailSubject.value + '\n\n' + emailBody.value;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(showCopied);
    } else {
      // Fallback for browsers without the async clipboard API
      const ta = document.createElement('textarea');
      ta.value = text; document.body.appendChild(ta);
      ta.select(); document.execCommand('copy');
      document.body.removeChild(ta);
      showCopied();
    }
  }
  function showCopied() {
    copyToast.classList.add('show');
    setTimeout(() => copyToast.classList.remove('show'), 1400);
  }
  function openInMail() {
    const to   = encodeURIComponent(emailTo.value || '');
    const subj = encodeURIComponent(emailSubject.value || '');
    const body = encodeURIComponent(emailBody.value || '');
    // Most mail clients cap mailto bodies around 2000 chars; clipboard copy is the
    // safer path for longer drafts. We still offer mailto for one-click prefill.
    window.location.href = 'mailto:' + to + '?subject=' + subj + '&body=' + body;
  }
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && emailBackdrop.classList.contains('open')) {
      closeEmail();
    }
  });

  function renderNextSteps(steps) {
    if (!steps || !steps.length) return '';
    const lis = steps.map(s => '<li>' + esc(s) + '</li>').join('');
    return (
      '<div class="next-steps">' +
        '<h3>Next moves</h3>' +
        '<ol>' + lis + '</ol>' +
      '</div>'
    );
  }

  function refreshPanel(state) {
    const hash = JSON.stringify(state);
    if (hash === _lastHash) return;
    _lastHash = hash;

    const b = state.leads;
    if (!b) return;

    emptyState.style.display = 'none';
    dataScroll.innerHTML = '';

    let html = '';
    html += renderHero(b, state);

    const leads = (b.leads || []).slice().sort((a, c) => (c.fit_score || 0) - (a.fit_score || 0));
    if (leads.length) {
      html += '<div class="section-title">Leads · ranked by fit</div>';
      leads.forEach((lead, i) => { html += renderLead(lead, i); });
    }

    html += renderNextSteps(b.next_steps);

    const wrap = document.createElement('div');
    wrap.style.display = 'contents';
    wrap.innerHTML = html;
    dataScroll.appendChild(wrap);
  }

  async function fetchSession() {
    try {
      const res = await fetch('/session/' + SESSION_ID);
      if (res.ok) {
        const data = await res.json();
        refreshPanel(data);
      }
    } catch (_) { /* ignore */ }
  }
  // Auto-refresh removed — fetchSession() runs only after /ask returns,
  // or when the user clicks the Refresh badge in the data panel header.

  async function sendMessage() {
    const question = inputEl.value.trim();
    if (!question) return;
    inputEl.value = '';
    sendBtn.disabled = true;
    setStatus(true, 'Scouting…');
    addMessage(question, 'user');
    const thinking = addMessage('Geocoding, querying OSM, gathering web evidence…', 'thinking');

    try {
      const res = await fetch('/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question, thread_id: SESSION_ID }),
      });
      const data = await res.json();
      thinking.remove();
      const elapsedLabel = data.elapsed_human
        ? ('answered in ' + data.elapsed_human)
        : null;
      if (!res.ok) {
        addMessage('Error: ' + (data.answer || res.statusText), 'error',
          elapsedLabel);
      } else {
        addMessage(data.answer, 'agent', elapsedLabel);
        await fetchSession();
        await refreshRunsList();
      }
    } catch (err) {
      thinking.remove();
      addMessage('Network error: ' + err.message, 'error');
    } finally {
      sendBtn.disabled = false;
      setStatus(false, 'Ready');
      inputEl.focus();
    }
  }

  function sendChip(el) {
    inputEl.value = el.textContent.trim();
    sendMessage();
  }

  // Register the typed question as a recurring loop. Doesn't run /ask now —
  // the supervisor will fire on the chosen cadence in a fresh thread.
  async function scheduleFromInput() {
    const question = inputEl.value.trim();
    if (!question) {
      inputEl.focus();
      return;
    }
    const cadence = inputCadence.value || 'daily';
    scheduleBtn.disabled = true;
    sendBtn.disabled = true;
    const original = scheduleBtn.textContent;
    scheduleBtn.textContent = 'Scheduling…';
    addMessage(question, 'user');
    inputEl.value = '';
    try {
      const r = await fetch('/cuga/loops/api/create', {
        method: 'POST',
        headers: {'content-type': 'application/json'},
        body: JSON.stringify({
          agent_name: 'ouroboros_supervisor',
          thread_id:  SESSION_ID,
          prompt:     question,
          cadence:    cadence,
          metadata:   {source: 'chat_input'},
        }),
      });
      const j = await r.json();
      if (!r.ok) throw new Error(j.error || j.detail?.[0]?.msg || ('HTTP ' + r.status));
      const lid = j.loop?.id || '';
      addMessage(
        '🔁 Scheduled ' + cadence + ' · '
        + 'loop ' + (lid ? lid.slice(0, 16) + '…' : '?')
        + ' — manage at /cuga/loops/',
        'agent',
        'scheduled');
    } catch (err) {
      addMessage('Schedule failed: ' + err.message, 'error');
    } finally {
      scheduleBtn.disabled = false;
      sendBtn.disabled = false;
      scheduleBtn.textContent = original;
      inputEl.focus();
    }
  }

  // ── Past runs drawer ───────────────────────────────────────────
  const runsDrawer = document.getElementById('runsDrawer');
  const runsList   = document.getElementById('runsList');

  function toggleRunsDrawer() {
    const isOpen = runsDrawer.classList.toggle('open');
    if (isOpen) refreshRunsList();
  }

  function fmtTs(filename) {
    // 20260506T160919Z.json → 2026-05-06 16:09 UTC
    const m = /^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z/.exec(filename || '');
    if (!m) return filename;
    return m[1] + '-' + m[2] + '-' + m[3] + ' ' + m[4] + ':' + m[5] + ' UTC';
  }

  function agentPillsHtml(counts) {
    if (!counts) return '';
    const order = ['scout', 'voice_of_customer', 'site_auditor',
                   'revenue_estimator', 'person_finder', 'stack_scanner',
                   'pitch_email_writer'];
    const seen = new Set();
    let html = '';
    order.forEach(name => {
      const n = counts[name];
      if (!n) return;
      seen.add(name);
      const cls = name === 'scout' ? 'scout'
                : name === 'pitch_email_writer' ? 'writer'
                : '';
      const short = name === 'voice_of_customer' ? 'voc'
                  : name === 'site_auditor'      ? 'audit'
                  : name === 'revenue_estimator' ? 'revenue'
                  : name === 'person_finder'     ? 'person'
                  : name === 'stack_scanner'     ? 'stack'
                  : name === 'pitch_email_writer' ? 'writer'
                  : name;
      html += '<span class="agent-pill ' + cls + '">'
            + esc(short) + '×' + n + '</span>';
    });
    // Any other agents we didn't sort.
    Object.entries(counts).forEach(([name, n]) => {
      if (seen.has(name)) return;
      html += '<span class="agent-pill">' + esc(name) + '×' + n + '</span>';
    });
    return html;
  }

  // Drawer scope: 'thread' (default — runs for the current thread_id)
  // or 'all' (every run on disk across every thread).
  let _runsScope = 'thread';
  const scopeLabel    = document.getElementById('runsScopeLabel');
  const scopeToggleBtn = document.getElementById('scopeToggleBtn');

  function toggleRunsScope() {
    _runsScope = (_runsScope === 'thread') ? 'all' : 'thread';
    scopeLabel.textContent = (_runsScope === 'thread')
      ? 'Saved turns · this thread'
      : 'Saved turns · all threads on disk';
    scopeToggleBtn.textContent = (_runsScope === 'thread')
      ? 'All threads'
      : 'This thread';
    refreshRunsList();
  }

  async function refreshRunsList() {
    try {
      // /runs       → all threads (defensive: localStorage may be wiped)
      // /runs/<id>  → just the current thread
      const url = (_runsScope === 'all')
        ? '/runs'
        : '/runs/' + SESSION_ID;
      const res = await fetch(url);
      if (!res.ok) {
        runsList.className = 'empty';
        runsList.textContent = 'Could not load runs.';
        return;
      }
      const data = await res.json();
      const runs = data.runs || [];
      if (!runs.length) {
        runsList.className = 'empty';
        runsList.textContent = (_runsScope === 'all')
          ? 'No runs found anywhere on disk.'
          : 'No runs yet for this thread — ask a question, or click "All threads" to see prior sessions.';
        return;
      }
      runsList.className = '';
      runsList.innerHTML = '';
      // The /runs (all) endpoint already returns newest-first; the
      // per-thread endpoint sorts oldest-first, so we reverse there.
      const ordered = (_runsScope === 'all') ? runs : runs.slice().reverse();
      ordered.forEach((r) => {
        const item = document.createElement('div');
        item.className = 'run-item';
        const isLoop = (r.source === 'loop');
        if (isLoop) item.classList.add('run-item-loop');
        const pills = agentPillsHtml(r.agent_counts);
        const threadTag = (_runsScope === 'all' && r.thread_id)
          ? '<span class="agent-pill" style="margin-left:6px;color:var(--muted)">'
            + esc(r.thread_id.slice(0, 8)) + '</span>'
          : '';
        // Source badge: 🔁 loop (with link to loops UI) vs 👤 user.
        // Always rendered so the two are visually distinct at a glance.
        const sourceBadge = isLoop
          ? '<a class="src-badge src-loop" href="/cuga/loops/" target="_blank" '
            + 'onclick="event.stopPropagation()" '
            + 'title="Fired by loop ' + esc(r.loop_id || '') + ' — open loops dashboard">'
            + '🔁 loop' + (r.loop_id ? ' · ' + esc(r.loop_id.slice(0, 14)) : '')
            + '</a>'
          : '<span class="src-badge src-user" title="Manual user request">👤 user</span>';
        item.innerHTML =
          '<div class="row">' +
            sourceBadge +
          '  <span class="ts" title="' + esc(r.timestamp || '') + '">'
              + esc(fmtTs(r.file)) + '</span>' +
          (r.elapsed_human
            ? '<span class="elapsed">' + esc(r.elapsed_human) + '</span>'
            : '') +
          (r.leads_count != null
            ? '<span class="leads-pill">' + r.leads_count + ' leads</span>'
            : '') +
          threadTag +
          '</div>' +
          '<div class="question">' +
            esc(r.question || '(no question saved)') +
          '</div>' +
          (pills
            ? '<div class="trace-row">' + pills +
              '<span class="agent-pill" style="margin-left:auto;cursor:pointer;color:var(--accent3)" '
              + 'onclick="event.stopPropagation();openTrace(\'' + r.url + '\')">'
              + 'view trace</span></div>'
            : '');
        item.onclick = () => loadRun(r.url);
        runsList.appendChild(item);
      });
    } catch (err) {
      runsList.className = 'empty';
      runsList.textContent = 'Error loading runs: ' + err.message;
    }
  }

  // ── Agent trace modal ──────────────────────────────────────────
  const traceBackdrop = document.getElementById('traceBackdrop');
  const traceBody     = document.getElementById('traceBody');
  const traceMeta     = document.getElementById('traceMeta');

  async function openTrace(runUrl) {
    try {
      const res = await fetch(runUrl);
      if (!res.ok) return;
      const r = await res.json();
      const trace = (r.agent_trace || {}).calls || [];
      const counts = (r.agent_trace || {}).counts || {};
      traceMeta.textContent =
        (r.elapsed_human ? r.elapsed_human + ' · ' : '') +
        (trace.length + ' calls');
      let html = '';
      if (!trace.length) {
        html = '<div style="color:var(--muted);font-size:12px;padding:10px 0;">'
             + 'No agent calls recorded for this run.</div>';
      } else {
        trace.forEach((s) => {
          html +=
            '<div class="trace-step">' +
            '<span class="num">' + s.step + '.</span>' +
            '<span class="agent">' + esc(s.agent) + '</span>' +
            (s.has_output
              ? '<div class="preview">' + esc(s.output_preview || '') + '</div>'
              : '<div class="preview"><span class="badge">no output</span></div>') +
            '</div>';
        });
      }
      // Per-agent fan-out summary at the bottom.
      const summary = Object.entries(counts)
        .map(([k, v]) => esc(k) + ' × ' + v).join(' · ');
      if (summary) {
        html += '<div style="margin-top:14px;padding-top:10px;'
              + 'border-top:1px solid var(--border);font-size:11px;'
              + 'color:var(--muted);">Fan-out: ' + summary + '</div>';
      }
      traceBody.innerHTML = html;
      traceBackdrop.classList.add('open');
    } catch (err) {
      addMessage('Could not load trace: ' + err.message, 'error');
    }
  }

  function closeTrace() {
    traceBackdrop.classList.remove('open');
  }

  async function loadRun(url) {
    try {
      const res = await fetch(url);
      if (!res.ok) return;
      const r = await res.json();
      // Replay the turn into the chat panel + lead board.
      messagesEl.innerHTML = '';
      addMessage('▶ Replaying saved run from ' + fmtTs(url.split('/').pop()),
                 'thinking');
      if (r.question) addMessage(r.question, 'user');
      if (r.answer_full) {
        const meta = r.elapsed_human ? ('answered in ' + r.elapsed_human) : null;
        addMessage(r.answer_full, 'agent', meta);
      }
      // Replay into the right panel via refreshPanel.
      _lastHash = '';   // force re-render
      if (r.leads) {
        refreshPanel({ leads: r.leads });
      } else {
        emptyState.style.display = '';
        dataScroll.innerHTML = '';
        dataScroll.appendChild(emptyState);
      }
      runsDrawer.classList.remove('open');
    } catch (err) {
      addMessage('Could not load saved run: ' + err.message, 'error');
    }
  }

  // Close drawer on outside click.
  document.addEventListener('click', (e) => {
    if (!runsDrawer.classList.contains('open')) return;
    if (runsDrawer.contains(e.target)) return;
    if (e.target.id === 'runsBtn') return;
    runsDrawer.classList.remove('open');
  });

  // Initial population so the drawer isn't stale on first open.
  refreshRunsList();

  // ── Email-config panel (NB: distinct from the per-lead "draft email"
  //     modal whose names start with `email...`) ─────────────────────
  const emailCfgBackdrop = document.getElementById('emailCfgBackdrop');
  const emailCfgMsg      = document.getElementById('emailCfgMsg');

  async function openEmailCfgModal() {
    emailCfgMsg.textContent = '';
    emailCfgMsg.style.color = '';
    try {
      const r = await fetch('/email/config');
      if (!r.ok) throw new Error('failed to load config');
      const data = await r.json();
      const c = data.config;
      const e = data.effective;
      document.getElementById('ecRecipient').value      = c.recipient || '';
      document.getElementById('ecMinLeads').value       = c.min_leads ?? 0;
      document.getElementById('ecIncludeUser').checked  = c.include_user !== false;
      document.getElementById('ecIncludeLoop').checked  = c.include_loop !== false;
      document.getElementById('ecSmtpHost').value       = c.smtp_host || '';
      document.getElementById('ecSmtpPort').value       = c.smtp_port || '';
      document.getElementById('ecSmtpUsername').value   = c.smtp_username || '';
      const pwInput = document.getElementById('ecSmtpPassword');
      const pwState = document.getElementById('ecPwState');
      const hasSavedPw = (c.smtp_password === '•••');
      pwInput.value = '';
      if (hasSavedPw) {
        pwInput.placeholder = '••• saved — leave blank to keep, or type to replace';
        pwInput.style.borderColor = '#3fb950';
        pwState.innerHTML = '<span style="color:#3fb950">✓ saved</span>';
      } else {
        pwInput.placeholder = 'paste your gmail app-password here';
        pwInput.style.borderColor = '#f85149';
        pwState.innerHTML = '<span style="color:#f85149">⚠ required — no password saved yet</span>';
      }
      document.getElementById('ecSmtpFrom').value       = c.smtp_from || '';

      const status = document.getElementById('emailCfgStatus');
      status.innerHTML =
        '<strong>Effective SMTP:</strong> ' +
        (e.ready
          ? `<span style="color:#3fb950">✓ ${esc(e.host)}:${e.port} as ${esc(e.username)}, from ${esc(e.from)}</span>`
          : `<span style="color:#f85149">✗ incomplete — fill SMTP fields below or set env vars (SMTP_USERNAME, SMTP_PASSWORD, FROM_EMAIL)</span>`);
      emailCfgBackdrop.style.display = 'flex';
    } catch (err) {
      alert('Could not load email config: ' + err.message);
    }
  }
  function closeEmailCfgModal() { emailCfgBackdrop.style.display = 'none'; }

  function _ecCollect() {
    return {
      recipient:     document.getElementById('ecRecipient').value.trim(),
      min_leads:     parseInt(document.getElementById('ecMinLeads').value, 10) || 0,
      include_user:  document.getElementById('ecIncludeUser').checked,
      include_loop:  document.getElementById('ecIncludeLoop').checked,
      smtp_host:     document.getElementById('ecSmtpHost').value.trim(),
      smtp_port:     parseInt(document.getElementById('ecSmtpPort').value, 10) || 0,
      smtp_username: document.getElementById('ecSmtpUsername').value.trim(),
      smtp_password: document.getElementById('ecSmtpPassword').value, // empty = keep
      smtp_from:     document.getElementById('ecSmtpFrom').value.trim(),
    };
  }

  async function emailCfgSave() {
    const body = _ecCollect();
    try {
      const r = await fetch('/email/config', {
        method: 'POST',
        headers: {'content-type': 'application/json'},
        body: JSON.stringify(body),
      });
      if (!r.ok) throw new Error(await r.text());
      emailCfgMsg.style.color = '#3fb950';
      emailCfgMsg.textContent = body.recipient
        ? 'Saved. Emails will be sent automatically after each run.'
        : 'Saved. (No recipient set — emails are off.)';
      // Refresh the effective banner without re-opening
      const data = await (await fetch('/email/config')).json();
      const e = data.effective;
      document.getElementById('emailCfgStatus').innerHTML =
        '<strong>Effective SMTP:</strong> ' +
        (e.ready
          ? `<span style="color:#3fb950">✓ ${esc(e.host)}:${e.port} as ${esc(e.username)}, from ${esc(e.from)}</span>`
          : `<span style="color:#f85149">✗ incomplete</span>`);
    } catch (err) {
      emailCfgMsg.style.color = '#f85149';
      emailCfgMsg.textContent = 'Save failed: ' + err.message;
    }
  }

  async function emailCfgTest() {
    // Test using the form's CURRENT values — does NOT save first. This
    // lets you try creds before committing them.
    emailCfgMsg.style.color = '';
    emailCfgMsg.innerHTML = 'Sending test…';
    const body = _ecCollect();
    // Show what we're about to send (just lengths, never the password itself)
    console.log('[email/test] sending:', {
      recipient: body.recipient,
      smtp_host: body.smtp_host,
      smtp_port: body.smtp_port,
      smtp_username: body.smtp_username,
      smtp_password_chars: (body.smtp_password || '').length,
      smtp_from: body.smtp_from,
    });
    if (!body.recipient) {
      emailCfgMsg.style.color = '#f85149';
      emailCfgMsg.textContent = 'Recipient is empty — fill it in above first.';
      return;
    }
    try {
      const r = await fetch('/email/test', {
        method: 'POST',
        headers: {'content-type': 'application/json'},
        body: JSON.stringify(body),
      });
      const j = await r.json();
      console.log('[email/test] response:', j);
      if (!r.ok || !j.ok) {
        // FastAPI 422 returns {detail: [{loc, msg, ...}]}; our handler returns
        // {error, diag}. Surface whichever shape we got.
        let humanError = j.error;
        if (!humanError && Array.isArray(j.detail)) {
          humanError = 'validation failed: ' + j.detail.map(d =>
            `${(d.loc || []).slice(-1)[0]} → ${d.msg} (got ${JSON.stringify(d.input)})`
          ).join('; ');
        }
        if (!humanError) humanError = 'HTTP ' + r.status;
        let msg = '<strong style="color:#f85149">Test failed:</strong> ' + esc(humanError);
        const debugObj = j.diag || j.detail;
        if (debugObj) {
          msg += '<details style="margin-top:6px;color:#888;font-size:11px">'
               + '<summary style="cursor:pointer">diagnostics</summary>'
               + '<pre style="margin:4px 0;background:#0d1117;padding:6px;'
               + 'border-radius:4px;overflow-x:auto">'
               + esc(JSON.stringify(debugObj, null, 2))
               + '</pre></details>';
        }
        emailCfgMsg.innerHTML = msg;
        return;
      }
      emailCfgMsg.style.color = '#3fb950';
      emailCfgMsg.textContent = '✓ Test sent — ' + j.info;
    } catch (err) {
      emailCfgMsg.style.color = '#f85149';
      emailCfgMsg.textContent = 'Test failed: ' + err.message;
    }
  }
</script>
</body>
</html>
"""
