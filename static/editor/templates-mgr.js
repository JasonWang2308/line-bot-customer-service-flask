/*
 * editor/templates-mgr.js — 公版管理頁
 *
 * 定位:
 *   公版頁 (#templates-pane) 的列表渲染與 CRUD 操作。
 *   負責把 templates 全域 (來自 api.js) 渲染為列表，並處理新增 / 編輯 / 刪除。
 *   寫入由 api.js 的 fetch 完成。
 *
 * 包含單元 (units):
 *   renderTplList            渲染左側公版列表
 *   fillTplForm(t)           把公版資料填到右側表單
 *   newTemplate              清空表單準備新增
 *   saveTemplate / deleteTemplate   後端 CRUD
 */

function renderTplList() {
  const ul = $("#tpl-list");
  if (!ul) return;
  ul.innerHTML = "";

  if (templates.length === 0) {
    const li = document.createElement("li");
    li.textContent = "尚無公版，請按上方「＋ 新增公版」";
    li.style.color = "#999";
    li.style.padding = "12px";
    li.style.fontSize = "13px";
    ul.appendChild(li);
    return;
  }

  templates.forEach((t) => {
    const li = document.createElement("li");
    li.className = "tpl-item";
    if (t.id === selectedTplId) li.classList.add("selected");

    const idEl = document.createElement("div");
    idEl.className = "tpl-item-id";
    idEl.textContent = t.id;

    const nameEl = document.createElement("div");
    nameEl.className = "tpl-item-name";
    nameEl.textContent = t.name || "(未命名)";

    li.appendChild(idEl);
    li.appendChild(nameEl);

    if (t.description) {
      const descEl = document.createElement("div");
      descEl.className = "tpl-item-desc";
      descEl.textContent = t.description;
      li.appendChild(descEl);
    }

    li.onclick = () => {
      if (tplDirty && !confirm("公版表單有未儲存的修改，捨棄?")) return;
      selectedTplId = t.id;
      renderTplList();
      fillTplForm(t);
      tplDirty = false;
    };
    ul.appendChild(li);
  });
}

function fillTplForm(t) {
  $("#tpl-id").value = t.id || "";
  $("#tpl-id").disabled = !!t.id; // 編輯既有 → 鎖住 id
  $("#tpl-name").value = t.name || "";
  $("#tpl-description").value = t.description || "";
  $("#tpl-text").value = t.text || "";
}

function newTemplate() {
  if (tplDirty && !confirm("公版表單有未儲存的修改，捨棄?")) return;
  selectedTplId = null;
  tplDirty = false;
  fillTplForm({});
  $("#tpl-id").disabled = false;
  $("#tpl-id").focus();
  renderTplList();
  setStatus("輸入新公版資訊後按「儲存公版」");
}

async function saveTemplate() {
  const tpl = {
    id: $("#tpl-id").value.trim(),
    name: $("#tpl-name").value.trim(),
    description: $("#tpl-description").value.trim(),
    text: $("#tpl-text").value,
  };
  if (!tpl.id) {
    alert("id 不可為空");
    return;
  }
  if (!tpl.name) {
    alert("name 不可為空");
    return;
  }
  try {
    const r = await api("POST", "/api/templates", tpl);
    selectedTplId = tpl.id;
    tplDirty = false;
    await loadTemplates();
    setStatus(`公版已${r.result === "created" ? "建立" : "更新"}：${tpl.name}`);
    showToast(`公版${r.result === "created" ? "建立" : "更新"}成功`, "success");
  } catch (e) {
    setStatus(`公版儲存失敗：${e.message}`);
    showToast(`公版儲存失敗：${e.message}`, "error");
  }
}

async function deleteTemplate() {
  const id = $("#tpl-id").value.trim();
  if (!id) {
    alert("沒有選取要刪除的公版");
    return;
  }
  if (!confirm(`確定刪除公版「${id}」?\n\n注意：已套用此公版的節點不會受影響（公版套用後是獨立內容）。`)) return;
  try {
    await api("DELETE", `/api/templates/${encodeURIComponent(id)}`);
    selectedTplId = null;
    tplDirty = false;
    fillTplForm({});
    $("#tpl-id").disabled = false;
    await loadTemplates();
    setStatus(`已刪除公版：${id}`);
    showToast("公版已刪除", "success");
  } catch (e) {
    setStatus(`刪除失敗：${e.message}`);
    showToast(`刪除失敗：${e.message}`, "error");
  }
}
