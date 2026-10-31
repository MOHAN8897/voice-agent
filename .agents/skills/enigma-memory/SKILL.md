---
name: enigma-memory
description: Local-first verifiable context delivery infrastructure and sovereign memory passport for AI coding agents. Use when remembering architectural decisions, recording gotchas and tribal knowledge across sessions, querying project context packs, or checking memory health.
---

# Enigma Memory Skill

## Overview
Enigma Memory (`enigma-memory`) provides local-first, offline-verifiable AI memory and context delivery. It gives agents persistent episodic and procedural memory across sessions, backed by an encrypted local vault (`.enigma/bundle.json`) with cryptographic receipt provenance.

## Available CLI Commands
Run through npm or npx from the repository root:

- **Status & Health**:
  ```bash
  npm run enigma:status
  # Or:
  npx enigma passport status --bundle .enigma/bundle.json --passphrase-file .enigma/passphrase
  ```

- **Remembering State & Decisions**:
  ```bash
  npx enigma remember --bundle .enigma/bundle.json --passphrase-file .enigma/passphrase --text "<memory content>"
  ```

- **Recalling / Searching Memory**:
  ```bash
  npx enigma search --bundle .enigma/bundle.json --passphrase-file .enigma/passphrase --query "<search term>"
  ```

- **Export & Verification**:
  ```bash
  npm run enigma:verify
  # Or:
  npx enigma verify --export .enigma/export.json
  ```

- **Compiling Context Pack**:
  ```bash
  npx enigma context --bundle .enigma/bundle.json --passphrase-file .enigma/passphrase --out .enigma/context-pack.json
  ```

## MCP Tools Integration
Enigma Memory operates as an MCP server (`enigma-mcp`) configured in `.cursor/mcp.json`:
- `enigma_init`: Initialize or inspect vault bundle.
- `enigma_remember`: Save facts, architectural decisions, and bug workarounds.
- `enigma_search`: Query semantic memories with strict relevance and redaction.
- `enigma_context_pack`: Compile context for agent sessions.
- `enigma_delete`: Tombstone deprecated or invalid memories.
- `enigma_verify_receipts`: Verify cryptographic receipts and Merkle root integrity.

## Best Practices
1. **Never commit `.enigma/passphrase`**: Keep passphrase files local and git-ignored.
2. **Atomic Context**: Save clear, concise architectural decisions rather than raw full-file dumps.
3. **Verify Integrity**: Run `npm run enigma:verify` periodically to audit receipt logs.
