// Variables used by Scriptable.
// These must be at the very top of the file. Do not edit.
// icon-color: light-brown; icon-glyph: magic;
// MLB Refresh — phone-side trigger (GitHub Actions version)

const GITHUB_USER = "mannamedjames";
const GITHUB_REPO = "mlb-iphone";
const GITHUB_BRANCH = "main";

const pat = Keychain.get("mlb_github_pat");
if (!pat) {
  const a = new Alert();
  a.title = "PAT not found";
  a.message = 'Run this once in Scriptable\'s REPL:\nKeychain.set("mlb_github_pat", "ghp_...")';
  a.addAction("OK");
  await a.present();
  Script.complete();
}

const sheet = new Alert();
sheet.title = "Refresh MLB Data";
sheet.message = "\"Splits + Reds HRs\" is slow (a few minutes). Everything else is quick.";
sheet.addAction("All (subs + matchups + splits)");
sheet.addAction("Sub Tracker only");
sheet.addAction("Matchups only");
sheet.addAction("Splits + Reds HRs only");
sheet.addCancelAction("Cancel");

const choiceIdx = await sheet.presentSheet();

if (choiceIdx >= 0) {
  const CHOICES = [
    { label: "all",      workflow: "matchups.yml", input: "all",      heavy: false },
    { label: "subs",     workflow: "matchups.yml", input: "subs",     heavy: false },
    { label: "matchups", workflow: "matchups.yml", input: "matchups", heavy: false },
    { label: "splits",   workflow: "splits.yml",   input: null,       heavy: true  },
  ];
  const choice = CHOICES[choiceIdx];
  const url = `https://api.github.com/repos/${GITHUB_USER}/${GITHUB_REPO}/actions/workflows/${choice.workflow}/dispatches`;
  const req = new Request(url);
  req.method = "POST";
  req.headers = {
    "Authorization": `token ${pat}`,
    "Accept": "application/vnd.github.v3+json",
    "Content-Type": "application/json",
  };
  req.body = JSON.stringify({
    ref: GITHUB_BRANCH,
    ...(choice.input ? { inputs: { target: choice.input } } : {}),
  });
  let ok = false;
  try { await req.load(); ok = req.response.statusCode === 204; } catch(e) {}
  const confirm = new Alert();
  if (ok) {
    const eta = choice.heavy ? "Takes a few minutes — check GitHub Actions for progress." : "Data should appear within about 60–90 seconds.";
    confirm.title = "✓ Dispatched";
    confirm.message = `Target: ${choice.label}. ${eta}`;
  } else {
    confirm.title = "Dispatch may have failed";
    confirm.message = "Check your PAT has the \"workflow\" scope. Status: " + (req.response?.statusCode ?? "unknown");
  }
  confirm.addAction("OK");
  await confirm.present();
}

Script.complete();
