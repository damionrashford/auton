#!/usr/bin/env node
const { execSync, spawn } = require('child_process'), fs = require('fs'), path = require('path')
const { resolve, dirname, join, basename } = path

// --- Config (config.json > env vars) ---
const CFG_PATH = resolve(__dirname, 'config.json')
const CFG = (() => { try { return JSON.parse(fs.readFileSync(CFG_PATH, 'utf8')) } catch { return {} } })()
const API_KEY = CFG.llm?.apiKey || process.env.API_KEY
const API_URL = CFG.llm?.apiUrl || process.env.API_URL || 'https://api.openai.com/v1'
const MODEL = CFG.llm?.model || process.env.MODEL || 'gpt-4o'
const MAX_TURNS = CFG.agent?.maxTurns || 25
const DAEMON_INTERVAL = (CFG.agent?.daemonInterval || 30) * 1000
const STATE = resolve(__dirname, 'state.json')
const HOME = process.env.HOME || process.env.USERPROFILE || '~'
if (!API_KEY) { console.error('Set llm.apiKey in config.json or API_KEY env var'); process.exit(1) }

// --- State ---
let S = { memory: {}, goals: [], schedule: [], log: [], mcp: {}, skills_dirs: [] }
const load = () => { try { S = JSON.parse(fs.readFileSync(STATE, 'utf8')) } catch {} }
const save = () => fs.writeFileSync(STATE, JSON.stringify(S, null, 2))
const slog = (a, r) => { S.log.push({ ts: new Date().toISOString(), a, r: String(r).slice(0, 200) }); if (S.log.length > 50) S.log = S.log.slice(-50) }

// =========================================================================
//  YAML FRONTMATTER PARSER  (proper parser, not regex)
// =========================================================================
function parseFrontmatter(text) {
  const lines = text.split('\n')
  let start = -1, end = -1
  for (let i = 0; i < lines.length; i++) { if (lines[i].trim() === '---') { if (start < 0) start = i; else { end = i; break } } }
  if (start < 0 || end < 0) return null
  return { meta: parseYamlBlock(lines.slice(start + 1, end), 0), body: lines.slice(end + 1).join('\n').trim() }
}

function parseYamlBlock(lines, minIndent) {
  const result = {}; let i = 0
  while (i < lines.length) {
    const raw = lines[i]
    if (!raw.trim() || raw.trim()[0] === '#') { i++; continue }
    const indent = raw.length - raw.trimStart().length
    if (indent < minIndent) break
    const trimmed = raw.trim(), colonIdx = trimmed.indexOf(':')
    if (colonIdx < 0) { i++; continue }
    const key = trimmed.slice(0, colonIdx).trim()
    let val = trimmed.slice(colonIdx + 1).trim()
    // Block scalar: | or >
    if (val === '|' || val === '>') {
      const join = val === '|' ? '\n' : ' ', parts = []; i++
      while (i < lines.length && (lines[i].trim() === '' || (lines[i].length - lines[i].trimStart().length) > indent)) { parts.push(lines[i].trimStart()); i++ }
      result[key] = parts.join(join).trim(); continue
    }
    // Empty value → check for nested map
    if (!val && i + 1 < lines.length) {
      const nxt = lines[i + 1]; const nxtIndent = nxt.length - nxt.trimStart().length
      if (nxt.trim() && nxtIndent > indent) {
        const nested = []; i++
        while (i < lines.length && (lines[i].trim() === '' || (lines[i].length - lines[i].trimStart().length) > indent)) { nested.push(lines[i]); i++ }
        result[key] = parseYamlBlock(nested, indent + 1); continue
      }
    }
    // Strip surrounding quotes
    if (val.length >= 2 && ((val[0] === '"' && val.at(-1) === '"') || (val[0] === "'" && val.at(-1) === "'"))) val = val.slice(1, -1)
    result[key] = val; i++
  }
  return result
}

// =========================================================================
//  AGENT SKILLS  (progressive disclosure: catalog → instructions → resources)
// =========================================================================
let skillCatalog = [] // { name, description, dir, path, compatibility, allowedTools }

function getSkillsDirs() {
  const dirs = [
    resolve(__dirname, 'skills'),                  // project-level
    resolve(HOME, '.agents', 'skills'),            // user-level (cross-client standard)
  ]
  if (process.env.SKILLS_DIR) process.env.SKILLS_DIR.split(',').forEach(d => dirs.push(resolve(d.trim())))
  if (S.skills_dirs) S.skills_dirs.forEach(d => dirs.push(resolve(d)))
  return [...new Set(dirs)]
}

function discoverSkills() {
  skillCatalog = []; const seen = new Map() // name → priority (lower = higher precedence)
  const dirs = getSkillsDirs()
  for (let priority = 0; priority < dirs.length; priority++) {
    const base = dirs[priority]
    if (!fs.existsSync(base)) continue
    let entries
    try { entries = fs.readdirSync(base, { withFileTypes: true }) } catch { continue }
    for (const e of entries) {
      if (!e.isDirectory() || e.name === '.git' || e.name === 'node_modules') continue
      const skillMd = join(base, e.name, 'SKILL.md')
      if (!fs.existsSync(skillMd)) continue
      try {
        const parsed = parseFrontmatter(fs.readFileSync(skillMd, 'utf8'))
        if (!parsed || !parsed.meta) continue
        const name = parsed.meta.name || e.name
        const desc = parsed.meta.description
        if (!desc) continue // description is required per spec
        // Project-level overrides user-level (lower priority index wins)
        if (seen.has(name) && seen.get(name) <= priority) continue
        seen.set(name, priority)
        // Remove previous entry if shadowed
        skillCatalog = skillCatalog.filter(s => s.name !== name)
        skillCatalog.push({
          name, description: desc, dir: join(base, e.name), path: skillMd,
          compatibility: parsed.meta.compatibility || null,
          allowedTools: parsed.meta['allowed-tools'] || null
        })
      } catch {}
    }
  }
  if (skillCatalog.length) console.log(`  📦 Skills: ${skillCatalog.map(s => s.name).join(', ')}`)
}

function activateSkill(name) {
  const skill = skillCatalog.find(s => s.name === name)
  if (!skill) return `Skill "${name}" not found. Available: ${skillCatalog.map(s => s.name).join(', ')}`
  const parsed = parseFrontmatter(fs.readFileSync(skill.path, 'utf8'))
  if (!parsed) return `Failed to parse ${skill.path}`
  // List bundled resources (tier 3 — not loaded yet, just listed)
  const resources = []
  for (const sub of ['scripts', 'references', 'assets']) {
    const subDir = join(skill.dir, sub)
    if (!fs.existsSync(subDir)) continue
    try { fs.readdirSync(subDir, { recursive: true }).forEach(f => resources.push(`${sub}/${f}`)) } catch {}
  }
  const resSection = resources.length ? `\n\nBundled resources (read with skill action:"read"):\n${resources.map(r => `  - ${r}`).join('\n')}` : ''
  return `<skill_content name="${name}">\n${parsed.body}\n\nSkill directory: ${skill.dir}\nRelative paths in this skill resolve from the skill directory.${resSection}\n</skill_content>`
}

function readSkillFile(name, file) {
  const skill = skillCatalog.find(s => s.name === name)
  if (!skill) return `Skill "${name}" not found`
  const target = resolve(skill.dir, file)
  // Security: must be within skill directory
  if (!target.startsWith(skill.dir)) return 'ERROR: Path escapes skill directory'
  try { return fs.readFileSync(target, 'utf8') } catch (e) { return `ERROR: ${e.message}` }
}

function installSkill(source, targetDir) {
  const dest = targetDir || resolve(__dirname, 'skills')
  fs.mkdirSync(dest, { recursive: true })
  if (source.startsWith('http') || source.includes('github.com')) {
    try { execSync(`git clone --depth 1 "${source}" "${join(dest, basename(source).replace('.git', ''))}"`, { encoding: 'utf8', timeout: 30000 }); return 'Installed. Run skill list to see it.' } catch (e) { return `ERROR: ${e.message}` }
  }
  // Local path — copy
  const src = resolve(source)
  if (!fs.existsSync(src)) return `Source not found: ${src}`
  const name = basename(src)
  try { execSync(`cp -r "${src}" "${join(dest, name)}"`, { encoding: 'utf8' }); return 'Installed.' } catch (e) { return `ERROR: ${e.message}` }
}

function buildSkillCatalogPrompt() {
  if (!skillCatalog.length) return ''
  const items = skillCatalog.map(s => {
    let line = `  <skill name="${s.name}">${s.description}</skill>`
    return line
  }).join('\n')
  return `\n\n<available_skills>\n${items}\n</available_skills>\nTo use a skill, call the skill tool with action "activate" and the skill name. The skill's full instructions will be returned. Follow them.`
}

// =========================================================================
//  MCP TRANSPORTS  (stdio + Streamable HTTP/SSE)
// =========================================================================
function mcpStdio(command, args = [], env = {}) {
  const proc = spawn(command, args, { env: { ...process.env, ...env }, stdio: ['pipe', 'pipe', 'pipe'] })
  const pending = {}; let buf = '', nid = 1
  proc.stdout.on('data', chunk => {
    buf += chunk; const lines = buf.split('\n'); buf = lines.pop()
    for (const l of lines) { if (!l.trim()) continue; try { const m = JSON.parse(l); if (m.id in pending) { pending[m.id](m); delete pending[m.id] } } catch {} }
  })
  proc.stderr.on('data', d => process.stderr.write(`[mcp:stderr] ${d}`))
  return {
    request(method, params) { const id = nid++; proc.stdin.write(JSON.stringify({ jsonrpc: '2.0', id, method, params }) + '\n'); return new Promise((y, n) => { pending[id] = y; setTimeout(() => { delete pending[id]; n(new Error('MCP timeout')) }, 30000) }) },
    notify(method, params) { proc.stdin.write(JSON.stringify({ jsonrpc: '2.0', method, params }) + '\n') },
    close() { proc.kill() }
  }
}

function mcpHttp(url) {
  let sid = null, nid = 1
  return {
    async request(method, params) {
      const h = { 'Content-Type': 'application/json', Accept: 'application/json, text/event-stream' }
      if (sid) h['mcp-session-id'] = sid
      const r = await fetch(url, { method: 'POST', headers: h, body: JSON.stringify({ jsonrpc: '2.0', id: nid++, method, params }) })
      const s = r.headers.get('mcp-session-id'); if (s) sid = s
      if ((r.headers.get('content-type') || '').includes('text/event-stream')) {
        for (const line of (await r.text()).split('\n'))
          if (line.startsWith('data: ')) try { const d = JSON.parse(line.slice(6)); if ('result' in d || 'error' in d) return d } catch {}
        throw new Error('No result in SSE stream')
      }
      return r.json()
    },
    notify(method, params) { const h = { 'Content-Type': 'application/json' }; if (sid) h['mcp-session-id'] = sid; fetch(url, { method: 'POST', headers: h, body: JSON.stringify({ jsonrpc: '2.0', method, params }) }).catch(() => {}) },
    close() {}
  }
}

// =========================================================================
//  MCP CLIENT
// =========================================================================
const mcpConns = {}

async function mcpConnect(name, cfg) {
  if (mcpConns[name]) { mcpConns[name].transport.close(); delete mcpConns[name] }
  const transport = cfg.url ? mcpHttp(cfg.url) : mcpStdio(cfg.command, cfg.args || [], cfg.env || {})
  await transport.request('initialize', { protocolVersion: '2025-03-26', capabilities: {}, clientInfo: { name: 'auto-agent', version: '1.0' } })
  transport.notify('notifications/initialized')
  const res = await transport.request('tools/list', {})
  const list = res.result?.tools || res.tools || []
  for (const t of list) {
    const fn = `${name}__${t.name}`
    tools[fn] = { desc: `[MCP:${name}] ${t.description || t.name}`, schema: t.inputSchema,
      fn: async (args) => { const r = await transport.request('tools/call', { name: t.name, arguments: args }); if (r.error) return `ERROR: ${r.error.message}`; return (r.result?.content || []).map(c => c.text ?? JSON.stringify(c)).join('\n') || 'OK' } }
  }
  mcpConns[name] = { transport, tools: list.map(t => `${name}__${t.name}`) }
  console.log(`  ⚙ MCP "${name}": ${list.map(t => t.name).join(', ') || '(no tools)'}`)
}

function mcpDisconnect(name) {
  if (!mcpConns[name]) return 'Not connected'
  mcpConns[name].transport.close(); for (const t of mcpConns[name].tools) delete tools[t]
  delete mcpConns[name]; return 'Disconnected'
}

async function mcpInit() {
  const servers = { ...S.mcp }
  if (process.env.MCP_SERVERS) try { Object.assign(servers, JSON.parse(process.env.MCP_SERVERS)) } catch {}
  for (const [name, cfg] of Object.entries(servers)) {
    try { await mcpConnect(name, cfg) } catch (e) { console.error(`  ✗ MCP "${name}": ${e.message}`) }
  }
}

// =========================================================================
//  BUILT-IN TOOLS
// =========================================================================
const tools = {
  shell: {
    desc: 'Execute a shell command', params: { command: { type: 'string', description: 'The shell command' } },
    fn: ({ command }) => { try { return execSync(command, { encoding: 'utf8', timeout: 30000, maxBuffer: 1024 * 1024 }).trim() } catch (e) { return `ERROR: ${e.message}` } }
  },
  read_file: {
    desc: 'Read a file', params: { path: { type: 'string', description: 'File path' } },
    fn: ({ path: p }) => { try { return fs.readFileSync(resolve(p), 'utf8') } catch (e) { return `ERROR: ${e.message}` } }
  },
  write_file: {
    desc: 'Write to a file (creates dirs)', params: { path: { type: 'string', description: 'File path' }, content: { type: 'string', description: 'Content' } },
    fn: ({ path: p, content }) => { const fp = resolve(p); fs.mkdirSync(dirname(fp), { recursive: true }); fs.writeFileSync(fp, content); return 'OK' }
  },
  http: {
    desc: 'HTTP request', params: { url: { type: 'string', description: 'URL' }, method: { type: 'string', description: 'HTTP method (optional, default GET)' }, body: { type: 'string', description: 'Request body (optional)' } },
    fn: async ({ url, method = 'GET', body }) => { try { const r = await fetch(url, { method, body: body || undefined, headers: body ? { 'Content-Type': 'application/json' } : {} }); return await r.text() } catch (e) { return `ERROR: ${e.message}` } }
  },
  store: {
    desc: 'Store a value in persistent memory', params: { key: { type: 'string', description: 'Key' }, value: { type: 'string', description: 'Value' } },
    fn: ({ key, value }) => { S.memory[key] = value; save(); return 'Stored' }
  },
  recall: {
    desc: 'Recall from memory ("all" lists keys)', params: { key: { type: 'string', description: 'Key or "all"' } },
    fn: ({ key }) => key === 'all' ? JSON.stringify(S.memory, null, 2) : (S.memory[key] ?? 'NOT FOUND')
  },
  goal: {
    desc: 'Manage goals: set|complete|list|remove', params: { action: { type: 'string', description: 'set|complete|list|remove' }, text: { type: 'string', description: 'Goal text or ID' }, priority: { type: 'string', description: 'high|medium|low (optional)' } },
    fn: ({ action, text, priority = 'medium' }) => {
      if (action === 'list') return JSON.stringify(S.goals, null, 2)
      if (action === 'set') { const g = { id: Date.now().toString(36), text, status: 'active', priority, created: new Date().toISOString() }; S.goals.push(g); save(); return `Goal set: ${g.id}` }
      if (action === 'complete') { const g = S.goals.find(x => x.id === text); if (g) { g.status = 'done'; save(); return 'Done' } return 'Not found' }
      if (action === 'remove') { S.goals = S.goals.filter(x => x.id !== text); save(); return 'Removed' }
      return 'Unknown action'
    }
  },
  schedule: {
    desc: 'Schedule recurring tasks: set|list|remove', params: { action: { type: 'string', description: 'set|list|remove' }, every: { type: 'string', description: 'Interval: 30s, 5m, 1h, 1d (optional)' }, task: { type: 'string', description: 'Task description (optional)' }, id: { type: 'string', description: 'Schedule ID for remove (optional)' } },
    fn: ({ action, every, task, id }) => {
      if (action === 'list') return JSON.stringify(S.schedule, null, 2)
      if (action === 'set') { const s = { id: Date.now().toString(36), every, task, next: Date.now() + parseMs(every) }; S.schedule.push(s); save(); return `Scheduled: ${s.id}` }
      if (action === 'remove') { S.schedule = S.schedule.filter(x => x.id !== id); save(); return 'Removed' }
      return 'Unknown action'
    }
  },
  skill: {
    desc: 'Agent Skills: discover and use specialized capabilities. Actions: list (show all skills), activate (load full instructions for a skill), read (read a file from a skill directory), install (install from git URL or local path), refresh (re-scan skill directories)',
    params: {
      action: { type: 'string', description: 'list|activate|read|install|refresh' },
      name: { type: 'string', description: 'Skill name (for activate/read) (optional)' },
      file: { type: 'string', description: 'Relative file path within skill dir (for read) (optional)' },
      source: { type: 'string', description: 'Git URL or local path (for install) (optional)' }
    },
    fn: ({ action, name, file, source }) => {
      if (action === 'list') return skillCatalog.length ? skillCatalog.map(s => `${s.name}: ${s.description}${s.compatibility ? ` [${s.compatibility}]` : ''}`).join('\n') : 'No skills installed.'
      if (action === 'activate') return activateSkill(name)
      if (action === 'read') return readSkillFile(name, file)
      if (action === 'install') { const r = installSkill(source); discoverSkills(); return r }
      if (action === 'refresh') { discoverSkills(); return `Found ${skillCatalog.length} skills.` }
      return 'Unknown action. Use: list, activate, read, install, refresh'
    }
  },
  mcp_connect: {
    desc: 'Connect to an MCP server (stdio or HTTP/SSE)', params: { name: { type: 'string', description: 'Server name' }, command: { type: 'string', description: 'Command for stdio (optional)' }, args: { type: 'string', description: 'Comma-separated args for stdio (optional)' }, url: { type: 'string', description: 'URL for HTTP/SSE (optional)' } },
    fn: async ({ name, command, args, url }) => {
      const cfg = url ? { url } : { command, args: args ? args.split(',').map(s => s.trim()) : [] }
      try { await mcpConnect(name, cfg); S.mcp[name] = cfg; save(); return `Connected to ${name}` } catch (e) { return `ERROR: ${e.message}` }
    }
  },
  mcp_disconnect: {
    desc: 'Disconnect an MCP server', params: { name: { type: 'string', description: 'Server name' } },
    fn: ({ name }) => { const r = mcpDisconnect(name); delete S.mcp[name]; save(); return r }
  }
}

const parseMs = s => { const m = s.match(/^(\d+)(s|m|h|d)$/); if (!m) return 60000; return parseInt(m[1]) * { s: 1e3, m: 6e4, h: 36e5, d: 864e5 }[m[2]] }

// =========================================================================
//  LLM INTERFACE
// =========================================================================
const getSchema = () => Object.entries(tools).map(([name, t]) => ({
  type: 'function', function: { name, description: t.desc,
    parameters: t.schema || { type: 'object', properties: t.params, required: Object.keys(t.params).filter(k => !t.params[k].description?.includes('optional')) } }
}))

const system = () => {
  const goals = S.goals.filter(g => g.status === 'active')
  const mem = Object.keys(S.memory).length ? `\nMemory: ${JSON.stringify(S.memory)}` : ''
  const sched = S.schedule.length ? `\nScheduled: ${JSON.stringify(S.schedule)}` : ''
  const g = goals.length ? `\nActive goals:\n${goals.map(x => `- [${x.priority}] ${x.text} (${x.id})`).join('\n')}` : '\nNo active goals.'
  const mcp = Object.keys(mcpConns).length ? `\nMCP servers: ${Object.keys(mcpConns).join(', ')}` : ''
  const skills = buildSkillCatalogPrompt()
  return `You are an autonomous AI agent on ${process.platform} (cwd: ${process.cwd()}).
You act independently. Decide what to do, execute tools, keep going until done.
Tools prefixed "servername__" are from MCP servers. You can connect new ones with mcp_connect.
When your task is fully complete, respond with text only (no tool calls) to stop.
Think step by step. If something fails, try another approach.${g}${mem}${sched}${mcp}${skills}
Time: ${new Date().toISOString()}`
}

async function think(messages) {
  const r = await fetch(`${API_URL}/chat/completions`, {
    method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${API_KEY}` },
    body: JSON.stringify({ model: MODEL, messages, tools: getSchema(), tool_choice: 'auto' })
  })
  const j = await r.json()
  if (!r.ok) throw new Error(j.error?.message || JSON.stringify(j))
  return j.choices[0].message
}

// =========================================================================
//  AGENT LOOP
// =========================================================================
async function loop(task) {
  console.log(`\n▸ ${task}`)
  const messages = [{ role: 'system', content: system() }, { role: 'user', content: task }]
  for (let turn = 0; turn < MAX_TURNS; turn++) {
    const msg = await think(messages); messages.push(msg)
    if (!msg.tool_calls?.length) { if (msg.content) console.log(`  ✓ ${msg.content}`); return msg.content || '' }
    for (const tc of msg.tool_calls) {
      const t = tools[tc.function.name]
      if (!t) { messages.push({ role: 'tool', tool_call_id: tc.id, content: `ERROR: Unknown tool "${tc.function.name}"` }); continue }
      const args = JSON.parse(tc.function.arguments || '{}')
      console.log(`  → ${tc.function.name}(${Object.values(args).map(v => String(v).slice(0, 60)).join(', ')})`)
      let result; try { result = await Promise.resolve(t.fn(args)) } catch (e) { result = `ERROR: ${e.message}` }
      slog(tc.function.name, result)
      // Skill activate returns full instructions — don't truncate
      const maxLen = (tc.function.name === 'skill' && args.action === 'activate') ? 50000 : 8000
      messages.push({ role: 'tool', tool_call_id: tc.id, content: String(result).slice(0, maxLen) })
    }
    save()
  }
  return ''
}

// =========================================================================
//  DAEMON (persistent mode)
// =========================================================================
const sleep = ms => new Promise(r => setTimeout(r, ms))

async function daemon() {
  console.log('⚡ Agent daemon started\n'); load(); discoverSkills(); await mcpInit()
  while (true) {
    const now = Date.now()
    for (const s of S.schedule.filter(s => now >= s.next)) { await loop(`[Scheduled] ${s.task}`); s.next = now + parseMs(s.every); save() }
    const active = S.goals.filter(g => g.status === 'active').sort((a, b) => ({ high: 0, medium: 1, low: 2 })[a.priority] - ({ high: 0, medium: 1, low: 2 })[b.priority])
    if (active.length) await loop(`Pursue goal: ${active[0].text}`)
    await sleep(DAEMON_INTERVAL)
  }
}

// =========================================================================
//  MAIN
// =========================================================================
process.on('exit', () => { for (const c of Object.values(mcpConns)) c.transport.close() })
process.on('SIGINT', () => process.exit(0))

async function init() { load(); discoverSkills(); await mcpInit() }

if (require.main === module) {
  init().then(() => { const t = process.argv.slice(2).join(' '); return t ? loop(t).then(save) : daemon() })
    .catch(e => { console.error(e.message); process.exit(1) })
}

module.exports = { init, loop, save }
