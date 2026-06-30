// Variables used by Scriptable.
// These must be at the very top of the file. Do not edit.
// icon-color: blue; icon-glyph: magic;
// MLB Daily Matchups — Scriptable (phone side, read-only)
// Fetches mlb_matchups.json directly from GitHub — no iCloud sync needed.

const GITHUB_USER = "mannamedjames";
const GITHUB_REPO = "mlb-iphone";
const GITHUB_BRANCH = "main";
const DATA_URL = `https://raw.githubusercontent.com/${GITHUB_USER}/${GITHUB_REPO}/${GITHUB_BRANCH}/data/mlb_matchups.json`;

const MAX_RANK = 30;
const NUM_COL = 23;
const NUM_AREA = NUM_COL * 3;
const BG = new Color("#0b1622");
const CARD_BG = new Color("#15263b");
const MUTED = new Color("#6b7785");
const SUBTLE = new Color("#9bb0c4");

async function loadData() {
  const req = new Request(DATA_URL);
  req.timeoutInterval = 15;
  const data = await req.loadJSON();
  if (!data || !Array.isArray(data.games)) throw new Error("Matchup data missing or malformed.");
  try {
    const fm = FileManager.local();
    fm.writeString(fm.joinPath(fm.libraryDirectory(), "mlb_matchups_last_good.json"),
      JSON.stringify({ generatedAt: data.generated_at, savedAt: new Date().toISOString() }));
  } catch (e) {}
  return data;
}

async function getTeamLogo(teamId) {
  if (!teamId) return null;
  const fm = FileManager.local();
  const dir = fm.joinPath(fm.libraryDirectory(), "mlb-logos");
  if (!fm.fileExists(dir)) fm.createDirectory(dir, true);
  const path = fm.joinPath(dir, `${teamId}.png`);
  if (fm.fileExists(path)) { try { return fm.readImage(path); } catch (e) {} }
  try {
    const img = await new Request(`https://midfield.mlbstatic.com/v1/team/${teamId}/spots/100`).loadImage();
    try { fm.writeImage(path, img); } catch (e) {}
    return img;
  } catch (e) { return null; }
}

function colorForRank(rank) {
  if (rank == null) return MUTED;
  const t = Math.max(0, Math.min(1, (rank - 1) / (MAX_RANK - 1)));
  const from = { r: 46, g: 204, b: 113 }, to = { r: 231, g: 76, b: 60 };
  const r = Math.round(from.r + (to.r - from.r) * t);
  const g = Math.round(from.g + (to.g - from.g) * t);
  const b = Math.round(from.b + (to.b - from.b) * t);
  return new Color(`#${[r,g,b].map(v=>v.toString(16).padStart(2,"0")).join("")}`);
}

function formatTime(iso) {
  if (!iso) return "";
  try { return new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit", hour12: true }); }
  catch (e) { return ""; }
}

function formatTimestampVerbose(input) {
  try {
    const d = input instanceof Date ? input : new Date(input);
    if (isNaN(d.getTime())) return String(input);
    return d.toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit", hour12: true, timeZoneName: "short" });
  } catch (e) { return String(input); }
}

function dhTag(g) { return g.doubleHeader && g.doubleHeader !== "N" ? ` G${g.gameNumber}` : ""; }

function weatherIcon(w) {
  if (!w || !w.condition) return null;
  const c = w.condition.toLowerCase();
  if (c.includes("rain") || c.includes("shower")) return "🌧️";
  if (c.includes("dome") || c.includes("roof")) return "🏟️";
  if (c.includes("snow")) return "❄️";
  if (c.includes("cloud") || c.includes("overcast")) return "☁️";
  if (c.includes("clear") || c.includes("sun")) return "☀️";
  return "🌤️";
}

function weatherText(w) {
  if (!w) return "";
  const icon = weatherIcon(w) || "";
  const temp = w.temp ? `${w.temp}°` : "";
  const wind = w.wind ? ` · ${w.wind}` : "";
  return `${icon} ${temp}${wind}`.trim();
}

async function preloadLogos(data) {
  const ids = new Set();
  data.games.forEach(g => { ids.add(g.home.teamId); ids.add(g.away.teamId); });
  const logos = {};
  await Promise.all([...ids].filter(Boolean).map(async id => { logos[id] = await getTeamLogo(id); }));
  return logos;
}

function bestRank(starter) {
  if (!starter.confirmed || !starter.oppSplits) return null;
  const s = starter.oppSplits;
  const ranks = [s.woba30Rank, s.woba7Rank, s.kPct30Rank].filter(r => r != null);
  return ranks.length ? Math.min(...ranks) : null;
}

function addColumnHeader(parent, cardWidth) {
  const wrap = parent.addStack();
  wrap.layoutHorizontally();
  wrap.size = new Size(cardWidth, 0);
  wrap.addSpacer();
  ["wOBA30","wOBA7","K%30"].forEach(lbl => {
    const cell = wrap.addStack();
    cell.size = new Size(NUM_COL, 0);
    const t = cell.addText(lbl);
    t.font = Font.systemFont(7);
    t.textColor = MUTED;
    t.lineLimit = 1;
    t.minimumScaleFactor = 0.6;
    t.centerAlignText();
  });
}

function buildWidget(data, logos, family) {
  const w = new ListWidget();
  w.backgroundColor = BG;
  w.setPadding(10, 12, 9, 12);

  const header = w.addStack();
  header.layoutHorizontally();
  header.centerAlignContent();
  const title = header.addText("⚾ MLB Matchups");
  title.font = Font.boldSystemFont(12.5);
  title.textColor = new Color("#7fd1ff");
  header.addSpacer();
  const updated = header.addText(data.generated_at);
  updated.font = Font.systemFont(7.5);
  updated.textColor = MUTED;
  w.addSpacer(4);

  const now = new Date();
  const upcoming = data.games.filter(g => new Date(g.gameTime) > now);
  const showingTomorrow = upcoming.length === 0 && Array.isArray(data.games_tomorrow) && data.games_tomorrow.length > 0;
  const games = showingTomorrow ? data.games_tomorrow : upcoming;

  if (games.length === 0) {
    const msg = w.addText(data.games.length ? "All today's games are underway" : "No games today");
    msg.font = Font.systemFont(10); msg.textColor = MUTED;
    return w;
  }

  if (showingTomorrow) {
    const tmrw = w.addText("TOMORROW · " + (data.date_tomorrow || ""));
    tmrw.font = Font.boldSystemFont(8.5);
    tmrw.textColor = new Color("#e8a23d");
    w.addSpacer(3);
  }

  const cardWidth = family === "small" ? 285 : 153;
  const colHead = w.addStack();
  colHead.layoutHorizontally();
  addColumnHeader(colHead, cardWidth);
  if (family !== "small") { colHead.addSpacer(8); addColumnHeader(colHead, cardWidth); }
  w.addSpacer(5);

  const rowsShown = family === "large" ? 8 : family === "medium" ? 4 : 3;
  const shown = games.slice(0, rowsShown);

  shown.forEach((g, i) => {
    const gh = w.addText(`${g.away.teamAbbr} @ ${g.home.teamAbbr}${dhTag(g)} · ${formatTime(g.gameTime)}`);
    gh.font = Font.semiboldSystemFont(8);
    gh.textColor = SUBTLE;
    gh.lineLimit = 1;
    w.addSpacer(2);
    const row = w.addStack();
    row.layoutHorizontally();
    addPitcherLine(row, g.away, logos, cardWidth);
    if (family !== "small") { row.addSpacer(8); addPitcherLine(row, g.home, logos, cardWidth); }
    if (i < shown.length - 1) w.addSpacer(6);
  });

  if (games.length > rowsShown) {
    w.addSpacer(4);
    const more = w.addText(`+${games.length - rowsShown} more — open app`);
    more.font = Font.systemFont(7.5); more.textColor = MUTED;
  }
  return w;
}

function addPitcherLine(parent, side, logos, width) {
  const line = parent.addStack();
  line.layoutHorizontally();
  line.centerAlignContent();
  line.size = new Size(width, 0);
  const s = side.starter;
  const accent = line.addStack();
  accent.size = new Size(3, 15);
  accent.backgroundColor = colorForRank(bestRank(s));
  line.addSpacer(4);
  const logo = logos[side.teamId];
  if (logo) { const img = line.addImage(logo); img.imageSize = new Size(13, 13); line.addSpacer(4); }
  const lastName = s.confirmed ? s.name.split(" ").slice(-1)[0] : "TBD";
  const nameText = s.confirmed ? `${lastName} ${s.hand || "?"}${s.isOpener ? " Ⓞ" : ""}` : "TBD";
  const name = line.addText(nameText);
  name.font = Font.semiboldSystemFont(10.5);
  name.textColor = Color.white();
  name.lineLimit = 1;
  name.minimumScaleFactor = 0.6;
  line.addSpacer();
  const nums = line.addStack();
  nums.layoutHorizontally();
  nums.size = new Size(NUM_AREA, 0);
  if (s.confirmed && s.oppSplits) {
    [s.oppSplits.woba30Rank, s.oppSplits.woba7Rank, s.oppSplits.kPct30Rank].forEach(rank => {
      const cell = nums.addStack();
      cell.size = new Size(NUM_COL, 0);
      const t = cell.addText(rank != null ? `${rank}` : "–");
      t.font = Font.boldSystemFont(11.5);
      t.textColor = colorForRank(rank);
      t.centerAlignText();
    });
  } else {
    const cell = nums.addStack();
    cell.size = new Size(NUM_AREA, 0);
    const t = cell.addText(s.confirmed ? "no data" : "not conf.");
    t.font = Font.systemFont(7.5); t.textColor = MUTED; t.centerAlignText();
  }
}

function buildTable(data, logos) {
  const table = new UITable();
  table.showSeparators = true;
  const head = new UITableRow();
  head.isHeader = true;
  const hc = head.addText(`⚾ Updated ${data.generated_at}`, `${data.date} · ${data.games.length} games`);
  hc.titleFont = Font.boldSystemFont(15); hc.titleColor = new Color("#7fd1ff");
  table.addRow(head);
  data.games.forEach(g => {
    const sec = new UITableRow();
    sec.isHeader = true; sec.backgroundColor = CARD_BG;
    const wx = weatherText(g.weather);
    const subtitle = [formatTime(g.gameTime), wx].filter(Boolean).join("  ·  ");
    const s = sec.addText(`${g.away.teamAbbr} @ ${g.home.teamAbbr}${dhTag(g)}`, subtitle);
    s.titleFont = Font.semiboldSystemFont(14); s.subtitleFont = Font.systemFont(11); s.subtitleColor = SUBTLE;
    table.addRow(sec);
    [{ side: g.away, opp: g.home.teamAbbr }, { side: g.home, opp: g.away.teamAbbr }].forEach(({ side, opp }) => {
      const starter = side.starter;
      const row = new UITableRow(); row.height = 64;
      const logo = logos[side.teamId];
      if (logo) { const c = row.addImage(logo); c.widthWeight = 10; }
      const openerSuffix = starter.confirmed && starter.isOpener ? "  [O]" : "";
      const nameText = starter.confirmed ? `${starter.name} (${starter.hand || "?"})${openerSuffix}` : "TBD — not confirmed";
      const left = row.addText(nameText, `vs ${opp}` + (starter.confirmed ? ` · ${starter.era ?? "—"} ERA · ${starter.ipDisplay ?? "—"} IP · ${starter.avgIpPerOuting ?? "—"} IP/out` : ""));
      left.titleFont = Font.systemFont(14); left.subtitleFont = Font.systemFont(10); left.subtitleColor = Color.gray(); left.widthWeight = 50;
      const splits = starter.confirmed ? starter.oppSplits : null;
      [["30d wOBA", splits ? splits.woba30Rank : null, splits ? splits.woba30 : null],
       ["7d wOBA",  splits ? splits.woba7Rank  : null, splits ? splits.woba7  : null],
       ["30d K%",   splits ? splits.kPct30Rank : null, splits ? splits.kPct30 : null],
      ].forEach(([label, rank, value]) => {
        const cell = row.addText(rank != null ? `#${rank}` : "—", `${label}${value != null ? ` · ${value}` : ""}`);
        cell.titleFont = Font.boldSystemFont(15); cell.titleColor = colorForRank(rank);
        cell.subtitleFont = Font.systemFont(9); cell.subtitleColor = Color.gray(); cell.widthWeight = 16.5;
      });
      table.addRow(row);
    });
  });
  return table;
}

async function run() {
  let data;
  try { data = await loadData(); }
  catch (e) {
    if (config.runsInWidget) {
      const w = new ListWidget();
      const t = w.addText(String(e.message)); t.textColor = Color.white(); t.font = Font.systemFont(11);
      w.backgroundColor = BG; Script.setWidget(w);
    } else {
      const a = new Alert(); a.title = "MLB Matchups"; a.message = String(e.message); a.addAction("OK"); await a.present();
    }
    Script.complete(); return;
  }
  const logos = await preloadLogos(data);
  if (config.runsInWidget) Script.setWidget(buildWidget(data, logos, config.widgetFamily || "large"));
  else await buildTable(data, logos).present();
  Script.complete();
}

await run();
