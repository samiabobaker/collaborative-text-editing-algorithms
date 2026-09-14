// Code to reproduce the prosemirror weak list specification violation, requires the prosemirror
// npm modules. 


import { Schema, Slice, Fragment } from "prosemirror-model"
import { EditorState } from "prosemirror-state"
import { ReplaceStep } from "prosemirror-transform"
import { collab, receiveTransaction, sendableSteps, getVersion } from "prosemirror-collab"

const schema = new Schema({
  nodes: { doc: { content: "paragraph" }, paragraph: { content: "text*" }, text: {} },
})

// One paragraph of plain text, so document position i + 1 is text offset i.
const emptyDoc = () => schema.node("doc", null, [schema.node("paragraph")])
const textOf = (state) => {
  let s = ""
  state.doc.descendants((n) => {
    if (n.isText) s += n.text
  })
  return s
}

// ---------------------------------------------------------------- the authority
// The whole server: an append-only log of accepted steps and who wrote each one.
const log = []
const logIds = []
const pending = new Map() // client id -> submissions waiting to be processed

function submit(client) {
  const sendable = sendableSteps(client.state)
  if (sendable) pending.get(client.id).push(sendable)
}

// Process one queued submission. A stale version is dropped silently: the authority
// never transforms, it only accepts or rejects, and the client resends after it syncs.
function serverStep(client) {
  const queue = pending.get(client.id)
  if (!queue.length) return
  const submission = queue.shift()
  if (submission.version !== log.length) return
  for (const step of submission.steps) {
    log.push(step)
    logIds.push(client.id)
  }
}

// ---------------------------------------------------------------- the clients
function makeClient(id) {
  return { id, state: EditorState.create({ doc: emptyDoc(), plugins: [collab({ clientID: id })] }) }
}

function insert(client, pos, char) {
  const tr = client.state.tr
  tr.step(new ReplaceStep(pos + 1, pos + 1, new Slice(Fragment.from(schema.text(char)), 0, 0)))
  client.state = client.state.apply(tr)
  submit(client)
  report(client, `insert '${char}' at ${pos}`)
}

function remove(client, pos) {
  const tr = client.state.tr
  tr.step(new ReplaceStep(pos + 1, pos + 2, Slice.empty))
  client.state = client.state.apply(tr)
  submit(client)
  report(client, `delete at ${pos}`)
}

// Catch up with everything the authority has accepted since this client's version, then
// resubmit whatever is still outstanding. This is DummyServer.broadcast's sync-then-send.
function sync(client) {
  const version = getVersion(client.state)
  if (version === log.length) return
  client.state = client.state.apply(
    receiveTransaction(client.state, log.slice(version), logIds.slice(version)),
  )
  submit(client)
  report(client, `sync (log now ${log.length})`)
}

const seen = new Map()
function report(client, what) {
  const before = seen.get(client.id) ?? ""
  const after = textOf(client.state)
  seen.set(client.id, after)
  const arrow = before === after ? "  " : "->"
  console.log(
    `  ${("client " + client.id).padEnd(9)} ${what.padEnd(22)} ` +
      `${JSON.stringify(before).padEnd(8)} ${arrow} ${JSON.stringify(after)}`,
  )
}

// ---------------------------------------------------------------- the scenario
const A = makeClient(0)
const B = makeClient(1)
pending.set(A.id, [])
pending.set(B.id, [])

console.log("\nA's own edits are never accepted by the authority, so they stay unconfirmed")
console.log("and are rebased every time B's work arrives.\n")

insert(B, 0, "y") //  B types y
serverStep(B) //        the authority accepts it, log = [insert y]
sync(B) //              B sees its own step come back and stops resending it

insert(A, 0, "y") //  A types its own y, unconfirmed
insert(A, 1, "d") //  and a d after it, still unconfirmed
sync(A) //              A learns about B's y and rebases over it

insert(A, 0, "u") //  A types u at the very front, in front of B's y

remove(B, 0) //       B deletes the y it inserted
serverStep(B) //        accepted, log = [insert y, delete y]

const before = textOf(A.state)
sync(A) //              the deletion reaches A, and its three local steps are rebased
const after = textOf(A.state)

// ---------------------------------------------------------------- the result
console.log(`\n  client 0 went from ${JSON.stringify(before)} to ${JSON.stringify(after)}`)

const survives = (ch) => before.includes(ch) && after.includes(ch)
const swapped = []
for (const x of new Set(before)) {
  for (const y of new Set(before)) {
    if (x >= y || !survives(x) || !survives(y)) continue
    if (before.indexOf(x) < before.indexOf(y) !== after.indexOf(x) < after.indexOf(y)) {
      swapped.push(`'${x}' and '${y}'`)
    }
  }
}

if (swapped.length) {
  console.log(`  ${swapped.join(", ")} changed places, though neither was deleted`)
  console.log("\n  the weak list specification does not hold\n")
  process.exitCode = 1
} else {
  console.log("\n  no reordering: the weak list specification held here\n")
}
