// Minimal ICU message formatting: {name}, {count, plural, one {...} other {...}} with '#'.
// Plural categories come from Intl.PluralRules, so every catalogue locale gets correct rules.
export function formatMessage(template: string, locale: string, values: Record<string, unknown> = {}): string {
  let out = "";
  let i = 0;
  while (i < template.length) {
    const ch = template[i];
    if (ch !== "{") { out += ch; i++; continue; }
    let depth = 0, j = i;
    for (; j < template.length; j++) {
      if (template[j] === "{") depth++;
      else if (template[j] === "}" && --depth === 0) break;
    }
    const inner = template.slice(i + 1, j);
    i = j + 1;
    const [name, kind, ...rest] = splitTop(inner);
    const value = values[name.trim()];
    if (kind?.trim() === "plural") {
      const n = Number(value);
      const options = parseOptions(rest.join(","));
      const exact = options[`=${n}`];
      const cat = new Intl.PluralRules(locale).select(n);
      const chosen = exact ?? options[cat] ?? options.other ?? "";
      out += formatMessage(chosen, locale, values).replace(/#/g, new Intl.NumberFormat(locale).format(n));
    } else {
      out += value === undefined ? `{${inner}}` : String(value);
    }
  }
  return out;
}

function splitTop(s: string): string[] {
  const parts: string[] = [];
  let depth = 0, cur = "";
  for (const c of s) {
    if (c === "{") depth++;
    if (c === "}") depth--;
    if (c === "," && depth === 0 && parts.length < 2) { parts.push(cur); cur = ""; continue; }
    cur += c;
  }
  parts.push(cur);
  return parts;
}

function parseOptions(s: string): Record<string, string> {
  const opts: Record<string, string> = {};
  const re = /\s*(=?\w+)\s*\{/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(s))) {
    let depth = 1, j = re.lastIndex;
    for (; j < s.length && depth; j++) {
      if (s[j] === "{") depth++;
      else if (s[j] === "}") depth--;
    }
    opts[m[1]] = s.slice(re.lastIndex, j - 1);
    re.lastIndex = j;
  }
  return opts;
}

export function formatDateTime(iso: string | null | undefined, locale: string): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" }).format(d);
}

export function formatRelative(iso: string | null | undefined, locale: string, now = Date.now()): string {
  if (!iso) return "—";
  const diff = (new Date(iso).getTime() - now) / 1000;
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });
  const abs = Math.abs(diff);
  if (abs < 60) return rtf.format(Math.round(diff), "second");
  if (abs < 3600) return rtf.format(Math.round(diff / 60), "minute");
  if (abs < 86400) return rtf.format(Math.round(diff / 3600), "hour");
  return rtf.format(Math.round(diff / 86400), "day");
}

export function formatNumber(n: number, locale: string): string {
  return new Intl.NumberFormat(locale).format(n);
}

/** Human-readable size (audit: "70,267 B"). Uses the locale's own unit formatting. */
export function formatBytes(n: number, locale: string): string {
  const units = ["byte", "kilobyte", "megabyte", "gigabyte", "terabyte"] as const;
  let i = 0, v = n;
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
  return new Intl.NumberFormat(locale, { style: "unit", unit: units[i], unitDisplay: "short",
    maximumFractionDigits: i === 0 ? 0 : 1 }).format(v);
}

export function formatCurrency(amount: number, currency: string, locale: string): string {
  return new Intl.NumberFormat(locale, { style: "currency", currency }).format(amount);
}

// Locale-aware search: accent- and case-insensitive comparison via Intl.Collator (L10N-09).
export function localeIncludes(haystack: string, needle: string, locale: string): boolean {
  if (!needle) return true;
  const coll = new Intl.Collator(locale, { sensitivity: "base", usage: "search" });
  const h = haystack.normalize("NFC"), n = needle.normalize("NFC");
  for (let i = 0; i + n.length <= h.length; i++) {
    if (coll.compare(h.slice(i, i + n.length), n) === 0) return true;
  }
  return false;
}
