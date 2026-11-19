/** Presentation only: never feed this text back into engine inputs or exports. */
export function displayNumber(value: number, precision: "4" | "full" = "4"): string {
  if (value !== 0 && Math.abs(value) < .0001) return `${value < 0 ? "−" : ""}< 0.0001`;
  return precision === "full"
    ? value.toLocaleString("en-US", { useGrouping: false, maximumSignificantDigits: 21 })
    : Math.abs(value) >= 1e21 ? value.toLocaleString("en-US", { useGrouping: false, minimumFractionDigits: 4, maximumFractionDigits: 4 }) : value.toFixed(4);
}

/** Other labelled display precisions retain their convention, with the same floor. */
export function displayFixed(value: number, digits: number): string {
  const tiny = value !== 0 && Math.abs(value) < .0001;
  if (tiny || digits === 4) return displayNumber(value);
  return Math.abs(value) >= 1e21
    ? value.toLocaleString("en-US", { useGrouping: false, minimumFractionDigits: digits, maximumFractionDigits: digits })
    : value.toFixed(digits);
}
export function displayOptional(value: number | null | undefined): string | undefined {
  return value == null ? undefined : displayNumber(value);
}
export function displayPercent(value: number): string {
  const percent = value * 100;
  return `${percent !== 0 && Math.abs(percent) < .1 ? displayNumber(percent) : displayFixed(percent, 1)} %`;
}

/** Compact measurement labels retain familiar units without long binary decimals. */
export function displayCompact(value: number | string | null | undefined): string {
  return typeof value === "number" ? displayNumber(value).replace(/(\.\d*?[1-9])0+$|\.0+$/u, "$1") : String(value);
}
