// Nelderim Lab - front end (no build step, no frameworks). Talks only to nelderim_app.py on 127.0.0.1.
import * as THREE from "three";
import { OrbitControls } from "/app/vendor/OrbitControls.js";

// ------------------------------------------------------------------ helpers
const $ = (s, r = document) => r.querySelector(s);
const el = (tag, attrs = {}, ...kids) => {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k === "class") e.className = v;
    else if (k === "text") e.textContent = v;
    else if (k === "html") e.innerHTML = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (k === "style") e.style.cssText = v;
    else e.setAttribute(k, v === true ? "" : v);
  }
  for (const k of kids.flat()) if (k !== null && k !== undefined && k !== false) e.append(k.nodeType ? k : document.createTextNode(k));
  return e;
};
const api = {
  async get(url) { const r = await fetch(url); const j = await r.json(); if (!r.ok) throw new Error(j.error || r.statusText); return j; },
  async post(url, data) {
    const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data || {}) });
    const j = await r.json(); if (!r.ok) throw new Error(j.error || r.statusText); return j;
  },
};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
function toast(msg, kind = "") {
  const t = el("div", { class: "toast " + kind, text: msg }); document.body.append(t);
  setTimeout(() => t.remove(), kind === "bad" ? 9000 : 4500);
}
function slug(s) { return (s || "").trim().replace(/[^A-Za-z0-9_-]+/g, "_").replace(/^_+|_+$/g, "") || "praca"; }
function store(k, v) { try { localStorage.setItem("nl." + k, JSON.stringify(v)); } catch (e) {} }
function restore(k, d) { try { const v = localStorage.getItem("nl." + k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } }

// tooltips: any element with data-tip
const tipEl = $("#tip");
document.addEventListener("mouseover", (e) => {
  const t = e.target.closest("[data-tip]"); if (!t) { tipEl.hidden = true; return; }
  tipEl.textContent = t.dataset.tip; tipEl.hidden = false;
  const r = t.getBoundingClientRect();
  tipEl.style.left = Math.min(window.innerWidth - 380, r.left) + "px";
  tipEl.style.top = (r.bottom + 6 + 200 > window.innerHeight ? r.top - tipEl.offsetHeight - 6 : r.bottom + 6) + "px";
});

// ------------------------------------------------------------------ state, status, jobs
let S = null;
const ACTIONS = () => S.actions;
async function refresh() { S = await api.get("/api/state"); document.documentElement.dataset.theme = restore("theme", "dark"); return S; }
const statusMsg = $("#statusMsg"), prog = $("#prog"), logEl = $("#log"), stopBtn = $("#stopBtn");
function setStatus(msg, cls = "") { statusMsg.textContent = msg; statusMsg.className = "msg " + cls; }
$("#logBtn").onclick = () => { logEl.classList.toggle("show"); $("#logBtn").textContent = logEl.classList.contains("show") ? "Szczegóły ▾" : "Szczegóły ▸"; };
function showLog(on = true) { logEl.classList.toggle("show", on); $("#logBtn").textContent = on ? "Szczegóły ▾" : "Szczegóły ▸"; }
function log(line) { logEl.append(line + "\n"); logEl.scrollTop = logEl.scrollHeight; }
let current = null;
stopBtn.onclick = () => current && api.post("/api/job/stop", { id: current });
async function runTask(task, params, title) {
  if (current) { toast("Poprzednie zadanie jeszcze trwa. Poczekaj chwilę.", "bad"); throw new Error("busy"); }
  let info;
  try { info = await api.post("/api/task", { task, params }); }
  catch (e) { toast(e.message, "bad"); setStatus("✗ " + e.message, "bad"); throw e; }
  current = info.id; prog.hidden = false; stopBtn.hidden = false; $("#hints").innerHTML = "";
  setStatus("⏳ " + (title || info.title) + "…"); log("── " + info.title + " ──");
  let from = 0, lines = [], j;
  while (true) {
    await sleep(350);
    j = await api.get(`/api/job?id=${info.id}&from=${from}`);
    for (const l of j.lines) { log(l); lines.push(l); }
    from = j.next;
    $("#hints").innerHTML = ""; for (const h of j.hints) $("#hints").append(el("div", { class: "h", text: "💡 " + h }));
    if (j.status !== "running") break;
  }
  current = null; prog.hidden = true; stopBtn.hidden = true;
  if (j.status === "ok") setStatus("✓ " + j.title + ": gotowe (" + j.elapsed + " s).", "ok");
  else { setStatus("✗ " + j.title + ": nie udało się – zobacz Szczegóły.", "bad"); showLog(true); }
  j.lines = lines; return j;
}

// ------------------------------------------------------------------ form builder
async function pickPath(kind, title, filter) { const r = await api.post("/api/pick", { kind, title, filter }); return r.path; }
function field(parent, f, val = "") {
  // f: {key, label, help, type: text|file|dir|save|select|check|num, options, filter, placeholder}
  const id = "f_" + f.key + "_" + Math.random().toString(36).slice(2, 6);
  let input;
  if (f.type === "select") { input = el("select", { id }); for (const o of f.options) input.append(el("option", { value: o[0] ?? o, text: o[1] ?? o })); input.value = val || (f.options[0][0] ?? f.options[0]); }
  else if (f.type === "check") { input = el("input", { type: "checkbox", id }); input.checked = val === "" ? !!f.def : !!val; }
  else input = el("input", { type: "text", id, value: val ?? "", placeholder: f.placeholder || "" });
  const ctl = el("div", { class: "ctl" }, input);
  if (["file", "dir", "save"].includes(f.type)) ctl.append(el("button", { class: "small", text: "Wybierz…", onclick: async () => { const p = await pickPath(f.type, f.label, f.filter || ""); if (p) { input.value = p; input.dispatchEvent(new Event("change")); } } }));
  if (f.help) { input.dataset.tip = f.help; }
  const row = el("div", { class: "row" }, el("label", { for: id, text: f.label, "data-tip": f.help || null }), ctl, f.help ? el("span", { class: "q", "data-tip": f.help, text: "?" }) : el("span"));
  if (f.type === "check") { row.children[1].replaceChildren(el("label", { class: "check" }, input, f.text || "")); }
  parent.append(row);
  input.dataset.key = f.key;
  return { get: () => (f.type === "check" ? input.checked : input.value.trim()), set: (v) => (f.type === "check" ? (input.checked = !!v) : (input.value = v)), input, row };
}
function form(parent, fields, values = {}) {
  const F = {}; for (const f of fields) F[f.key] = field(parent, f, values[f.key] ?? f.def ?? "");
  F.values = () => Object.fromEntries(Object.entries(F).filter(([k]) => k !== "values").map(([k, v]) => [k, v.get()]));
  return F;
}
function step(parent, n, title, text) {
  const s = el("div", { class: "step" }, el("div", { class: "h" }, el("span", { class: "n", text: n }), el("span", { class: "t", text: title })), el("div", { class: "hint", text: text }));
  const body = el("div"); const res = el("div", { class: "res" }); s.append(body, res); parent.append(s);
  return { body, ok: (m) => { res.className = "res ok"; res.textContent = "✓ " + m; }, bad: (m) => { res.className = "res bad"; res.textContent = "✗ " + m; },
    info: (m) => { res.className = "res muted"; res.textContent = m; }, el: s };
}
function btns(parent, ...list) { const b = el("div", { class: "btns" }, ...list.map(([t, fn, cls, tip]) => el("button", { class: cls || "", text: t, onclick: fn, "data-tip": tip }))); parent.append(b); return b; }
function adv(parent, title = "Ustawienia zaawansowane (nie musisz ich ruszać)") { const d = el("details", { class: "adv" }, el("summary", { text: title })); parent.append(d); return d; }
function page(id, title, sub) { const p = $("#p-" + id); p.innerHTML = ""; p.append(el("h1", { text: title }), el("div", { class: "hint", text: sub })); return p; }

// lookup: ItemID -> animation; parses the output of the lookup task
async function lookup(stepObj, graphic, onAnim) {
  if (!graphic) { toast("Wpisz numer przedmiotu, np. 0x2683.", "bad"); return; }
  stepObj.info("Sprawdzam…");
  try {
    const j = await runTask("lookup", { graphic }, "Sprawdzanie przedmiotu");
    const t = j.lines.join("\n");
    const m = t.match(/item (0x[0-9a-fA-F]+) '(.*?)' animId (\d+) layer (\d+)/); const tg = t.match(/animation used for body 400: (\d+)/); const b = t.match(/Bodyconv: (.*)/);
    if (!m || !tg) return stepObj.bad("Nie znalazłem tego przedmiotu. Sprawdź numer.");
    const anim = +tg[1];
    if (anim < 400) return stepObj.bad(`To „${m[2]}”, animacja ${anim}: to nie jest animacja ubrania, nie nadaje się.`);
    const inmul = b && b[1].startsWith("none");
    stepObj.ok(`To „${m[2]}”. Animacja ${anim}. ` + (inmul ? "Da się przerobić." : "Oryginalny plik .vd tej animacji wyciągnij UOFiddlerem (leży w anim2..5.mul)."));
    onAnim && onAnim(anim);
  } catch (e) { stepObj.bad(e.message); }
}

// ------------------------------------------------------------------ navigation
const PAGES = [
  ["start", "🏠", "Start"], ["fit", "🧊", "Model 3D (Fit Lab)"], ["cloth", "👕", "Ubranie 2D (obrazek)"], ["weapon", "⚔", "Broń 2D (obrazek)"],
  ["gump", "🖼", "Gump (lalka)"], ["pack", "📦", "Spakuj do .vd"], ["set", "🧩", "Zestaw z arkusza"], ["vd", "🎞", "Podgląd .vd"],
  ["client", "🛠", "Dodawanie do klienta"], ["settings", "⚙", "Ustawienia"], ["help", "❓", "Pomoc"],
];
const built = {};
function show(id) {
  document.querySelectorAll(".page").forEach((p) => p.classList.toggle("show", p.id === "p-" + id));
  document.querySelectorAll("#navlist button").forEach((b) => b.classList.toggle("sel", b.dataset.p === id));
  document.body.classList.toggle("fitmode", id === "fit");
  $("#ctx").innerHTML = "";
  if (BUILD[id] && (!built[id] || id === "start" || id === "settings")) { BUILD[id](); built[id] = true; }
  if (id === "fit") { FIT.onShow(); }
  store("page", id);
}
function buildNav() {
  const n = $("#navlist"); n.innerHTML = "";
  for (const [id, ic, t] of PAGES) n.append(el("button", { "data-p": id, onclick: () => show(id) }, el("span", { class: "ic", text: ic }), t));
}
$("#themeBtn").onclick = () => { const t = document.documentElement.dataset.theme === "dark" ? "light" : "dark"; document.documentElement.dataset.theme = t; store("theme", t); };
$("#quitBtn").onclick = async () => { if (confirm("Zamknąć Nelderim Lab? (wyłącza program działający w tle)")) { try { await api.post("/api/quit"); } catch (e) {} document.body.innerHTML = "<div style='padding:40px'>Program zamknięty. Możesz zamknąć tę kartę.</div>"; } };

// ------------------------------------------------------------------ pages
const BUILD = {};

BUILD.start = async () => {
  await refresh();
  const box = $("#startChecks"); box.innerHTML = "";
  for (const p of S.paths.filter((p) => p.req || p.key === "bodyglb")) {
    box.append(el("div", { class: "check" }, el("span", { class: "dot " + (p.ok ? "ok" : p.req ? "bad" : "off") }), p.label + (p.req ? "" : " (do metody 3D)"),
      p.ok ? "" : el("button", { class: "small", text: "Ustaw", onclick: () => show("settings") })));
  }
  const ex = S.extras || {};
  if (S.paths.find((p) => p.key === "bodyglb").ok)
    box.append(el("div", { class: "check muted" }, "Dane obok modelu 3D: ciało z oryginału " + (ex.body_vd ? "✓" : "✗") + ", koń " + (ex.horse_vd ? "✓" : "✗") + ", broń " + (ex.motion ? "✓" : "✗") + ", tarcza " + (ex.shield ? "✓" : "✗")));
  const dl = el("div", { class: "check muted", text: "… sprawdzam biblioteki Pythona" }); box.append(dl);
  api.post("/api/deps").then((d) => {
    dl.replaceChildren(el("span", { class: "dot " + (d.self ? "ok" : "bad") }), "Biblioteki programu (numpy, Pillow) ", d.self ? "" : el("button", { class: "small", text: "Zainstaluj", onclick: () => runTask("deps_self", {}).then(() => show("start")) }));
    if (d.toolkit !== null) box.append(el("div", { class: "check" }, el("span", { class: "dot " + (d.toolkit ? "ok" : "bad") }), "Biblioteki toolkitu ", d.toolkit ? "" : el("button", { class: "small", text: "Zainstaluj", onclick: () => runTask("deps_toolkit", {}).then(() => show("start")) })));
  });
  if (S.paths.find((p) => p.key === "toolkit").ok && !S.toolkit.axisfit) box.append(el("div", { class: "check warn", text: "⚠ Toolkit ma starą wersję skryptów Levy'ego (bez broni i gumpów). Skopiuj paczkę v2." }));
  const tiles = $("#startTiles"); tiles.innerHTML = "";
  const T = [["fit", "🧊 Przerobić model 3D na animację", "Masz model 3D (.glb, .fbx, .obj): ubranie, zbroja, hełm, włosy, szata, peleryna, broń, tarcza. Dopasujesz go suwakami i wyrenderujesz do .vd."],
    ["cloth", "👕 Zmienić wygląd ubrania obrazkiem", "Masz obrazek PNG szaty, koszuli, spodni… Program przeniesie go na oryginalną animację (metoda Levy'ego)."],
    ["weapon", "⚔ Zmienić wygląd broni obrazkiem", "Poziomy PNG miecza lub laski, dopasowany do osi oryginalnej broni."],
    ["gump", "🖼 Obrazek broni na lalce (gump)", "Ten w oknie Paperdoll. Męski i damski."],
    ["vd", "🎞 Obejrzeć plik .vd", "Podgląd dowolnej animacji .vd razem z ciałem."],
    ["client", "🛠 Dodać przedmiot do klienta", "Receptura, wolne ID, przebieg na sucho, zapis do kopii klienta."],
    ["settings", "⚙ Ustawić foldery", "Gdzie leży klient gry, toolkit, model 3D ciała."]];
  for (const [id, t, d] of T) tiles.append(el("div", { class: "tile", onclick: () => show(id) }, el("div", { class: "t", text: t }), el("div", { class: "muted", text: d })));
};

BUILD.settings = async () => {
  await refresh();
  const p = page("settings", "Ustawienia – gdzie co leży", "Program zapamięta to na tym komputerze (" + S.config_file + "). Zielona kropka = poprawnie.");
  const card = el("div", { class: "card" }); p.append(card);
  const F = {};
  for (const x of S.paths) {
    const f = field(card, { key: x.key, label: x.label + (x.req ? "" : " (opcjonalnie)"), help: x.help, type: x.kind === "file" ? "file" : "dir", filter: x.key === "bodyglb" ? ".glb" : x.key === "vdviewer" ? ".html" : "" }, x.value);
    f.row.prepend(el("span", { class: "dot " + (x.ok ? "ok" : x.req ? "bad" : "off"), style: "position:absolute;margin-left:-14px;margin-top:2px" }));
    f.row.style.position = "relative"; F[x.key] = f;
  }
  btns(p, ["💾 Zapisz", async () => { const v = {}; for (const k in F) v[k] = F[k].get(); await api.post("/api/config", v); toast("Zapisano.", "ok"); built.settings = false; show("settings"); }, "primary"],
    ["🔍 Wykryj automatycznie", async () => { const r = await api.post("/api/autodetect"); toast("Wykryto: " + (Object.keys(r.found).length || "nic nowego")); show("settings"); }]);
};

BUILD.help = () => {
  const p = page("help", "Pomoc", "Słowniczek i typowa kolejność pracy.");
  p.append(el("div", { class: "card", html: `
<h2 class="sec">Słowniczek</h2>
<p><b>ItemID</b> – numer przedmiotu (np. 0x2683), z UOFiddlera: Items → ID.<br>
<b>Animacja</b> – jak przedmiot wygląda na ruszającej się postaci; każdy ma numer animacji.<br>
<b>.vd</b> – plik animacji do UOFiddlera (Animation Edit → Import from VD).<br>
<b>Gump</b> – obrazek przedmiotu na lalce postaci (Paperdoll).<br>
<b>Kamera UO</b> – rzut z góry pod kątem 28,45°, tak jak w grze. Kierunki 0–4 są w pliku, 5–7 to lustra.<br>
<b>Poke px</b> – piksele, w których ciało przebija przez przedmiot (dziury). Im mniej, tym lepiej.<br>
<b>Na sucho (dry run)</b> – pokazuje, co by się zmieniło, niczego nie zapisuje.</p>
<h2 class="sec">Kolejność pracy</h2>
<ol><li>Ustawienia: foldery (raz).</li><li>Wybierz metodę: <b>Model 3D</b> (masz model 3D) albo <b>Ubranie/Broń 2D</b> (masz obrazek).</li>
<li>Najpierw kilka akcji na próbę, obejrzyj, popraw, potem wszystkie 35.</li><li>Wynik .vd: obejrzyj w „Podgląd .vd”, zaimportuj w UOFiddlerze na <b>kopii</b> klienta.</li>
<li>Nowy przedmiot w kliencie: „Dodawanie do klienta” (receptura → na sucho → zastosuj).</li></ol>
<h2 class="sec">Model 3D – sterowanie</h2>
<p>Lewy przycisk myszy: obrót widoku, prawy: przesuwanie, kółko: przybliżenie. Suwaki „Slot fit” po prawej przesuwają/obracają/skalują przedmiot względem automatycznego dopasowania. Ctrl+Z / Ctrl+Y: cofnij / ponów.</p>` }));
};

// ---- 2D cloth (Levy's texture transfer)
BUILD.cloth = () => {
  const p = page("cloth", "👕 Ubranie / szata z obrazka (2D)", "Zmieniasz materiał, kolor i wzór istniejącego ubrania. Kształt i fałdy zostają z oryginalnej animacji.");
  const s1 = step(p, 1, "Które ubranie zmieniasz?", "Numer przedmiotu (ItemID) z UOFiddlera, np. 0x2683.");
  const f1 = form(s1.body, [{ key: "graphic", label: "Numer przedmiotu (ItemID)", help: "np. 0x2683. Z UOFiddlera (Items → ID)." }]);
  btns(s1.body, ["Sprawdź przedmiot", () => lookup(s1, f1.graphic.get())]);
  const s2 = step(p, 2, "Twój obrazek", "PNG z PRZEZROCZYSTYM tłem, ubranie z przodu, równe światło.");
  const f2 = form(s2.body, [{ key: "image", label: "Obrazek (PNG)", type: "file", filter: ".png,.webp", help: "Plik PNG z wyciętym tłem." }]);
  btns(s2.body, ["Sprawdź obrazek", () => checkImage(s2, f2.image.get())]);
  const s3 = step(p, 3, "Nazwa pracy", "Na jej podstawie powstanie folder na wyniki.");
  const f3 = form(s3.body, [{ key: "name", label: "Nazwa pracy", help: "Np. nekro-szata." }]);
  const a = adv(s3.body);
  const f3b = form(a, [{ key: "hide", label: "Odsłoń części ciała", def: "1 5", help: "1 = twarz, 5 = dłonie. Puste = nic nie odsłaniaj." },
    { key: "actions", label: "Akcje (próba)", def: "0 4 9 13 16", help: "0 chód, 4 stanie, 9 cięcie, 13 cięcie 2h, 16 czar. Puste = wszystkie 35." },
    { key: "title", label: "Tytuł podglądu", help: "Napis na stronie podglądu." }]);
  const s4 = step(p, 4, "Zbuduj i obejrzyj", "Na próbę kilka akcji, potem wszystkie.");
  let lab = null;
  const build = async (acts) => {
    const v = { ...f1.values(), ...f2.values(), ...f3.values(), ...f3b.values() };
    if (!v.graphic || !v.image || !v.name) return toast("Uzupełnij kroki 1–3.", "bad");
    try { const j = await runTask("build_item", { ...v, actions: acts }); if (j.status === "ok") { lab = j.result.lab; s4.ok("Zbudowane: " + lab); } else s4.bad("Nie udało się (podpowiedź na dole)."); } catch (e) {}
  };
  btns(s4.body, ["▶ Zbuduj (próba)", () => build(f3b.actions.get()), "primary"], ["Zbuduj wszystkie 35", () => build("")], ["🌐 Podgląd", () => openLab(lab)]);
  const s5 = step(p, 5, "Zapisz do .vd", "Pakuje wynik do pliku dla UOFiddlera (z kopią poprzedniej wersji).");
  btns(s5.body, ["📦 Spakuj do .vd", async () => { if (!lab) return toast("Najpierw zbuduj.", "bad"); const j = await runTask("pack", { lab, outline: "" }); packResult(s5, j); }, "primary"]);
};
async function checkImage(stepObj, image) {
  if (!image) return toast("Wskaż plik PNG.", "bad");
  try {
    const j = await runTask("image_check", { image }, "Sprawdzanie obrazka"); const t = j.lines.join("\n");
    const sz = t.match(/SIZE (\d+) (\d+)/), al = t.match(/ALPHA (\d+) (\d+)/), bb = t.match(/BBOX \((\d+), (\d+), (\d+), (\d+)\)/);
    if (!sz || !al) return stepObj.bad("Nie mogę odczytać obrazka.");
    if (!bb) return stepObj.bad("Obrazek jest pusty (całkiem przezroczysty).");
    const w = bb[3] - bb[1], h = bb[4] - bb[2];
    if (+al[1] === 255) return stepObj.bad(`Obrazek NIE ma przezroczystego tła – wytnij tło, inaczej wyjdzie kwadrat. (${w}×${h} px)`);
    stepObj.ok(`Rysunek ${w}×${h} px, tło przezroczyste.`);
  } catch (e) {}
}
async function openLab(lab) {
  if (!lab) return toast("Najpierw zbuduj.", "bad");
  try { const r = await api.post("/api/lab/open", { path: lab }); window.open(r.url, "_blank"); } catch (e) { toast(e.message, "bad"); }
}
function packResult(stepObj, j) {
  if (j.status === "ok") { stepObj.ok(`Gotowe: ${j.result.vd}\nImport: UOFiddler → Animations → Animation Edit → ID ${j.result.anim} → Import from VD → Save (na KOPII klienta).`); VD.open(j.result.vd); }
  else if (j.result.need_fiddler) stepObj.bad(`Oryginał tej animacji leży w anim2..5.mul. Wyciągnij go UOFiddlerem (Export to VD) i zapisz jako:\n${j.result.need_fiddler}\nPotem kliknij ponownie.`);
  else stepObj.bad("Nie udało się (podpowiedź na dole).");
}

// ---- 2D weapon (axis fit)
BUILD.weapon = () => {
  const p = page("weapon", "⚔ Broń z obrazka (2D)", "Wąska broń w dłoni: miecz, laska, włócznia. Obrazek dopasowany do osi oryginalnej broni (metoda Levy'ego).");
  const s1 = step(p, 1, "Jaka broń?", "Rodzaj i ItemID broni, którą zastępujesz (np. 0xF5E szabla, 0xDF0 BlackStaff).");
  const f1 = form(s1.body, [{ key: "type", label: "Rodzaj", type: "select", options: [["sword", "Miecz / szabla"], ["staff", "Laska / kij / włócznia"]], help: "Miecz: chwyt przy rękojeści. Laska: chwyt pośrodku." },
    { key: "graphic", label: "Numer przedmiotu (ItemID)", help: "np. 0xF5E" }]);
  btns(s1.body, ["Sprawdź przedmiot", () => lookup(s1, f1.graphic.get())]);
  const s2 = step(p, 2, "Obrazek broni", "PNG, broń POZIOMO: rękojeść po LEWEJ, czubek po PRAWEJ.");
  const f2 = form(s2.body, [{ key: "image", label: "Obrazek (PNG)", type: "file", filter: ".png,.webp", help: "Poziomy obrazek z przezroczystym tłem." }]);
  btns(s2.body, ["Sprawdź obrazek", () => checkImage(s2, f2.image.get())]);
  const s3 = step(p, 3, "Nazwa i grubość", "Grubość popraw po obejrzeniu podglądu.");
  const f3 = form(s3.body, [{ key: "name", label: "Nazwa pracy", help: "Np. moja-szabla." }]);
  const a = adv(s3.body);
  const f3b = form(a, [{ key: "thick", label: "Grubość (px)", help: "Stała grubość na ekranie; oryginalna laska ≈ 3 px. Puste = domyślnie." },
    { key: "hide", label: "Odsłoń części ciała", def: "5", help: "5 = dłonie (broń w dłoni, nie na niej)." },
    { key: "actions", label: "Akcje (próba)", def: "0 4 9 13", help: "Puste = WSZYSTKIE 35 akcji (dłużej)." },
    { key: "cont", label: "Ten sam koniec", type: "check", def: true, text: "trzymaj ten sam koniec przez animację", help: "Zapobiega skakaniu kuli/rękojeści." },
    { key: "torso", label: "Koniec roboczy", type: "check", def: true, text: "dalej od tułowia", help: "Który koniec to czubek." }]);
  const s4 = step(p, 4, "Zbuduj i obejrzyj", "Sprawdź akcje ataku i śmierci (7, 10, 14, 18, 22).");
  let lab = null;
  const build = async (acts) => {
    const v = { ...f1.values(), ...f2.values(), ...f3.values(), ...f3b.values() };
    if (!v.graphic || !v.image || !v.name) return toast("Uzupełnij kroki 1–3.", "bad");
    try { const j = await runTask("weapon2d", { ...v, actions: acts }); if (j.status === "ok") { lab = j.result.lab; s4.ok("Zbudowane: " + lab + "\nRaport w Szczegółach: szukaj \"errors\": []."); } else s4.bad("Nie udało się."); } catch (e) {}
  };
  btns(s4.body, ["▶ Zbuduj (próba)", () => build(f3b.actions.get()), "primary"], ["Zbuduj wszystkie 35", () => build("")], ["🌐 Podgląd", () => openLab(lab)]);
  const s5 = step(p, 5, "Zapisz do .vd", "Przycina broń do ciała.");
  const f5 = form(s5.body, [{ key: "outline", label: "Ciemny kontur 1 px", type: "check", def: true, text: "dla cienkiej klingi", help: "Wyłącz, jeśli obrazek ma już ciemny kontur." }]);
  btns(s5.body, ["📦 Spakuj do .vd", async () => { if (!lab) return toast("Najpierw zbuduj.", "bad"); const j = await runTask("pack", { lab, outline: f5.outline.get() ? "1" : "" }); packResult(s5, j); }, "primary"]);
};

// ---- gump
BUILD.gump = () => {
  const p = page("gump", "🖼 Obrazek broni na lalce (gump)", "Męski numer = animacja + 50000, damski = męski + 10000. Broń dopasowana do osi oryginału.");
  const s1 = step(p, 1, "Która broń?", "ItemID → „Sprawdź” wpisze numer animacji.");
  const f1 = form(s1.body, [{ key: "graphic", label: "Numer przedmiotu", help: "np. 0xDF0" }, { key: "anim", label: "Numer animacji", help: "np. 617 laska, 618 szabla." }]);
  btns(s1.body, ["Sprawdź przedmiot", () => lookup(s1, f1.graphic.get(), (a) => f1.anim.set(a))]);
  const s2 = step(p, 2, "Obrazek broni", "PNG poziomo: rękojeść po lewej.");
  const f2 = form(s2.body, [{ key: "image", label: "Obrazek (PNG)", type: "file", filter: ".png", help: "Twoja broń jako PNG z przezroczystym tłem, POZIOMO: rękojeść z lewej, czubek / kula z prawej." }]);
  const s3 = step(p, 3, "Rodzaj i nazwa", "Gotowe ustawienia Levy'ego dla laski i szabli.");
  const f3 = form(s3.body, [{ key: "preset", label: "Rodzaj broni", type: "select", options: [["sabre", "Szabla / miecz"], ["staff", "Laska / kij"], ["own", "Własne ustawienia"]], help: "Gotowe ustawienia grubości i przesunięcia, sprawdzone na szabli (618) i lasce (617). „Własne” = wpisujesz sam w ustawieniach zaawansowanych." },
    { key: "name", label: "Nazwa pracy", help: "Nazwa folderu na wyniki (gumpy i porównanie). Bez polskich znaków i spacji najbezpieczniej." }]);
  const a = adv(s3.body);
  const f3b = form(a, [{ key: "thick", label: "Grubość px", help: "Laska ≈ 26." }, { key: "ratio", label: "Proporcja", def: "0.15", help: "Szabla 0.15." },
    { key: "shift", label: "Przesunięcie dx,dy", def: "0,0", help: "Szabla 3,-9." }, { key: "front", label: "Dłoń przed bronią od wiersza", help: "Szabla 106." },
    { key: "gid", label: "Własny numer gumpu", help: "Puste = animacja + 50000." }, { key: "outline", label: "Kontur", type: "check", text: "ciemny kontur 1 px" }]);
  const s4 = step(p, 4, "Zrób gump", "Powstaną PNG męski i damski oraz porównanie.");
  const img = el("img", { style: "max-width:100%;image-rendering:pixelated;margin-top:8px;display:none" }); s4.body.append(img);
  btns(s4.body, ["▶ Zrób gump", async () => {
    const v = { ...f1.values(), ...f2.values(), ...f3.values(), ...f3b.values() };
    if (!/^\d+$/.test(v.anim) || !v.image || !v.name) return toast("Uzupełnij numer animacji, obrazek i nazwę.", "bad");
    try { const j = await runTask("gump", v); if (j.status === "ok") { s4.ok("Pliki: " + j.result.dir + "\nDamskiego gumpu często nie ma w kliencie – w UOFiddlerze Insert, nie Replace."); img.src = "/api/file?path=" + encodeURIComponent(j.result.image) + "&t=" + Date.now(); img.style.display = "block"; } else s4.bad("Nie udało się."); } catch (e) {}
  }, "primary"]);
};

// ---- set from a sheet
BUILD.set = () => {
  const p = page("set", "🧩 Zestaw z arkusza (zaawansowane)", "Cały strój: arkusz PNG 4×3, osobny miecz, plik konfiguracji. Przykład: Wiedźmin z toolkitu.");
  const s = step(p, 1, "Pliki", "");
  const F = form(s.body, [{ key: "design", label: "Arkusz (PNG)", type: "file", filter: ".png", help: "4 kolumny × 3 rzędy." }, { key: "sword", label: "Miecz (PNG)", type: "file", filter: ".png", help: "Obraz dla klucza „sword” (poziomo, rękojeść z lewej). Gdy zestaw nie ma miecza, zostaw puste – program podstawi zastępczy plik." },
    { key: "config", label: "Konfiguracja (JSON)", type: "file", filter: ".json", help: "Plik JSON zestawu (title, items, cells…), np. witcher.json z przykładu Levy'ego. Zapisany jako UTF-8 bez BOM." }, { key: "out", label: "Folder wynikowy (lab)", type: "dir", help: "Gdzie zapisać przymiarkę (atlas + podgląd HTML). Puste = folder pracy w toolkicie." },
    { key: "actions", label: "Akcje", def: "0 4 9 13 16", help: "Puste = wszystkie." }]);
  btns(s.body, ["Wypełnij przykładem Wiedźmina", () => { const b = S.workroot + "/witcher-lab/"; F.design.set(b + "witcher_design.png"); F.sword.set(b + "witcher_sword.png"); F.config.set(b + "witcher.json"); F.out.set(b + "lab"); }],
    ["▶ Zbuduj", async () => { const v = F.values(); if (!v.design || !v.sword || !v.config || !v.out) return toast("Uzupełnij pliki.", "bad"); try { const j = await runTask("build_set", v); j.status === "ok" ? s.ok("Zbudowane.") : s.bad("Nie udało się."); } catch (e) {} }, "primary"],
    ["Sprawdź (verify)", () => runTask("verify", { lab: F.out.get() })], ["🌐 Podgląd", () => openLab(F.out.get())]);
};

// ---- pack any lab
BUILD.pack = () => {
  const p = page("pack", "📦 Spakuj do .vd", "Dla wcześniej zbudowanych prac 2D (kreatory robią to same na końcu).");
  const s = step(p, 1, "Praca i opcje", "Folder „lab” (z manifest.json).");
  const F = form(s.body, [{ key: "lab", label: "Folder pracy (lab)", type: "dir", help: "Folder „lab” zbudowanej przymiarki (ten z index.html i atlasami), np. workspace/ultima-online/<praca>/lab w toolkicie." }, { key: "key", label: "Przedmiot (klucz)", help: "Puste = pierwszy przedmiot w pracy." },
    { key: "outline", label: "Kontur", type: "check", text: "ciemny kontur 1 px (cienka broń)" }, { key: "body", label: "Własny plik ciała .vd", type: "file", filter: ".vd", help: "Puste = z klienta." },
    { key: "out", label: "Plik wynikowy .vd", type: "save", filter: ".vd", help: "Puste = folder roboczy toolkitu." }]);
  btns(s.body, ["📦 Spakuj", async () => { const v = F.values(); if (!v.lab) return toast("Wskaż folder pracy.", "bad"); try { const j = await runTask("pack", { ...v, outline: v.outline ? "1" : "" }); packResult(s, j); } catch (e) {} }, "primary"]);
};

// ---- vd viewer
const VD = { path: null, open(p) { this.path = p; store("vdpath", p); built.vd = false; show("vd"); } };
BUILD.vd = () => {
  const p = page("vd", "🎞 Podgląd pliku .vd", "Wszystkie 5 kierunków wybranej akcji, z oryginalnym ciałem pod spodem (jeśli jest body400.vd).");
  const card = el("div", { class: "card" }); p.append(card);
  const F = form(card, [{ key: "path", label: "Plik .vd", type: "file", filter: ".vd", help: "Pełna ścieżka do pliku .vd (eksport UOFiddlera albo wynik z tego programu), np. …\\workspace\\ultima-online\\vd\\nowy_0469.vd. Kliknij „Wybierz…” albo wklej ścieżkę i naciśnij Enter / Wczytaj." }], { path: VD.path || restore("vdpath", "") });
  const ctl = el("div", { class: "btns" }); card.append(ctl);
  const act = el("select"); const fr = el("input", { type: "range", min: 0, max: 0, value: 0, style: "width:200px" }); const fl = el("span", { class: "muted" });
  const body = el("input", { type: "checkbox", checked: true }); const play = el("button", { text: "Play" });
  ctl.append(el("span", { class: "muted", text: "Akcja" }), act, fr, fl, play, el("label", { class: "check" }, body, "ciało pod spodem"),
    el("button", { text: "Kopiuj do toolkitu", "data-tip": "Kopiuje .vd do folderu roboczego toolkitu (z kopią starego) i sprawdza go.", onclick: () => F.path.get() && runTask("copy_to_toolkit", { vd: F.path.get() }) }),
    el("button", { text: "Otwórz folder", onclick: () => F.path.get() && api.post("/api/open", { path: F.path.get(), folder: true }) }),
    el("button", { text: "🧊 Przymierz w 3D", "data-tip": "Odtwarza z klatek „stój” tego .vd model 3D (.glb) założony na ciało i otwiera go w zakładce Model 3D (Fit Lab).", onclick: () => { const v = F.path.get(); if (!v) return toast("Najpierw wskaż plik .vd.", "bad"); show("fit"); FIT.fromVd(v); } }));
  const grid = el("div", { id: "vdgrid" }); card.append(grid);
  let info = null, timer = null;
  const draw = () => {
    const a = +act.value, k = +fr.value; const n = info.frames[a] || 1; fl.textContent = `${k + 1}/${n}`;
    grid.innerHTML = "";
    for (let d = 0; d < 5; d++) grid.append(el("figure", {}, el("img", { src: `/api/vd/frame?path=${encodeURIComponent(F.path.get())}&a=${a}&d=${d}&k=${k}&body=${body.checked ? 1 : 0}&s=2` }), el("figcaption", { class: "muted", text: "kierunek " + d })));
  };
  const load = async () => {
    const path = F.path.get(); if (!path) return;
    try { info = await api.get("/api/vd/info?path=" + encodeURIComponent(path)); } catch (e) { return toast(e.message, "bad"); }
    act.innerHTML = ""; for (const [a, n] of Object.entries(info.frames)) act.append(el("option", { value: a, text: `${a} · ${(S.actions[a] || "")} (${n})` }));
    act.value = info.frames["4"] !== undefined ? "4" : act.options[0]?.value; fr.max = (info.frames[act.value] || 1) - 1; fr.value = 0; draw(); store("vdpath", path);
  };
  F.path.input.addEventListener("change", load); act.onchange = () => { fr.max = (info.frames[act.value] || 1) - 1; fr.value = 0; draw(); }; fr.oninput = draw; body.onchange = draw;
  play.onclick = () => { if (timer) { clearInterval(timer); timer = null; play.textContent = "Play"; } else { timer = setInterval(() => { fr.value = (+fr.value + 1) % (+fr.max + 1); draw(); }, 180); play.textContent = "Stop"; } };
  btns(card, ["Wczytaj", load, "primary"]);
  if (F.path.get()) load();
};

// ---- client: recipe editor + search + patch
BUILD.client = () => {
  const p = page("client", "🛠 Dodawanie do klienta", "Nowe grafiki, gumpy i animacje potworów z receptury (JSON). Zawsze najpierw „na sucho”. Zapis tylko do KOPII klienta.");
  const s1 = step(p, 1, "Szukaj / sprawdź kolizje", "Nazwa lub numer przedmiotu albo animacji.");
  const f1 = form(s1.body, [{ key: "query", label: "Nazwa lub numer", help: "np. staff albo 0xDF0" }]);
  btns(s1.body, ["Szukaj", () => f1.query.get() && runTask("search", { query: f1.query.get() }).then(() => showLog(true))],
    ["Wolne ID animacji (5)", () => runTask("free_anim", { count: 5 }).then(() => showLog(true))]);
  const s2 = step(p, 2, "Receptura", "Lista przedmiotów do dodania. Ścieżki plików mogą być względne do pliku receptury.");
  const fpath = field(s2.body, { key: "recipe", label: "Plik receptury (.json)", type: "save", filter: ".json", help: "Nowy albo istniejący plik." }, restore("recipe", ""));
  const tbl = el("table", { class: "t" }); s2.body.append(tbl);
  const ed = el("div", { class: "card" }); s2.body.append(ed);
  let items = [], sel = -1;
  const FIELDS = { wearable: [["name", "Nazwa"], ["item_id", "Item ID (0x..)"], ["anim", "Anim id"], ["layer", "Warstwa (layer)"], ["tile_name", "Nazwa w tiledata"], ["art", "Ikona (PNG)", "file"], ["gump_male", "Gump męski (PNG)", "file"], ["gump_female", "Gump damski (PNG)", "file"]],
    monster: [["name", "Nazwa"], ["vd", "Plik .vd", "file"], ["body", "Body (puste = automatycznie)"]] };
  const FIELD_HELP = { name: "Nazwa pozycji w recepturze (dla Ciebie i w raporcie).", item_id: "Numer grafiki przedmiotu, np. 0x2683 (z UOFiddlera → Items).",
    anim: "Numer animacji na postaci (animId). Puste = z tiledata albo pierwszy wolny – sprawdź „Wolne ID animacji”.", layer: "Warstwa w tiledata (np. 22 = szata, 20 = płaszcz). Puste = jak w tiledata.",
    tile_name: "Nazwa przedmiotu zapisywana w tiledata.mul.", art: "Ikona przedmiotu (PNG z przezroczystym tłem).", gump_male: "Gump paperdolla męski (PNG, np. gump_<id>_meski.png z zakładki Gump).",
    gump_female: "Gump paperdolla damski (PNG). Puste = brak.", vd: "Plik .vd z animacją potwora (eksport UOFiddlera).", body: "Numer body potwora. Puste = program wybierze wolny („Zaproponuj wolny slot”)." };
  const kindOf = (it) => (it.vd !== undefined ? "monster" : "wearable");
  const drawT = () => {
    tbl.innerHTML = ""; tbl.append(el("tr", {}, el("th", { text: "#" }), el("th", { text: "Nazwa" }), el("th", { text: "Rodzaj" }), el("th", { text: "ID / plik" })));
    items.forEach((it, i) => tbl.append(el("tr", { class: i === sel ? "sel" : "", onclick: () => { sel = i; drawT(); drawE(); } }, el("td", { text: i + 1 }), el("td", { text: it.name || "—" }), el("td", { text: kindOf(it) === "monster" ? "potwór (.vd)" : "przedmiot" }), el("td", { class: "mono", text: it.item_id || it.vd || "" }))));
  };
  const drawE = () => {
    ed.innerHTML = ""; if (sel < 0) { ed.append(el("div", { class: "muted", text: "Wybierz pozycję z listy albo dodaj nową." })); return; }
    const it = items[sel]; const k = kindOf(it);
    ed.append(el("h2", { class: "sec", text: k === "monster" ? "Potwór z pliku .vd" : "Przedmiot do noszenia" }));
    for (const [key, label, type] of FIELDS[k]) { const f = field(ed, { key, label, type: type || "text", help: FIELD_HELP[key] || label }, it[key] ?? ""); f.input.addEventListener("change", () => { const v = f.get(); if (v === "") delete it[key]; else it[key] = ["anim", "layer", "body"].includes(key) && /^\d+$/.test(v) ? +v : v; drawT(); }); }
    if (k === "monster") btns(ed, ["Zaproponuj wolny slot", async () => { if (!it.vd) return toast("Najpierw wskaż plik .vd.", "bad"); const j = await runTask("suggest_slot", { vd: it.vd }); if (j.result.body) { it.body = j.result.body; drawE(); drawT(); toast("Wolny body: " + j.result.body, "ok"); } else toast("Nie znalazłem propozycji – zobacz Szczegóły.", "bad"); }]);
  };
  btns(s2.body, ["Wczytaj", async () => { const pth = fpath.get(); if (!pth) return; const r = await api.get("/api/recipe?path=" + encodeURIComponent(pth)); items = r.items || []; sel = items.length ? 0 : -1; drawT(); drawE(); store("recipe", pth); }],
    ["+ Przedmiot", () => { items.push({ name: "Nowy przedmiot" }); sel = items.length - 1; drawT(); drawE(); }], ["+ Potwór (.vd)", () => { items.push({ name: "Nowy potwór", vd: "" }); sel = items.length - 1; drawT(); drawE(); }],
    ["Usuń", () => { if (sel >= 0) { items.splice(sel, 1); sel = Math.min(sel, items.length - 1); drawT(); drawE(); } }],
    ["💾 Zapisz recepturę", async () => { const pth = fpath.get(); if (!pth) return toast("Podaj plik receptury.", "bad"); await api.post("/api/recipe", { path: pth, items }); store("recipe", pth); toast("Zapisano.", "ok"); }, "primary"]);
  drawT(); drawE();
  const s3 = step(p, 3, "Na sucho, potem zastosuj", "„Na sucho” niczego nie zapisuje. Przeczytaj wynik i ostrzeżenia (WARN).");
  const f3 = form(s3.body, [{ key: "missing", label: "Brakujące pliki", type: "select", options: [["stop", "zatrzymaj i pokaż listę"], ["skip", "pomiń brakujące pola"]], help: "Co zrobić, gdy receptura wskazuje plik, którego nie ma." }]);
  const go = async (apply) => {
    const pth = fpath.get(); if (!pth) return toast("Podaj i zapisz recepturę.", "bad");
    await api.post("/api/recipe", { path: pth, items });
    if (apply && !confirm("To ZAPISZE zmiany w kliencie.\n\nTo jest KOPIA klienta i sprawdziłeś wynik „na sucho”?")) return;
    runTask("patch", { recipe: pth, apply, missing: f3.missing.get() }).then(() => showLog(true));
  };
  btns(s3.body, ["👁 Na sucho (bezpieczne)", () => go(false), "primary"], ["✍ Zastosuj…", () => go(true)]);

  // ---- 4: animations in anim2..5.mul that no body uses yet -> Bodyconv.def + mobtypes.txt
  const s4 = step(p, 4, "Nieprzypisane animacje (anim2–5.mul)", "Program przegląda wybrany plik animacji, porównuje z Bodyconv.def i pokazuje animacje, których żadne body jeszcze nie używa. Dla zaznaczonych dobiera wolne body i dopisuje wpisy do Bodyconv.def i mobtypes.txt (w folderze wyników, nie w kliencie).");
  const f4 = form(s4.body, [{ key: "file", label: "Plik animacji", type: "select", options: [["5", "anim5.mul"], ["4", "anim4.mul"], ["3", "anim3.mul"], ["2", "anim2.mul"]],
    help: "Który z plików anim2–5.mul (z folderu klienta) przejrzeć. Typ animacji (potwór / zwierzę / człowiek) wynika z numeru miejsca w pliku." }], { file: restore("animfile", "5") });
  const wrap = el("div"); s4.body.append(wrap);
  let rows = [], fileN = 5;
  const draw4 = () => {
    wrap.innerHTML = "";
    if (!rows.length) return;
    const t = el("table", { class: "t" });
    t.append(el("tr", {}, el("th", { text: "" }), el("th", { text: "Podgląd" }), el("th", { text: "Miejsce" }), el("th", { text: "Typ" }), el("th", { text: "Akcje" }), el("th", { text: "Body" }), el("th", { text: "Nazwa (opis w pliku)" })));
    for (const r of rows) {
      const c = el("input", { type: "checkbox", checked: r.on !== false && r.body !== null }); c.onchange = () => { r.on = c.checked; };
      const nm = el("input", { type: "text", value: r.name || "", placeholder: "np. Czerwony smok" }); nm.onchange = () => { r.name = nm.value.trim(); };
      t.append(el("tr", {}, el("td", {}, c),
        el("td", {}, el("img", { src: `/api/animslot/thumb?file=${fileN}&slot=${r.slot}`, style: "max-height:72px;image-rendering:pixelated;background:#0a0c10;border-radius:4px", alt: "" })),
        el("td", { class: "mono", text: r.slot }), el("td", { text: { MONSTER: "potwór", ANIMAL: "zwierzę", HUMAN: "człowiek" }[r.type] || r.type }),
        el("td", { text: `${r.actions}/${r.actions_total}` }),
        el("td", { class: "mono" + (r.body === null ? " bad" : ""), text: r.body === null ? "brak wolnego" : r.body }), el("td", {}, nm)));
    }
    wrap.append(t);
  };
  const scan = async () => {
    fileN = +f4.file.get(); store("animfile", String(fileN));
    try {
      const j = await runTask("anim_wire", { file: fileN }, `Szukanie w anim${fileN}.mul`);
      if (j.result.error) return s4.bad(j.result.error);
      rows = j.result.unassigned || []; draw4();
      s4.info(`anim${fileN}.mul: ${j.result.slots_with_data} animacji, ${j.result.assigned} już przypisanych, ${rows.length} do podpięcia.` + (rows.length ? " Odznacz te, których nie chcesz, nadaj nazwy i kliknij „Podepnij”." : ""));
    } catch (e) {}
  };
  const wire = async () => {
    const sel = rows.filter((r) => r.on !== false && r.body !== null);
    if (!sel.length) return toast("Najpierw „Szukaj” i zaznacz animacje.", "bad");
    if (!confirm(`Dopisać ${sel.length} wpis(ów) do Bodyconv.def i mobtypes.txt?\n\nPliki trafią do folderu wyników (anim_wire), z kopią obecnych. Do klienta (KOPII) kopiujesz je sam. Dopisywanie do Bodyconv.def nie było jeszcze sprawdzone w grze – najpierw sprawdź jedno body.`)) return;
    const names = Object.fromEntries(sel.filter((r) => r.name).map((r) => [r.slot, r.name]));
    try {
      const j = await runTask("anim_wire", { file: fileN, slots: sel.map((r) => r.slot), names, apply: true }, "Podpinanie animacji");
      if (j.result.applied) { s4.ok(`Zapisano w ${j.result.out}. Skopiuj Bodyconv.def i mobtypes.txt do KOPII klienta i sprawdź body w grze.`); showLog(true); }
      else s4.bad(j.result.error || "Nie zapisano – zobacz Szczegóły.");
    } catch (e) {}
  };
  const fchk = form(s4.body, [{ key: "body", label: "Sprawdź body", placeholder: "np. 32", help: "Pokazuje, co już używa danego numeru body: mobtypes.txt, body.def, Bodyconv.def, pliki UOP (klient 3D) i anim.mul. Jeśli w grze widać inny wygląd niż w UOFiddlerze, zwykle winne są pliki UOP – mają pierwszeństwo." }]);
  btns(s4.body, ["🩺 Sprawdź", () => { const b = fchk.body.get(); if (!/^\d+$/.test(b)) return toast("Wpisz numer body, np. 32.", "bad"); runTask("anim_check", { body: +b }).then(() => showLog(true)); }]);
  btns(s4.body, ["🔍 Szukaj", scan, "primary", "Przegląda plik i pokazuje nieprzypisane animacje z proponowanym body. Niczego nie zapisuje."],
    ["🔗 Podepnij zaznaczone…", wire, "", "Dopisuje Bodyconv.def i mobtypes.txt do folderu wyników (z kopią obecnych)."]);
};

// ------------------------------------------------------------------ FIT LAB (3D)
const FIT = {
  inited: false, params: null, hist: [], hpos: -1, loaded: false, a: 4, k: 0, d: 0, timer: null, reloadT: null, frames: null,
  def() {
    return { name: "", kind: "shirt", item: "", off: [0, 0, 0], rot: [0, 0, 0], scl: 100, fit: true, exact: true, horse: true, cloth: true, sat: 1, skip: "", roll: "", actions: "0 4 9 16" };
  },
  onShow() {
    if (!this.inited) this.init();
    this.drawCtx(); this.resize();
  },
  async drawCtx() {
    const c = $("#ctx"); c.innerHTML = "";
    c.append(el("h2", { class: "sec", text: "Prace 3D" }), el("button", { class: "small", text: "+ Nowa praca", onclick: () => { this.params = this.def(); this.hist = []; this.hpos = -1; this.panel(); } }));
    let works = [];
    try { works = await api.get("/api/m3d/works"); } catch (e) {}
    if (!works.length) c.append(el("div", { class: "muted", style: "margin-top:8px", text: "Brak zapisanych prac. Wczytaj model i kliknij „Zapisz ustawienia”." }));
    for (const w of works) c.append(el("div", { class: "item" + (this.params && this.params.name === w.name ? " sel" : ""), onclick: () => { this.params = { ...this.def(), ...w.data }; this.hist = []; this.hpos = -1; this.panel(); this.load(true); this.drawCtx(); } },
      el("input", { type: "checkbox", checked: this.params && this.params.name === w.name, style: "pointer-events:none" }), el("div", {}, el("div", { class: "t", text: w.name }), el("div", { class: "s", text: (w.kind || "") + " · " + (w.saved || "") }))));
  },
  init() {
    this.inited = true;
    this.params = { ...this.def(), ...restore("fitparams", {}) };
    // three.js
    const view = $("#view");
    this.renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
    this.renderer.setPixelRatio(window.devicePixelRatio || 1);
    view.prepend(this.renderer.domElement);
    this.scene = new THREE.Scene(); this.scene.background = new THREE.Color(0x0a0c10);
    this.persp = new THREE.PerspectiveCamera(32, 1, 0.01, 50); this.persp.position.set(0.0, 1.35, 3.6);
    this.ortho = new THREE.OrthographicCamera(-1, 1, 1, -1, -20, 20);
    this.cam = this.persp;
    this.controls = new OrbitControls(this.persp, this.renderer.domElement); this.controls.target.set(0, 0.95, 0); this.controls.update();
    this.scene.add(new THREE.HemisphereLight(0xdfe8ff, 0x20242a, 1.6));
    const dl = new THREE.DirectionalLight(0xffffff, 1.6); dl.position.set(1.5, 3, 4); this.scene.add(dl);
    const grid = new THREE.GridHelper(4, 16, 0x26303a, 0x1a2028); this.scene.add(grid);
    this.group = new THREE.Group(); this.scene.add(this.group);
    this.bodyMesh = null; this.itemMesh = null;
    new ResizeObserver(() => this.resize()).observe(view);
    const loop = () => { requestAnimationFrame(loop); this.renderer.render(this.scene, this.cam); };
    loop();
    // bottom bar
    const as = $("#actSel"); as.innerHTML = ""; S.actions.forEach((n, i) => as.append(el("option", { value: i, text: `${i} ${n}` }))); as.value = 4;
    as.onchange = () => { this.a = +as.value; this.k = 0; this.syncFrame(); this.pose(); this.previews(); };
    const db = $("#dirBtns"); db.innerHTML = "";
    for (let d = 0; d < 8; d++) db.append(el("button", { text: d, "data-tip": d <= 4 ? "Kierunek " + d + " (zapisany w .vd)" : "Kierunek " + d + " (lustro " + (8 - d) + ", rysuje klient)", onclick: () => { this.d = d; this.dirSync(); } }));
    $("#frameSl").oninput = (e) => { this.k = +e.target.value; this.syncFrame(); this.pose(); if ($("#animPrev").checked || true) this.previews(); };
    $("#playBtn").onclick = () => this.play();
    $("#uoCamBtn").onclick = () => { this.cam = this.cam === this.persp ? this.ortho : this.persp; $("#uoCamBtn").classList.toggle("on", this.cam === this.ortho); this.dirSync(); this.resize(); };
    $("#showBody").onchange = () => { if (this.bodyMesh) this.bodyMesh.visible = $("#showBody").checked; };
    $("#prevSize").onchange = () => this.previews();
    document.addEventListener("keydown", (e) => {
      if (!document.body.classList.contains("fitmode") || e.target.matches("input[type=text]")) return;
      if (e.ctrlKey && e.key.toLowerCase() === "z") { e.preventDefault(); this.undo(); }
      if (e.ctrlKey && e.key.toLowerCase() === "y") { e.preventDefault(); this.redo(); }
    });
    this.dirSync(); this.syncFrame(); this.panel();
    if (this.params.item) this.load(true);
  },
  resize() {
    const v = $("#view"); const w = v.clientWidth, h = v.clientHeight; if (!w || !h || !this.renderer) return;
    this.renderer.setSize(w, h, false); this.persp.aspect = w / h; this.persp.updateProjectionMatrix();
    const H = 1.25; this.ortho.left = -H * w / h; this.ortho.right = H * w / h; this.ortho.top = H; this.ortho.bottom = -H; this.ortho.updateProjectionMatrix();
  },
  dirSync() {
    document.querySelectorAll("#dirBtns button").forEach((b, i) => b.classList.toggle("on", i === this.d));
    // UO direction d: the character turns by -45 deg * d about the vertical axis (directions 5-7 are mirrors drawn by the client)
    this.group.rotation.y = THREE.MathUtils.degToRad(-45 * this.d);
    const e = THREE.MathUtils.degToRad(28.45), D = 6;
    this.ortho.position.set(0, 0.95 + Math.sin(e) * D, Math.cos(e) * D); this.ortho.lookAt(0, 0.95, 0);
    if (this.cam === this.persp) this.controls.enabled = true;
  },
  syncFrame() {
    const n = S.frames[this.a] || 1; this.k = Math.min(this.k, n - 1);
    $("#frameSl").max = n - 1; $("#frameSl").value = this.k; $("#frameLbl").textContent = `${this.k + 1}/${n}`;
    $("#prevInfo").textContent = `Akcja ${this.a} ${S.actions[this.a]} · klatka ${this.k + 1}/${n}`;
  },
  play() {
    if (this.timer) { clearInterval(this.timer); this.timer = null; $("#playBtn").textContent = "Play"; return; }
    $("#playBtn").textContent = "Stop";
    let busy = false;
    this.timer = setInterval(async () => { if (busy) return; busy = true; const n = S.frames[this.a] || 1; this.k = (this.k + 1) % n; this.syncFrame(); await this.pose(); if ($("#animPrev").checked) await this.previews(); busy = false; }, 140);
  },
  // ---- right panel
  panel() {
    const P = this.params; const side = $("#side"); side.innerHTML = "";
    const sec = (t) => side.append(el("h2", { class: "sec", text: t }));
    sec("Historia " + (this.hpos + 1) + " / " + this.hist.length);
    side.append(el("div", { class: "btns", style: "margin-top:0" }, el("button", { class: "small", text: "Cofnij", disabled: this.hpos <= 0, onclick: () => this.undo() }), el("button", { class: "small", text: "Ponów", disabled: this.hpos >= this.hist.length - 1, onclick: () => this.redo() })));
    side.append(el("div", { class: "hint", id: "saveInfo", text: P.saved ? "Zapisano: " + P.saved : "Niezapisane" }));
    sec("Przedmiot");
    const kv = (label, ctl, tip) => side.append(el("div", { class: "kv", "data-tip": tip || null }, el("span", { class: "muted", text: label }), ctl));
    const name = el("input", { type: "text", value: P.name, placeholder: "np. nekro-szata" }); name.onchange = () => { P.name = name.value.trim(); this.persist(false); };
    kv("Nazwa", name, "Nazwa pracy: folder na wyniki i zapis ustawień.");
    const kind = el("select"); for (const k of S.kinds3d) kind.append(el("option", { value: k.kind, text: k.label })); kind.value = P.kind;
    kind.onchange = () => { P.kind = kind.value; note.textContent = (S.kinds3d.find((x) => x.kind === P.kind) || {}).note || ""; this.change(); };
    kv("Rodzaj", kind, "Rodzaj decyduje o rozmiarze, miejscu na ciele i przypięciu do kości.");
    const note = el("div", { class: "hint", text: (S.kinds3d.find((x) => x.kind === P.kind) || {}).note || "" }); side.append(note);
    const file = el("input", { type: "text", value: P.item, placeholder: "model .glb / .fbx / .obj" });
    file.onchange = () => { P.item = file.value.trim(); this.change(); };
    side.append(el("div", { class: "kv" }, el("span", { class: "muted", text: "Plik" }), el("div", { style: "display:flex;gap:4px" }, file,
      el("button", { class: "small", text: "…", "data-tip": "Wybierz plik modelu", onclick: async () => { const p = await pickPath("file", "Model 3D", ".glb,.gltf,.fbx,.obj"); if (p) { file.value = p; P.item = p; if (!P.name) { P.name = slug(p.split(/[\\/]/).pop().replace(/\.[^.]+$/, "")); name.value = P.name; } this.change(); } } }))));
    side.append(el("div", { class: "btns" }, el("button", { class: "primary", text: "Wczytaj / odśwież", onclick: () => this.load(true) }),
      el("button", { text: "🎞 Z pliku .vd…", "data-tip": "Nie masz modelu 3D? Wskaż .vd oryginalnego przedmiotu (eksport UOFiddlera albo anim_XXXX.vd z mul2vd). Program odtworzy z klatek „stój” bryłę 3D z kolorami, już założoną na ciało, i wczyta ją tutaj. Kształt jest przybliżony (z sylwetek), dobry do przymiarki i poprawek.", onclick: async () => { const p = await pickPath("file", "Plik .vd przedmiotu", ".vd"); if (p) this.fromVd(p); } })));
    const info = el("div", { class: "hint", id: "loadInfo" }); side.append(info);
    sec("Slot fit");
    const slider = (label, get, set, min, max, stepv, unit, tip) => {
      const r = el("input", { type: "range", min, max, step: stepv, value: get() }); const v = el("span", { class: "v", text: get() + unit });
      r.oninput = () => { v.textContent = r.value + unit; set(+r.value); this.change(true); };
      r.ondblclick = () => { r.value = label.startsWith("Skala") ? 100 : 0; r.oninput(); };
      side.append(el("div", { class: "sl", "data-tip": (tip || "") + " Podwójne kliknięcie = zero." }, el("span", { class: "muted", text: label }), r, v));
    };
    ["X", "Y", "Z"].forEach((ax, i) => slider("Offset " + ax, () => P.off[i], (x) => (P.off[i] = x), -30, 30, 0.5, " cm", ["W lewo / w prawo postaci.", "W górę / w dół.", "Do przodu / do tyłu."][i]));
    ["X", "Y", "Z"].forEach((ax, i) => slider("Rotate " + ax, () => P.rot[i], (x) => (P.rot[i] = x), -180, 180, 1, "°", "Obrót wokół środka przedmiotu."));
    slider("Skala", () => P.scl, (x) => (P.scl = x), 25, 300, 1, " %", "Względem automatycznego rozmiaru.");
    if (S.held.includes(P.kind) && P.kind !== "shield") {
      const rl = el("input", { type: "text", value: P.roll, placeholder: "auto" }); rl.onchange = () => { P.roll = rl.value.trim(); this.change(); };
      kv("Roll broni", rl, "Obrót ostrza / głowicy wokół trzonu w stopniach. Puste = jak oryginalna broń klasy.");
    }
    const chk = (label, key, tip, disabled) => { const c = el("input", { type: "checkbox", checked: !!P[key], disabled }); c.onchange = () => { P[key] = c.checked; this.change(); }; side.append(el("label", { class: "check", "data-tip": tip }, c, label)); };
    chk("Wypchnij z ciała (dopasuj)", "fit", "Części przedmiotu bliżej skóry niż 1,5–3 cm są wypychane na zewnątrz (ubrania i zbroje).");
    sec("Opcje");
    const ex = S.extras || {};
    chk("Dokładne ciało z oryginału" + (ex.body_vd ? "" : " (brak body400.vd)"), "exact", "Ciało zasłania przedmiot dokładnie wzdłuż oryginalnych klatek.", !ex.body_vd);
    chk("Koń w akcjach 23–29" + (ex.horse_vd ? "" : " (brak horse200.vd)"), "horse", "Koń z oryginalnych klatek zasłania część przedmiotu.", !ex.horse_vd);
    chk("Symulacja tkaniny", "cloth", "Szata / spódnica / peleryna faluje i zderza się z ciałem (wolniej).");
    const sat = el("input", { type: "range", min: 0, max: 1, step: 0.05, value: P.sat }); sat.oninput = () => { P.sat = +sat.value; this.change(true); };
    kv("Nasycenie", sat, "1 = kolory modelu, 0 = szarości (przedmiot farbowany w grze).");
    const sk = el("input", { type: "text", value: P.skip, placeholder: "np. eyes,body" }); sk.onchange = () => { P.skip = sk.value; this.change(); };
    kv("Pomiń", sk, "Elementy pliku do pominięcia (fragmenty nazw, po przecinku).");
    sec("Mierz (poke px)");
    side.append(el("div", { class: "hint", text: "Piksele, w których ciało przebija przez przedmiot, w zaznaczonych akcjach × 5 kierunków." }));
    const acts = el("div", { class: "acts" }); const sel = new Set(restore("measure", [0, 2, 4, 9, 16]));
    for (let i = 0; i < 35; i++) { const c = el("input", { type: "checkbox", checked: sel.has(i) }); c.onchange = () => { c.checked ? sel.add(i) : sel.delete(i); store("measure", [...sel]); }; acts.append(el("label", {}, c, i)); }
    side.append(acts);
    const mres = el("div", { class: "hint" });
    side.append(el("div", { class: "btns" }, el("button", { class: "small", text: "Zmierz", onclick: async () => { if (!this.loaded) return toast("Najpierw wczytaj model.", "bad"); mres.textContent = "Liczę…"; try { const r = await api.post("/api/m3d/measure", { actions: [...sel] }); mres.innerHTML = ""; mres.append("Razem: " + r.total + " px. "); for (const [a, n] of Object.entries(r.per_action)) mres.append(el("span", { class: n ? "warn" : "ok", text: ` ${a}: ${n}` })); } catch (e) { mres.textContent = e.message; } } })), mres);
    sec("Zbuduj .vd");
    const ac = el("input", { type: "text", value: P.actions }); ac.onchange = () => { P.actions = ac.value; this.persist(false); };
    kv("Akcje", ac, "Na próbę kilka akcji. „Wszystkie” = 35 (konne tylko z koniem).");
    const bres = el("div", { class: "hint" });
    side.append(el("div", { class: "btns" },
      el("button", { class: "primary", text: "▶ Próba", onclick: () => this.build(P.actions) }),
      el("button", { text: "Wszystkie", onclick: () => this.build([...Array(35).keys()].filter((i) => (P.horse && ex.horse_vd) || i < 23 || i > 29).join(" ")) })), bres);
    this.bres = bres;
    side.append(el("div", { class: "btns" }, el("button", { text: "💾 Zapisz ustawienia", onclick: () => this.save() }), el("button", { text: "Reset slotu", onclick: () => { P.off = [0, 0, 0]; P.rot = [0, 0, 0]; P.scl = 100; this.change(); this.panel(); } })));
  },
  persist(hist = true) { store("fitparams", this.params); if (hist) { this.hist = this.hist.slice(0, this.hpos + 1); this.hist.push(JSON.stringify(this.params)); if (this.hist.length > 60) this.hist.shift(); this.hpos = this.hist.length - 1; } },
  change(slider) {
    this.persist(true);
    const h = $("#side h2.sec"); if (h) h.textContent = "Historia " + (this.hpos + 1) + " / " + this.hist.length;
    const si = $("#saveInfo"); if (si) si.textContent = "Niezapisane zmiany";
    clearTimeout(this.reloadT); this.reloadT = setTimeout(() => this.load(false), slider ? 450 : 50);
  },
  undo() { if (this.hpos > 0) { this.hpos--; this.params = JSON.parse(this.hist[this.hpos]); store("fitparams", this.params); this.panel(); this.load(false); } },
  redo() { if (this.hpos < this.hist.length - 1) { this.hpos++; this.params = JSON.parse(this.hist[this.hpos]); store("fitparams", this.params); this.panel(); this.load(false); } },
  async load(first) {
    const P = this.params; if (!P.item) return;
    if (this.loading) { this.again = true; return; }
    this.loading = true; let info = $("#loadInfo"); if (info) info.textContent = "Wczytuję i dopasowuję…";
    try {
      const r = await api.post("/api/m3d/load", P);
      info = $("#loadInfo");
      if (info) info.innerHTML = `Skala ${r.scale}, ${r.verts} wierzch., ${r.tris} trójk. ` + (r.exact ? "· dokładne ciało " : "") + (r.horse ? "· koń" : "");
      if (first || !this.bodyMesh) this.hist.length || this.persist(true);
      await this.static(); this.loaded = true; $("#viewEmpty").style.display = "none";
      await this.pose(); await this.previews();
      $("#viewInfo").textContent = (S.kinds3d.find((x) => x.kind === P.kind) || {}).label + " · " + P.item.split(/[\\/]/).pop();
    } catch (e) { info = $("#loadInfo"); if (info) info.innerHTML = ""; if (info) info.append(el("span", { class: "bad", text: e.message })); toast(e.message, "bad"); }
    this.loading = false;
    if (this.again) { this.again = false; this.load(false); }
  },
  async static() {
    const r = await api.get("/api/m3d/static");
    const u32 = (b64) => new Uint32Array(Uint8Array.from(atob(b64), (c) => c.charCodeAt(0)).buffer);
    const f32 = (b64) => new Float32Array(Uint8Array.from(atob(b64), (c) => c.charCodeAt(0)).buffer);
    if (!this.bodyMesh) {
      const g = new THREE.BufferGeometry(); g.setIndex(new THREE.BufferAttribute(u32(r.body_tri), 1));
      g.setAttribute("position", new THREE.BufferAttribute(new Float32Array(r.body_n * 3), 3));
      this.bodyMesh = new THREE.Mesh(g, new THREE.MeshStandardMaterial({ color: 0x8f7a68, roughness: 0.9, metalness: 0 }));
      this.bodyMesh.frustumCulled = false; this.group.add(this.bodyMesh);
    }
    if (this.itemMesh) { this.group.remove(this.itemMesh); this.itemMesh.geometry.dispose(); }
    const g = new THREE.BufferGeometry(); g.setIndex(new THREE.BufferAttribute(u32(r.item_tri), 1));
    g.setAttribute("position", new THREE.BufferAttribute(new Float32Array(r.item_n * 3), 3));
    g.setAttribute("color", new THREE.BufferAttribute(f32(r.item_col), 3));
    this.itemMesh = new THREE.Mesh(g, new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.7, metalness: 0.05, side: THREE.DoubleSide }));
    this.itemMesh.frustumCulled = false; this.group.add(this.itemMesh);
    this.nb = r.body_n; this.ni = r.item_n;
  },
  async pose() {
    if (!this.itemMesh) return;
    const buf = await (await fetch(`/api/m3d/pose?a=${this.a}&k=${this.k}`)).arrayBuffer();
    const f = new Float32Array(buf);
    const bp = this.bodyMesh.geometry.attributes.position; bp.array.set(f.subarray(0, this.nb * 3)); bp.needsUpdate = true; this.bodyMesh.geometry.computeVertexNormals();
    const ip = this.itemMesh.geometry.attributes.position; ip.array.set(f.subarray(this.nb * 3)); ip.needsUpdate = true; this.itemMesh.geometry.computeVertexNormals();
  },
  async previews() {
    if (!this.itemMesh) return;
    const grid = $("#prevgrid"); const s = $("#prevSize").value;
    if (!grid.children.length) for (let d = 0; d < 5; d++) grid.append(el("figure", {}, el("img", { alt: "kierunek " + d }), el("figcaption", { text: "kierunek " + d })));
    await Promise.all([0, 1, 2, 3, 4].map(async (d) => {
      const fig = grid.children[d];
      let r;
      try { r = await fetch(`/api/m3d/preview?a=${this.a}&k=${this.k}&d=${d}&s=${s}`); } catch (e) { return; }
      if (!r.ok) { let m = r.statusText; try { m = (await r.json()).error || m; } catch (e) {} fig.querySelector("figcaption").innerHTML = ""; fig.querySelector("figcaption").append(el("span", { class: "bad", text: `kierunek ${d}: ${m}` })); return; }
      const poke = r.headers.get("X-Poke"); const url = URL.createObjectURL(await r.blob()); const img = fig.querySelector("img"); const old = img.src; img.src = url; if (old.startsWith("blob:")) URL.revokeObjectURL(old);
      fig.querySelector("figcaption").innerHTML = `kierunek ${d} · <span class="${+poke ? "warn" : "ok"}">${poke} poke px</span>`;
    }));
  },
  async fromVd(vd) {
    const P = this.params;
    try {
      const j = await runTask("vd2glb", { vd, kind: P.kind, name: P.name }, "Model 3D z pliku .vd");
      if (j.status === "ok" && j.result.glb) {
        P.item = j.result.glb; if (!P.name) P.name = j.result.name;
        this.persist(true); this.panel(); await this.load(true);
        toast("Gotowe: model z " + vd.split(/[\\/]/).pop() + ". Dobierz rodzaj i dopasuj suwakami.", "ok");
      }
    } catch (e) {}
  },
  async build(actions) {
    const P = this.params; if (!P.item || !P.name) return toast("Podaj plik modelu i nazwę pracy.", "bad");
    try {
      const j = await runTask("uo3d_render", { ...P, actions }, "Render modelu 3D");
      if (j.status === "ok" && j.result.vd) {
        this.bres.innerHTML = ""; this.bres.append("Gotowe: " + j.result.vd + " ",
          el("button", { class: "small", text: "Podgląd", onclick: () => VD.open(j.result.vd) }), " ",
          el("button", { class: "small", text: "Do toolkitu", onclick: () => runTask("copy_to_toolkit", { vd: j.result.vd }) }), " ",
          el("button", { class: "small", text: "Folder", onclick: () => api.post("/api/open", { path: j.result.vd, folder: true }) }));
        this.save(true);
      } else this.bres.textContent = "Nie udało się – zobacz podpowiedź na dole.";
    } catch (e) {}
  },
  async save(quiet) {
    const P = this.params; if (!P.name) return toast("Podaj nazwę pracy.", "bad");
    const r = await api.post("/api/m3d/save", P); P.saved = r.saved; store("fitparams", P);
    const si = $("#saveInfo"); if (si) si.textContent = "Zapisano: " + r.saved + (r.versions.length ? " · poprzednie wersje: " + r.versions.length : "");
    if (!quiet) toast("Zapisano: " + r.path, "ok"); this.drawCtx();
  },
};

// ------------------------------------------------------------------ boot
(async () => {
  document.documentElement.dataset.theme = restore("theme", "dark");
  await refresh(); buildNav();
  const bg = S.paths.find((p) => p.key === "bodyglb");
  $("#brandsub").textContent = bg && bg.ok ? bg.value.split(/[\\/]/).pop() : "animacje przedmiotów UO";
  show(S.missing.length ? "settings" : restore("page", "start"));
  if (S.missing.length) toast("Pierwsze uruchomienie: wskaż foldery (albo kliknij „Wykryj automatycznie”).");
})();
