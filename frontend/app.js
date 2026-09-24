// Model çıktıları SADECE textContent ile yazılır (innerHTML yok): çıktıdaki HTML/script çalışmaz.
const $ = (s) => document.querySelector(s);
const NAMES = { claude: "Claude", gpt: "GPT", gemini: "Gemini" };
const CRITERIA = [
  ["jury_fit", "Jüri uyumu"], ["feasibility", "Yapılabilirlik"], ["wow", "Etki anı"],
  ["originality", "Özgünlük"], ["demo", "Demo"],
];
const STAGES = ["input", "refine", "council_round1", "council_round2", "judge", "decision", "research", "build"];
const STAGE_NAMES = { refine: "Netleştirme", council_round1: "Konsey I", council_round2: "Konsey II", judge: "Jüri" };

function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text != null) n.textContent = text;
  return n;
}

let runId = null;
let source = null;
const ideaCards = {};   // idea_id → kart elemanı (eleştiriler altına eklenir)
const ideaCount = {};   // model → fikir sayısı
const seconds = {};     // "aşama:model" → süre (saniye)

// ---------- aşama rayı + saat ----------
function setStage(stage) {
  const idx = STAGES.indexOf(stage);
  document.querySelectorAll("#rail li").forEach((li, i) => {
    li.classList.toggle("done", i < idx);
    li.classList.toggle("active", i === idx);
  });
}

let clockTimer = null;
function startClock() {
  const t0 = Date.now();
  const c = $("#clock");
  c.hidden = false;
  clockTimer = setInterval(() => {
    const s = Math.floor((Date.now() - t0) / 1000);
    c.textContent = `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
  }, 1000);
}
const stopClock = () => clearInterval(clockTimer);

// ---------- şerit durumu ----------
function lane(model) { return document.querySelector(`.lane[data-model="${model}"]`); }
function setLane(model, status, { busy = false, down = false } = {}) {
  const l = lane(model);
  if (!l || l.classList.contains("down")) return;  // düşen model düşük kalır
  l.classList.toggle("busy", busy);
  l.classList.toggle("down", down);
  l.querySelector(".status").textContent = status;
}

// ---------- olay işleyiciler ----------
const handlers = {
  stage({ stage }) {
    setStage(stage);
    if (stage === "council_round1") Object.keys(NAMES).forEach((m) => setLane(m, "düşünüyor…", { busy: true }));
    if (stage === "council_round2") Object.keys(NAMES).forEach((m) => setLane(m, "eleştiriyor…", { busy: true }));
    if (stage === "judge") Object.keys(NAMES).forEach((m) => setLane(m, `${ideaCount[m] || 0} fikir`));
  },

  timing(d) {
    seconds[`${d.stage}:${d.model}`] = d.seconds;
    if (!d.stage.startsWith("council")) return;
    const l = lane(d.model);
    let t = l.querySelector(".time");
    if (!t) { t = el("p", "time mono"); l.querySelector("header").after(t); }
    const part = `${STAGE_NAMES[d.stage]} ${Math.round(d.seconds)}s${d.ok ? "" : " ✗"}`;
    t.textContent = t.textContent ? `${t.textContent} · ${part}` : part;
  },

  refined(d) {
    $("#brief-topic").textContent = d.topic;
    $("#brief-by").textContent = `· ${NAMES[d.model]} · ${Math.round(seconds[`refine:${d.model}`] || 0)}s`;
    const ul = $("#criteria");
    ul.replaceChildren(...d.jury_criteria.map((c) => el("li", null, c)));
  },

  idea(d) {
    ideaCount[d.author] = (ideaCount[d.author] || 0) + 1;
    const card = el("article", "idea");
    const meta = el("p", "meta mono", `${d.idea_id} · tur ${d.round} `);
    if (d.round === 2) meta.append(el("span", "synth", "· sentez"));
    card.append(meta, el("h3", null, d.title), el("p", null, d.pitch));
    ideaCards[d.idea_id] = card;
    lane(d.author).querySelector(".cards").append(card);
    setLane(d.author, d.round === 2 ? "sentezledi" : `${ideaCount[d.author]} fikir`);
  },

  critique(d) {
    const card = ideaCards[d.idea_id];
    if (!card || !d.weaknesses.length) return;
    let box = card.querySelector(".crit");
    if (!box) { box = el("div", "crit"); card.append(box); }
    const p = el("p");
    const who = el("b", null, NAMES[d.by]);
    who.dataset.by = d.by;
    p.append(who, d.weaknesses[0]);
    box.append(p);
  },

  error(d) {
    if (d.stage.startsWith("council")) setLane(d.model, "düştü", { down: true });
    console.warn(d);
  },

  ranking(d) {
    renderRanking(d.ranking);
    $("#judge-by").textContent = `Jüri: ${NAMES[d.judge]}, ${Math.round(seconds[`judge:${d.judge}`] || 0)}s.`;
  },

  done(d) {
    $("#timings").textContent = "Süre: " + Object.entries(d.stages)
      .map(([k, v]) => `${STAGE_NAMES[k]} ${Math.round(v)}s`).join(" · ") + ` · toplam ${Math.round(d.total)}s`;
    setStage("decision");
    stopClock();
    source.close();
  },

  fatal(d) {
    stopClock();
    source.close();
    const f = $("#fatal");
    f.hidden = false;
    f.textContent = `Durdu: ${d.error}. Sayfayı yenileyip tekrar dene.`;
  },
};

// ---------- jüri puan kartları ----------
function ticks(value, color) {
  const dd = el("dd");
  for (let i = 1; i <= 10; i++) dd.append(el("span", i <= value ? "on" : null));
  dd.style.setProperty("--c", color);
  return dd;
}

function detailRow(dl, label, value) {
  dl.append(el("dt", null, label));
  const dd = el("dd");
  if (Array.isArray(value)) {
    const ul = el("ul");
    value.forEach((v) => ul.append(el("li", null, v)));
    dd.append(ul);
  } else dd.textContent = value;
  dl.append(dd);
}

function renderRanking(ranking) {
  $("#jury").hidden = false;
  const box = $("#scores");
  box.replaceChildren();
  for (const r of ranking) {
    const color = `var(--${r.author})`;
    const row = el("article", "score");
    row.dataset.id = r.idea_id;

    const body = el("div");
    body.append(
      el("p", "meta mono", `${r.idea_id} · ${NAMES[r.author]} · tur ${r.round}`),
      el("h3", null, r.idea.title),
      el("p", "pitch", r.idea.pitch),
    );

    const dl = el("dl", "ticks");
    for (const [key, label] of CRITERIA) {
      dl.append(el("dt", null, label), ticks(r.scores[key], color), el("span", "n", r.scores[key]));
    }
    body.append(dl);

    const det = el("details");
    det.append(el("summary", null, "Detaylar ve jüri gerekçesi"));
    const ddl = el("dl");
    detailRow(ddl, "Jüri", r.reasoning);
    detailRow(ddl, "Problem", r.idea.problem);
    detailRow(ddl, "Çözüm", r.idea.solution);
    detailRow(ddl, "MVP", r.idea.mvp_scope);
    detailRow(ddl, "Etki anı", r.idea.wow_factor);
    detailRow(ddl, "Riskler", r.idea.risks);
    det.append(ddl);
    body.append(det);

    const pick = el("button", "pick", "Bu fikri seç");
    pick.type = "button";
    pick.addEventListener("click", () => openDecision(row, r));
    body.append(pick);

    const total = el("div", "total", r.total.toFixed(2));
    total.append(el("small", null, "/ 10"));
    row.append(el("div", "rank", r.rank), body, total);
    box.append(row);
  }
}

function openDecision(row, r) {
  document.querySelectorAll(".decide").forEach((n) => n.remove());
  const form = el("form", "decide");
  const note = el("input");
  note.placeholder = "Not ekle (isteğe bağlı), ör. MVP'den sesli girişi çıkar";
  note.setAttribute("aria-label", "Karar notu");
  const save = el("button", "primary", "Kararı kaydet");
  form.append(note, save);
  row.querySelector(".pick").after(form);
  note.focus();

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    save.disabled = true;
    const res = await fetch(`/api/runs/${runId}/decision`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ idea_id: r.idea_id, note: note.value }),
    });
    const data = await res.json();
    if (!res.ok) { save.disabled = false; form.append(el("p", "error", data.detail)); return; }
    document.querySelectorAll(".score").forEach((s) => s.classList.remove("chosen"));
    row.classList.add("chosen");
    const done = el("div", "decided");
    const go = el("button", "primary", "Bu fikir için araştırma yap");
    go.type = "button";
    go.addEventListener("click", () => startResearch(go));
    done.append(el("p", "saved", `Karar kaydedildi: ${data.saved}`), go);
    form.replaceWith(done);
  });
}

// ---------- V2: araştırma ----------
const R_STATUS = {
  research_queries: "Arama sorguları yazılıyor…",
  research_collect: "Makaleler, repolar, web kaynakları ve videolar toplanıyor…",
  research_verify: "Linkler tek tek doğrulanıyor…",
  research_analyze: "Kaynaklardan sayılar ve özellikler çıkarılıyor…",
};
const BADGE = { verified: ["✓", "doğrulandı"], unverified: ["?", "doğrulanamadı: site erişimi engelledi"], dead: ["✗", "ulaşılamadı"] };
let rSource = null;

// Model linkleri: SADECE http/https tıklanabilir (javascript: vb. linkler düz metin kalır)
function link(url, text) {
  let u;
  try { u = new URL(url); } catch { return el("span", null, text); }
  if (u.protocol !== "http:" && u.protocol !== "https:") return el("span", null, text);
  const a = el("a", null, text);
  a.href = u.href;
  a.target = "_blank";
  a.rel = "noopener noreferrer";
  return a;
}
const host = (url) => { try { return new URL(url).hostname.replace(/^www\./, ""); } catch { return url; } };
function badge(status) {
  const [sym, label] = BADGE[status] || BADGE.unverified;
  const b = el("span", `badge ${status}`, sym);
  b.title = label;
  b.setAttribute("aria-label", label);
  return b;
}

function addSource(kind, title, url, status, meta) {
  const li = el("li");
  li.append(el("span", "kind mono", kind), badge(status), link(url, title));
  if (meta) li.append(el("p", "meta", meta));
  $("#sources").append(li);
  $("#source-count").textContent = `· ${$("#sources").children.length}`;
}

const researchHandlers = {
  stage({ stage }) { $("#research-status").textContent = R_STATUS[stage] || ""; },
  source(d) {
    if (d.status === "dead") return;  // ölü linkler listelenmez
    const kind = d.kind === "paper" ? "makale" : d.kind === "video" ? "video" : "web";
    const meta = d.kind === "paper" ? `${d.year} · ${d.citations} atıf` : d.finding;
    addSource(kind, d.title, d.url, d.status, meta);
  },
  repo(d) {
    const meta = [`${d.stars} yıldız · son güncelleme ${d.last_push}`, d.reuse && `Alınabilir: ${d.reuse}`, d.caution && `Dikkat: ${d.caution}`]
      .filter(Boolean).join(" · ");
    addSource("repo", d.name, d.url, "verified", meta);
  },
  research(d) {
    renderStats(d.stats);
    renderFeatures(d.features);
  },
  error(d) { console.warn(d); },
  timing() {},
  queries() {},
  done(d) {
    stopClock();
    rSource.close();
    $("#research-status").textContent = `Araştırma bitti: ${Math.round(d.total)} saniye.`;
  },
  fatal(d) {
    stopClock();
    rSource.close();
    $("#research-status").textContent = `Araştırma durdu: ${d.error}`;
  },
};

function renderStats(stats) {
  const box = $("#stats");
  if (!stats.length) { box.replaceChildren(el("p", "hint", "Kaynaklarda kullanılabilir sayı bulunamadı.")); return; }
  box.replaceChildren(...stats.map((s) => {
    const card = el("article", "stat");
    const src = el("p", "src");
    src.append(badge(s.status), link(s.source_url, host(s.source_url)));
    card.append(el("p", "value", s.value), el("p", "claim", s.claim), src, el("p", "use mono", s.pitch_use));
    return card;
  }));
}

function renderFeatures(features) {
  const form = $("#features");
  if (!features.length) { form.replaceChildren(el("p", "hint", "Kaynaklara dayanan özellik bulunamadı.")); return; }
  const items = features.map((f, i) => {
    const row = el("label", "feature");
    const cb = el("input");
    cb.type = "checkbox";
    cb.value = f.name;
    cb.id = `f${i}`;
    const body = el("span");
    const name = el("strong", null, f.name);
    body.append(name, el("span", `effort ${f.effort}`, { low: "kolay", medium: "orta", high: "zor" }[f.effort] || f.effort),
      el("span", "why", f.why));
    const srcs = el("span", "fsrc");
    f.source_urls.forEach((u) => srcs.append(link(u, host(u))));
    body.append(srcs);
    row.append(cb, body);
    return row;
  });
  const note = el("input");
  note.placeholder = "Not (isteğe bağlı)";
  note.setAttribute("aria-label", "Özellik kararı notu");
  const save = el("button", "primary", "Seçili özellikleri kaydet");
  save.type = "submit";
  form.replaceChildren(...items, note, save);

  form.onsubmit = async (e) => {
    e.preventDefault();
    save.disabled = true;
    const chosen = [...form.querySelectorAll("input[type=checkbox]:checked")].map((c) => c.value);
    const res = await fetch(`/api/runs/${runId}/research-decision`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ features: chosen, note: note.value }),
    });
    const data = await res.json();
    if (!res.ok) { save.disabled = false; form.append(el("p", "error", data.detail)); return; }
    const go = el("button", "primary", "Kodlamaya başla");
    go.type = "button";
    go.addEventListener("click", () => startBuild(go, false));
    save.replaceWith(el("p", "saved", `${data.count} özellik kaydedildi: ${data.saved}`), go);
  };
}

async function startResearch(btn) {
  btn.disabled = true;
  const res = await fetch(`/api/runs/${runId}/research`, { method: "POST" });
  const data = await res.json();
  if (!res.ok) { btn.disabled = false; btn.after(el("p", "error", data.detail)); return; }
  document.querySelectorAll(".pick").forEach((p) => { p.disabled = true; });  // karar araştırmayla kilitlenir
  btn.remove();
  setStage("research");
  $("#research").hidden = false;
  $("#research").scrollIntoView({ behavior: "smooth" });
  startClock();
  rSource = new EventSource(`/api/runs/${data.research_id}/events`);
  for (const [name, fn] of Object.entries(researchHandlers)) {
    rSource.addEventListener(name, (ev) => fn(JSON.parse(ev.data)));
  }
}

// ---------- V3: kodlama ----------
const T_STATUS = {
  coding: "kod yazılıyor", "security review": "güvenlik incelemesi", "fixing security": "güvenlik düzeltmesi",
  done: "bitti", "tests failing": "testler kırık", "done (önceki çalıştırma)": "bitti (önceki)",
};
const tStatus = (s) => T_STATUS[s] || s.replace("fixing", "düzeltiliyor");
let bSource = null;

function taskRow(id) { return document.querySelector(`#tasks li[data-id="${CSS.escape(id)}"]`); }
function taskLog(id, node) {
  const li = taskRow(id);
  if (li) li.querySelector(".tlog").append(node);
}

async function answer(ok, note, box) {
  box.querySelectorAll("button").forEach((b) => { b.disabled = true; });
  const res = await fetch(`/api/runs/${runId}/build/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ok, note }),
  });
  if (res.ok) box.remove();
  else box.append(el("p", "error", (await res.json()).detail));
}

function renderApproval({ kind, data }) {
  const box = el("div", "approve");
  const note = el("input");
  const row = el("div", "row");
  const yes = el("button", "primary", kind === "plan" ? "Planı onayla" : "Paketleri kur");
  const no = el("button", "pick", kind === "plan" ? "Notla yeniden planla" : "Kurma");
  yes.type = no.type = "button";
  if (kind === "plan") {
    box.append(el("h3", null, "Planı onaylıyor musun?"), el("p", null, data.summary));
    const ul = el("ul");
    ul.append(el("li", null, `Ek paketler: ${data.packages.length ? data.packages.join(", ") : "yok"}`));
    box.append(ul);
    note.placeholder = "Düzeltme notu, ör. T6'yı çıkar, haritayı basit tut";
    note.setAttribute("aria-label", "Plan düzeltme notu");
    row.append(yes, note, no);
    no.addEventListener("click", () => answer(false, note.value, box));  // not boşsa plan reddedilir
  } else {
    box.append(el("h3", null, "Bu pip paketleri internetten kurulsun mu?"));
    const ul = el("ul");
    data.packages.forEach((p) => ul.append(el("li", "mono", p)));
    box.append(ul, el("p", "hint", "Kurmazsan kodlayıcıya bu paketleri kullanmaması söylenir."));
    row.append(yes, no);
    no.addEventListener("click", () => answer(false, "", box));
  }
  yes.addEventListener("click", () => answer(true, "", box));
  box.append(row);
  $("#approval").replaceChildren(box);
  $("#build-status").textContent = "Onayını bekliyor.";
}

function renderResult(r) {
  const box = el("div", "result");
  const passed = r.tasks.filter((t) => t.tests_ok).length;
  box.append(el("h3", "eyebrow", `${passed}/${r.tasks.length} görev testleri geçti · son test ${r.all_tests_ok ? "✓" : "✗"}`));
  box.append(el("p", "hint", "Çalıştırmak için terminalde:"), el("code", null, `cd ${r.project} && ${r.run_command}`));
  if (r.demo_steps.length) {
    box.append(el("h3", "eyebrow", "Jüriye demo"));
    const ol = el("ol");
    r.demo_steps.forEach((s) => ol.append(el("li", null, s)));
    box.append(ol);
  }
  if (!r.all_tests_ok) {
    const det = el("details");
    det.append(el("summary", null, "Son test çıktısı"), el("pre", null, r.final_test_output));
    box.append(det);
  }
  $("#build-result").replaceChildren(box);
}

function endBuild(text, canResume) {
  stopClock();
  bSource.close();
  $("#build-status").textContent = text;
  $("#approval").replaceChildren();
  $("#build-stop").hidden = true;
  $("#build-resume").hidden = !canResume;
  document.querySelectorAll("#tasks li.busy").forEach((li) => {
    li.classList.remove("busy");
    li.querySelector(".tstat").textContent = "yarım kaldı";
  });
}

const buildHandlers = {
  stage({ stage }) {
    if (stage === "build_plan") $("#build-status").textContent = "Plan yazılıyor…";
    else if (stage === "build_setup") $("#build-status").textContent = "Proje klasörü kuruluyor…";
    else $("#build-status").textContent = `${stage.replace("build_", "")} kodlanıyor…`;
  },
  plan(d) {
    $("#tasks").replaceChildren(...d.tasks.map((t) => {
      const li = el("li");
      li.dataset.id = t.id;
      li.append(el("span", "tid mono", t.id), el("span", "ttitle", t.title), el("span", "tstat mono", "bekliyor"),
        el("p", "tgoal", t.goal), el("div", "tlog"));
      return li;
    }));
  },
  approval: renderApproval,
  project(d) { $("#build-status").textContent = `Proje: ${d.path}`; },
  packages_installed(d) { $("#build-status").textContent = `Kuruldu: ${d.packages.join(", ")}`; },
  resume(d) {
    d.done.forEach((id) => {
      const li = taskRow(id);
      if (!li) return;
      li.classList.add("ok");
      li.querySelector(".tstat").textContent = "bitti (önceki)";
    });
  },
  task(d) {
    const li = taskRow(d.id);
    if (!li) return;
    const final = "tests_ok" in d;
    li.classList.toggle("busy", !final);
    li.classList.toggle("ok", final && d.tests_ok);
    li.classList.toggle("bad", final && !d.tests_ok);
    li.querySelector(".tstat").textContent = tStatus(d.status);
  },
  test(d) {
    taskLog(d.id, el("p", null, `${d.ok ? "✓" : "✗"} testler${d.attempt ? ` (düzeltme ${d.attempt})` : ""}`));
    if (!d.ok) {
      const det = el("details");
      det.append(el("summary", null, "Test çıktısı"), el("pre", null, d.output));
      taskLog(d.id, det);
    }
  },
  security(d) {
    if (!d.reviewed) { taskLog(d.id, el("p", "error", "⚠ Güvenlik incelemesi yapılamadı")); return; }
    if (!d.findings.length) { taskLog(d.id, el("p", null, "🔒 güvenlik: bulgu yok")); return; }
    d.findings.forEach((f) => {
      const p = el("p");
      p.append(el("span", `sev ${f.severity}`, f.severity), `${f.file}: ${f.issue}`);
      taskLog(d.id, p);
    });
  },
  timing() {},
  error(d) { console.warn(d); },
  build: renderResult,
  done(d) { endBuild(`Kodlama bitti: ${Math.round(d.total / 60)} dakika.`, false); },
  fatal(d) { endBuild(`Durdu: ${d.error}`, d.resumable); },
  stopped(d) { endBuild("Durduruldu.", d.resumable); },
};

async function startBuild(btn, resume) {
  btn.disabled = true;
  const res = await fetch(`/api/runs/${runId}/build`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ resume }),
  });
  const data = await res.json();
  if (!res.ok) { btn.disabled = false; btn.after(el("p", "error", data.detail)); return; }
  if (resume) { btn.hidden = true; btn.disabled = false; } else btn.remove();
  $("#features").querySelectorAll("input").forEach((i) => { i.disabled = true; });  // özellikler kodlamayla kilitlenir
  $("#build-result").replaceChildren();
  $("#build-stop").hidden = false;
  setStage("build");
  $("#build").hidden = false;
  $("#build").scrollIntoView({ behavior: "smooth" });
  stopClock();
  startClock();
  bSource = new EventSource(`/api/runs/${data.build_id}/events`);
  for (const [name, fn] of Object.entries(buildHandlers)) {
    bSource.addEventListener(name, (ev) => fn(JSON.parse(ev.data)));
  }
}

$("#build-resume").addEventListener("click", (e) => startBuild(e.target, true));
$("#build-stop").addEventListener("click", async (e) => {
  e.target.disabled = true;
  await fetch(`/api/runs/${runId}/build/stop`, { method: "POST" });
  e.target.disabled = false;
});

// ---------- başlat ----------
$("#intake").addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = e.target.querySelector("button");
  const err = $("#intake-error");
  btn.disabled = true;
  err.hidden = true;

  const res = await fetch("/api/runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ topic: $("#topic").value, hours: Number($("#hours").value), team: $("#team").value, lang: $("#lang").value }),
  });
  const data = await res.json();
  if (!res.ok) {
    btn.disabled = false;
    err.hidden = false;
    err.textContent = typeof data.detail === "string" ? data.detail : "Girdiyi kontrol et.";
    return;
  }

  runId = data.run_id;
  $("#intake").hidden = true;
  $("#work").hidden = false;
  startClock();
  setStage("refine");

  // EventSource koparsa kendisi yeniden bağlanır; sunucu Last-Event-ID ile kaldığı yerden devam eder
  source = new EventSource(`/api/runs/${runId}/events`);
  for (const [name, fn] of Object.entries(handlers)) {
    source.addEventListener(name, (ev) => fn(JSON.parse(ev.data)));
  }
});

setStage("input");

$("#topic").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("#intake").requestSubmit(); }
});
