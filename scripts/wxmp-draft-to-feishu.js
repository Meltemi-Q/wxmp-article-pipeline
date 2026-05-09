#!/usr/bin/env node
/*
 * Convert a wxmp-studio Markdown draft (article.md/content.md) into one Feishu Docx.
 *
 * Default layout matches Yulong's current preference:
 *   1. put article text first;
 *   2. then append all images, each followed by its caption.
 *
 * Usage:
 *   node wxmp-draft-to-feishu.js <draft-dir-or-md-file> [title] [--grant ou_xxx] [--preserve-order] [--dry-run]
 */

const fs = require('fs');
const path = require('path');
const os = require('os');

const IMAGE_RE = /^!\[([^\]]*)\]\(([^)]+)\)\s*$/;
const ITALIC_RE = /^\s*\*([^*]+)\*\s*$/;

function loadEnvFile(file) {
  if (!fs.existsSync(file)) return;
  for (const raw of fs.readFileSync(file, 'utf8').split('\n')) {
    const line = raw.trim();
    if (!line || line.startsWith('#') || !line.includes('=')) continue;
    const idx = line.indexOf('=');
    const key = line.slice(0, idx).trim();
    let value = line.slice(idx + 1).trim();
    value = value.replace(/^['"]|['"]$/g, '');
    if (!process.env[key]) process.env[key] = value;
  }
}

function loadEnv() {
  for (const file of [
    path.resolve(process.cwd(), '.env'),
    '/root/.openclaw/skills/feishu-md-docx/.env',
    '/root/.hermes/.env',
    '/root/.openclaw/extensions/openclaw-lark/.env',
  ]) loadEnvFile(file);
}

function ensureMarkdown(input) {
  const p = path.resolve(input);
  if (fs.statSync(p).isDirectory()) {
    for (const name of ['article.md', 'content.md', 'draft.md']) {
      const candidate = path.join(p, name);
      if (fs.existsSync(candidate)) return candidate;
    }
    throw new Error(`No article.md/content.md/draft.md in ${p}`);
  }
  return p;
}

function parseArgs(argv) {
  const args = [...argv];
  const opts = { preserveOrder: false, dryRun: false, grant: null, imageLimit: null };
  const positional = [];
  while (args.length) {
    const a = args.shift();
    if (a === '--preserve-order') opts.preserveOrder = true;
    else if (a === '--dry-run') opts.dryRun = true;
    else if (a === '--grant') opts.grant = args.shift();
    else if (a === '--image-limit') opts.imageLimit = Number(args.shift());
    else positional.push(a);
  }
  return { input: positional[0], titleArg: positional[1], opts };
}

function extractTitle(lines, titleArg) {
  if (titleArg) return titleArg;
  const h1 = lines.find((l) => l.startsWith('# '));
  return h1 ? h1.slice(2).trim() : `wxmp 草稿 ${new Date().toISOString().slice(0, 10)}`;
}

function isCaptionLine(line) {
  return ITALIC_RE.test(line.trim());
}

function collectImages(lines) {
  const images = [];
  for (let i = 0; i < lines.length; i++) {
    const m = lines[i].trim().match(IMAGE_RE);
    if (!m) continue;
    let caption = m[1].trim();
    const next = lines[i + 1] || '';
    const cm = next.trim().match(ITALIC_RE);
    if (cm) {
      caption = cm[1].trim();
      i++;
    }
    images.push({ alt: m[1].trim(), src: m[2].trim(), caption: caption || m[1].trim() || '配图' });
  }
  return images;
}

function parseInline(text) {
  const els = [];
  const re = /(\*\*(.+?)\*\*|\*(.+?)\*|`(.+?)`)/g;
  let last = 0;
  let m;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) els.push({ text_run: { content: text.slice(last, m.index) } });
    if (m[2]) els.push({ text_run: { content: m[2], text_element_style: { bold: true } } });
    else if (m[3]) els.push({ text_run: { content: m[3], text_element_style: { italic: true } } });
    else if (m[4]) els.push({ text_run: { content: m[4], text_element_style: { inline_code: true } } });
    last = m.index + m[0].length;
  }
  if (last < text.length) els.push({ text_run: { content: text.slice(last) } });
  return els.length ? els : [{ text_run: { content: text } }];
}

function lineToBlocks(line, title) {
  const t = line.trim();
  if (!t || /^[-_]{3,}$/.test(t)) return [];
  if (t === `# ${title}`) return [];

  const h = t.match(/^(#{1,3})\s+(.+)$/);
  if (h) {
    const lvl = h[1].length;
    const fieldMap = { 1: 'heading1', 2: 'heading2', 3: 'heading3' };
    const typeMap = { 1: 3, 2: 4, 3: 5 };
    return [{ block_type: typeMap[lvl], [fieldMap[lvl]]: { elements: parseInline(h[2]) } }];
  }
  if (t.startsWith('>')) {
    const content = t.replace(/^>\s*/, '');
    const els = parseInline(content);
    els.forEach((e) => {
      if (e.text_run) e.text_run.text_element_style = { ...(e.text_run.text_element_style || {}), italic: true };
    });
    els.unshift({ text_run: { content: '｜', text_element_style: { bold: true } } });
    return [{ block_type: 2, text: { elements: els } }];
  }
  if (/^[-*]\s+/.test(t)) return [{ block_type: 12, bullet: { elements: parseInline(t.replace(/^[-*]\s+/, '')) } }];
  if (/^\d+\.\s+/.test(t)) return [{ block_type: 13, ordered: { elements: parseInline(t.replace(/^\d+\.\s+/, '')) } }];
  return [{ block_type: 2, text: { elements: parseInline(t) } }];
}

function mdToBlocks(lines, title, images, opts) {
  const blocks = [];
  const imageInputs = [];

  if (opts.preserveOrder) {
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      const m = line.trim().match(IMAGE_RE);
      if (m) {
        let caption = m[1].trim();
        const cm = (lines[i + 1] || '').trim().match(ITALIC_RE);
        if (cm) {
          caption = cm[1].trim();
          i++;
        }
        blocks.push({ block_type: 27, image: {} });
        imageInputs.push({ src: m[2].trim(), caption: caption || m[1].trim() || '配图' });
        blocks.push({ block_type: 2, text: { elements: parseInline(caption || m[1].trim() || '配图') } });
        continue;
      }
      blocks.push(...lineToBlocks(line, title));
    }
    return { blocks, imageInputs };
  }

  const skipImageOrCaption = new Set();
  for (let i = 0; i < lines.length; i++) {
    if (IMAGE_RE.test(lines[i].trim())) {
      skipImageOrCaption.add(i);
      if (isCaptionLine(lines[i + 1] || '')) skipImageOrCaption.add(i + 1);
    }
  }
  for (let i = 0; i < lines.length; i++) {
    if (!skipImageOrCaption.has(i)) blocks.push(...lineToBlocks(lines[i], title));
  }

  if (images.length) {
    blocks.push({ block_type: 4, heading2: { elements: parseInline('图片与图注') } });
    for (const img of images) {
      blocks.push({ block_type: 27, image: {} });
      imageInputs.push(img);
      blocks.push({ block_type: 2, text: { elements: parseInline(img.caption) } });
    }
  }
  return { blocks, imageInputs };
}

async function fetchWithRetries(url, opts, retries = 3) {
  for (let i = 0; i < retries; i++) {
    const ac = new AbortController();
    const t = setTimeout(() => ac.abort(), 30000);
    try {
      const r = await fetch(url, { ...opts, signal: ac.signal });
      clearTimeout(t);
      if (r.ok) return r;
      if (r.status === 429) {
        await new Promise((res) => setTimeout(res, 2000));
        continue;
      }
      throw new Error(`HTTP ${r.status} ${await r.text().catch(() => '')}`);
    } catch (err) {
      clearTimeout(t);
      if (i === retries - 1) throw err;
      await new Promise((res) => setTimeout(res, 1000 * (i + 1)));
    }
  }
}

async function getToken() {
  const appId = process.env.FEISHU_APP_ID;
  const appSecret = process.env.FEISHU_APP_SECRET;
  if (!appId || !appSecret) throw new Error('Missing FEISHU_APP_ID / FEISHU_APP_SECRET');
  const cache = process.env.FEISHU_TOKEN_CACHE || path.join(os.homedir(), '.cache', 'wxmp-draft-to-feishu', 'tenant_access_token.json');
  try {
    const c = JSON.parse(fs.readFileSync(cache, 'utf8'));
    if (c.expire && c.token && c.expire > Math.floor(Date.now() / 1000) + 300) return c.token;
  } catch {}
  const r = await fetchWithRetries('https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ app_id: appId, app_secret: appSecret }),
  });
  const d = await r.json();
  if (!d.tenant_access_token) throw new Error(`No tenant_access_token: ${JSON.stringify(d)}`);
  fs.mkdirSync(path.dirname(cache), { recursive: true });
  fs.writeFileSync(cache, JSON.stringify({ token: d.tenant_access_token, expire: Math.floor(Date.now() / 1000) + (d.expire || 3600) }));
  return d.tenant_access_token;
}

async function createDoc(token, title) {
  const r = await fetchWithRetries('https://open.feishu.cn/open-apis/docx/v1/documents', {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json; charset=utf-8' },
    body: JSON.stringify({ title }),
  });
  const d = await r.json();
  if (d.code && d.code !== 0) throw new Error(`Create doc failed: ${JSON.stringify(d)}`);
  const docId = (d.data?.document || d.data)?.document_id;
  if (!docId) throw new Error(`Create doc missing document_id: ${JSON.stringify(d)}`);
  return docId;
}

async function appendBlocks(token, docId, blocks) {
  const inserted = [];
  const batchSize = Number(process.env.FEISHU_DOCX_BATCH_SIZE || 35);
  for (let i = 0; i < blocks.length; i += batchSize) {
    const batch = blocks.slice(i, i + batchSize);
    const r = await fetchWithRetries(`https://open.feishu.cn/open-apis/docx/v1/documents/${docId}/blocks/${docId}/children`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json; charset=utf-8' },
      body: JSON.stringify({ children: batch }),
    });
    const d = await r.json();
    if (d.code && d.code !== 0) throw new Error(`Append blocks failed: ${JSON.stringify(d)}`);
    inserted.push(...(d.data?.children || []));
    if (i + batchSize < blocks.length) await new Promise((res) => setTimeout(res, 500));
  }
  return inserted;
}

async function loadImageBuffer(src, mdDir) {
  if (/^https?:\/\//i.test(src)) {
    const r = await fetchWithRetries(src, { headers: { Referer: 'https://mp.weixin.qq.com/' } });
    const ab = await r.arrayBuffer();
    return { buffer: Buffer.from(ab), fileName: path.basename(new URL(src).pathname) || 'image.jpg' };
  }
  const full = path.resolve(mdDir, src);
  return { buffer: fs.readFileSync(full), fileName: path.basename(full) };
}

async function uploadImage(token, docId, blockId, src, mdDir) {
  const { buffer, fileName } = await loadImageBuffer(src, mdDir);
  const form = new FormData();
  form.append('file_name', fileName);
  form.append('parent_type', 'docx_image');
  form.append('parent_node', blockId);
  form.append('size', String(buffer.length));
  form.append('file', new Blob([buffer]), fileName);
  form.append('extra', JSON.stringify({ drive_route_token: docId }));
  const upload = await fetchWithRetries('https://open.feishu.cn/open-apis/drive/v1/medias/upload_all', {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  });
  const uploadJson = await upload.json();
  if (uploadJson.code && uploadJson.code !== 0) throw new Error(`Image upload failed: ${JSON.stringify(uploadJson)}`);
  const fileToken = uploadJson.data?.file_token || uploadJson.file_token;
  if (!fileToken) throw new Error(`Image upload missing file_token: ${JSON.stringify(uploadJson)}`);
  const patch = await fetchWithRetries(`https://open.feishu.cn/open-apis/docx/v1/documents/${docId}/blocks/${blockId}`, {
    method: 'PATCH',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json; charset=utf-8' },
    body: JSON.stringify({ replace_image: { token: fileToken } }),
  });
  const patchJson = await patch.json();
  if (patchJson.code && patchJson.code !== 0) throw new Error(`Image patch failed: ${JSON.stringify(patchJson)}`);
  return { fileName, fileToken };
}

async function grantPermission(token, docId, openId) {
  const r = await fetchWithRetries(`https://open.feishu.cn/open-apis/drive/v1/permissions/${docId}/members?type=docx`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json; charset=utf-8' },
    body: JSON.stringify({ member_type: 'openid', member_id: openId, perm: 'full_access' }),
  });
  const d = await r.json();
  return d.code === 0 ? { ok: true } : { ok: false, error: d };
}

async function main() {
  loadEnv();
  const { input, titleArg, opts } = parseArgs(process.argv.slice(2));
  if (!input) {
    console.error('Usage: node wxmp-draft-to-feishu.js <draft-dir-or-md-file> [title] [--grant ou_xxx] [--preserve-order] [--dry-run]');
    process.exit(1);
  }
  const mdFile = ensureMarkdown(input);
  const mdDir = path.dirname(mdFile);
  const lines = fs.readFileSync(mdFile, 'utf8').replace(/\r\n/g, '\n').split('\n');
  const title = extractTitle(lines, titleArg);
  const images = collectImages(lines).slice(0, opts.imageLimit || undefined);
  const { blocks, imageInputs } = mdToBlocks(lines, title, images, opts);

  if (opts.dryRun) {
    console.log(JSON.stringify({ title, mdFile, blocks: blocks.length, images: imageInputs.length, layout: opts.preserveOrder ? 'preserve-order' : 'text-first' }, null, 2));
    return;
  }

  const token = await getToken();
  const docId = await createDoc(token, title);
  const inserted = await appendBlocks(token, docId, blocks);
  const imageBlocks = inserted.filter((b) => b.block_type === 27);
  let uploaded = 0;
  const imageErrors = [];
  for (let i = 0; i < Math.min(imageInputs.length, imageBlocks.length); i++) {
    try {
      await uploadImage(token, docId, imageBlocks[i].block_id, imageInputs[i].src, mdDir);
      uploaded++;
    } catch (err) {
      imageErrors.push({ src: imageInputs[i].src, error: String(err.message || err) });
    }
  }
  const permission = opts.grant ? await grantPermission(token, docId, opts.grant) : null;
  const base = (process.env.FEISHU_DOCX_BASE_URL || 'https://www.feishu.cn').replace(/\/$/, '');
  console.log(JSON.stringify({
    ok: imageErrors.length === 0,
    document_id: docId,
    url: `${base}/docx/${docId}`,
    title,
    blocks: blocks.length,
    images_found: imageInputs.length,
    images_uploaded: uploaded,
    image_errors: imageErrors,
    permission,
  }, null, 2));
}

main().catch((err) => {
  console.error(err?.stack || String(err));
  process.exit(1);
});
