// SPDX-License-Identifier: Apache-2.0
// Independent bounded ZIP32 reader. Consumed entries are CRC/length checked.
const utf8 = new TextDecoder("utf-8", { fatal: true });
const MiB = 1048576;
const table = Uint32Array.from({ length: 256 }, (_, n) => {
  for (let b = 0; b < 8; b++) n = (n >>> 1) ^ (n & 1 ? 0xedb88320 : 0);
  return n >>> 0;
});
const view = (bytes) => new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
const fail = (message) => { throw new Error(`TSOG ZIP: ${message}`); };
export function entryName(name) {
  if (typeof name !== "string" || !name || /[\\\x00-\x1f:?#]/.test(name) ||
      name.split("/").some(part => !part || part === "." || part === "..")) fail("invalid entry name");
  return name;
}
function extra(bytes) {
  const v = view(bytes);
  let at = 0;
  while (at < bytes.length) {
    if (at + 4 > bytes.length) fail("truncated extra field");
    const id = v.getUint16(at, true), length = v.getUint16(at + 2, true);
    if (id === 1) fail("ZIP64 is unsupported");
    at += 4 + length;
  }
  if (at !== bytes.length) fail("extra field size mismatch");
}
function crc32(bytes) {
  let crc = 0xffffffff;
  for (let i = 0; i < bytes.length; i++) crc = table[(crc ^ bytes[i]) & 255] ^ (crc >>> 8);
  return (crc ^ 0xffffffff) >>> 0;
}
export async function readZIP(blob, { maxArchiveBytes = 512 * MiB } = {}) {
  if (blob.size > maxArchiveBytes) fail("device/resource limit: archive size");
  const slice = async (start, end) => new Uint8Array(await blob.slice(start, end).arrayBuffer());
  const tailOffset = Math.max(0, blob.size - 65557);
  const tail = await slice(tailOffset, blob.size), endView = view(tail);
  let end = tail.length - 22;
  while (end >= 0 && !(endView.getUint32(end, true) === 0x06054b50 && end + 22 + endView.getUint16(end + 20, true) === tail.length)) end--;
  if (end < 0) fail("missing end record");
  const entries = endView.getUint16(end + 10, true);
  const size = endView.getUint32(end + 12, true), offset = endView.getUint32(end + 16, true);
  if (endView.getUint16(end + 4, true) || endView.getUint16(end + 6, true) || entries !== endView.getUint16(end + 8, true) || entries === 65535 || offset === 0xffffffff || size === 0xffffffff) fail("ZIP64/multi-disk archive");
  if (!entries || entries > 1024 || size > 4 * MiB || offset + size !== tailOffset + end) fail("invalid directory bounds");
  const directory = await slice(offset, offset + size), dir = view(directory);
  const members = new Map(), intervals = [];
  let at = 0;
  for (let index = 0; index < entries; index++) {
    if (at + 46 > directory.length || dir.getUint32(at, true) !== 0x02014b50) fail("invalid directory entry");
    const flags = dir.getUint16(at + 8, true), method = dir.getUint16(at + 10, true);
    const crc = dir.getUint32(at + 16, true), compressed = dir.getUint32(at + 20, true), length = dir.getUint32(at + 24, true);
    const nameLength = dir.getUint16(at + 28, true), extraLength = dir.getUint16(at + 30, true), commentLength = dir.getUint16(at + 32, true);
    const localOffset = dir.getUint32(at + 42, true);
    const next = at + 46 + nameLength + extraLength + commentLength;
    if (next > directory.length || dir.getUint16(at + 34, true) || flags & (1 | 64 | 8192) || ![0, 8].includes(method) || length > 512 * MiB) fail("unsupported or truncated member");
    const rawName = directory.subarray(at + 46, at + 46 + nameLength);
    if (!(flags & 0x800) && rawName.some(n => n > 127)) fail("non-ASCII filename needs UTF-8 flag");
    const name = entryName(utf8.decode(rawName));
    if (members.has(name)) fail("duplicate name");
    extra(directory.subarray(at + 46 + nameLength, at + 46 + nameLength + extraLength));
    const local = await slice(localOffset, localOffset + 30);
    if (local.length !== 30) fail("truncated local header");
    const header = view(local);
    if (header.getUint32(0, true) !== 0x04034b50 || header.getUint16(6, true) !== flags || header.getUint16(8, true) !== method) fail("local header mismatch");
    const localNameLength = header.getUint16(26, true), localExtraLength = header.getUint16(28, true);
    const variable = await slice(localOffset + 30, localOffset + 30 + localNameLength + localExtraLength);
    if (variable.length !== localNameLength + localExtraLength || localNameLength !== rawName.length || rawName.some((n, i) => n !== variable[i])) fail("local name mismatch");
    extra(variable.subarray(localNameLength));
    const dataOffset = localOffset + 30 + localNameLength + localExtraLength;
    let recordEnd = dataOffset + compressed;
    if (flags & 8) {
      if (header.getUint32(14, true) || header.getUint32(18, true) || header.getUint32(22, true)) fail("descriptor local fields must be zero");
      const descriptor = await slice(recordEnd, recordEnd + 16), d = view(descriptor);
      const matches = p => descriptor.length >= p + 12 && d.getUint32(p, true) === crc && d.getUint32(p + 4, true) === compressed && d.getUint32(p + 8, true) === length;
      if (descriptor.length >= 16 && d.getUint32(0, true) === 0x08074b50 && matches(4)) recordEnd += 16;
      else if (matches(0)) recordEnd += 12;
      else fail("invalid data descriptor");
    } else if (header.getUint32(14, true) !== crc || header.getUint32(18, true) !== compressed || header.getUint32(22, true) !== length) fail("local CRC/size mismatch");
    if (recordEnd > offset) fail("entry overlaps directory");
    intervals.push([localOffset, recordEnd]);
    members.set(name, { dataOffset, compressed, length, method, crc });
    at = next;
  }
  if (at !== directory.length) fail("directory size mismatch");
  intervals.sort((a, b) => a[0] - b[0]);
  if (intervals.some((p, i) => i && p[0] < intervals[i - 1][1])) fail("overlapping entries");
  return {
    members,
    async read(name, limit = 512 * MiB) {
      const member = members.get(entryName(name));
      if (!member || member.length > limit) fail("missing or oversized entry");
      let bytes = await slice(member.dataOffset, member.dataOffset + member.compressed);
      if (member.method === 8) {
        const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream("deflate-raw"));
        const reader = stream.getReader(), chunks = [];
        let total = 0;
        try {
          while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            total += value.length;
            if (total > member.length || total > limit) { await reader.cancel(); fail("inflation exceeds declared size"); }
            chunks.push(value);
          }
        } finally { reader.releaseLock(); }
        bytes = new Uint8Array(total);
        let position = 0;
        for (const chunk of chunks) { bytes.set(chunk, position); position += chunk.length; }
      }
      if (bytes.length !== member.length || crc32(bytes) !== member.crc) fail("entry length or CRC mismatch");
      return bytes;
    },
  };
}
