// speak-reply — dst (cordis) plugin: hand each finished top-level reply to the shared
// speaker, which owns the on/off toggle, rate, voice and replay protection.
import { spawn } from 'node:child_process'
import { homedir } from 'node:os'
import { join } from 'node:path'

export const name = 'speak-reply'

const STATE = process.env.TALK_SPEAK_HOME || join(homedir(), '.talk-speak')
const SPEAKER = join(STATE, 'bin/speak-text.sh')

export function apply(ctx) {
  const last = new Map() // sessionId -> final text of the current turn

  ctx.on('session/event', (session, event) => {
    try {
      if ((session.header?.delegationDepth ?? 0) > 0) return // subagents stay silent

      if (event.type === 'assistant/message') {
        const text = (event.data.message.content ?? [])
          .filter(block => block.type === 'text') // never speak 'reasoning' blocks
          .map(block => block.text)
          .join('\n')
          .trim()
        if (text) last.set(session.id, text)
        return
      }

      if (event.type === 'turn/end') {
        const text = last.get(session.id)
        last.delete(session.id)
        if (!text || event.data.reason?.kind !== 'completed') return
        const child = spawn('bash', [SPEAKER], { stdio: ['pipe', 'ignore', 'ignore'], detached: true })
        child.on('error', () => {})
        child.stdin.on('error', () => {})
        child.stdin.end(text)
        child.unref()
      }
    } catch {
      // observer failures must never touch the session
    }
  })
}
