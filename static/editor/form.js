/*
 * editor/form.js — 右側節點屬性表單
 *
 * 定位:
 *   把 selectedPath 對應節點的屬性 (label / 類型 / description / text / action)
 *   渲染到表單欄位，並提供「套用變更」把表單值寫回 menuData。
 *   也包含「套用公版」的便利功能 (公版資料來自 api.js 的 templates 全域)。
 *
 * 包含單元 (units):
 *   renderForm                依 selectedPath 填表單
 *   updateFieldStates         依目前類型 + action 啟用/禁用對應欄位
 *   currentKindRadio          目前選取的類型 radio 值
 *   applyChanges              表單值寫回節點 (含類型轉換確認)
 *   applyTemplateToForm       把選定公版內容套用到 #f-text
 */

function renderForm() {
  const node = getNode(selectedPath);
  $("#f-label").value = node.label || "";
  $("#f-desc").value = node.description || "";
  $("#f-text").value = node.text || "";
  $("#f-action").value = node.action || "";
  $("#f-phone").value = node.phone || "";
  $("#f-template").value = "";

  const kind = nodeKind(node);
  document.querySelectorAll('input[name="type"]').forEach((r) => {
    r.checked = r.value === kind;
  });
  updateFieldStates();
  fieldsDirty = false;
}

function updateFieldStates() {
  const kind = currentKindRadio();
  const sel = $("#f-action");
  const hasAction = sel && sel.value;

  $("#f-desc").disabled = kind !== "branch";
  $("#f-text").disabled = kind !== "leaf" || hasAction;

  // 套用公版只在 leaf / empty 啟用（套用後會切到 leaf）
  $("#f-template").disabled = kind === "branch" || hasAction;
  $("#btn-apply-tpl").disabled = kind === "branch" || hasAction;

  if (sel) {
    sel.disabled = kind === "branch";
    if (kind === "branch" && sel.value) {
      sel.value = "";
      fieldsDirty = true;
    }
  }

  // call_phone action 才顯示電話欄位
  const phoneGroup = $("#f-phone-group");
  if (phoneGroup) phoneGroup.hidden = sel?.value !== "call_phone";

  const hint = document.getElementById("f-action-hint");
  if (hint) {
    if (kind === "branch") {
      hint.textContent = "分支節點無法設定動作。";
      hint.className = "hint";
    } else if (hasAction) {
      hint.textContent = "已綁定動作；此節點的回覆內容將由程式邏輯接管。";
      hint.className = "hint warn";
    } else {
      hint.textContent = "設定後會覆蓋此節點的回覆內容，改由程式邏輯處理（例如收集留言）。";
      hint.className = "hint";
    }
  }
}

function currentKindRadio() {
  return document.querySelector('input[name="type"]:checked')?.value || "empty";
}

function applyChanges() {
  const node = getNode(selectedPath);
  const newLabel = $("#f-label").value.trim();
  if (!newLabel) {
    alert("標題不可為空");
    return;
  }

  const targetKind = currentKindRadio();
  const hadChildren = Array.isArray(node.children) && node.children.length > 0;

  if (hadChildren && targetKind !== "branch") {
    if (!confirm(`「${node.label}」目前有 ${node.children.length} 個子節點，切換類型會一併刪除子節點。確定?`)) return;
  }

  node.label = newLabel;

  if (targetKind === "branch") {
    const desc = $("#f-desc").value.trim();
    if (desc) node.description = desc;
    else delete node.description;
    delete node.text;
    delete node.action;
    if (!Array.isArray(node.children)) node.children = [];
  } else if (targetKind === "leaf") {
    const text = $("#f-text").value.trim();
    if (text) node.text = text;
    else delete node.text;
    delete node.description;
    delete node.children;
  } else {
    delete node.description;
    delete node.text;
    delete node.children;
  }

  if (targetKind !== "branch") {
    const action = $("#f-action").value;
    if (action) {
      node.action = action;
      // call_phone 必須帶 phone 欄位 (server 也會驗證, 這裡先擋避免無謂 round-trip)
      if (action === "call_phone") {
        const phone = $("#f-phone").value.trim();
        if (!phone) {
          alert("撥打電話 action 需要填入電話號碼");
          return;
        }
        node.phone = phone;
      } else {
        delete node.phone;
      }
    } else {
      delete node.action;
      delete node.phone;
    }
  } else {
    delete node.action;
    delete node.phone;
  }

  fieldsDirty = false;
  treeDirty = true;
  renderTree();
  renderForm();
  setStatus("已套用變更（記得按「儲存」寫回檔案）");
}

function applyTemplateToForm() {
  const tplId = $("#f-template").value;
  if (!tplId) {
    setStatus("請先選擇一個公版");
    return;
  }
  const tpl = templates.find((t) => t.id === tplId);
  if (!tpl) {
    setStatus("找不到該公版");
    return;
  }
  const cur = $("#f-text").value;
  if (cur && !confirm(`目前回覆內容已有文字，套用公版「${tpl.name}」會覆蓋原內容。確定?`)) return;

  // 切到 leaf 類型（公版只有 text 內容）
  const leafRadio = document.querySelector('input[name="type"][value="leaf"]');
  if (leafRadio) leafRadio.checked = true;
  $("#f-text").value = tpl.text || "";
  fieldsDirty = true;
  updateFieldStates();
  setStatus(`已套用公版「${tpl.name}」，記得「套用變更到此節點」並儲存`);
  showToast(`已套用「${tpl.name}」`, "success");
}
