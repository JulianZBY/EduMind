// 备课会话浏览器本地持久化（DESIGN §6.1 会话持久化 v3）：
// 消息 + 生成物 + 追问粒度随会话存 localStorage，刷新/重开浏览器完整恢复；
// 支持多会话切换；不建服务端会话实体。
// 任何读写失败（隐私模式/配额满/脏数据）一律降级：读失败回全新会话，写失败静默跳过，
// 不阻断备课主流程与现场演示。

import type { Artifacts, Granularity, Message } from "./types";

export interface StoredSession {
  id: string;
  name: string;
  createdAt: string;
  updatedAt: string;
  granularity: Granularity;
  messages: Message[];
  artifacts: Artifacts | null;
}

export interface SessionStore {
  version: 1;
  activeId: string;
  sessions: StoredSession[];
}

const SESSIONS_KEY = "edumind.sessions.v1";
const GRANULARITIES: readonly Granularity[] = ["快速", "标准", "精细"];
const GREETING: Message = {
  role: "assistant",
  content: "你好，我是 EduMind 教学智能体。今天要备什么课？",
};

export function makeId(): string {
  return `s_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

function formatStamp(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getMonth() + 1}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** 新会话：默认名带创建时间，首条教师消息到达后由 sessionName 重命名。 */
export function createSession(now = new Date()): StoredSession {
  return {
    id: makeId(),
    name: `备课 ${formatStamp(now)}`,
    createdAt: now.toISOString(),
    updatedAt: now.toISOString(),
    granularity: "标准",
    messages: [{ ...GREETING }],
    artifacts: null,
  };
}

/** 会话命名：取首条教师消息截断，便于按班级/课程区分；无教师消息时返回 null（保持默认名）。 */
export function sessionName(messages: Message[]): string | null {
  const first = messages.find((m) => m.role === "user");
  if (!first) return null;
  const text = first.content.replace(/\s+/g, " ").trim();
  if (!text) return null;
  return text.length > 16 ? `${text.slice(0, 16)}…` : text;
}

function isGranularity(v: unknown): v is Granularity {
  return (
    typeof v === "string" && (GRANULARITIES as readonly string[]).includes(v)
  );
}

function isMessages(v: unknown): v is Message[] {
  return (
    Array.isArray(v) &&
    v.every(
      (m) =>
        typeof m === "object" &&
        m !== null &&
        ((m as Message).role === "user" ||
          (m as Message).role === "assistant") &&
        typeof (m as Message).content === "string",
    )
  );
}

// 生成物做浅结构校验：核心字段齐才认，缺了宁可当无产物也不让预览面板崩。
// 未知字段（如互动内容 interactive）原样透传，避免持久化层剥离他人后续追加的产物成员。
function toArtifacts(v: unknown): Artifacts | null {
  if (typeof v !== "object" || v === null) return null;
  const a = v as Artifacts;
  if (!Array.isArray(a.ppt?.slides) || typeof a.word?.filename !== "string") {
    return null;
  }
  return {
    ...a,
    intent: typeof a.intent?.topic === "string" ? a.intent : { topic: "" },
    knowledge_hits: a.knowledge_hits === true,
    references: Array.isArray(a.references) ? a.references : [],
    ppt: {
      slides: a.ppt.slides,
      path: a.ppt.path ?? "",
      filename: a.ppt.filename,
    },
    word: {
      data: a.word.data,
      path: a.word.path ?? "",
      filename: a.word.filename,
    },
    outline: typeof a.outline === "string" ? a.outline : "",
  };
}

function toSession(v: unknown): StoredSession | null {
  if (typeof v !== "object" || v === null) return null;
  const s = v as StoredSession;
  if (typeof s.id !== "string" || s.id === "") return null;
  if (!isGranularity(s.granularity)) return null;
  if (!isMessages(s.messages)) return null;
  return {
    id: s.id,
    name: typeof s.name === "string" && s.name ? s.name : "备课会话",
    createdAt:
      typeof s.createdAt === "string" ? s.createdAt : new Date(0).toISOString(),
    updatedAt:
      typeof s.updatedAt === "string" ? s.updatedAt : new Date(0).toISOString(),
    granularity: s.granularity,
    messages: s.messages,
    artifacts: toArtifacts(s.artifacts),
  };
}

/** 读取并整卷校验；缺失/损坏/指向失效一律返回 null，由调用方回落全新会话。 */
export function loadSessionStore(): SessionStore | null {
  try {
    const raw = localStorage.getItem(SESSIONS_KEY);
    if (!raw) return null;
    const data: unknown = JSON.parse(raw);
    if (typeof data !== "object" || data === null) return null;
    const d = data as SessionStore;
    if (
      d.version !== 1 ||
      !Array.isArray(d.sessions) ||
      d.sessions.length === 0
    ) {
      return null;
    }
    const sessions = d.sessions
      .map(toSession)
      .filter((s): s is StoredSession => s !== null);
    if (sessions.length === 0) return null;
    const activeId = sessions.some((s) => s.id === d.activeId)
      ? d.activeId
      : sessions[0].id;
    return { version: 1, activeId, sessions };
  } catch {
    return null;
  }
}

/** 写入；配额满或隐私模式下静默降级为不持久化。 */
export function saveSessionStore(store: SessionStore): void {
  try {
    localStorage.setItem(SESSIONS_KEY, JSON.stringify(store));
  } catch {
    // 持久化失败不阻断备课
  }
}

export function freshStore(now = new Date()): SessionStore {
  const s = createSession(now);
  return { version: 1, activeId: s.id, sessions: [s] };
}

/** 对当前会话做纯函数更新，并刷新其 updatedAt（会话列表按最近使用排序）。 */
export function mapActiveSession(
  store: SessionStore,
  fn: (s: StoredSession) => StoredSession,
): SessionStore {
  const now = new Date().toISOString();
  return {
    ...store,
    sessions: store.sessions.map((s) =>
      s.id === store.activeId ? { ...fn(s), updatedAt: now } : s,
    ),
  };
}

/** 删除会话；删的是当前会话则切到最近更新的剩余会话，删空则回落全新会话。 */
export function removeSession(store: SessionStore, id: string): SessionStore {
  const sessions = store.sessions.filter((s) => s.id !== id);
  if (sessions.length === 0) return freshStore();
  const activeId =
    store.activeId !== id
      ? store.activeId
      : [...sessions].sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))[0]
          .id;
  return { ...store, sessions, activeId };
}
