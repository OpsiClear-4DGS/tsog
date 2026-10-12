// SPDX-License-Identifier: Apache-2.0
// Read integer attribute bytes through a framebuffer, without Canvas 2D alpha loss.
export function webpDimensions(bytes) {
  const v = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const tag = at => String.fromCharCode(...bytes.subarray(at, at + 4));
  if (bytes.length < 25 || tag(0) !== "RIFF" || tag(8) !== "WEBP" || v.getUint32(4, true) + 8 !== bytes.length) throw new Error("Invalid WebP container");
  let at = 12, result, extended;
  while (at < bytes.length) {
    if (at + 8 > bytes.length) throw new Error("Truncated WebP chunk");
    const kind = tag(at), size = v.getUint32(at + 4, true), data = at + 8;
    if (data + size > bytes.length || ["VP8 ", "ALPH", "ANIM", "ANMF"].includes(kind)) throw new Error("Attribute WebP must be still and lossless");
    if (kind === "VP8L") {
      if (result || size < 5 || bytes[data] !== 47) throw new Error("Invalid lossless WebP");
      const bits = v.getUint32(data + 1, true);
      if (bits >>> 29) throw new Error("Unsupported VP8L version");
      result = [(bits & 16383) + 1, ((bits >>> 14) & 16383) + 1];
    }
    if (kind === "VP8X") {
      if (extended || size !== 10 || bytes[data] & 2) throw new Error("Invalid extended WebP");
      const u24 = p => bytes[p] + 256 * bytes[p + 1] + 65536 * bytes[p + 2];
      extended = [u24(data + 4) + 1, u24(data + 7) + 1];
    }
    at = data + size + (size & 1);
  }
  if (at !== bytes.length || !result || extended && extended.some((n, i) => n !== result[i])) throw new Error("Missing or inconsistent lossless WebP");
  return result;
}
export function createWebPDecoder() {
  const canvas = new OffscreenCanvas(1, 1);
  const gl = canvas.getContext("webgl2", { premultipliedAlpha: false, antialias: false });
  if (!gl) throw new Error("Capability limitation: OffscreenCanvas WebGL2 is required");
  const texture = gl.createTexture(), framebuffer = gl.createFramebuffer();
  const maximum = gl.getParameter(gl.MAX_TEXTURE_SIZE);
  let closed = false;
  return {
    async decode(bytes) {
      if (closed) throw new Error("Decoder is closed");
      const [width, height] = webpDimensions(bytes);
      if (width > maximum || height > maximum || width * height > 64000000) throw new Error("Device/resource limit: texture dimensions");
      const bitmap = await createImageBitmap(new Blob([bytes], { type: "image/webp" }), {
        premultiplyAlpha: "none", colorSpaceConversion: "none", imageOrientation: "none",
      });
      try {
        if (bitmap.width !== width || bitmap.height !== height) throw new Error("Decoded image dimensions mismatch");
        gl.bindTexture(gl.TEXTURE_2D, texture);
        gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, false);
        gl.pixelStorei(gl.UNPACK_COLORSPACE_CONVERSION_WEBGL, gl.NONE);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
        gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, bitmap);
        gl.bindFramebuffer(gl.FRAMEBUFFER, framebuffer);
        gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, texture, 0);
        if (gl.checkFramebufferStatus(gl.FRAMEBUFFER) !== gl.FRAMEBUFFER_COMPLETE) throw new Error("Incomplete attribute framebuffer");
        const pixels = new Uint8Array(width * height * 4);
        gl.readPixels(0, 0, width, height, gl.RGBA, gl.UNSIGNED_BYTE, pixels);
        if (gl.getError() !== gl.NO_ERROR) throw new Error("WebGL attribute read failed");
        return { width, height, pixels };
      } finally { bitmap.close(); }
    },
    close() {
      if (closed) return;
      closed = true;
      gl.deleteFramebuffer(framebuffer);
      gl.deleteTexture(texture);
      gl.getExtension("WEBGL_lose_context")?.loseContext();
    },
  };
}
