/**
 * The date arithmetic behind `add_days` / `sub_days` / `format_date`.
 *
 * Deliberately narrow. Python's `date.fromisoformat` accepts a whole family of ISO 8601 spellings
 * (`20260907`, `2026-W36-1`, …); reproducing it would be a parser of its own for input the tooling
 * never produces. The embedded engine accepts `YYYY-MM-DD` and refuses the rest **loudly** — a
 * documented limit beats a silently different date (see docs/embedded.md).
 *
 * Everything runs in UTC. A local-time `Date` would shift the day across a DST boundary, which is
 * exactly the class of bug a date-only value must not have.
 */

import { TemplateError } from "../errors.js";
import { pythonRepr } from "./truthy.js";

const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})$/;

const DAY_MS = 86_400_000;

const WEEKDAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];

const MONTHS = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

/** Parse an ISO `YYYY-MM-DD` date, or raise the way the Python filter does. */
export function parseIsoDate(value: unknown, filter: string): Date {
  const match = typeof value === "string" ? ISO_DATE.exec(value.trim()) : null;
  if (match === null) {
    throw new TemplateError(`${filter}: cannot parse date ${pythonRepr(value)}`);
  }
  const [, year, month, day] = match as unknown as [string, string, string, string];
  const date = new Date(Date.UTC(Number(year), Number(month) - 1, Number(day)));
  // Date.UTC rolls 2026-02-30 over to March; Python refuses it, so refuse it too.
  if (date.getUTCMonth() !== Number(month) - 1 || date.getUTCDate() !== Number(day)) {
    throw new TemplateError(`${filter}: cannot parse date ${pythonRepr(value)}`);
  }
  return date;
}

export function shiftDays(date: Date, days: number): Date {
  return new Date(date.getTime() + days * DAY_MS);
}

export function toIsoDate(date: Date): string {
  return date.toISOString().slice(0, 10);
}

/**
 * The strftime directives the engine honours, with C-locale (English) names — the locale Python
 * runs the engine under. Anything else raises rather than passing the directive through, so an
 * unsupported format is visible at once instead of producing a plausible wrong string.
 */
export function strftime(date: Date, format: string, filter: string): string {
  let out = "";
  for (let i = 0; i < format.length; i += 1) {
    const char = format[i] as string;
    if (char !== "%") {
      out += char;
      continue;
    }
    const directive = format[i + 1];
    if (directive === undefined) {
      throw new TemplateError(`${filter}: trailing '%' in format ${pythonRepr(format)}`);
    }
    out += expand(date, directive, format, filter);
    i += 1;
  }
  return out;
}

function expand(date: Date, directive: string, format: string, filter: string): string {
  switch (directive) {
    case "Y":
      return String(date.getUTCFullYear()).padStart(4, "0");
    case "y":
      return String(date.getUTCFullYear() % 100).padStart(2, "0");
    case "m":
      return pad2(date.getUTCMonth() + 1);
    case "d":
      return pad2(date.getUTCDate());
    // A date carries no time; Python's strftime renders these as zero, and so do we.
    case "H":
    case "M":
    case "S":
      return "00";
    case "j":
      return String(dayOfYear(date)).padStart(3, "0");
    case "a":
      return (WEEKDAYS[date.getUTCDay()] as string).slice(0, 3);
    case "A":
      return WEEKDAYS[date.getUTCDay()] as string;
    case "b":
      return (MONTHS[date.getUTCMonth()] as string).slice(0, 3);
    case "B":
      return MONTHS[date.getUTCMonth()] as string;
    case "%":
      return "%";
    default:
      throw new TemplateError(
        `${filter}: unsupported strftime directive '%${directive}' in ${pythonRepr(format)}. ` +
          "The embedded engine supports %Y %y %m %d %H %M %S %j %a %A %b %B %%.",
      );
  }
}

function pad2(value: number): string {
  return String(value).padStart(2, "0");
}

function dayOfYear(date: Date): number {
  const start = Date.UTC(date.getUTCFullYear(), 0, 1);
  return Math.floor((date.getTime() - start) / DAY_MS) + 1;
}
