/** The only DOM side effect for downloads. Callers must capture and verify their analysis context. */
export function saveDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url; anchor.download = filename;
  document.body.append(anchor); anchor.click(); anchor.remove();
  // Browsers may start reading the object URL after the click handler returns.
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
