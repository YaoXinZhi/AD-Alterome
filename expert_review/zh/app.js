/* Standalone, dependency-free expert review client. Source text is always rendered as text nodes. */
(() => {
  "use strict";
  const data = window.REVIEW_DATA;
  const $ = (id) => document.getElementById(id);
  const create = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = String(text);
    return node;
  };
  if (!data || !Array.isArray(data.pages) || !data.pages.length) {
    $("workbench").replaceChildren(create("p", "fatal-error", "未能载入评阅材料。请确认 data/review-data.js 与本页面位于同一目录包内，再通过启动脚本打开。"));
    $("question-en").textContent = "评阅材料尚未就绪";
    return;
  }
  const pages = data.pages;
  const pageIds = new Set(pages.map((page) => page.id));
  const isFile = location.protocol === "file:";
  const storagePrefix = `expert-review:${data.dataset_id}:${data.rubric_version}:`;
  const scoreKeys = ["accuracy", "evidence", "coverage"];
  const rubric = [
    { key: "accuracy", name: "事实与来源准确性", scope: "（证据本身）", definition: "核查所列证据和来源是否真实准确：PMID、题名、原句，以及基因、干预对象和模型背景是否对应。", anchors: ["核心来源或证据严重失实，存在系统性错误。", "存在重要来源、实体或背景错误。", "证据与来源基本准确，仅有轻微错误。", "可核查的证据、来源标识和关键背景均准确。"] },
    { key: "evidence", name: "证据支持与可追溯性", scope: "（证据-回答关联）", definition: "核查关键论断能否定位到具体来源，且原句确实支持该论断的对象、方向、条件和模型。", anchors: ["核心论断无可核查支持，或引用严重不支持结论。", "部分论断有支持，但存在重要错配、推断越界或证据缺口。", "多数关键论断可追溯且获支持，仅有小幅缺口。", "全部关键论断有对应支持，方向与适用范围匹配。"] },
    { key: "coverage", name: "问题回应与覆盖度", scope: "（回答本身）", definition: "评价回答是否直接回应问题，并覆盖必要且正确的核心内容；认可等效答案，不要求穷举实例。", anchors: ["未有效回应问题，或缺少核心内容。", "仅部分回应，遗漏重要内容。", "覆盖主要内容，仅有小幅遗漏。", "必要且正确的核心内容覆盖完整，回应直接。"] },
  ];
  const emptyRating = () => ({ accuracy: null, evidence: null, coverage: null, note: "" });
  const cleanRating = (record) => {
    const value = emptyRating();
    for (const key of scoreKeys) value[key] = Number.isInteger(record?.[key]) && record[key] >= 1 && record[key] <= 4 ? record[key] : null;
    value.note = typeof record?.note === "string" ? record.note.slice(0, 10000) : "";
    return value;
  };
  const sameRating = (a, b) => JSON.stringify(cleanRating(a)) === JSON.stringify(cleanRating(b));
  const revisionOf = (record) => Number.isInteger(record?.revision) && record.revision >= 0 ? record.revision : 0;
  const complete = (record) => !!record && scoreKeys.every((key) => Number.isInteger(record[key]) && record[key] >= 1 && record[key] <= 4);
  let localStorageAvailable = true;
  function readStorage(key) {
    try { return JSON.parse(localStorage.getItem(storagePrefix + key) || "null"); }
    catch (_) { localStorageAvailable = false; return null; }
  }
  function writeStorage(key, value) {
    try { localStorage.setItem(storagePrefix + key, JSON.stringify(value)); return true; }
    catch (_) { localStorageAvailable = false; return false; }
  }
  const savedUi = readStorage("ui") || {};
  const ui = { expert: /^[A-Za-z0-9_-]{1,40}$/.test(savedUi.expert || "") ? savedUi.expert : "E01", page: savedUi.page || pages[0].id };
  for (const key of ["rules", "points"]) {
    ui[`${key}Open`] = savedUi[`${key}Open`] === true;
    ui[`${key}Pinned`] = savedUi[`${key}Pinned`] !== false;
    ui[`${key}X`] = Number.isFinite(savedUi[`${key}X`]) ? savedUi[`${key}X`] : null;
    ui[`${key}Y`] = Number.isFinite(savedUi[`${key}Y`]) ? savedUi[`${key}Y`] : null;
  }
  let pageIndex = Math.max(0, pages.findIndex((page) => page.id === ui.page));
  let context = null;
  let busy = false;
  let toastTimer;
  let writeChain = Promise.resolve();
  const saveTimers = new Map();
  const scoreControls = new Map();
  function persistUi() { writeStorage("ui", ui); }
  function backup(ctx) {
    if (!ctx) return;
    writeStorage(`reviewer:${ctx.expert}`, { dataset_id: data.dataset_id, rubric_version: data.rubric_version, expert_id: ctx.expert, records: ctx.records, drafts: ctx.drafts, saved_at: new Date().toISOString() });
  }
  function toast(message) {
    $("toast").textContent = message;
    $("toast").hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { $("toast").hidden = true; }, 4500);
  }
  function setBusy(value) {
    busy = value;
    $("rating-fields").disabled = value;
    $("expert-id").disabled = value;
    $("expert-form").querySelector("button").disabled = value;
    $("workbench").setAttribute("aria-busy", String(value));
    for (const button of document.querySelectorAll("#question-tabs button, #answer-tabs button")) button.disabled = value;
    updateNavigation();
  }
  function validRecordMap(records) {
    const result = Object.create(null);
    if (!records || typeof records !== "object") return result;
    for (const [id, record] of Object.entries(records)) {
      if (!pageIds.has(id) || !record || typeof record !== "object") continue;
      result[id] = { ...cleanRating(record), revision: revisionOf(record), updated_at: typeof record.updated_at === "string" ? record.updated_at : "" };
    }
    return result;
  }
  async function request(path, options = {}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 9000);
    try {
      const response = await fetch(path, { cache: "no-store", ...options, signal: controller.signal });
      let body;
      try { body = await response.json(); } catch (_) { throw new Error("本地服务未返回有效的评分数据"); }
      return { response, body };
    } finally { clearTimeout(timer); }
  }
  async function loadReviewer(expert) {
    const cached = readStorage(`reviewer:${expert}`);
    const cache = cached?.dataset_id === data.dataset_id && cached?.rubric_version === data.rubric_version && cached?.expert_id === expert ? cached : null;
    const ctx = { expert, records: Object.create(null), server: Object.create(null), drafts: Object.create(null), statuses: Object.create(null), conflicts: Object.create(null), connected: false, sessionLoaded: false, sessionError: "" };
    if (!isFile) {
      try {
        const { response, body } = await request(`/api/session?expert=${encodeURIComponent(expert)}`);
        if (!response.ok || body.dataset_id !== data.dataset_id || body.rubric_version !== data.rubric_version || body.expert_id !== expert) throw new Error("本地评分会话与当前材料不匹配");
        ctx.server = validRecordMap(body.records);
        ctx.records = validRecordMap(body.records);
        ctx.connected = true;
        ctx.sessionLoaded = true;
        Object.keys(ctx.server).forEach((id) => { ctx.statuses[id] = "saved"; });
      } catch (error) { ctx.sessionError = error.name === "AbortError" ? "本地服务响应超时" : "暂时无法读取本地评分文件"; }
    }
    const cachedRecords = validRecordMap(cache?.records);
    if (!ctx.connected) {
      ctx.records = cachedRecords;
      Object.keys(ctx.records).forEach((id) => { ctx.statuses[id] = "browser"; });
    }
    const drafts = cache?.drafts && typeof cache.drafts === "object" ? cache.drafts : {};
    for (const [id, draft] of Object.entries(drafts)) {
      if (!pageIds.has(id) || !draft || !draft.rating) continue;
      const rating = cleanRating(draft.rating);
      const baseRevision = Number.isInteger(draft.base_revision) && draft.base_revision >= 0 ? draft.base_revision : revisionOf(cachedRecords[id]);
      if (ctx.connected && sameRating(rating, ctx.server[id])) continue;
      ctx.records[id] = { ...rating, revision: baseRevision, updated_at: typeof draft.edited_at === "string" ? draft.edited_at : "" };
      ctx.drafts[id] = { rating, base_revision: baseRevision, edited_at: ctx.records[id].updated_at };
      if (ctx.connected && baseRevision !== revisionOf(ctx.server[id])) {
        ctx.conflicts[id] = ctx.server[id] || { ...emptyRating(), revision: 0 };
        ctx.statuses[id] = "conflict";
      } else ctx.statuses[id] = isFile ? "browser" : "pending";
    }
    context = ctx;
    ui.expert = expert;
    $("expert-id").value = expert;
    persistUi();
    backup(ctx);
    renderPage();
    updateConnection();
    if (ctx.connected) for (const id of Object.keys(ctx.drafts)) if (!ctx.conflicts[id]) scheduleSave(ctx, id);
  }
  async function recoverSession(ctx) {
    // A successful write is not a substitute for loading all of this reviewer's existing pages.
    const { response, body } = await request(`/api/session?expert=${encodeURIComponent(ctx.expert)}`);
    if (!response.ok || body.dataset_id !== data.dataset_id || body.rubric_version !== data.rubric_version || body.expert_id !== ctx.expert) throw new Error("尚未恢复完整的磁盘评分会话");
    const currentBefore = ctx.records[pages[pageIndex].id];
    ctx.server = validRecordMap(body.records);
    ctx.records = validRecordMap(body.records);
    ctx.statuses = Object.create(null);
    ctx.conflicts = Object.create(null);
    for (const id of Object.keys(ctx.server)) ctx.statuses[id] = "saved";
    // Read drafts after the GET resolves, so edits made while reconnecting remain intact.
    for (const [id, draft] of Object.entries(ctx.drafts)) {
      if (sameRating(draft.rating, ctx.server[id])) { delete ctx.drafts[id]; continue; }
      ctx.records[id] = { ...cleanRating(draft.rating), revision: draft.base_revision, updated_at: draft.edited_at || "" };
      if (draft.base_revision !== revisionOf(ctx.server[id])) {
        ctx.conflicts[id] = ctx.server[id] || { ...emptyRating(), revision: 0 };
        ctx.statuses[id] = "conflict";
      } else ctx.statuses[id] = "pending";
    }
    ctx.connected = true;
    ctx.sessionLoaded = true;
    ctx.sessionError = "";
    backup(ctx);
    if (context === ctx) {
      if (!sameRating(currentBefore, ctx.records[pages[pageIndex].id])) renderRatings();
      else updateRatingStatus();
      updateProgress(); updateConnection();
    }
  }
  function updateConnection() {
    if (!context) return;
    const banner = $("connection-banner");
    let message = "";
    if (isFile) message = "浏览器预览模式：评分仅保存在本浏览器，无法自动写回文件。请用启动脚本打开以保存至 ratings；当前结果可随时导出 JSON / CSV。";
    else if (!context.connected) message = `${context.sessionError || "本地评分服务暂不可用"}。当前改动保留为浏览器草稿；“重试保存”成功前，不会显示为磁盘已保存。`;
    if (!localStorageAvailable) message += `${message ? " " : ""}浏览器草稿备份不可用，请及时导出当前评分。`;
    banner.textContent = message;
    banner.hidden = !message;
  }
  function markChanged() {
    if (busy || !context) return;
    const page = pages[pageIndex];
    const rating = emptyRating();
    for (const key of scoreKeys) {
      const control = scoreControls.get(key);
      rating[key] = control.input.dataset.unrated === "true" ? null : Number(control.input.value);
    }
    rating.note = $("rating-note").value;
    if (sameRating(rating, context.records[page.id]) && context.records[page.id]) return;
    const baseRevision = context.drafts[page.id]?.base_revision ?? revisionOf(context.server[page.id] || context.records[page.id]);
    const now = new Date().toISOString();
    context.records[page.id] = { ...rating, revision: baseRevision, updated_at: now };
    context.drafts[page.id] = { rating: { ...rating }, base_revision: baseRevision, edited_at: now };
    context.statuses[page.id] = context.conflicts[page.id] ? "conflict" : isFile ? "browser" : "pending";
    backup(context);
    updateProgress();
    updateRatingStatus();
    updateConnection();
    scheduleSave(context, page.id);
  }
  function scheduleSave(ctx, id) {
    if (isFile || ctx.conflicts[id]) return;
    const key = `${ctx.expert}:${id}`;
    clearTimeout(saveTimers.get(key));
    saveTimers.set(key, setTimeout(() => {
      saveTimers.delete(key);
      enqueueSave(ctx, id);
    }, 600));
  }
  function enqueueSave(ctx, id) {
    writeChain = writeChain.catch(() => {}).then(() => savePage(ctx, id));
    return writeChain;
  }
  async function savePage(ctx, id) {
    if (isFile || ctx.conflicts[id] || !ctx.drafts[id]) return;
    if (!ctx.sessionLoaded) {
      ctx.statuses[id] = "saving";
      if (context === ctx) updateRatingStatus();
      try { await recoverSession(ctx); }
      catch (error) {
        ctx.statuses[id] = "failed";
        ctx.connected = false;
        ctx.sessionError = error.name === "AbortError" ? "恢复磁盘评分会话超时" : error.message;
        backup(ctx);
        if (context === ctx) { updateRatingStatus(); updateProgress(); updateConnection(); }
        return;
      }
    }
    while (ctx.drafts[id] && !ctx.conflicts[id]) {
      const draft = { ...ctx.drafts[id], rating: { ...ctx.drafts[id].rating } };
      ctx.statuses[id] = "saving";
      if (context === ctx) updateRatingStatus();
      try {
        const { response, body } = await request("/api/ratings", { method: "PUT", headers: { "Content-Type": "application/json", "X-Review-App": "1" }, body: JSON.stringify({ expert_id: ctx.expert, page_id: id, base_revision: draft.base_revision, rating: draft.rating }) });
        if (response.status === 409 && body.error === "conflict") {
          ctx.conflicts[id] = { ...cleanRating(body.record), revision: revisionOf(body.record), updated_at: body.record?.updated_at || "" };
          ctx.statuses[id] = "conflict";
          ctx.connected = true;
          break;
        }
        if (!response.ok || body.saved !== true || body.expert_id !== ctx.expert || body.page_id !== id || !body.record || revisionOf(body.record) <= draft.base_revision || !sameRating(body.record, draft.rating)) throw new Error(response.status >= 500 ? "磁盘写入失败" : "评分未获本地服务确认");
        const saved = { ...cleanRating(body.record), revision: revisionOf(body.record), updated_at: body.record.updated_at || new Date().toISOString() };
        ctx.server[id] = saved;
        ctx.connected = true;
        ctx.sessionError = "";
        if (ctx.drafts[id] && sameRating(ctx.drafts[id].rating, draft.rating)) {
          ctx.records[id] = { ...saved };
          delete ctx.drafts[id];
          ctx.statuses[id] = "saved";
        } else if (ctx.drafts[id]) {
          ctx.drafts[id].base_revision = saved.revision;
          ctx.records[id].revision = saved.revision;
          ctx.statuses[id] = "pending";
        }
      } catch (error) {
        ctx.statuses[id] = "failed";
        ctx.connected = false;
        ctx.sessionError = error.name === "AbortError" ? "本地评分服务响应超时" : error.message;
        break;
      } finally {
        backup(ctx);
        if (context === ctx) { updateRatingStatus(); updateProgress(); updateConnection(); }
      }
    }
  }
  async function flush(ctx = context) {
    if (!ctx) return;
    for (const id of Object.keys(ctx.drafts)) {
      const key = `${ctx.expert}:${id}`;
      clearTimeout(saveTimers.get(key));
      saveTimers.delete(key);
      if (!ctx.conflicts[id] && !isFile) enqueueSave(ctx, id);
    }
    backup(ctx);
    await writeChain;
  }
  async function navigate(index) {
    if (busy || index < 0 || index >= pages.length || index === pageIndex) return;
    setBusy(true);
    try {
      await flush();
      pageIndex = index;
      ui.page = pages[index].id;
      for (const key of ["rules", "points"]) if (!ui[`${key}Pinned`]) setFloatingOpen(key, false);
      persistUi();
      renderPage();
    } finally { setBusy(false); }
  }
  function safeUrl(value) {
    try { const url = new URL(String(value)); return ["http:", "https:"].includes(url.protocol) ? url.href : null; }
    catch (_) { return null; }
  }
  function pmidFrom(value) {
    const found = String(value).match(/(?:pubmed\.ncbi\.nlm\.nih\.gov\/|\bPMID\s*:?\s*)(\d{5,9})/i);
    return found?.[1] || null;
  }
  function citation(label, pmid) {
    const button = create("button", "inline-cite", label);
    button.type = "button";
    button.title = `定位 PMID ${pmid} 的文献与原句`;
    button.addEventListener("click", () => focusReference(pmid));
    return button;
  }
  function appendInline(parent, value, answer = false, depth = 0) {
    const text = String(value ?? "");
    if (depth > 6) { parent.append(document.createTextNode(text)); return; }
    const pattern = /\[([^\]\n]+)\]\(([^\s)]+)\)|\*\*([^\n]+?)\*\*|__([^\n]+?)__|`([^`\n]+)`|\*([^*\n]+)\*|\bPMID\s*:?\s*\d{5,9}\b|https?:\/\/pubmed\.ncbi\.nlm\.nih\.gov\/\d+\/?/gi;
    let end = 0;
    for (const match of text.matchAll(pattern)) {
      parent.append(document.createTextNode(text.slice(end, match.index)));
      if (match[1] !== undefined) {
        const pmid = pmidFrom(match[2]) || pmidFrom(match[1]);
        const url = safeUrl(match[2]);
        if (answer && pmid) parent.append(citation(match[1], pmid));
        else if (url) { const link = create("a", "", match[1]); link.href = url; link.target = "_blank"; link.rel = "noopener noreferrer"; parent.append(link); }
        else parent.append(document.createTextNode(match[1]));
      } else if (match[3] !== undefined || match[4] !== undefined) {
        const strong = create("strong"); appendInline(strong, match[3] ?? match[4], answer, depth + 1); parent.append(strong);
      } else if (match[5] !== undefined) parent.append(create("code", "", match[5]));
      else if (match[6] !== undefined) { const em = create("em"); appendInline(em, match[6], answer, depth + 1); parent.append(em); }
      else if (answer && pmidFrom(match[0])) parent.append(citation(match[0], pmidFrom(match[0])));
      else parent.append(document.createTextNode(match[0]));
      end = match.index + match[0].length;
    }
    parent.append(document.createTextNode(text.slice(end)));
  }
  function markdown(target, value, answer = false) {
    target.classList.add("markdown");
    const chunks = String(value ?? "").split(/\n\s*\n/);
    for (const chunk of chunks) {
      if (!chunk.trim()) continue;
      const lines = chunk.split("\n");
      let list = null;
      for (const line of lines) {
        const listMatch = line.match(/^\s*(?:([-*+])|(\d+)\.)\s+(.+)$/);
        const heading = line.match(/^\s*(#{1,6})\s+(.+)$/);
        if (listMatch) {
          const kind = listMatch[2] ? "OL" : "UL";
          if (!list || list.tagName !== kind) { list = create(kind.toLowerCase()); if (listMatch[2]) list.start = Number(listMatch[2]); target.append(list); }
          const li = create("li"); appendInline(li, listMatch[3], answer); list.append(li);
        } else {
          list = null;
          const node = create(heading ? "h3" : /^\s*>/.test(line) ? "blockquote" : "p");
          appendInline(node, heading ? heading[2] : line.replace(/^\s*>\s?/, ""), answer);
          target.append(node);
        }
      }
    }
  }
  function focusReference(pmid) {
    const card = document.getElementById(`reference-${pmid}`);
    if (!card) { toast(`当前材料未提供 PMID ${pmid} 的原句；请在备注中记录需要核对的内容。`); return; }
    const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
    const evidence = $("evidence-content");
    // Compute against the independently scrolling evidence pane, without moving the entire desktop page.
    evidence.scrollTo({ top: evidence.scrollTop + card.getBoundingClientRect().top - evidence.getBoundingClientRect().top - 14, behavior: reduced ? "instant" : "smooth" });
    if (innerWidth <= 760) $("evidence-heading").scrollIntoView({ block: "start", behavior: reduced ? "instant" : "smooth" });
    card.classList.remove("highlight");
    void card.offsetWidth;
    card.classList.add("highlight");
    card.focus({ preventScroll: true });
    setTimeout(() => card.classList.remove("highlight"), 2300);
  }
  function renderAnswer(page) {
    const body = $("answer-content");
    body.replaceChildren();
    for (const block of page.answer_blocks || []) {
      const wrapper = create("article", "answer-block");
      const original = create("div", "answer-en"); original.lang = "en"; markdown(original, block.en, true); wrapper.append(original);
      if (block.zh) { const translated = create("div", "translation"); translated.lang = "zh-CN"; markdown(translated, block.zh, true); wrapper.append(translated); }
      body.append(wrapper);
    }
    if (!body.children.length) body.append(create("p", "empty-state", "此页未提供可评阅的回答。"));
    body.scrollTop = 0;
  }
  function renderEvidence(page) {
    const body = $("evidence-content"); body.replaceChildren();
    const references = Array.isArray(page.references) ? page.references : [];
    $("reference-count").textContent = `${references.length} 篇文献`;
    body.append(create("p", "evidence-intro", "供独立核对。文献及摘录的收录，不代表回答中的论断已获其支持。"));
    for (const ref of references) {
      const card = create("article", "reference-card"); card.id = `reference-${String(ref.pmid)}`; card.tabIndex = -1;
      const meta = create("div", "reference-meta"); meta.append(create("span", "pmid-tag", `PMID ${ref.pmid}`));
      if (ref.journal || ref.year) meta.append(create("span", "reference-journal", [ref.journal, ref.year].filter(Boolean).join(" · ")));
      card.append(meta);
      const title = create("h3", "reference-title", ref.title_en || "题名暂未取得"); title.lang = "en"; card.append(title);
      if (ref.title_zh) card.append(create("p", "translation title-translation", ref.title_zh));
      const url = safeUrl(ref.url || `https://pubmed.ncbi.nlm.nih.gov/${encodeURIComponent(ref.pmid)}/`);
      if (url) { const link = create("a", "source-link", "PubMed ↗"); link.href = url; link.target = "_blank"; link.rel = "noopener noreferrer"; card.append(link); }
      for (const item of ref.excerpts || []) {
        const excerpt = create("div", "excerpt"); excerpt.append(create("div", "excerpt-label", item.source_label || "原文摘录"));
        const en = create("div", "excerpt-en"); en.lang = "en"; en.textContent = item.en || ""; excerpt.append(en);
        if (item.zh) excerpt.append(create("div", "translation excerpt-zh", item.zh));
        const sourceUrl = safeUrl(item.url);
        if (sourceUrl && sourceUrl !== url) { const source = create("a", "source-link", "摘录来源 ↗"); source.href = sourceUrl; source.target = "_blank"; source.rel = "noopener noreferrer"; excerpt.append(source); }
        card.append(excerpt);
      }
      if (ref.note) card.append(create("p", "reference-note", ref.note));
      else if (!(ref.excerpts || []).length) card.append(create("p", "reference-note", "当前材料未取得可展示的原文摘录；不能仅据此判定来源是否支持回答。"));
      body.append(card);
    }
    if (!references.length) body.append(create("p", "empty-state", "此回答未提供可列示的引用材料。请分别判断事实准确性与证据支持，不因缺少引用直接认定虚构。"));
    body.scrollTop = 0;
  }
  function buildScores() {
    rubric.forEach((dimension, index) => {
      const field = create("div", "score-field");
      const labelRow = create("div", "score-label");
      const label = create("label"); label.htmlFor = `score-${dimension.key}`; label.append(create("span", "", `D${index + 1}`), document.createTextNode(dimension.name));
      const output = create("output", "score-value", "未评"); output.htmlFor = `score-${dimension.key}`; labelRow.append(label, output);
      const help = create("p", "score-help", dimension.scope); help.id = `score-help-${dimension.key}`; help.title = dimension.definition;
      const input = create("input"); input.type = "range"; input.id = `score-${dimension.key}`; input.name = dimension.key; input.min = "1"; input.max = "4"; input.step = "1"; input.value = "1"; input.dataset.unrated = "true"; input.setAttribute("aria-describedby", help.id);
      const ticks = create("div", "score-ticks"); ticks.setAttribute("role", "group"); ticks.setAttribute("aria-label", `${dimension.name}分值`);
      const select = () => { if (busy) return; input.dataset.unrated = "false"; updateScoreAppearance(dimension.key); markChanged(); };
      input.addEventListener("input", select);
      input.addEventListener("change", select);
      input.addEventListener("pointerup", select);
      input.addEventListener("keydown", (event) => {
        if (["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End", "PageUp", "PageDown", " ", "Enter"].includes(event.key)) {
          event.preventDefault();
          let value = Number(input.value);
          if (["ArrowRight", "ArrowUp", "PageUp"].includes(event.key)) value += 1;
          if (["ArrowLeft", "ArrowDown", "PageDown"].includes(event.key)) value -= 1;
          if (event.key === "Home") value = 1;
          if (event.key === "End") value = 4;
          input.value = String(Math.min(4, Math.max(1, value)));
          select();
        }
      });
      for (let value = 1; value <= 4; value += 1) {
        const button = create("button", "", value); button.type = "button"; button.title = `${value} 分：${dimension.anchors[value - 1]}`; button.setAttribute("aria-label", `${dimension.name} ${value} 分`); button.setAttribute("aria-pressed", "false");
        button.addEventListener("click", () => { input.value = String(value); select(); }); ticks.append(button);
      }
      field.append(labelRow, input, ticks, help); $("score-fields").append(field);
      scoreControls.set(dimension.key, { input, output, ticks });
    });
  }
  function updateScoreAppearance(key) {
    const control = scoreControls.get(key);
    const rated = control.input.dataset.unrated !== "true";
    const value = Number(control.input.value);
    control.output.textContent = rated ? `${value} 分` : "未评";
    control.output.classList.toggle("rated", rated);
    control.input.setAttribute("aria-valuetext", rated ? `${value} 分` : "未评，操作后选择 1 至 4 分");
    control.input.style.setProperty("--range-progress", rated ? `${(value - 1) / 3 * 100}%` : "0%");
    [...control.ticks.children].forEach((button, index) => button.setAttribute("aria-pressed", String(rated && index + 1 === value)));
  }
  function renderRatings() {
    const record = context.records[pages[pageIndex].id] || emptyRating();
    for (const key of scoreKeys) {
      const control = scoreControls.get(key); control.input.value = String(record[key] ?? 1); control.input.dataset.unrated = String(record[key] === null || record[key] === undefined); updateScoreAppearance(key);
    }
    $("rating-note").value = record.note || "";
    updateRatingStatus();
    document.querySelector(".rating-body").scrollTop = 0;
  }
  function renderQuestionTabs() {
    const nav = $("question-tabs"); nav.replaceChildren();
    const current = pages[pageIndex];
    const seen = new Set();
    const groups = new Map();
    const categoryNames = { G: "基因", P: "表型", H: "假说" };
    pages.forEach((page, index) => {
      if (seen.has(page.question_id)) return;
      seen.add(page.question_id);
      const category = String(page.question_id).charAt(0);
      if (!groups.has(category)) {
        const group = create("div", "question-group"); group.setAttribute("role", "group"); group.setAttribute("aria-label", `${categoryNames[category] || "其他"}题目`);
        group.append(create("span", "question-group-label", categoryNames[category] || "其他"));
        groups.set(category, group); nav.append(group);
      }
      const button = create("button", "", page.question_id); button.type = "button"; button.title = page.question_zh; button.setAttribute("aria-label", `跳转到 ${page.question_id}：${page.question_zh}`); button.setAttribute("aria-current", String(current.question_id === page.question_id)); button.disabled = busy; button.addEventListener("click", () => navigate(index)); groups.get(category).append(button);
    });
    const answerNav = $("answer-tabs"); answerNav.replaceChildren();
    pages.forEach((page, index) => {
      if (page.question_id !== current.question_id) return;
      const button = create("button", "", page.id); button.type = "button"; button.setAttribute("aria-current", String(index === pageIndex)); button.disabled = busy; button.addEventListener("click", () => navigate(index)); answerNav.append(button);
    });
  }
  function renderPage() {
    const page = pages[pageIndex];
    $("question-en").textContent = page.question_en; $("question-en").lang = "en";
    $("question-zh").textContent = page.question_zh;
    $("current-page-id").textContent = `${page.question_id} · ${page.id}`;
    renderQuestionTabs(); renderAnswer(page); renderEvidence(page); renderReferencePoints(page); renderRatings(); updateProgress(); updateNavigation();
    document.title = `${page.question_id} · 第 ${pageIndex + 1} 页 | AD-Alterome 专家评阅`;
  }
  function updateNavigation() {
    $("previous-page").disabled = busy || pageIndex === 0;
    $("next-page").disabled = busy || pageIndex === pages.length - 1;
  }
  function updateProgress() {
    if (!context) return;
    const count = pages.filter((page) => complete(context.records[page.id])).length;
    const diskCount = pages.filter((page) => complete(context.server[page.id]) && !context.drafts[page.id]).length;
    const draftCount = Object.keys(context.drafts).length;
    $("rated-progress").textContent = `已评 ${count} / ${pages.length}`;
    $("rated-progress").title = draftCount ? `已填完整 ${count} 页，${draftCount} 页含未写入磁盘的草稿` : `已填完整 ${count} 页`;
    $("page-progress").textContent = `第 ${pageIndex + 1} / ${pages.length} 页`;
    $("progress-fill").style.width = `${count / pages.length * 100}%`;
    if (isFile) $("footer-save-summary").textContent = "仅浏览器草稿 · 请导出备份";
    else if (draftCount) $("footer-save-summary").textContent = `${draftCount} 页草稿待存盘 · 完整存盘 ${diskCount}/${pages.length}`;
    else if (!context.connected) $("footer-save-summary").textContent = "浏览器备份 · 尚未核对磁盘";
    else $("footer-save-summary").textContent = `完整存盘 ${diskCount}/${pages.length} · 改动自动保存`;
  }
  function ratingSummary(record) {
    return `D1–D3：${scoreKeys.map((key) => record?.[key] ?? "—").join(" / ")}`;
  }
  function renderConflict(id) {
    const panel = $("conflict-panel"); panel.replaceChildren();
    const remote = context.conflicts[id]; panel.hidden = !remote;
    if (!remote) return;
    panel.append(create("h3", "", "检测到评分版本冲突"), create("p", "", "本地草稿已保留，磁盘上有不同版本。请选择要保留的内容；系统不会自动覆盖。"));
    panel.append(create("p", "conflict-values", `本地草稿 · ${ratingSummary(context.records[id])}`), create("p", "conflict-values", `磁盘版本 r${revisionOf(remote)} · ${ratingSummary(remote)}`));
    if (remote.note) panel.append(create("p", "", `磁盘备注：${remote.note}`));
    const keep = create("button", "", "保留本地，写入新版本"); keep.type = "button";
    keep.addEventListener("click", () => {
      const revision = revisionOf(context.conflicts[id]);
      context.server[id] = { ...context.conflicts[id] };
      context.drafts[id] = { rating: cleanRating(context.records[id]), base_revision: revision, edited_at: new Date().toISOString() };
      context.records[id].revision = revision;
      delete context.conflicts[id]; context.statuses[id] = "pending"; backup(context); updateRatingStatus(); enqueueSave(context, id);
    });
    const useDisk = create("button", "", "改用磁盘版本"); useDisk.type = "button";
    useDisk.addEventListener("click", () => {
      const remoteRecord = { ...context.conflicts[id] }; context.server[id] = remoteRecord; context.records[id] = { ...remoteRecord };
      delete context.conflicts[id]; delete context.drafts[id]; context.statuses[id] = "saved"; backup(context); renderRatings(); updateProgress(); toast("已采用磁盘版本。");
    });
    panel.append(keep, useDisk);
  }
  function updateRatingStatus() {
    if (!context) return;
    const id = pages[pageIndex].id;
    const record = context.records[id] || emptyRating();
    const state = context.statuses[id] || (isFile ? "browser" : "empty");
    const messages = { empty: "尚未评分 · 改动将自动写入磁盘", saved: "已保存到磁盘", pending: "浏览器草稿已备份 · 等待存盘", saving: "正在保存到磁盘…", failed: "存盘失败 · 浏览器草稿已保留", browser: isFile ? "仅浏览器草稿 · 未写入文件" : "浏览器备份 · 尚未核对磁盘", conflict: "版本冲突 · 本地草稿已保留" };
    $("save-status").dataset.state = state;
    $("save-message").textContent = messages[state] || messages.empty;
    if (!localStorageAvailable && ["pending", "failed", "browser", "conflict"].includes(state)) $("save-message").textContent = `${state === "conflict" ? "版本冲突" : "尚未存盘"} · 仅当前页面内存，请导出`;
    $("retry-save").hidden = isFile || (context.sessionLoaded && !["failed", "browser"].includes(state));
    $("retry-save").textContent = context.drafts[id] ? "重试保存" : "重新连接";
    $("note-length").textContent = `${record.note.length} / 10000`;
    const missing = scoreKeys.filter((key) => record[key] === null).length;
    $("completion-message").textContent = complete(record) ? "三维已评分，可继续下一页。" : `还有 ${missing} 个维度未评；允许稍后补充。`;
    renderConflict(id);
  }
  function buildRules() {
    const body = $("rules-content");
    body.append(create("p", "", "逐维选择 1–4 分；三维均已评分即计为完成，备注选填。初始“未评”不代表 1 分，尚未核对时可保留草稿。"));
    rubric.forEach((dimension, index) => {
      const section = create("section", "rule-section"); section.append(create("h3", "", `D${index + 1} · ${dimension.name}`));
      section.append(create("p", "rule-definition", `${dimension.scope} ${dimension.definition}`));
      dimension.anchors.forEach((anchor, number) => { const row = create("div", "rule-anchor"); row.append(create("strong", "", number + 1), create("span", "", anchor)); section.append(row); });
      body.append(section);
    });
    const note = create("div", "rule-note");
    note.append(create("p", "", "分别判断证据是否准确、证据是否支持回答、回答是否覆盖问题。同一错误不自动连扣三维；每项扣分须有对应依据。例如真实文献被反向解读主要影响 D2，只有遗漏必要正确内容时才另影响 D3。"));
    note.append(create("p", "", "缺少引用主要影响 D2，不直接证明事实虚构。无法核实证据真实性时可暂留 D1 未评并备注；区分人体与模型、关联与干预因果。参考得分点允许等效答案，不机械数条目。"));
    note.append(create("p", "", "建议备注写明错误片段、核对来源和受影响维度。技术无输出或无法评价时保留未评并说明，不强行赋分。"));
    body.append(note);
  }
  function renderReferencePoints(page) {
    const body = $("points-content");
    $("points-question-id").textContent = page.question_id;
    if (body.dataset.questionId === page.question_id) return;
    body.dataset.questionId = page.question_id;
    body.replaceChildren();
    const reference = page.reference_points;
    const bilingual = (en, zh, className) => {
      const block = create("div", className);
      if (en) { const original = create("div", "point-en"); original.lang = "en"; markdown(original, en); block.append(original); }
      if (zh) { const translated = create("div", "translation point-translation"); translated.lang = "zh-CN"; markdown(translated, zh); block.append(translated); }
      return block;
    };
    if (!reference || !Array.isArray(reference.points) || !reference.points.length) {
      body.append(create("p", "empty-state", "本题参考得分点尚未载入。"));
    } else {
      body.append(create("p", "evidence-intro", "以下为代表性参照：认可有可靠证据的等效答案，不要求命中全部实例，不按条数机械计分。"));
      if (reference.intro_en || reference.intro_zh) body.append(bilingual(reference.intro_en, reference.intro_zh, "points-intro"));
      const list = create("ol", "reference-point-list");
      for (const point of reference.points) {
        const item = create("li", "reference-point"); item.append(bilingual(point.en, point.zh, "reference-point-body")); list.append(item);
      }
      body.append(list);
      if (reference.boundary_en || reference.boundary_zh) {
        const boundary = create("section", "points-boundary"); boundary.append(create("h3", "", "评价边界"), bilingual(reference.boundary_en, reference.boundary_zh, "")); body.append(boundary);
      }
    }
    body.scrollTop = 0;
    positionFloating("points");
  }
  function setFloatingOpen(key, open) {
    ui[`${key}Open`] = open; $(`${key}-window`).hidden = !open;
    $(`open-${key}`).setAttribute("aria-expanded", String(open));
    persistUi();
    if (open) {
      for (const other of ["rules", "points"]) $(`${other}-window`).style.zIndex = other === key ? "61" : "60";
      positionFloating(key); $(`${key}-content`).focus({ preventScroll: true });
    }
  }
  function positionFloating(key) {
    const panel = $(`${key}-window`);
    if (panel.hidden || ui[`${key}X`] === null || ui[`${key}Y`] === null) return;
    const rect = panel.getBoundingClientRect();
    ui[`${key}X`] = Math.min(Math.max(8, ui[`${key}X`]), Math.max(8, innerWidth - rect.width - 8));
    ui[`${key}Y`] = Math.min(Math.max(8, ui[`${key}Y`]), Math.max(8, innerHeight - rect.height - 8));
    panel.style.left = `${ui[`${key}X`]}px`; panel.style.top = `${ui[`${key}Y`]}px`; panel.style.right = "auto"; panel.style.bottom = "auto";
  }
  function setupFloating(key) {
    const panel = $(`${key}-window`);
    panel.hidden = !ui[`${key}Open`];
    $(`open-${key}`).setAttribute("aria-expanded", String(ui[`${key}Open`]));
    $(`pin-${key}`).setAttribute("aria-pressed", String(ui[`${key}Pinned`])); $(`pin-${key}`).textContent = ui[`${key}Pinned`] ? "已固定" : "固定";
    $(`open-${key}`).addEventListener("click", () => setFloatingOpen(key, !ui[`${key}Open`]));
    if ($(`open-${key}-inline`)) $(`open-${key}-inline`).addEventListener("click", () => setFloatingOpen(key, true));
    $(`close-${key}`).addEventListener("click", () => setFloatingOpen(key, false));
    $(`pin-${key}`).addEventListener("click", () => { ui[`${key}Pinned`] = !ui[`${key}Pinned`]; $(`pin-${key}`).setAttribute("aria-pressed", String(ui[`${key}Pinned`])); $(`pin-${key}`).textContent = ui[`${key}Pinned`] ? "已固定" : "固定"; persistUi(); });
    panel.addEventListener("pointerdown", () => { for (const other of ["rules", "points"]) $(`${other}-window`).style.zIndex = other === key ? "61" : "60"; });
    const handle = $(`${key}-drag-handle`);
    let drag = null;
    handle.addEventListener("pointerdown", (event) => {
      if (event.target.closest("button") || event.button !== 0) return;
      const rect = panel.getBoundingClientRect(); drag = { x: event.clientX - rect.left, y: event.clientY - rect.top }; handle.setPointerCapture(event.pointerId); event.preventDefault();
    });
    handle.addEventListener("pointermove", (event) => { if (!drag) return; ui[`${key}X`] = event.clientX - drag.x; ui[`${key}Y`] = event.clientY - drag.y; positionFloating(key); });
    const stop = () => { if (!drag) return; drag = null; persistUi(); };
    handle.addEventListener("pointerup", stop); handle.addEventListener("pointercancel", stop);
    window.addEventListener("resize", () => positionFloating(key));
    panel.addEventListener("keydown", (event) => { if (event.key === "Escape") { setFloatingOpen(key, false); $(`open-${key}`).focus(); } });
    positionFloating(key);
  }
  function exportRecords(format) {
    if (!context) return;
    backup(context);
    const now = new Date().toISOString();
    const records = Object.fromEntries(pages.filter((page) => context.records[page.id]).map((page) => [page.id, context.records[page.id]]));
    let contents;
    if (format === "json") {
      contents = JSON.stringify({ dataset_id: data.dataset_id, rubric_version: data.rubric_version, expert_id: context.expert, records, updated_at: now, export_status: { exported_at: now, mode: isFile ? "browser-only" : "local-server", unsaved_page_ids: Object.keys(context.drafts), disk_verified: context.connected && context.sessionLoaded, session_loaded: context.sessionLoaded, states: context.statuses } }, null, 2);
    } else {
      const headers = ["dataset_id", "rubric_version", "expert_id", "page_id", "question_id", ...scoreKeys, "note", "revision", "updated_at", "complete", "save_state"];
      const csvCell = (value) => `"${String(value ?? "").replace(/"/g, '""')}"`;
      const rows = pages.map((page) => {
        const record = context.records[page.id] || emptyRating();
        return [data.dataset_id, data.rubric_version, context.expert, page.id, page.question_id, ...scoreKeys.map((key) => record[key]), record.note, record.revision ?? 0, record.updated_at || "", complete(record), context.statuses[page.id] || "unrated"].map(csvCell).join(",");
      });
      contents = "\ufeff" + [headers.join(","), ...rows].join("\r\n");
    }
    const blob = new Blob([contents], { type: format === "json" ? "application/json;charset=utf-8" : "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob); const link = create("a"); link.href = url; link.download = `expert-review_${context.expert}_${now.replace(/[:.]/g, "-")}.${format}`; document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 2000);
    toast(`已导出当前评阅者 ${context.expert} 的 ${format.toUpperCase()}${Object.keys(context.drafts).length ? "（包含未存盘草稿）" : ""}。`);
  }
  buildScores(); buildRules(); setupFloating("rules"); setupFloating("points");
  $("previous-page").addEventListener("click", () => navigate(pageIndex - 1));
  $("next-page").addEventListener("click", () => navigate(pageIndex + 1));
  $("rating-form").addEventListener("submit", (event) => event.preventDefault());
  $("rating-note").addEventListener("input", markChanged);
  $("export-json").addEventListener("click", () => exportRecords("json"));
  $("export-csv").addEventListener("click", () => exportRecords("csv"));
  $("retry-save").addEventListener("click", async () => {
    if (busy || !context) return;
    setBusy(true);
    try { await flush(); if (!context.sessionLoaded || !context.connected) await loadReviewer(context.expert); }
    finally { setBusy(false); }
  });
  $("expert-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    if (busy) return;
    const expert = $("expert-id").value.trim();
    if (!/^[A-Za-z0-9_-]{1,40}$/.test(expert)) { toast("评阅者标识须为 1–40 个字母、数字、下划线或短横线。"); return; }
    if (expert === context?.expert) { toast(`当前评阅者为 ${expert}。`); return; }
    setBusy(true);
    try { await flush(); await loadReviewer(expert); toast(`已切换到评阅者 ${expert}，评分单独保存。`); }
    finally { setBusy(false); }
  });
  window.addEventListener("beforeunload", (event) => {
    backup(context);
    if (!isFile && context && Object.keys(context.drafts).length) { event.preventDefault(); event.returnValue = ""; }
  });
  document.addEventListener("visibilitychange", () => { if (document.hidden && context) { backup(context); flush(); } });
  window.addEventListener("online", () => { if (context && !isFile) flush(); });
  // Cross-tab updates never overwrite the current draft; the next PUT is protected by revision checks.
  window.addEventListener("storage", (event) => {
    if (context && event.key === storagePrefix + `reviewer:${context.expert}` && event.newValue) toast("同一评阅者的浏览器备份在另一窗口有更新；当前输入已保留，存盘时会核对版本。");
  });
  setBusy(true);
  loadReviewer(ui.expert).catch(() => { toast("评阅会话载入失败，请保留页面并重试。"); }).finally(() => setBusy(false));
})();
