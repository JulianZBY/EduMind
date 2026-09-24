# EduMind

多模态 AI 备课智能体:教师多轮对话备课,融合本地知识库与知识图谱,一键生成课件/教案/提纲/试卷/互动内容。

## 必读指针

- **动代码前**:读 `CONTEXT.md` 领域词汇——面向教师的文案与命名一律用词汇表术语。
- **方案有取舍时**:扫 `docs/adr/`——与已有 ADR 冲突须显式指出并说明理由,不得静默绕过。
- **前端任何改动**:`docs/style/minimalist-flat.md` 是验收硬标准,交付前过其自检清单。
- **拿不准整体结构**:`docs/architecture.md` 是目标架构一页图。
- **接口语义读不懂**:`docs/api/` 放机器表达不了的协议专题。

## 结构

- `backend/` — FastAPI 后端,规范见 `backend/AGENTS.md`
- `frontend/` — React 前端,规范见 `frontend/AGENTS.md`

## Agent skills

### Issue tracker

Issues are tracked as local markdown files under `.scratch/<feature>/` in this repo. See `docs/agents/issue-tracker.md`.

### Triage labels

Default label vocabulary — each role label equals its name (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.
