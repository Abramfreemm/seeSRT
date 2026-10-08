const state = {
  episodes: [],         // 台词库
  srtFilenames: {},     // ep_no -> 原始文件名
  current: null,        // 当前选中的集
  groups: [],           // 当前集的纠错组
  report: null,         // 当前集的完整度报告
  processed: {},        // ep_no -> groups（已处理集缓存）
  reports: {},          // ep_no -> report
};

const $ = (sel) => document.querySelector(sel);

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

async function api(url, body) {
  const res = await fetch(url, body ? {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  } : undefined);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || res.statusText);
  }
  return res.json();
}

async function uploadFile(url, file) {
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch(url, { method: "POST", body: fd });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || res.statusText);
  }
  return res.json();
}

function setStep(n) {
  document.querySelectorAll(".step").forEach((el) => {
    el.classList.toggle("active", Number(el.dataset.step) <= n);
  });
}

function renderDiffLine(ops, side, lang) {
  const sep = lang === "zh" ? "" : " ";
  let html = "";
  for (const op of ops) {
    if (side === "old") {
      if (op.op === "insert") continue;
      const cls = (op.op === "replace" || op.op === "delete") ? "del" : "";
      html += cls ? `<span class="${cls}">${escapeHtml(op.old)}</span>${sep}` : `${escapeHtml(op.old)}${sep}`;
    } else {
      if (op.op === "delete") continue;
      const cls = (op.op === "replace" || op.op === "insert") ? "ins" : "";
      html += cls ? `<span class="${cls}">${escapeHtml(op.new)}</span>${sep}` : `${escapeHtml(op.new)}${sep}`;
    }
  }
  return html;
}

function updateStickyOffsets() {
  // 精确测量顶栏与台词库面板高度，让台词库、审查区工具栏在滚动时依次吸顶固定
  const topbar = document.querySelector(".topbar");
  const libPanel = document.querySelector(".lib-panel");
  const toolbar = document.querySelector(".review-toolbar");
  if (!topbar || !libPanel || !toolbar) return;
  const topbarH = topbar.offsetHeight;
  libPanel.style.top = topbarH + "px";
  toolbar.style.top = (topbarH + libPanel.offsetHeight) + "px";
}

function renderLib() {
  const lib = $("#lib");
  if (!state.episodes.length) {
    lib.innerHTML = '<span class="muted">上传剧本后显示台词库</span>';
    updateStickyOffsets();
    return;
  }
  lib.innerHTML = state.episodes.map((ep) => `
    <div class="lib-ep">
      <div class="ep-title">第 ${ep.episode_no} 集</div>
      ${ep.scenes.map((sc) => `
        <div class="lib-scene">
          <div class="sc-title">场景 ${sc.scene_no}</div>
          ${sc.dialogues.map((d) => `
            <div class="lib-dlg" data-copy="${escapeHtml(d.text_en || d.text_zh)}">
              <div class="zh">${escapeHtml(d.text_zh || '')}</div>
              <div class="en">${escapeHtml(d.text_en || '')}</div>
            </div>`).join("")}
        </div>`).join("")}
    </div>`).join("");
  updateStickyOffsets();
}

function updateEpisodeSelect() {
  const sel = $("#episode-select");
  const eps = state.episodes.map((e) => e.episode_no);
  const hasSrt = eps.filter((n) => state.srtFilenames[n]);
  const prev = state.current;
  sel.innerHTML = '<option value="">-- 选择集 --</option>' +
    hasSrt.map((n) => `<option value="${n}">第 ${n} 集 (${state.srtFilenames[n]})</option>`).join("");
  sel.disabled = hasSrt.length === 0;
  $("#process-btn").disabled = hasSrt.length === 0;
  $("#batch-btn").disabled = hasSrt.length === 0;
  if (prev && hasSrt.includes(prev)) sel.value = String(prev);
}

function renderGroups() {
  const box = $("#groups");
  updateReviewAllBtn();
  if (!state.current) {
    box.innerHTML = '<span class="muted">选择集后在此审查</span>';
    $("#export-btn").hidden = true;
    $("#stats").hidden = true;
    return;
  }
  if (!state.groups.length) {
    box.innerHTML = '<span class="muted">该集尚未处理，点击「对齐 + 纠错」或「批量处理」</span>';
    $("#export-btn").hidden = true;
    return;
  }
  box.innerHTML = state.groups.map((g) => {
    let badge, cls;
    if (g.is_sound_marker) {
      badge = '<span class="badge sound">音效标记 · 导出时删除</span>';
      cls = "sound";
    } else if (g.matched) {
      badge = '<span class="badge ok">命中</span>';
      cls = "";
    } else if (g.reviewed) {
      badge = '<span class="badge reviewed">已复核</span>';
      cls = "reviewed";
    } else {
      badge = '<span class="badge unmatched">未命中 · 需复核</span>';
      cls = "unmatched";
    }
    const reviewBtn = (!g.matched && !g.is_sound_marker)
      ? `<button class="btn small ${g.reviewed ? "" : "primary"}" data-act="review">${g.reviewed ? "取消复核" : "确认复核"}</button>`
      : "";
    const splitHtml = (g.split || []).map((s) =>
      `<div class="split-item"><span class="tt">${s.start} → ${s.end}</span>${escapeHtml(s.text).replace(/\n/g, "<br>")}</div>`
    ).join("");
    const lang = g.lang || "en";
    const splitHint = lang === "zh" ? "每行 ≤ 12 字 / 每片段 ≤ 2 行" : "每行 ≤ 23 字符 / 每片段 ≤ 2 行";
    return `
      <div class="group ${cls}" data-id="${g.id}">
        <div class="group-head">${badge}
          <span class="time">${g.start} → ${g.end}</span>
        </div>
        <div class="diff-line"><span class="lbl">原文</span><span class="txt">${renderDiffLine(g.diff, "old", lang)}</span></div>
        <div class="diff-line"><span class="lbl">修正</span><span class="txt">${renderDiffLine(g.diff, "new", lang)}</span></div>
        <div class="group-actions">
          <button class="btn small" data-act="edit">编辑</button>
          <button class="btn small" data-act="undo" ${g.corrected === g.original ? "disabled" : ""}>改回原文</button>
          ${reviewBtn}
        </div>
        <div class="split-preview">
          <h4>拆分预览（${splitHint}）</h4>
          ${splitHtml}
        </div>
      </div>`;
  }).join("");
}

function renderReport() {
  const el = $("#report");
  const stats = $("#stats");
  if (!state.report) {
    el.hidden = true;
    stats.hidden = true;
    return;
  }
  stats.hidden = false;
  stats.innerHTML = `共 <b>${state.groups.length}</b> 组 · 命中 <b>${state.groups.filter(g => g.matched).length}</b> · <span class="unmatched">未命中 <b>${state.groups.filter(g => !g.matched).length}</b></span>`;

  const r = state.report;
  const missingHtml = r.missing_dialogues.map((t) => `<li>${escapeHtml(t)}</li>`).join("");
  const extraHtml = r.extra_segments.map((t) => `<li>${escapeHtml(t)}</li>`).join("");
  el.hidden = false;
  el.innerHTML = `
    <h3>完整度报告</h3>
    <div class="report-stats">
      <span>剧本台词 <b>${r.total_dialogues}</b></span>
      <span class="ok">命中 <b>${r.matched_dialogues}</b></span>
      <span class="unmatched">缺失 <b>${r.missing_count}</b></span>
      <span class="unmatched">多余片段 <b>${r.extra_count}</b></span>
      <span>音效标记 <b>${r.sound_markers}</b></span>
    </div>
    <details class="report-sec">
      <summary>缺失台词（${r.missing_count}）</summary>
      <ol class="report-list">${missingHtml || '<li class="muted">无</li>'}</ol>
    </details>
    <details class="report-sec">
      <summary>多余 / 需复核片段（${r.extra_count}）</summary>
      <ol class="report-list">${extraHtml || '<li class="muted">无</li>'}</ol>
    </details>`;
}

function bindGroupEvents() {
  $("#groups").querySelectorAll(".group").forEach((card) => {
    const id = Number(card.dataset.id);
    card.querySelector('[data-act="edit"]').addEventListener("click", () => openEditor(card, id));
    card.querySelector('[data-act="undo"]').addEventListener("click", async () => {
      const g = state.groups[id];
      await saveEdit(id, g.original);
    });
    const reviewBtn = card.querySelector('[data-act="review"]');
    if (reviewBtn) {
      reviewBtn.addEventListener("click", async () => {
        const g = state.groups[id];
        await toggleReview(id, !g.reviewed);
      });
    }
  });
}

function openEditor(card, id) {
  const g = state.groups[id];
  if (card.querySelector(".editor")) return;
  const ta = document.createElement("textarea");
  ta.className = "editor";
  ta.rows = 3;
  ta.value = g.corrected;
  const save = document.createElement("button");
  save.className = "btn small primary";
  save.textContent = "保存";
  const cancel = document.createElement("button");
  cancel.className = "btn small";
  cancel.textContent = "取消";
  const wrap = document.createElement("div");
  wrap.className = "group-actions";
  wrap.append(save, cancel);
  card.appendChild(ta);
  card.appendChild(wrap);
  ta.focus();
  save.addEventListener("click", async () => {
    await saveEdit(id, ta.value);
  });
  cancel.addEventListener("click", () => {
    renderGroups();
    bindGroupEvents();
  });
}

async function saveEdit(id, text) {
  try {
    const updated = await api("/api/edit", {
      episode_no: state.current,
      group_id: id,
      text,
    });
    const g = state.groups.find((x) => x.id === id);
    if (g) Object.assign(g, updated);
    state.processed[state.current] = state.groups;
    renderGroups();
    bindGroupEvents();
  } catch (err) {
    alert(err.message);
  }
}

async function toggleReview(id, reviewed) {
  try {
    const updated = await api("/api/review", {
      episode_no: state.current,
      group_id: id,
      reviewed,
    });
    const g = state.groups.find((x) => x.id === id);
    if (g) Object.assign(g, updated);
    state.processed[state.current] = state.groups;
    renderGroups();
    bindGroupEvents();
  } catch (err) {
    alert(err.message);
  }
}

function updateReviewAllBtn() {
  const btn = $("#review-all-btn");
  const unReviewed = (state.groups || []).filter(
    (g) => !g.matched && !g.is_sound_marker && !g.reviewed
  ).length;
  btn.hidden = unReviewed === 0;
  btn.textContent = `复核全部未命中 (${unReviewed})`;
}

async function reviewAll() {
  if (!state.current) return;
  try {
    const r = await api("/api/review_batch", { episode_no: state.current });
    for (const g of state.groups) {
      if (!g.matched && !g.is_sound_marker) g.reviewed = true;
    }
    state.processed[state.current] = state.groups;
    renderGroups();
    bindGroupEvents();
    alert(`已复核 ${r.reviewed} 个未命中片段`);
  } catch (err) {
    alert(err.message);
  }
}

function jumpToEpisode() {
  const v = $("#ep-jump-input").value.trim();
  if (!v) return;
  const ep = Number(v);
  if (!Number.isInteger(ep) || ep <= 0) {
    $("#ep-jump-hint").textContent = "请输入正整数集数";
    return;
  }
  const exists = state.episodes.some((e) => e.episode_no === ep);
  if (!exists) {
    $("#ep-jump-hint").textContent = `未找到第 ${ep} 集`;
    return;
  }
  if (state.srtFilenames[ep]) {
    $("#episode-select").value = String(ep);
  }
  selectEpisode(ep);
  if (state.processed[ep]) {
    $("#ep-jump-hint").textContent = "";
  } else {
    $("#ep-jump-hint").textContent = `第 ${ep} 集尚未处理，请先「对齐 + 纠错」`;
  }
}

function isDesktop() {
  return !!(window.pywebview && window.pywebview.api && window.pywebview.api.save_text);
}

function arrayBufferToBase64(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk));
  }
  return btoa(binary);
}

async function exportSrt() {
  try {
    const data = await api("/api/export", { episode_no: state.current });
    if (isDesktop()) {
      const r = await window.pywebview.api.save_text(data.filename, data.srt);
      if (r && !r.ok && !r.canceled) alert("保存失败: " + r.error);
      return;
    }
    const blob = new Blob([data.srt], { type: "text/plain;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = data.filename;
    a.click();
    URL.revokeObjectURL(a.href);
  } catch (err) {
    alert(err.message);
  }
}

function updateBatchExport() {
  $("#export-batch-btn").hidden = Object.keys(state.processed).length === 0;
}

async function exportBatch() {
  try {
    const res = await fetch("/api/export_batch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || res.statusText);
    }
    const blob = await res.blob();
    if (isDesktop()) {
      const buf = await blob.arrayBuffer();
      const b64 = arrayBufferToBase64(buf);
      const r = await window.pywebview.api.save_bytes("seeSRT_export.zip", b64);
      if (r && !r.ok && !r.canceled) alert("保存失败: " + r.error);
      return;
    }
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "seeSRT_export.zip";
    a.click();
    URL.revokeObjectURL(a.href);
  } catch (err) {
    alert(err.message);
  }
}

async function resetAll() {
  if (!confirm("确定恢复初始状态？将清空已上传的剧本、SRT 与全部处理结果。")) return;
  try {
    await api("/api/reset", {});
  } catch (err) {
    alert(err.message);
    return;
  }
  state.episodes = [];
  state.srtFilenames = {};
  state.current = null;
  state.groups = [];
  state.report = null;
  state.processed = {};
  state.reports = {};
  $("#script-status").textContent = "未上传";
  $("#srt-status").textContent = "未上传";
  $("#script-input").value = "";
  $("#srt-input").value = "";
  $("#review-hint").textContent = "";
  $("#ep-jump-input").value = "";
  $("#ep-jump-hint").textContent = "";
  renderLib();
  updateEpisodeSelect();
  updateBatchExport();
  renderGroups();
  renderReport();
  setStep(0);
}

function selectEpisode(ep) {
  state.current = ep;
  if (!ep) {
    state.groups = [];
    state.report = null;
    renderGroups();
    renderReport();
    return;
  }
  state.groups = state.processed[ep] || [];
  state.report = state.reports[ep] || null;
  renderGroups();
  renderReport();
  if (state.processed[ep]) {
    $("#export-btn").hidden = false;
    $("#review-hint").textContent = `第 ${ep} 集`;
    setStep(3);
  } else {
    $("#export-btn").hidden = true;
    $("#review-hint").textContent = "";
  }
}

async function restoreState() {
  const s = await api("/api/state");
  state.episodes = s.episodes || [];
  state.srtFilenames = {};
  for (const [k, v] of Object.entries(s.srts || {})) state.srtFilenames[Number(k)] = v;
  state.processed = {};
  state.reports = {};
  for (const [k, groups] of Object.entries(s.groups || {})) state.processed[Number(k)] = groups;
  for (const [k, report] of Object.entries(s.reports || {})) state.reports[Number(k)] = report;

  renderLib();
  updateEpisodeSelect();
  updateBatchExport();
  if (state.episodes.length) setStep(1);
  if (Object.keys(state.srtFilenames).length) setStep(2);

  const firstProcessed = Object.keys(state.processed).map(Number)[0];
  if (firstProcessed) {
    const sel = $("#episode-select");
    sel.value = String(firstProcessed);
    selectEpisode(firstProcessed);
  }
}

function bindGlobal() {
  $("#script-input").addEventListener("change", async (e) => {
    const f = e.target.files[0];
    if (!f) return;
    $("#script-status").textContent = "解析中…";
    try {
      const r = await uploadFile("/api/script", f);
      state.episodes = r.episodes;
      state.srtFilenames = {};
      state.processed = {};
      state.reports = {};
      state.groups = [];
      state.report = null;
      state.current = null;
      if (r.count === 0) {
        $("#script-status").textContent = "解析到 0 集：请确认剧本含「第X集」标题与台词";
      } else if (r.total_en_lines) {
        $("#script-status").textContent = `已解析 ${r.count} 集 · ${r.total_en_lines} 句英文台词`;
      } else if (r.total_zh_lines) {
        $("#script-status").textContent = `已解析 ${r.count} 集 · ${r.total_zh_lines} 句中文台词`;
      } else {
        $("#script-status").textContent = `已解析 ${r.count} 集，但未提取到台词，请确认剧本格式`;
      }
      setStep(1);
      renderLib();
      updateEpisodeSelect();
      updateBatchExport();
      renderGroups();
      renderReport();
    } catch (err) {
      $("#script-status").textContent = "解析失败：" + err.message;
    }
  });

  $("#srt-input").addEventListener("change", async (e) => {
    const files = [...e.target.files];
    if (!files.length) return;
    $("#srt-status").textContent = "解析中…";
    try {
      for (const f of files) {
        const r = await uploadFile("/api/srt", f);
        state.srtFilenames[r.episode_no] = f.name;
        delete state.processed[r.episode_no];
        delete state.reports[r.episode_no];
      }
      const names = Object.values(state.srtFilenames).join(", ");
      $("#srt-status").textContent = `已上传 ${files.length} 个：${names}`;
      setStep(2);
      updateEpisodeSelect();
    } catch (err) {
      $("#srt-status").textContent = "解析失败：" + err.message;
    }
  });

  $("#episode-select").addEventListener("change", (e) => {
    selectEpisode(Number(e.target.value));
  });

  $("#process-btn").addEventListener("click", async () => {
    const ep = Number($("#episode-select").value);
    if (!ep) return;
    try {
      const r = await api("/api/process", { episode_no: ep });
      state.current = ep;
      state.groups = r.groups;
      state.report = r.report;
      state.processed[ep] = r.groups;
      state.reports[ep] = r.report;
      renderGroups();
      bindGroupEvents();
      renderReport();
      updateBatchExport();
      $("#review-hint").textContent = `第 ${ep} 集`;
      setStep(3);
      $("#export-btn").hidden = false;
    } catch (err) {
      alert(err.message);
    }
  });

  $("#batch-btn").addEventListener("click", async () => {
    try {
      const r = await api("/api/process_batch", {});
      for (const res of r.results) {
        state.reports[res.episode_no] = res.report;
      }
      // 批量后刷新已处理集的 groups 缓存
      const s = await api("/api/state");
      for (const [k, groups] of Object.entries(s.groups || {})) {
        state.processed[Number(k)] = groups;
      }
      const ep = Number($("#episode-select").value) || Object.keys(state.processed).map(Number)[0];
      if (ep) {
        const sel = $("#episode-select");
        sel.value = String(ep);
        selectEpisode(ep);
      }
      updateBatchExport();
      setStep(3);
      alert(`批量处理完成：${r.results.length} 集`);
    } catch (err) {
      alert(err.message);
    }
  });

  $("#export-btn").addEventListener("click", exportSrt);
  $("#export-batch-btn").addEventListener("click", exportBatch);
  $("#reset-btn").addEventListener("click", resetAll);
  $("#ep-jump-btn").addEventListener("click", jumpToEpisode);
  $("#ep-jump-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") jumpToEpisode();
  });
  $("#review-all-btn").addEventListener("click", reviewAll);

  $("#lib").addEventListener("click", (e) => {
    const dlg = e.target.closest(".lib-dlg");
    if (!dlg) return;
    const copy = dlg.dataset.copy;
    if (!copy) return;
    navigator.clipboard.writeText(copy).then(() => {
      const orig = dlg.style.background;
      dlg.style.background = "#d8f0dc";
      setTimeout(() => { dlg.style.background = orig; }, 600);
    });
  });
}

bindGlobal();
updateStickyOffsets();
window.addEventListener("resize", updateStickyOffsets);
restoreState().catch(() => {});
