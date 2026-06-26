// MLB Substitution Tracker — Scriptable (phone side, read-only)
// Reads mlb_sub_tracker.json from the Scriptable iCloud folder (written daily
// by your Mac). Run in-app for a full table; add to Home Screen as a widget.

const FILENAME = "mlb_sub_tracker.json";

async function loadData() {
  const fm = FileManager.iCloud();
  const path = fm.joinPath(fm.documentsDirectory(), FILENAME);
  if (!fm.fileExists(path)) {
    throw new Error("No data file yet. Run the Mac job first.");
  }
  if (!fm.isFileDownloaded(path)) {
    await fm.downloadFileFromiCloud(path);
  }
  return JSON.parse(fm.readString(path));
}

// ------------------------------------------------------------- logo caching
// Team logos are small, static, and the same every day, so they're cached
// locally (not in iCloud) after the first download — no repeat network
// calls on later widget refreshes.
async function getTeamLogo(teamId) {
  if (!teamId) return null;
  const fm = FileManager.local();
  const dir = fm.joinPath(fm.libraryDirectory(), "mlb-logos");
  if (!fm.fileExists(dir)) fm.createDirectory(dir, true);
  const path = fm.joinPath(dir, `${teamId}.png`);
  if (fm.fileExists(path)) {
    try {
      return fm.readImage(path);
    } catch (e) {
      // fall through and refetch
    }
  }
  try {
    const req = new Request(`https://midfield.mlbstatic.com/v1/team/${teamId}/spots/100`);
    const img = await req.loadImage();
    try { fm.writeImage(path, img); } catch (e) { /* cache write is best-effort */ }
    return img;
  } catch (e) {
    return null; // no logo available — renderer should just skip it
  }
}

async function preloadLogos(data) {
  const allRows = [...data.subbed_out, ...data.subbed_in];
  const teamIds = [...new Set(allRows.map((r) => r.teamId).filter(Boolean))];
  const logos = {};
  await Promise.all(
    teamIds.map(async (id) => {
      logos[id] = await getTeamLogo(id);
    })
  );
  return logos;
}

// ---------------------------------------------------------------- widget view
function buildWidget(data, family, logos) {
  const w = new ListWidget();
  w.backgroundColor = new Color("#0b1622");
  w.setPadding(12, 14, 12, 14);

  const header = w.addText("MLB Subs · last 30 days");
  header.font = Font.semiboldSystemFont(12);
  header.textColor = new Color("#7fd1ff");
  w.addSpacing(6);

  const count = family === "small" ? 3 : 5;

  if (family === "large" || family === "medium") {
    const cols = w.addStack();
    cols.layoutHorizontally();
    addColumn(cols, "SUBBED OUT", data.subbed_out, count, logos);
    cols.addSpacing(10);
    addColumn(cols, "SUBBED IN", data.subbed_in, count, logos);
  } else {
    addColumn(w, "SUBBED OUT", data.subbed_out, count, logos);
  }

  w.addSpacing(6);
  const foot = w.addText(`updated ${data.generated_at}`);
  foot.font = Font.systemFont(8);
  foot.textColor = new Color("#56708a");
  return w;
}

function addColumn(parent, title, rows, count, logos) {
  const col = parent.addStack();
  col.layoutVertically();
  const t = col.addText(title);
  t.font = Font.boldSystemFont(9);
  t.textColor = new Color("#9bb0c4");
  col.addSpacing(3);
  rows.slice(0, count).forEach((r) => {
    const rowStack = col.addStack();
    rowStack.layoutHorizontally();
    rowStack.centerAlignContent();
    const logo = logos[r.teamId];
    if (logo) {
      const img = rowStack.addImage(logo);
      img.imageSize = new Size(13, 13);
      rowStack.addSpacing(4);
    }
    const pctText = r.pctStarted != null ? ` · ${r.pctStarted}%` : "";
    const line = rowStack.addText(`${r.rank}. ${shorten(r.name)} (${r.games})${pctText}`);
    line.font = Font.systemFont(10);
    line.textColor = Color.white();
    line.lineLimit = 1;
    col.addSpacing(1);
  });
}

function shorten(name) {
  const parts = name.split(" ");
  if (parts.length < 2) return name;
  return `${parts[0][0]}. ${parts.slice(1).join(" ")}`;
}

// -------------------------------------------------------------- in-app table
function buildTable(data, logos) {
  const table = new UITable();
  table.showSeparators = true;

  const head = new UITableRow();
  head.isHeader = true;
  const hc = head.addText(
    `Last 30 days · ${data.games_processed} games · ${data.generated_at}`
  );
  hc.titleFont = Font.boldSystemFont(13);
  table.addRow(head);

  addSection(table, "Subbed OUT (started, then exited)", data.subbed_out, logos);
  addSection(table, "Subbed IN (PH / PR / def. replacement)", data.subbed_in, logos);
  return table;
}

function addSection(table, title, rows, logos) {
  const sec = new UITableRow();
  sec.isHeader = true;
  sec.backgroundColor = new Color("#16263a");
  const s = sec.addText(title);
  s.titleColor = new Color("#7fd1ff");
  s.titleFont = Font.semiboldSystemFont(12);
  table.addRow(sec);

  rows.forEach((r) => {
    const row = new UITableRow();
    row.height = 54;

    const logo = logos[r.teamId];
    if (logo) {
      const imgCell = row.addImage(logo);
      imgCell.widthWeight = 12;
    }

    const left = row.addText(`${r.rank}. ${r.name}`, r.teamName || r.team || "");
    left.titleFont = Font.systemFont(15);
    left.subtitleFont = Font.systemFont(11);
    left.subtitleColor = Color.gray();
    left.widthWeight = logo ? 56 : 65;

    const pctLine = r.pctStarted != null ? `${r.pctStarted}% started` : "—";
    const right = row.addText(`${r.games} games`, `${pctLine} · ${r.hits} H`);
    right.titleFont = Font.semiboldSystemFont(15);
    right.subtitleFont = Font.systemFont(11);
    right.subtitleColor = Color.gray();
    right.rightAligned();
    right.widthWeight = 32;

    table.addRow(row);
  });
}

// ----------------------------------------------------------------------- run
async function run() {
  let data;
  try {
    data = await loadData();
  } catch (e) {
    if (config.runsInWidget) {
      const w = new ListWidget();
      w.addText(String(e.message)).textColor = Color.white();
      w.backgroundColor = new Color("#0b1622");
      Script.setWidget(w);
    } else {
      const a = new Alert();
      a.title = "MLB Sub Tracker";
      a.message = String(e.message);
      a.addAction("OK");
      await a.present();
    }
    Script.complete();
    return;
  }

  const logos = await preloadLogos(data);

  if (config.runsInWidget) {
    Script.setWidget(buildWidget(data, config.widgetFamily || "medium", logos));
  } else {
    await buildTable(data, logos).present();
  }
  Script.complete();
}

await run();