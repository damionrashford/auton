#!/usr/bin/env node
const fs = require('fs'), http = require('http'), { resolve } = require('path')
const agent = require('./agent.js')
const CFG = (() => { try { return JSON.parse(fs.readFileSync(resolve(__dirname, 'config.json'), 'utf8')) } catch { return {} } })()

function chunk(t, max = 3000) {
  if (!t || t.length <= max) return [t || '(no response)']
  const out = []; while (t.length) { const i = t.lastIndexOf('\n', max); const c = i > max * 0.3 ? i + 1 : max; out.push(t.slice(0, c)); t = t.slice(c) }; return out
}

async function handle(userId, channel, text) {
  const task = `[from ${channel} user:${userId}] ${text}`
  try { return chunk(await agent.loop(task), channel === 'telegram' ? 4096 : 4000) } catch (e) { return ['Error: ' + e.message] }
}

// =========================================================================
//  SLACK — Socket Mode (WebSocket + fetch, zero deps)
// =========================================================================
async function slack() {
  const { botToken: bt, appToken: at } = CFG.slack
  const api = (m, b, t) => fetch(`https://slack.com/api/${m}`, { method: 'POST', headers: { Authorization: `Bearer ${t || bt}`, 'Content-Type': 'application/json' }, body: JSON.stringify(b) }).then(r => r.json())

  const connect = async () => {
    const { ok, url, error } = await api('apps.connections.open', {}, at)
    if (!ok) { console.error('[slack]', error); return }
    const ws = new WebSocket(url)
    let alive = true

    ws.onopen = () => { console.log('[slack] connected'); alive = true }
    ws.onclose = () => { alive = false; console.log('[slack] reconnecting...'); setTimeout(connect, 3000) }
    ws.onerror = (e) => console.error('[slack] ws error:', e.message || e)

    // Keepalive — Slack drops idle sockets after ~30s
    const ping = setInterval(() => { if (!alive) return clearInterval(ping); try { ws.ping?.() } catch {} }, 15000)

    ws.onmessage = async ({ data }) => {
      const d = JSON.parse(data)
      // Ack envelope immediately (Slack requires <3s)
      if (d.envelope_id) ws.send(JSON.stringify({ envelope_id: d.envelope_id }))

      // Slash commands: /ask <text>
      if (d.type === 'slash_commands') {
        const p = d.payload; const text = p.text?.trim()
        if (!text) { await api('chat.postMessage', { channel: p.channel_id, text: 'Usage: /ask <your question>' }); return }
        await api('chat.postMessage', { channel: p.channel_id, text: ':hourglass_flowing_sand: Thinking...' })
        const chunks = await handle(p.user_id, 'slack', text)
        for (const c of chunks) await api('chat.postMessage', { channel: p.channel_id, text: c })
        return
      }

      // Events: messages + mentions
      if (d.type !== 'events_api') return
      const ev = d.payload?.event; if (!ev || ev.bot_id || ev.subtype) return
      const isAppMention = ev.type === 'app_mention'
      const isDM = ev.channel_type === 'im'
      if (!isAppMention && !isDM) return

      const text = (isAppMention ? ev.text.replace(/<@[A-Z0-9]+>/g, '') : ev.text)?.trim()
      if (!text) return

      // Typing indicator via reaction
      const ts = ev.thread_ts || ev.ts
      await api('reactions.add', { channel: ev.channel, name: 'hourglass_flowing_sand', timestamp: ev.ts }).catch(() => {})

      const chunks = await handle(ev.user, 'slack', text)

      await api('reactions.remove', { channel: ev.channel, name: 'hourglass_flowing_sand', timestamp: ev.ts }).catch(() => {})
      for (const c of chunks) await api('chat.postMessage', { channel: ev.channel, text: c, thread_ts: ts, unfurl_links: false })
    }
  }
  await connect()
}

// =========================================================================
//  TELEGRAM — Long-poll (fetch only, zero deps)
// =========================================================================
async function telegram() {
  const tok = CFG.telegram.botToken
  const tg = (m, b) => fetch(`https://api.telegram.org/bot${tok}/${m}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(b) }).then(r => r.json())

  const me = await tg('getMe', {}); const un = me.result?.username
  console.log(`[telegram] @${un} online`)

  // Register commands menu
  await tg('setMyCommands', { commands: [{ command: 'start', description: 'Start the bot' }, { command: 'help', description: 'Show help' }, { command: 'clear', description: 'Clear agent memory for you' }] })

  let off = 0
  while (true) {
    try {
      const { result } = await tg('getUpdates', { offset: off, timeout: 30, allowed_updates: ['message', 'callback_query'] })
      for (const u of result || []) {
        off = u.update_id + 1

        // Callback queries (inline button presses)
        if (u.callback_query) {
          const cb = u.callback_query
          await tg('answerCallbackQuery', { callback_query_id: cb.id })
          const chunks = await handle(String(cb.from.id), 'telegram', cb.data)
          for (const c of chunks) await tg('sendMessage', { chat_id: cb.message.chat.id, text: c, parse_mode: 'Markdown' })
          continue
        }

        const m = u.message; if (!m) continue
        const uid = String(m.from.id), cid = m.chat.id

        // Commands
        if (m.text?.startsWith('/')) {
          const cmd = m.text.split(' ')[0].replace(`@${un}`, '').slice(1)
          if (cmd === 'start') { await tg('sendMessage', { chat_id: cid, text: 'Agent online. Send me anything.' }); continue }
          if (cmd === 'help') { await tg('sendMessage', { chat_id: cid, text: '*Commands:*\n/start — Start\n/help — This message\n/clear — Clear your memory\n\nOr just send a message.', parse_mode: 'Markdown' }); continue }
          if (cmd === 'clear') { await agent.loop(`[from telegram user:${uid}] Forget all memory stored for user ${uid}`); await tg('sendMessage', { chat_id: cid, text: 'Memory cleared.' }); continue }
          // Treat unknown commands as messages — fall through
        }

        // Non-text messages: photos, docs, voice, stickers
        let text = m.text
        if (!text) {
          if (m.photo) text = '[User sent a photo]' + (m.caption ? ': ' + m.caption : '')
          else if (m.document) text = `[User sent file: ${m.document.file_name}]` + (m.caption ? ': ' + m.caption : '')
          else if (m.voice || m.audio) text = '[User sent audio/voice]'
          else if (m.sticker) text = `[User sent sticker: ${m.sticker.emoji || ''}]`
          else if (m.location) text = `[User shared location: ${m.location.latitude}, ${m.location.longitude}]`
          else continue
        }

        // Group: only respond to @mentions
        const grp = m.chat.type !== 'private'
        if (grp) { if (!text.includes(`@${un}`)) continue; text = text.replace(`@${un}`, '').trim() }
        if (!text) continue

        // Typing + reply
        const typing = setInterval(() => tg('sendChatAction', { chat_id: cid, action: 'typing' }).catch(() => {}), 4000)
        tg('sendChatAction', { chat_id: cid, action: 'typing' })
        const chunks = await handle(uid, 'telegram', text)
        clearInterval(typing)
        for (const c of chunks) await tg('sendMessage', { chat_id: cid, text: c, reply_to_message_id: m.message_id, parse_mode: 'Markdown' })
      }
    } catch (e) { console.error('[telegram]', e.message); await new Promise(r => setTimeout(r, 5000)) }
  }
}

// =========================================================================
//  WHATSAPP — Cloud API webhook (http + fetch, zero deps)
// =========================================================================
function whatsapp() {
  const { accessToken: at, phoneNumberId: pid, verifyToken: vt, port = 3000 } = CFG.whatsapp
  const wa = (to, body) => fetch(`https://graph.facebook.com/v21.0/${pid}/messages`, {
    method: 'POST', headers: { Authorization: `Bearer ${at}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ messaging_product: 'whatsapp', to, ...body })
  })
  const markRead = (msgId) => wa(null, { status: 'read', message_id: msgId }).catch(() => {})

  http.createServer(async (req, res) => {
    // Webhook verification
    if (req.method === 'GET') {
      const u = new URL(req.url, `http://${req.headers.host}`)
      u.searchParams.get('hub.verify_token') === vt ? res.end(u.searchParams.get('hub.challenge')) : (res.writeHead(403), res.end())
      return
    }
    let raw = ''; req.on('data', d => raw += d); req.on('end', async () => {
      res.writeHead(200); res.end() // Ack immediately (Meta requires <20s)
      try {
        const data = JSON.parse(raw)
        const value = data.entry?.[0]?.changes?.[0]?.value
        if (!value?.messages) return

        // Status updates (delivered, read) — ignore
        if (value.statuses) return

        for (const m of value.messages) {
          const from = m.from

          // Mark as read + typing
          markRead(m.id)

          let text
          if (m.type === 'text') text = m.text.body
          else if (m.type === 'image') text = `[User sent image]${m.image?.caption ? ': ' + m.image.caption : ''}`
          else if (m.type === 'document') text = `[User sent document: ${m.document?.filename || 'file'}]`
          else if (m.type === 'audio' || m.type === 'voice') text = '[User sent audio]'
          else if (m.type === 'location') text = `[User shared location: ${m.location?.latitude}, ${m.location?.longitude}]`
          else if (m.type === 'contacts') text = '[User shared a contact]'
          else if (m.type === 'sticker') text = '[User sent a sticker]'
          else if (m.type === 'reaction') continue // Skip reactions
          else text = `[User sent ${m.type} message]`

          const chunks = await handle(from, 'whatsapp', text)
          for (const c of chunks) await wa(from, { type: 'text', text: { body: c } })
        }
      } catch (e) { console.error('[whatsapp]', e.message) }
    })
  }).listen(port, () => console.log(`[whatsapp] webhook :${port}`))
}

// =========================================================================
//  BOOT + GRACEFUL SHUTDOWN
// =========================================================================
const shutdown = () => { console.log('\n[comms] shutting down...'); process.exit(0) }
process.on('SIGINT', shutdown); process.on('SIGTERM', shutdown)

;(async () => {
  await agent.init(); console.log('[comms] agent ready')
  if (CFG.slack?.botToken && CFG.slack?.appToken) slack().catch(e => console.error('[slack]', e))
  if (CFG.telegram?.botToken) telegram().catch(e => console.error('[telegram]', e))
  if (CFG.whatsapp?.accessToken) whatsapp()
  if (!CFG.slack && !CFG.telegram && !CFG.whatsapp) console.log('[comms] no channels configured — edit channels.json')
})()
