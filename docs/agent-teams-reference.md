# Agent Teams — Master Reference Guide

Source: https://code.claude.com/docs/en/agent-teams  
Claude Code minimum version with current behavior: v2.1.178

---

## What Are Agent Teams?

Agent teams coordinate multiple Claude Code instances working together. One session acts as the **team lead** — it spawns teammates, coordinates work, and synthesizes results. Each **teammate** is a fully independent Claude Code session with its own context window and can communicate directly with any other teammate.

This is distinct from subagents, which only report back to the main agent and cannot talk to each other.

**Enable with:**
```json
{
  "env": {
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"
  }
}
```
Without this flag: no team is set up, no team directories are written, and Claude will not spawn or propose teammates.

---

## When to Use Agent Teams

### Best use cases (parallel exploration adds real value)
- **Research and review** — multiple teammates investigate different aspects simultaneously, then challenge each other's findings
- **New modules or features** — teammates each own a separate piece with no overlap
- **Debugging with competing hypotheses** — teammates test different theories in parallel, converge faster
- **Cross-layer coordination** — changes spanning frontend, backend, and tests, each owned by a different teammate

### When NOT to use agent teams (use a single session or subagents instead)
- Sequential tasks with strong dependencies
- Same-file edits (causes overwrites)
- Work where coordination overhead exceeds the parallelism benefit
- Routine tasks where token cost doesn't justify the parallel speedup

---

## Agent Teams vs. Subagents

| | Subagents | Agent Teams |
|---|---|---|
| **Context** | Own context window; results return to caller | Own context window; fully independent |
| **Communication** | Report results back to main agent only | Teammates message each other directly |
| **Coordination** | Main agent manages all work | Shared task list with self-coordination |
| **Best for** | Focused tasks where only the result matters | Complex work requiring discussion and collaboration |
| **Token cost** | Lower — results summarized back to main context | Higher — each teammate is a separate Claude instance |

**Rule of thumb:** Use subagents when you need quick, focused workers that report back. Use agent teams when teammates need to share findings, challenge each other, and coordinate on their own.

---

## Architecture

```
Team Lead (main session)
├── Shared Task List  (~/.claude/tasks/{team-name}/)
├── Mailbox / Messaging system
└── Teammates (each = independent Claude Code session)
    ├── Teammate A
    ├── Teammate B
    └── Teammate C
```

### Storage locations
| Path | Contents | Persistence |
|---|---|---|
| `~/.claude/teams/{team-name}/config.json` | Runtime state (session IDs, tmux pane IDs) | Deleted when session ends |
| `~/.claude/tasks/{team-name}/` | Task list | Persists for resumed sessions |

Team name format: `session-` + first 8 characters of the session ID.

**Do not hand-edit `config.json`** — it is overwritten on every state update.

Task list directories are governed by the same `cleanupPeriodDays` setting as session transcripts.

---

## Display Modes

| Mode | Description | Requires |
|---|---|---|
| `in-process` (default) | All teammates inside your main terminal; use arrow keys + Enter to navigate | Any terminal |
| `auto` | Split panes when in tmux/iTerm2, falls back to in-process | tmux or iTerm2 |
| `tmux` | Split panes, auto-detects tmux or iTerm2 | tmux or iTerm2 |
| `iterm2` | iTerm2 native split panes explicitly | `it2` CLI + iTerm2 Python API |

Set globally in `~/.claude/settings.json`:
```json
{ "teammateMode": "auto" }
```

Set for a single session:
```bash
claude --teammate-mode auto
```

### In-process mode controls
- **Up/Down arrows** — select a teammate in the agent panel
- **Enter** — open selected teammate's transcript and message them
- **Escape** — interrupt selected teammate's current turn
- **x** (on selected teammate) — stop that teammate
- **Ctrl+T** — toggle the task list

Idle teammate rows hide after 30 seconds and reappear on next turn. The teammate keeps running; send it a message by name to bring the row back.

### Split pane requirements
- **tmux**: install via package manager; `tmux -CC` in iTerm2 is the recommended entry point
- **iTerm2**: install [`it2` CLI](https://github.com/mkusaka/it2); enable Python API in iTerm2 → Settings → General → Magic

Split panes are **not supported** in VS Code integrated terminal, Windows Terminal, or Ghostty.

---

## Task System

Tasks have three states: **pending → in progress → completed**.

Tasks can have **dependencies** — a pending task with unresolved dependencies cannot be claimed until those dependencies are completed. When a dependency completes, blocked tasks unblock automatically.

**Task claiming uses file locking** to prevent race conditions when multiple teammates try to claim the same task simultaneously.

### Assignment modes
- **Lead assigns** — tell the lead which task to give to which teammate
- **Self-claim** — after finishing a task, a teammate picks up the next unassigned, unblocked task on its own

### Sizing tasks
- **Too small** — coordination overhead exceeds the benefit
- **Too large** — teammates work too long without check-ins, risk of wasted effort
- **Just right** — self-contained units with a clear deliverable (a function, a test file, a review)

**Target:** 5–6 tasks per teammate keeps everyone productive without excessive context switching.

---

## Communication Between Agents

- **Automatic message delivery** — messages sent between teammates are delivered automatically; the lead does not need to poll
- **Idle notifications** — when a teammate finishes and stops, it automatically notifies the lead
- **Shared task list** — all agents see task status and can claim available work
- **Targeted messaging** — send to one specific teammate by name; to reach everyone, send one message per recipient

The lead assigns each teammate a name at spawn time. To get predictable names you can reference in later prompts, specify names explicitly in your spawn instruction.

---

## Teammate Context

Each teammate loads on spawn:
- Project CLAUDE.md files (from working directory)
- MCP servers (from project and user settings)
- Skills (from project and user settings)
- The spawn prompt from the lead

**What teammates do NOT inherit:**
- The lead's conversation history
- Skills and MCP servers from subagent definition frontmatter (those only apply to subagent mode)

---

## Subagent Definitions as Teammate Roles

You can reference a [subagent](https://code.claude.com/docs/en/sub-agents) type when spawning a teammate to give it a predefined role (security-reviewer, test-runner, etc.):

```text
Spawn a teammate using the security-reviewer agent type to audit the auth module.
```

When used as a teammate:
- The definition's `tools` allowlist and `model` are honored
- The definition's body is **appended** to the teammate's system prompt (not replacing it)
- Team coordination tools (`SendMessage`, task management tools) are **always available** even when `tools` restricts others
- `skills` and `mcpServers` frontmatter fields are **not applied** — teammates load those from project/user settings

---

## Models and Effort

- Teammates do **not** inherit the lead's `/model` selection by default
- Set **Default teammate model** in `/config`, or choose **Default (leader's model)** to follow the lead's model
- Teammates **do** inherit the lead's effort level (as of v2.1.186 for split-pane mode)
- Specify models explicitly in the spawn prompt: `"Spawn 4 teammates... use Sonnet for each teammate"`

---

## Permissions

- Teammates start with the lead's permission settings
- If the lead runs with `--dangerously-skip-permissions`, all teammates do too
- After spawning, you can change individual teammate modes
- You cannot set per-teammate modes at spawn time

**Tip:** Pre-approve common operations in permission settings before spawning teammates to reduce friction from permission prompts bubbling up to the lead.

---

## Plan Approval for Teammates

For complex or risky tasks, require teammates to plan before implementing:

```text
Spawn an architect teammate to refactor the authentication module.
Require plan approval before they make any changes.
```

Flow:
1. Teammate works in read-only plan mode
2. Teammate sends plan approval request to lead
3. Lead reviews: approves or rejects with feedback
4. If rejected → teammate revises and resubmits
5. If approved → teammate exits plan mode and begins implementation

The lead makes approval decisions autonomously. Influence its judgment via prompt criteria: *"only approve plans that include test coverage"*, *"reject plans that modify the database schema."*

---

## Hooks for Agent Teams

| Hook | Trigger | Use |
|---|---|---|
| `TeammateIdle` | Teammate about to go idle | Exit code 2 to send feedback and keep teammate working |
| `TaskCreated` | Task being created | Exit code 2 to prevent creation and send feedback |
| `TaskCompleted` | Task being marked complete | Exit code 2 to prevent completion and send feedback |

Hook payloads include a `team_name` field (deprecated; carries session-derived name).

---

## Token Cost Guidance

Token usage scales linearly with the number of active teammates — each has its own context window. Agent teams use **significantly more tokens** than a single session.

Worth the cost for: research, review, new feature work with clear parallelism.
Not worth the cost for: routine tasks, sequential work, same-file edits.

---

## Team Size Guidelines

- **Start with 3–5 teammates** for most workflows — balances parallel work with manageable coordination
- **5–6 tasks per teammate** is the productive sweet spot
- If you have 15 independent tasks, 3 teammates is a good starting point
- Scale up only when work genuinely benefits from simultaneous teammates
- Three focused teammates often outperform five scattered ones

---

## Spawning Teammates

How teammates get created:
1. **You request them** — describe the task and teammates in natural language; Claude spawns them per your instructions
2. **Claude proposes them** — Claude determines parallel work would help and suggests spawning; you confirm before it proceeds

Claude will never spawn teammates without your approval.

---

## Shutting Down Teammates

Refer to the teammate by name:
```text
Ask the researcher teammate to shut down
```

The lead sends a shutdown request. The teammate can approve (exits gracefully) or reject with an explanation.

Team shared directories clean up automatically when the session ends — no separate cleanup step needed.

---

## Effective Prompting Patterns

### Parallel code review with distinct lenses
```text
Spawn three teammates to review PR #142:
- One focused on security implications
- One checking performance impact
- One validating test coverage
Have them each review and report findings.
```

### Competing hypothesis investigation (adversarial debate)
```text
Users report the app exits after one message instead of staying connected.
Spawn 5 agent teammates to investigate different hypotheses. Have them talk to
each other to try to disprove each other's theories, like a scientific debate.
Update the findings doc with whatever consensus emerges.
```

### Parallel implementation with named roles
```text
Spawn 4 teammates to refactor these modules in parallel. Use Sonnet for each teammate.
```

### Rich spawn prompts (give teammates enough context)
```text
Spawn a security reviewer teammate with the prompt: "Review the authentication module
at src/auth/ for security vulnerabilities. Focus on token handling, session
management, and input validation. The app uses JWT tokens stored in httpOnly cookies.
Report any issues with severity ratings."
```

### Keeping the lead from doing work itself
```text
Wait for your teammates to complete their tasks before proceeding
```

---

## Known Limitations

| Limitation | Detail |
|---|---|
| No session resumption with in-process teammates | `/resume` and `/rewind` don't restore in-process teammates; tell lead to spawn new ones |
| Task status can lag | Teammates sometimes fail to mark tasks complete, blocking dependent tasks; nudge manually |
| Slow shutdown | Teammates finish current request/tool call before shutting down |
| One team per session | Can't create additional named teams or share a team across sessions |
| No nested teams | Teammates cannot spawn their own teammates; only the lead manages the team |
| Fixed lead | Can't promote a teammate to lead or transfer leadership |
| Permissions set at spawn | Can change individual modes after spawning, but not at spawn time |
| Split panes limited | Not supported in VS Code integrated terminal, Windows Terminal, or Ghostty |

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Teammates not appearing | Check agent panel (arrow keys); idle rows hide after 30s — send message by name to surface; verify task was complex enough to warrant a team |
| Too many permission prompts | Pre-approve common operations in permission settings before spawning |
| Teammate stopped on error | Select in agent panel → Enter to view; give additional instructions or spawn a replacement |
| Lead shuts down before work is done | Tell lead to keep going; instruct it to wait for teammates before proceeding |
| Orphaned tmux sessions | `tmux ls` then `tmux kill-session -t <session-name>` |

---

## Quick Decision Tree

```
Is the work parallelizable?
├── No → Single session
└── Yes
    ├── Do workers need to talk to each other?
    │   ├── No → Subagents
    │   └── Yes → Agent Teams
    └── Are there same-file edits?
        ├── Yes → Split by file ownership first, then Agent Teams
        └── No → Agent Teams
```

---

## CLAUDE.md Integration

CLAUDE.md works normally with agent teams. Teammates read CLAUDE.md files from their working directory. Use this to provide project-specific guidance that applies uniformly to all teammates without repeating it in every spawn prompt.
