#!/usr/bin/env node
const fs = require('fs');
const { webcrypto } = require('crypto');

const secretPath = 'secret.private';
const enc = new TextEncoder();
const dec = new TextDecoder();

function b64ToBytes(value) {
  return new Uint8Array(Buffer.from(String(value || ''), 'base64'));
}

function bytesToB64(value) {
  return Buffer.from(new Uint8Array(value)).toString('base64');
}

async function keyFromPassword(password, salt, usages) {
  const baseKey = await webcrypto.subtle.importKey(
    'raw',
    enc.encode(password),
    'PBKDF2',
    false,
    ['deriveKey'],
  );
  return webcrypto.subtle.deriveKey(
    { name: 'PBKDF2', salt, iterations: 120000, hash: 'SHA-256' },
    baseKey,
    { name: 'AES-GCM', length: 256 },
    false,
    usages,
  );
}

async function decryptSecret(password, payload) {
  const salt = b64ToBytes(payload.salt);
  const iv = b64ToBytes(payload.iv);
  const ciphertext = b64ToBytes(payload.ciphertext);
  const key = await keyFromPassword(password, salt, ['decrypt']);
  const plain = await webcrypto.subtle.decrypt({ name: 'AES-GCM', iv }, key, ciphertext);
  return JSON.parse(dec.decode(plain));
}

async function encryptSecret(password, plain) {
  const salt = webcrypto.getRandomValues(new Uint8Array(16));
  const iv = webcrypto.getRandomValues(new Uint8Array(12));
  const key = await keyFromPassword(password, salt, ['encrypt']);
  const ciphertext = await webcrypto.subtle.encrypt(
    { name: 'AES-GCM', iv },
    key,
    enc.encode(JSON.stringify(plain, null, 2)),
  );
  return {
    version: 1,
    salt: bytesToB64(salt),
    iv: bytesToB64(iv),
    ciphertext: bytesToB64(ciphertext),
  };
}

function hiddenPrompt(label) {
  return new Promise((resolve) => {
    const stdin = process.stdin;
    const stdout = process.stdout;
    let value = '';

    stdout.write(label);
    stdin.setRawMode(true);
    stdin.resume();
    stdin.setEncoding('utf8');

    const done = () => {
      stdin.setRawMode(false);
      stdin.pause();
      stdin.off('data', onData);
      stdout.write('\n');
      resolve(value);
    };

    function onData(char) {
      if (char === '\u0003') process.exit(130);
      if (char === '\r' || char === '\n') return done();
      if (char === '\u007f') {
        value = value.slice(0, -1);
        return;
      }
      value += char;
    }

    stdin.on('data', onData);
  });
}

(async () => {
  if (!fs.existsSync(secretPath)) {
    throw new Error(`${secretPath} not found`);
  }

  const payload = JSON.parse(fs.readFileSync(secretPath, 'utf8'));
  const oldPassword = await hiddenPrompt('Old unlock password: ');
  const plain = await decryptSecret(oldPassword, payload);

  const newPassword = await hiddenPrompt('New unlock password: ');
  const confirmPassword = await hiddenPrompt('Confirm new password: ');
  if (newPassword.length < 6) throw new Error('New password must be at least 6 characters');
  if (newPassword !== confirmPassword) throw new Error('New passwords do not match');

  const nextPayload = await encryptSecret(newPassword, {
    ...plain,
    updatedAt: new Date().toISOString(),
  });
  const backupPath = `secret.private.before-password-reset-${new Date()
    .toISOString()
    .replace(/[-:]/g, '')
    .replace(/\..+/, '')}`;
  fs.copyFileSync(secretPath, backupPath);
  fs.writeFileSync(secretPath, `${JSON.stringify(nextPayload, null, 2)}\n`);
  console.log(`Password reset. Backup: ${backupPath}`);
})().catch((error) => {
  console.error(`Password reset failed: ${error.message || error}`);
  process.exit(1);
});
