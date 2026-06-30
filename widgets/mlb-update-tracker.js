// Variables used by Scriptable.
// These must be at the very top of the file. Do not edit.
// icon-color: green; icon-glyph: magic;
// MLB Update Tracker — Scriptable (phone side)
// Fetches timestamps from all three GitHub data files and shows staleness.

const GITHUB_USER = "mannamedjames";
const GITHUB_REPO = "mlb-iphone";
const GITHUB_BRANCH = "main";
const RAW = `https://raw.githubusercontent.com/${GITHUB_USER}/${GITHUB_REPO}/${GITHUB_BRANCH}/data`;

const FEEDS = [
  { key: "matchups", label: "Matchups", url: `${RAW}/mlb_matchups.json` },
  { key: "subs",     label: "Subs",     url: `${RAW}/mlb_sub_tracker.json` },
  { key: "redsHr",   label: "Reds HRs", url: `${RAW}/reds_hr.json` },
];

const BG = new Color("#0b1622");
const MUTED = new Color("#6b7785");
const SUBTLE = new Color("#9bb0c4");
const GOOD = new Color("#2ecc71");
const WARN = new Color("#e8a23d");
const BAD = new Color("#e74c3c");
const HISTORY_MAX = 40;

function historyPath() {
  const fm = FileManager.local();
  return fm.joinPath(fm.libraryDirectory(), "mlb_update_history.json");
}
function loadHistory() {
  try {
    const fm = FileManager.local();
    const p = historyPath();
    if (fm.fileExists(p)) return JSON.parse(fm.readString(p));
  } catch(e) {}
  return { lastSeen: {}, log: [] };
}
function saveHistory(h) {
  try { FileManager.local().writeString(historyPath(), JSON.stringify(h)); } catch(e) {}
}
async function readFeed(url) {
  try {
    const req = new Request(url); req.timeoutInterval = 8;
    const parsed = await req.loadJSON();
    return parsed && parsed.generated_at ? parsed.generated_at : null;
  } catch(e) { return null; }
}
function parseStamp(s) {
  if (!s) return null;
  const m = s.match(/^(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2})$/);
  if (!m) return null;
  return new Date(+m[1], +m[2]-1, +m[3], +m[4], +m[5]);
}
function agoText(date) {
  if (!date) return "never";
  const mins = Math.round((Date.now() - date.getTime()) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ${mins % 60}m ago`;
  return `${Math.floor(hrs/24)}d ago`;
}
function staleColor(date) {
  if (!date) return BAD;
  const hrs = (Date.now() - date.getTime()) / 3600000;
  if (hrs <= 8) return GOOD;
  if (hrs <= 24) return WARN;
  return BAD;
}
function fmtDayClock(d) {
  try { return d.toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit", hour12: true }); }
  catch(e) { return ""; }
}
async function refreshHistory() {
  const h = loadHistory();
  for (const f of FEEDS) {
    const stamp = await readFeed(f.url);
    if (stamp && h.lastSeen[f.key] !== stamp) {
      h.lastSeen[f.key] = stamp;
      h.log.unshift({ key: f.key, label: f.label, stamp, observedAt: new Date().toISOString() });
    }
  }
  h.log = h.log.slice(0, HISTORY_MAX);
  saveHistory(h);
  return h;
}

function buildWidget(h, family) {
  const w = new ListWidget();
  w.backgroundColor = BG;
  w.setPadding(11, 13, 10, 13);
  const title = w.addText("⟳ Data Updates");
  title.font = Font.boldSystemFont(13); title.textColor = new Color("#7fd1ff");
  w.addSpacer(6);
  FEEDS.forEach(f => {
    const stamp = h.lastSeen[f.key];
    const d = parseStamp(stamp);
    const row = w.addStack();
    row.layoutHorizontally(); row.centerAlignContent();
    const dot = row.addText("●"); dot.font = Font.systemFont(10); dot.textColor = staleColor(d);
    row.addSpacer(5);
    const lbl = row.addText(f.label); lbl.font = Font.semiboldSystemFont(11); lbl.textColor = Color.white();
    row.addSpacer();
    const ago = row.addText(agoText(d)); ago.font = Font.systemFont(10); ago.textColor = SUBTLE;
    w.addSpacer(4);
  });
  if (family === "large" && h.log.length) {
    w.addSpacer(4);
    const lh = w.addText("Recent updates"); lh.font = Font.semiboldSystemFont(9); lh.textColor = MUTED;
    w.addSpacer(3);
    h.log.slice(0, 8).forEach(e => {
      const obs = new Date(e.observedAt);
      const line = w.addText(`${e.label} · ${e.stamp}  (seen ${fmtDayClock(obs)})`);
      line.font = Font.systemFont(8.5); line.textColor = SUBTLE; line.lineLimit = 1;
      w.addSpacer(1);
    });
  }
  return w;
}

function buildTable(h) {
  const table = new UITable();
  table.showSeparators = true;
  const head = new UITableRow(); head.isHeader = true;
  head.addText("Data Update Status").titleFont = Font.boldSystemFont(16);
  table.addRow(head);
  FEEDS.forEach(f => {
    const d = parseStamp(h.lastSeen[f.key]);
    const row = new UITableRow(); row.height = 50;
    const dot = row.addText("●"); dot.titleColor = staleColor(d); dot.titleFont = Font.boldSystemFont(20); dot.widthWeight = 10;
    const left = row.addText(f.label, h.lastSeen[f.key] || "never updated");
    left.titleFont = Font.semiboldSystemFont(15); left.subtitleFont = Font.systemFont(11);
    left.subtitleColor = Color.gray(); left.widthWeight = 60;
    const right = row.addText(agoText(d)); right.titleFont = Font.systemFont(13);
    right.titleColor = SUBTLE; right.rightAligned(); right.widthWeight = 30;
    table.addRow(row);
  });
  const lg = new UITableRow(); lg.isHeader = true; lg.backgroundColor = new Color("#15263b");
  lg.addText("Observed update history").titleFont = Font.semiboldSystemFont(13);
  table.addRow(lg);
  if (!h.log.length) {
    const none = new UITableRow();
    none.addText("Nothing observed yet — leave the widget on your Home Screen and it will fill in.").titleFont = Font.systemFont(12);
    table.addRow(none);
  } else {
    h.log.forEach(e => {
      const obs = new Date(e.observedAt);
      const row = new UITableRow(); row.height = 40;
      const r = row.addText(`${e.label} updated ${e.stamp}`, `observed ${fmtDayClock(obs)}`);
      r.titleFont = Font.systemFont(13); r.subtitleFont = Font.systemFont(10); r.subtitleColor = Color.gray();
      table.addRow(row);
    });
  }
  return table;
}

async function run() {
  const h = await refreshHistory();
  if (config.runsInWidget) Script.setWidget(buildWidget(h, config.widgetFamily || "medium"));
  else await buildTable(h).present();
  Script.complete();
}

await run();
