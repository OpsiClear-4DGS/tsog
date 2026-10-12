// SPDX-License-Identifier: Apache-2.0
import { decodeTSOG, mediaTiming } from "./codec.js";
self.onmessage = async ({ data }) => {
  try {
    self.postMessage({ stage: "Downloading" });
    const response = await fetch(data.url);
    if (!response.ok) throw new Error(`Download HTTP ${response.status}`);
    const blob = await response.blob();
    self.postMessage({ stage: "Decoding" });
    const start = performance.now();
    const model = await decodeTSOG(blob);
    const decodeMilliseconds = performance.now() - start;
    const arrays = Object.values(model).filter(value => ArrayBuffer.isView(value));
    const attributeBytes = arrays.reduce((sum, value) => sum + value.byteLength, 0);
    self.postMessage({ model, timing: mediaTiming(model.metadata), attributeBytes, decodeMilliseconds }, arrays.map(value => value.buffer));
  } catch (error) { self.postMessage({ error: error.message }); }
  finally { self.close(); }
};
