#!/usr/bin/env node
/* anchor-receipt — anchor the newest foreman measurement as a signed digest
   receipt in results/receipts.jsonl (the artery-integrity-twin's SLA target).
   Convention verified against the kit's founding receipt (549fbe05):
   sha256 = sha256( JSON.stringify(body) + "\n" ).
   Idempotent: skips if the newest receipt already anchors the same body.at. */
import { readFileSync, appendFileSync } from 'node:fs';
import { createHash } from 'node:crypto';

const oracle = readFileSync('results/fresh-oracle.jsonl', 'utf8')
  .trim().split('\n').filter(Boolean);
const foreman = oracle.reverse().find((l) => l.includes('"feed":"foreman"'));
if (!foreman) { console.error('no foreman line — aborting, no fake receipt'); process.exit(1); }
const body = JSON.parse(foreman);

const receipts = readFileSync('results/receipts.jsonl', 'utf8')
  .trim().split('\n').filter(Boolean).map((l) => JSON.parse(l));
const last = receipts[receipts.length - 1];
if (last && last.body && last.body.at === body.at) {
  console.log('[anchor] newest receipt already anchors', body.at, '— no duplicate');
  process.exit(0);
}

const receipt = {
  sha256: createHash('sha256').update(JSON.stringify(body) + '\n').digest('hex'),
  anchoredAt: new Date().toISOString(),
  body,
};
appendFileSync('results/receipts.jsonl', JSON.stringify(receipt) + '\n');
console.log('[anchor] receipt', receipt.sha256.slice(0, 12) + '…',
  'state=' + body.state, 'ageMin=' + body.ageMin, 'at=' + body.at);
