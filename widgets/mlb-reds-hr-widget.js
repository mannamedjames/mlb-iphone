// Variables used by Scriptable.
// These must be at the very top of the file. Do not edit.
// icon-color: cyan; icon-glyph: magic;
// Reds Home Run Tracker — Scriptable (phone side, read-only)
// Fetches reds_hr.json directly from GitHub.

const GITHUB_USER = "mannamedjames";
const GITHUB_REPO = "mlb-iphone";
const GITHUB_BRANCH = "main";
const DATA_URL = `https://raw.githubusercontent.com/${GITHUB_USER}/${GITHUB_REPO}/${GITHUB_BRANCH}/data/reds_hr.json`;

const WHITE = Color.white();
const REDS_RED = new Color("#c6011f");
const REDS_BLACK = new Color("#000000");
const GRAY = new Color("#6b6b6b");
const LIGHT_LINE = new Color("#e2e2e2");
const REDS_TEAM_ID = 113;

async function loadData() {
  const req = new Request(DATA_URL);
  req.timeoutInterval = 15;
  const data = await req.loadJSON();
  if (!data || !Array.isArray(data.homers)) throw new Error("Reds HR data missing or malformed.");
  return data;
}

async function getLogo(teamId) {
  if (!teamId) return null;
  const fm = FileManager.local();
  const dir = fm.joinPath(fm.libraryDirectory(), "mlb-logos");
  if (!fm.fileExists(dir)) fm.createDirectory(dir, true);
  const path = fm.joinPath(dir, `${teamId}.png`);
  if (fm.fileExists(path)) { try { return fm.readImage(path); } catch(e) {} }
  try {
    const img = await new Request(`https://midfield.mlbstatic.com/v1/team/${teamId}/spots/100`).loadImage();
    try { fm.writeImage(path, img); } catch(e) {}
    return img;
  } catch(e) { return null; }
}

async function preloadLogos(data) {
  const ids = new Set([REDS_TEAM_ID]);
  data.homers.forEach(h => { if (h.opponentId) ids.add(h.opponentId); });
  const logos = {};
  await Promise.all([...ids].map(async id => { logos[id] = await getLogo(id); }));
  return logos;
}

function shortDate(d) {
  try { return new Date(d + "T12:00:00").toLocaleDateString([], { month: "short", day: "numeric" }); }
  catch(e) { return d; }
}
function inningOuts(h) {
  const half = h.halfInning === "Top" ? "Top" : h.halfInning === "Bot" ? "Bot" : "";
  const inn = h.inning != null ? `${half} ${h.inning}` : "?";
  const outs = h.outs != null ? `${h.outs} out${h.outs === 1 ? "" : "s"}` : "";
  return [inn, outs].filter(Boolean).join(", ");
}
function rbiBadgeText(rbi) {
  if (rbi >= 4) return "GRAND SLAM";
  if (rbi === 3) return "3-RUN";
  if (rbi === 2) return "2-RUN";
  return null;
}
function parseGeneratedAt(s) {
  const m = String(s).match(/^(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2})$/);
  if (!m) return null;
  return new Date(+m[1], +m[2]-1, +m[3], +m[4], +m[5]);
}
function formatUpdated(s) {
  const d = parseGeneratedAt(s);
  if (!d) return `Updated ${s}`;
  return `Updated ${d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit", hour12: true })}`;
}
function addDivider(parent) {
  const line = parent.addStack();
  line.size = new Size(0, 1);
  line.backgroundColor = LIGHT_LINE;
}
function addHomerRow(parent, h, logos) {
  const row = parent.addStack();
  row.layoutVertically();
  const line1 = row.addStack();
  line1.layoutHorizontally();
  line1.centerAlignContent();
  const logo = logos[h.opponentId];
  if (logo) { const img = line1.addImage(logo); img.imageSize = new Size(15, 15); line1.addSpacer(5); }
  const name = line1.addText(h.batter);
  name.font = Font.boldSystemFont(12.5); name.textColor = REDS_BLACK;
  name.lineLimit = 1; name.minimumScaleFactor = 0.7;
  const badge = rbiBadgeText(h.rbi);
  if (badge) {
    line1.addSpacer(5);
    const pill = line1.addStack();
    pill.backgroundColor = REDS_RED; pill.cornerRadius = 4; pill.setPadding(1.5, 5, 1.5, 5);
    const pt = pill.addText(badge); pt.font = Font.boldSystemFont(7.5); pt.textColor = WHITE;
  }
  line1.addSpacer();
  const dist = line1.addText(h.distanceFt != null ? `${h.distanceFt} ft` : "—");
  dist.font = Font.boldSystemFont(15);
  dist.textColor = h.distanceFt != null ? REDS_RED : GRAY;
  row.addSpacer(2);
  const meta = row.addText(`${shortDate(h.date)} vs ${h.opponent || "?"} · ${inningOuts(h)}`);
  meta.font = Font.systemFont(9); meta.textColor = GRAY;
  meta.lineLimit = 1; meta.minimumScaleFactor = 0.8;
}

function buildWidget(data, logos, family) {
  const w = new ListWidget();
  w.backgroundColor = WHITE;
  w.setPadding(0, 0, 0, 0);
  const frame = w.addStack();
  frame.layoutVertically();
  frame.backgroundColor = WHITE;
  frame.borderWidth = 1.5; frame.borderColor = REDS_RED;
  frame.cornerRadius = 14; frame.setPadding(10, 12, 9, 12);
  const logo = logos[REDS_TEAM_ID];
  if (logo) {
    const logoRow = frame.addStack();
    logoRow.layoutHorizontally(); logoRow.addSpacer();
    const img = logoRow.addImage(logo); img.imageSize = new Size(18, 18);
    logoRow.addSpacer(); frame.addSpacer(3);
  }
  const title = frame.addText("REDS HOME RUNS");
  title.font = Font.heavySystemFont(13.5); title.textColor = REDS_RED; title.centerAlignText();
  const upd = frame.addText(formatUpdated(data.generated_at));
  upd.font = Font.systemFont(8); upd.textColor = GRAY; upd.centerAlignText();
  frame.addSpacer(7);
  addDivider(frame);
  frame.addSpacer(8);
  if (data.homers.length === 0) {
    const m = frame.addText("No Reds HRs in the window.");
    m.font = Font.systemFont(10); m.textColor = GRAY; m.centerAlignText();
    return w;
  }
  const count = family === "large" ? 6 : family === "medium" ? 3 : 2;
  const shown = data.homers.slice(0, count);
  shown.forEach((h, i) => {
    addHomerRow(frame, h, logos);
    if (i < shown.length - 1) { frame.addSpacer(6); addDivider(frame); frame.addSpacer(6); }
  });
  if (data.homers.length > count) {
    frame.addSpacer(7);
    const more = frame.addText(`+${data.homers.length - count} more — open app`);
    more.font = Font.systemFont(7.5); more.textColor = GRAY; more.centerAlignText();
  }
  return w;
}

function buildTable(data, logos) {
  const table = new UITable();
  table.showSeparators = true;
  const head = new UITableRow();
  head.isHeader = true;
  const hc = head.addText(`Reds HRs — ${formatUpdated(data.generated_at)}`, `last ${data.homers.length}, window ${data.window_start} to ${data.window_end}`);
  hc.titleFont = Font.boldSystemFont(15); hc.titleColor = REDS_RED; hc.subtitleColor = GRAY;
  table.addRow(head);
  data.homers.forEach(h => {
    const top = new UITableRow(); top.height = 56;
    const logo = logos[h.opponentId];
    if (logo) { const c = top.addImage(logo); c.widthWeight = 12; }
    const badge = rbiBadgeText(h.rbi);
    const titleText = badge ? `${h.batter}  •  ${badge}` : `${h.batter} — ${h.rbi} RBI`;
    const left = top.addText(titleText, `${shortDate(h.date)} vs ${h.opponent} · ${inningOuts(h)}`);
    left.titleFont = Font.semiboldSystemFont(15); left.subtitleFont = Font.systemFont(11);
    left.subtitleColor = Color.gray(); left.widthWeight = 68;
    const right = top.addText(h.distanceFt != null ? `${h.distanceFt} ft` : "—", h.exitVeloMph != null ? `${h.exitVeloMph} mph EV` : "");
    right.titleFont = Font.boldSystemFont(16); right.titleColor = REDS_RED;
    right.subtitleFont = Font.systemFont(10); right.subtitleColor = Color.gray();
    right.rightAligned(); right.widthWeight = 32;
    table.addRow(top);
    const detail = new UITableRow(); detail.height = 40;
    const pitchInfo = [h.pitch, h.pitchSpeed != null ? `${h.pitchSpeed} mph` : null, h.count ? `${h.count} count` : null].filter(Boolean).join(" · ");
    const fieldInfo = [h.field ? `to ${h.field}` : null, h.pitcher ? `off ${h.pitcher}${h.pitcherHand ? ` (${h.pitcherHand})` : ""}` : null].filter(Boolean).join(" · ");
    const d = detail.addText(pitchInfo || "—", fieldInfo || "");
    d.titleFont = Font.systemFont(12); d.titleColor = Color.darkGray();
    d.subtitleFont = Font.systemFont(11); d.subtitleColor = Color.gray();
    table.addRow(detail);
  });
  return table;
}

async function run() {
  let data;
  try { data = await loadData(); }
  catch(e) {
    if (config.runsInWidget) {
      const w = new ListWidget();
      const t = w.addText(String(e.message)); t.textColor = REDS_BLACK; t.font = Font.systemFont(11);
      w.backgroundColor = WHITE; Script.setWidget(w);
    } else {
      const a = new Alert(); a.title = "Reds HRs"; a.message = String(e.message); a.addAction("OK"); await a.present();
    }
    Script.complete(); return;
  }
  const logos = await preloadLogos(data);
  if (config.runsInWidget) Script.setWidget(buildWidget(data, logos, config.widgetFamily || "large"));
  else await buildTable(data, logos).present();
  Script.complete();
}

await run();
