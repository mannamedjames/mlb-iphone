// Variables used by Scriptable.
// These must be at the very top of the file. Do not edit.
// icon-color: light-brown; icon-glyph: magic;
// MLB Substitution Tracker — Scriptable (phone side, read-only)
// Fetches mlb_sub_tracker.json directly from GitHub.

const GITHUB_USER = "mannamedjames";
const GITHUB_REPO = "mlb-iphone";
const GITHUB_BRANCH = "main";
const DATA_URL = `https://raw.githubusercontent.com/${GITHUB_USER}/${GITHUB_REPO}/${GITHUB_BRANCH}/data/mlb_sub_tracker.json`;

async function loadData() {
  const req = new Request(DATA_URL);
  req.timeoutInterval = 15;
  const data = await req.loadJSON();
  if (!data || !Array.isArray(data.subbed_out) || !Array.isArray(data.subbed_in))
    throw new Error("Sub tracker data missing or malformed.");
  return data;
}

async function getTeamLogo(teamId) {
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

function buildWidget(data, logos, family) {
  const w = new ListWidget();
  w.backgroundColor = new Color("#0b1622");
  w.setPadding(12, 14, 12, 14);
  const title = w.addText("MLB Subs · last 30 days");
  title.font = Font.boldSystemFont(13);
  title.textColor = new Color("#7fd1ff");
  w.addSpacer(8);
  const cols = w.addStack();
  cols.layoutHorizontally();
  const addCol = (entries, header) => {
    const col = cols.addStack();
    col.layoutVertically();
    const h = col.addText(header);
    h.font = Font.boldSystemFont(9); h.textColor = new Color("#6b7785");
    col.addSpacer(4);
    const count = family === "large" ? 5 : family === "medium" ? 3 : 2;
    entries.slice(0, count).forEach((p, i) => {
      const row = col.addStack();
      row.layoutHorizontally();
      row.centerAlignContent();
      const logo = logos[p.teamId];
      if (logo) { const img = row.addImage(logo); img.imageSize = new Size(12, 12); row.addSpacer(3); }
      const line = row.addText(`${i+1}. ${p.name.split(" ").slice(-1)[0]} (${p.games}) · ${p.pctStarted}%`);
      line.font = Font.systemFont(9.5); line.textColor = Color.white(); line.lineLimit = 1;
      col.addSpacer(3);
    });
  };
  addCol(data.subbed_out, "SUBBED OUT");
  cols.addSpacer(10);
  addCol(data.subbed_in, "SUBBED IN");
  w.addSpacer(6);
  const upd = w.addText(`updated ${data.generated_at}`);
  upd.font = Font.systemFont(8); upd.textColor = new Color("#6b7785");
  return w;
}

function buildTable(data, logos) {
  const table = new UITable();
  table.showSeparators = true;
  const head = new UITableRow();
  head.isHeader = true;
  head.addText("MLB Subs · last 30 days", `updated ${data.generated_at}`).titleFont = Font.boldSystemFont(15);
  table.addRow(head);
  [["SUBBED OUT", data.subbed_out], ["SUBBED IN", data.subbed_in]].forEach(([label, entries]) => {
    const sec = new UITableRow(); sec.isHeader = true;
    sec.addText(label).titleFont = Font.semiboldSystemFont(13);
    table.addRow(sec);
    entries.forEach((p, i) => {
      const row = new UITableRow(); row.height = 44;
      const logo = logos[p.teamId];
      if (logo) { const c = row.addImage(logo); c.widthWeight = 10; }
      const left = row.addText(`${i+1}. ${p.name}`, `${p.games} times · ${p.pctStarted}% started`);
      left.titleFont = Font.systemFont(14); left.subtitleFont = Font.systemFont(11);
      left.subtitleColor = Color.gray(); left.widthWeight = 90;
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
      w.addText(String(e.message)).textColor = Color.white();
      w.backgroundColor = new Color("#0b1622"); Script.setWidget(w);
    } else {
      const a = new Alert(); a.title = "MLB Subs"; a.message = String(e.message); a.addAction("OK"); await a.present();
    }
    Script.complete(); return;
  }
  const ids = new Set([...data.subbed_out, ...data.subbed_in].map(p => p.teamId).filter(Boolean));
  const logos = {};
  await Promise.all([...ids].map(async id => { logos[id] = await getTeamLogo(id); }));
  if (config.runsInWidget) Script.setWidget(buildWidget(data, logos, config.widgetFamily || "large"));
  else await buildTable(data, logos).present();
  Script.complete();
}

await run();
