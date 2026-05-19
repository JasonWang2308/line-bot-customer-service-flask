import json
from pathlib import Path

BASE = Path(__file__).parent / "Knowledge"

# ── 載入 dictionary ──────────────────────────────────────────
with open(BASE / "dictionary.json", encoding="utf-8") as f:
    DICTIONARY = json.load(f)

# ── 載入 rules ───────────────────────────────────────────────
with open(BASE / "rules.json", encoding="utf-8") as f:
    RULES_DATA = json.load(f)

# ── 載入 QA ──────────────────────────────────────────────────
with open(BASE / "qa.json", encoding="utf-8") as f:
    _all_qa = json.load(f)["qa"]

# ── Build term → id lookup (term + synonyms) ─────────────────
TERM_MAP: dict[str, str] = {}

for _dim_items in DICTIONARY["dimensions"].values():
    for item in _dim_items:
        TERM_MAP[item["term"]] = item["id"]
        for syn in item.get("synonyms", []):
            if syn not in TERM_MAP:
                TERM_MAP[syn] = item["id"]

# 由長到短排序，讓長詞優先匹配（避免「補正」蓋掉「補正清單」）
SORTED_TERMS = sorted(TERM_MAP.keys(), key=len, reverse=True)

ASK_ORDER   = RULES_DATA["ask_order"]
RULES       = RULES_DATA["rules"]
POST_ANSWER = RULES_DATA["post_answer"]

BACK_LABEL  = "回到上一層"
OTHER_LABEL = "其他"
OTHER_DIMS  = {"C", "A"}   # 只有服務項目和動作選單才出現「其他」


def _prev_resolved_dim(current_dim: str, resolved_ids: list[str]) -> str | None:
    """
    在 ask_order 中、current_dim 之前，找到最近一個已有選項被 resolved 的規則鍵。
    若沒有，則回傳 None（表示已在第一層，無法再回退）。
    """
    try:
        current_idx = ASK_ORDER.index(current_dim)
    except ValueError:
        return None
    resolved_set = set(resolved_ids)
    for i in range(current_idx - 1, -1, -1):
        prev_key = ASK_ORDER[i]
        if {opt["id"] for opt in RULES[prev_key]["options"]} & resolved_set:
            return prev_key
    return None

# ── QA 反向索引：tag → QA ID 集合（啟動時建立一次）─────────
QA_BY_ID:     dict[str, dict]      = {}
QA_TAG_INDEX: dict[str, set[str]]  = {}

for _qa in _all_qa:
    QA_BY_ID[_qa["id"]] = _qa
    for _tag in _qa["tags"]:
        QA_TAG_INDEX.setdefault(_tag, set()).add(_qa["id"])


# ── Parse ─────────────────────────────────────────────────────

def parse_input(text: str) -> list[str]:
    """
    Greedy longest-match: 長詞先匹配，匹配後遮蔽該位置，
    避免短詞（如「補正」）再度命中已被長詞（「補正清單」）涵蓋的位置。
    """
    found: dict[str, str] = {}   # id → 匹配到的詞
    remaining = text

    for term in SORTED_TERMS:
        if term in remaining:
            id_ = TERM_MAP[term]
            if id_ not in found or len(term) > len(found[id_]):
                found[id_] = term
            # 將已匹配位置遮蔽，防止較短的詞再度匹配同一段文字
            remaining = remaining.replace(term, "\x00" * len(term))

    return list(found.keys())


# ── Pending dims ──────────────────────────────────────────────

def compute_pending_dims(resolved_ids: list[str]) -> list[str]:
    """
    Walk ask_order and return rule keys that still need to be asked.

    A rule is SKIPPED when:
      - One of its option IDs is already in resolved_ids  (already answered)
      - Its condition dims ARE resolved but values don't match (rule doesn't apply)
      - Its condition dims are NOT yet resolved (will re-evaluate after they are)
    """
    resolved_set = set(resolved_ids)

    dim_resolved: dict[str, set] = {}
    for id_ in resolved_ids:
        dim_resolved.setdefault(id_[0], set()).add(id_)

    pending = []
    for rule_key in ASK_ORDER:
        rule = RULES[rule_key]
        option_ids = {opt["id"] for opt in rule["options"]}

        if option_ids & resolved_set:
            continue

        condition = rule.get("condition")

        if condition is None:
            pending.append(rule_key)
            continue

        all_evaluable = all(dim_resolved.get(cond_dim) for cond_dim in condition)
        if not all_evaluable:
            continue

        condition_met = all(
            bool(dim_resolved.get(cond_dim, set()) & set(cond_ids))
            for cond_dim, cond_ids in condition.items()
        )
        if condition_met:
            pending.append(rule_key)

    return pending


# ── Viable option filtering ───────────────────────────────────

def viable_options(rule: dict, resolved_ids: list[str]) -> list[dict]:
    """
    只保留「加入此選項後，還有至少一筆 QA 可能匹配」的選項。
    使用反向索引做集合交集，避免逐筆掃描全部 QA。
    """
    result = []
    resolved_set = set(resolved_ids)
    for opt in rule["options"]:
        test_set = resolved_set | {opt["id"]}
        candidates = None
        for tag in test_set:
            tag_set = QA_TAG_INDEX.get(tag, set())
            candidates = tag_set if candidates is None else candidates & tag_set
            if not candidates:
                break
        if candidates:
            result.append(opt)
    return result


# ── Option matching ───────────────────────────────────────────

def match_option_reply(text: str, rule_key: str) -> str | None:
    """Try to match user reply to one of the clarification options."""
    rule = RULES.get(rule_key)
    if not rule:
        return None
    for opt in rule["options"]:
        if opt["label"] in text or text.strip() == opt["label"]:
            return opt["id"]
    return None


# ── Conflict detection ───────────────────────────────────────


# 規則 key → 衝突時顯示的維度名稱
_CONFLICT_LABEL = {"C": "服務項目", "A": "執行動作"}

def detect_conflict(resolved_ids: list[str]) -> str | None:
    """
    若同一個規則的選項中有 2 個以上 ID 同時出現在 resolved_ids，
    且沒有任何 QA 能同時包含這些 ID，則回傳衝突的維度名稱字串。
    可能回傳：None / "服務項目" / "執行動作" / "服務項目與執行動作"
    """
    resolved_set = set(resolved_ids)
    conflicted = []
    for rule_key in ASK_ORDER:
        rule = RULES[rule_key]
        dim = rule["dim"]
        if dim not in _CONFLICT_LABEL:
            continue
        option_ids = {opt["id"] for opt in rule["options"]}
        matched = option_ids & resolved_set
        if len(matched) > 1:
            if not any(matched <= set(qa["tags"]) for qa in _all_qa):
                label = _CONFLICT_LABEL[dim]
                if label not in conflicted:
                    conflicted.append(label)
    if not conflicted:
        return None
    return "與".join(conflicted)


# ── QA matching ───────────────────────────────────────────────

def find_qa_match(resolved_ids: list[str]) -> list[dict]:
    """
    Find QA entries where resolved_ids ⊆ tags.
    使用反向索引做集合交集，sorted by specificity（extra tags 少的優先）。
    """
    if not resolved_ids:
        return []
    candidates = None
    for tag in resolved_ids:
        tag_set = QA_TAG_INDEX.get(tag, set())
        candidates = tag_set if candidates is None else candidates & tag_set
        if not candidates:
            return []
    resolved_set = set(resolved_ids)
    return sorted(
        (QA_BY_ID[qid] for qid in candidates),
        key=lambda q: len(set(q["tags"]) - resolved_set)
    )


# ── Main entry ────────────────────────────────────────────────

def process(text: str, session: dict) -> dict:
    """
    Parse text, update session, return result dict.

    Result status:
      "answer"   → matched QA found
      "clarify"  → need more info, returns question + options
      "no_match" → no QA matched after all dims resolved
    """
    # ── 留言收集狀態：等待用戶輸入留言內容 ─────────────────
    if session["state"] == "awaiting_message":
        session["state"] = "idle"
        return {"status": "message_received", "content": text}

    # ── 回饋確認狀態：等待用戶回覆「是否解決」 ──────────────
    if session["state"] == "awaiting_feedback":
        yes_label = POST_ANSWER["options"][0]["label"]
        no_label  = POST_ANSWER["options"][1]["label"]
        if text.strip() == yes_label:
            session["state"] = "idle"
            return {"status": "resolved"}
        elif text.strip() == no_label:
            session["state"] = "awaiting_message"
            return {"status": "collect_message"}
        elif parse_input(text):
            # 含服務項目 ID → 視為重新提問；否則（如只輸入「確認」）視為「是，已解決」
            _c_ids = {opt["id"] for opt in RULES["C"]["options"]}
            if any(id_ in _c_ids for id_ in parse_input(text)):
                # 用戶直接輸入新問題（含服務項目詞彙），視為重新開始
                session["state"]        = "idle"
                session["resolved_ids"] = []
                session["current_dim"]  = None
            else:
                session["state"] = "idle"
                return {"status": "resolved"}
        else:
            # 無法識別的回覆，視為「是」，直接結束對話
            session["state"] = "idle"
            return {"status": "resolved"}

    new_ids = parse_input(text)

    # If waiting for a clarification reply, try to resolve current_dim first
    if session["state"] == "collecting" and session["current_dim"]:
        if text.strip() == OTHER_LABEL:
            # ── 其他：直接進入留言流程 ────────────────────────────
            session["state"]       = "awaiting_message"
            session["current_dim"] = None
            return {"status": "collect_message"}
        elif text.strip() == BACK_LABEL:
            # ── 回到上一層：只保留 prev_key 之前各層的答案 ──────
            # 同時清除被動解析的 T 標籤（如 T01 補正清單、T02 結果檔），
            # 避免它們汙染使用者重新選擇後的新路徑。
            prev_key = _prev_resolved_dim(session["current_dim"], session["resolved_ids"])
            if prev_key:
                prev_idx = ASK_ORDER.index(prev_key)
                keep_ids: set[str] = set()
                for i in range(prev_idx):          # prev_key 之前各層的合法 option ID
                    for opt in RULES[ASK_ORDER[i]]["options"]:
                        keep_ids.add(opt["id"])
                session["resolved_ids"] = [
                    id_ for id_ in session["resolved_ids"] if id_ in keep_ids
                ]
            else:
                session["resolved_ids"] = []       # 已在第一層，全部清除
            session["state"]       = "idle"
            session["current_dim"] = None
            new_ids = []
        else:
            opt_id = match_option_reply(text, session["current_dim"])
            if opt_id:
                rule = RULES.get(session["current_dim"], {})
                is_exact_button = any(
                    text.strip() == opt["label"]
                    for opt in rule.get("options", [])
                    if opt["id"] == opt_id
                )
                if is_exact_button:
                    # 按鈕點擊：只保留此選項，避免按鈕文字被 parse 出多餘 ID
                    new_ids = [opt_id]
                elif opt_id not in new_ids:
                    new_ids.insert(0, opt_id)

    # Merge into resolved_ids
    resolved = list(session["resolved_ids"])
    for id_ in new_ids:
        if id_ not in resolved:
            resolved.append(id_)

    session["resolved_ids"] = resolved
    session["raw_input"]    = session.get("raw_input") or text
    session["turn_count"]   = session.get("turn_count", 0) + 1

    # ── 衝突偵測：同一規則出現多個互斥 ID ────────────────────
    conflict_label = detect_conflict(resolved)
    if conflict_label:
        session["state"]       = "idle"
        session["current_dim"] = None
        return {"status": "conflict", "conflict_label": conflict_label}

    # ── Resolve loop: auto-select single-viable options ───────
    while True:
        pending = compute_pending_dims(resolved)
        session["pending_dims"] = pending

        if not pending:
            break

        next_key = pending[0]
        rule     = RULES[next_key]
        opts     = viable_options(rule, resolved)

        if len(opts) == 0:
            # 移除「條件不成立的 T 規則選項 ID」後重試
            # 例：使用者提到 VPN（T07）但動作是上傳（A01），
            # T_system 條件需要 A02，故 T07 此時不適用。
            dim_resolved_now: dict[str, set] = {}
            for id_ in resolved:
                dim_resolved_now.setdefault(id_[0], set()).add(id_)

            removable: set[str] = set()
            for _rk, _rule in RULES.items():
                if _rule["dim"] != "T":
                    continue
                _cond = _rule.get("condition")
                if _cond is None:
                    continue
                _cond_met = all(
                    bool(dim_resolved_now.get(_cd, set()) & set(_cids))
                    for _cd, _cids in _cond.items()
                )
                if not _cond_met:
                    removable |= {opt["id"] for opt in _rule["options"]} & set(resolved)

            if removable:
                resolved = [id_ for id_ in resolved if id_ not in removable]
                session["resolved_ids"] = resolved
                continue  # 重新計算 pending

            # 無可行選項且無可移除的 ID → 跳出
            break

        if len(opts) == 1:
            # 唯一可行選項 → 自動選取，不問使用者
            auto_id = opts[0]["id"]
            if auto_id not in resolved:
                resolved.append(auto_id)
            session["resolved_ids"] = resolved
            continue  # 重新計算 pending

        # 多個可行選項 → 詢問使用者（服務項目/動作附加「其他」；有上一層則附加「回到上一層」）
        has_prev = _prev_resolved_dim(next_key, resolved) is not None
        opts_display = (
            opts
            + ([{"label": OTHER_LABEL, "id": "OTHER"}] if rule["dim"] in OTHER_DIMS else [])
            + ([{"label": BACK_LABEL,  "id": "BACK"}]  if has_prev else [])
        )
        session["state"]       = "collecting"
        session["current_dim"] = next_key
        return {
            "status":   "clarify",
            "question": rule["question"],
            "options":  opts_display,
        }

    # ── All dims resolved → try to match ─────────────────────
    matches = find_qa_match(resolved)
    session["state"]       = "idle"
    session["current_dim"] = None

    if matches:
        best = matches[0]
        session["state"]       = "awaiting_feedback"
        session["current_dim"] = None
        return {
            "status":            "answer",
            "qa_id":             best["id"],
            "matched_question":  best["question"],
            "answer":            best["answer"],
            "feedback_question": POST_ANSWER["question"],
            "feedback_options":  POST_ANSWER["options"],
        }

    session["state"] = "awaiting_message"
    return {"status": "collect_message"}
