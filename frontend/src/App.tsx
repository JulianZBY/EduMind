import { useEffect, useRef, useState } from "react";
import "./App.css";
import Icon, { type IconName } from "./Icon";
import PresentationEditor from "./PresentationEditor";
import type { Artifacts, Granularity, Message } from "./types";
import {
  createSession,
  freshStore,
  loadSessionStore,
  mapActiveSession,
  removeSession,
  saveSessionStore,
  sessionName,
  type SessionStore,
  type StoredSession,
} from "./sessionStore";

interface Doc {
  id: string;
  filename: string;
  file_type: string;
  status: string;
  is_reference?: boolean;
}

interface ConflictItem {
  id: string;
  diff_description: string;
  status: string;
  new_knowledge: { title?: string; content?: string } | null;
  existing_knowledge: { title?: string; content?: string } | null;
}

// 试卷按需生成（产物区一键）：每题标注考查知识点；生成题目自动入题库（来源=自编）
interface ExamPaper {
  questions: {
    type: string;
    content: string;
    answer: string;
    knowledge_point?: string;
  }[];
  filename: string;
  bank_saved: number;
}

const TABS = ["会话", "知识库", "产物预览", "修改 PPT", "冲突审核", "会话信息"] as const;

const NAV_ICONS: Record<(typeof TABS)[number], IconName> = { "会话": "chat", "知识库": "library", "产物预览": "layers", "修改 PPT": "slides", "冲突审核": "shield", "会话信息": "info" };
const RESOURCE_DESCRIPTIONS: Record<string, string> = { "知识库": "把零散资料，沉淀为随时可用的教学知识。", "产物预览": "本次备课的课件、教案与互动内容，尽在这里。", "修改 PPT": "延续已有积累，让课件更适合下一堂课。", "冲突审核": "审阅知识之间的差异，决定如何保留。", "会话信息": "查看当前备课会话的信息与偏好。" };

type ReviseTarget = "课件" | "教案";

function formatTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getMonth() + 1}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

// 预览面板（双入口口径）：只展示会话内最新产物（当前版本）；历史产物仅落盘不展示；
// 修改意见只作用单个产物，方向性调整提示回对话区说明。
function PreviewPanel({
  artifacts,
  revising,
  generatingInteractive,
  onRevise,
  onGenerateInteractive,
}: {
  artifacts: Artifacts | null;
  revising: boolean;
  generatingInteractive: boolean;
  onRevise: (target: ReviseTarget, feedback: string) => Promise<boolean>;
  onGenerateInteractive: () => Promise<boolean>;
}) {
  const [feedback, setFeedback] = useState("");
  const [target, setTarget] = useState<ReviseTarget>("课件");
  const [exam, setExam] = useState<ExamPaper | null>(null);
  const [generatingExam, setGeneratingExam] = useState(false);
  const [examError, setExamError] = useState("");

  if (!artifacts) {
    return (
      <p className="placeholder">暂无产物，先去对话区输入教学需求生成一个吧</p>
    );
  }

  // 一键生成试卷：透传本次备课意图，后端检索知识内容自编出题并入题库
  async function generateExam() {
    if (generatingExam || !artifacts) return;
    setGeneratingExam(true);
    setExamError("");
    try {
      const res = await fetch("/api/v1/exam/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ intent: artifacts.intent }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setExam(await res.json());
    } catch {
      setExam(null);
      setExamError("试卷生成失败，请重试");
    } finally {
      setGeneratingExam(false);
    }
  }

  async function revise() {
    const text = feedback.trim();
    if (!text || revising) return;
    const ok = await onRevise(target, text);
    if (ok) setFeedback("");
  }

  return (
    <div className="artifacts">
      <div className="artifact-title">
        <Icon name="layers" /> 当前版本（
        {artifacts.knowledge_hits ? "已融合知识库" : "AI 直接生成"}）
      </div>
      <div className="artifact-buttons">
        <a
          className="btn"
          href={`/api/v1/files/${artifacts.ppt.filename}`}
          download
        >
          <Icon name="download" /> PPT（{artifacts.ppt.slides.length} 页）
        </a>
        <a
          className="btn"
          href={`/api/v1/files/${artifacts.word.filename}`}
          download
        >
          <Icon name="download" /> Word 教案
        </a>
        <button
          className="btn"
          onClick={generateExam}
          disabled={generatingExam}
          title="根据本次备课意图与知识库自编试卷，题目自动收入题库"
        >
          {generatingExam ? "出题中…" : "生成试卷"}
        </button>
        {exam && (
          <a className="btn" href={`/api/v1/files/${exam.filename}`} download>
            <Icon name="download" /> 试卷（{exam.questions.length} 题）
          </a>
        )}
        {artifacts.interactive && (
          <a
            className="btn"
            href={`/api/v1/files/${artifacts.interactive.filename}?inline=true`}
            target="_blank"
            rel="noreferrer"
            title="在新标签页打开互动内容（HTML5 小游戏/动画）"
          >
            <Icon name="play" /> 互动内容
          </a>
        )}
        <button
          className="btn"
          onClick={() => void onGenerateInteractive()}
          disabled={generatingInteractive}
          title="按本次备课意图生成本节课的互动内容（HTML5 小游戏/知识点动画）"
        >
          {generatingInteractive ? "生成中…" : "生成互动内容"}
        </button>
      </div>
      {examError && <p className="placeholder">{examError}</p>}
      {exam && (
        <details className="artifact-outline" open>
          <summary>
            预览试卷（{exam.questions.length} 题，已入库 {exam.bank_saved} 题）
          </summary>
          <ol className="exam-preview">
            {exam.questions.map((q, i) => (
              <li key={i}>
                <span className="tag">[{q.type}]</span>{" "}
                {q.knowledge_point && (
                  <span className="tag">考查知识点：{q.knowledge_point}</span>
                )}
                <div>{q.content}</div>
              </li>
            ))}
          </ol>
        </details>
      )}
      <div className="target-toggle" role="group" aria-label="修改对象">
        {(["课件", "教案"] as ReviseTarget[]).map((t) => (
          <button
            key={t}
            className={t === target ? "active" : ""}
            onClick={() => setTarget(t)}
          >
            {t}
          </button>
        ))}
      </div>
      <div className="revise-area">
        <input
          value={feedback}
          onChange={(e) => setFeedback(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && revise()}
          placeholder={
            target === "课件"
              ? "修改课件：简化某页 / 增加一个案例 / 调整顺序"
              : "修改教案：调整环节 / 增加活动 / 改作业"
          }
        />
        <button
          onClick={revise}
          disabled={revising || (target === "教案" && !artifacts.word.data)}
        >
          {revising ? "调整中…" : "修改"}
        </button>
      </div>
      <p className="revise-hint">
        <Icon name="info" size={14} /> 方向性调整（主题/学段/目标级变化）请回对话区说明
      </p>
      <details className="artifact-outline">
        <summary>查看教学提纲</summary>
        <pre>{artifacts.outline}</pre>
      </details>
    </div>
  );
}

function KnowledgePanel({ refreshKey }: { refreshKey: number }) {
  const [docs, setDocs] = useState<Doc[]>([]);
  const [nodes, setNodes] = useState<
    { id: string; title: string; difficulty: string }[]
  >([]);
  const [edges, setEdges] = useState(0);

  // refreshKey 变化（如刚完成上传）时重新拉取；存在「处理中」文档时轮询直至终态
  useEffect(() => {
    let timer: number | undefined;
    const load = () => {
      fetch("/api/v1/documents")
        .then((r) => r.json())
        .then((d) => {
          setDocs(d.documents ?? []);
          if (
            (d.documents ?? []).some(
              (x: Doc) => x.status === "处理中" || x.status === "解析中",
            )
          ) {
            timer = window.setTimeout(load, 2000);
          }
        })
        .catch(() => {});
      fetch("/api/v1/knowledge/graph")
        .then((r) => r.json())
        .then((d) => {
          setNodes(d.nodes ?? []);
          setEdges((d.edges ?? []).length);
        })
        .catch(() => {});
    };
    load();
    return () => window.clearTimeout(timer);
  }, [refreshKey]);

  return (
    <div className="panel">
      <h4><Icon name="library" /> 已上传文档（{docs.length}）</h4>
      {docs.length === 0 && (
        <p className="placeholder">还没有上传资料，点击「上传教学资料」添加文件</p>
      )}
      {docs.map((d) => (
        <div key={d.id} className="doc-item">
          <span className="doc-name">{d.filename}</span>
          {d.is_reference && <span className="tag">参考资料</span>}
          <span className={`doc-status ${d.status}`}>{d.status}</span>
        </div>
      ))}
      <h4>
        <Icon name="graph" /> 知识图谱（{nodes.length} 节点 / {edges} 关系）
      </h4>
      {nodes.length === 0 && (
        <p className="placeholder">上传资料后自动提取知识点</p>
      )}
      {nodes.slice(0, 30).map((n) => (
        <div key={n.id} className="node-item">
          {n.title}
          {n.difficulty && <span className="tag">{n.difficulty}</span>}
        </div>
      ))}
    </div>
  );
}

function ConflictPanel() {
  const [conflicts, setConflicts] = useState<ConflictItem[]>([]);
  const [busyId, setBusyId] = useState<string | null>(null);

  async function load() {
    try {
      const r = await fetch("/api/v1/conflicts");
      const d = await r.json();
      setConflicts(d.conflicts ?? []);
    } catch {
      // 后端不可达时保留现有列表
    }
  }

  useEffect(() => {
    void load();
  }, []);

  // 教师三选一（ADR-0001）：接受新=替换旧节点；保留旧=丢弃新知；并存=双留并标注差异
  async function review(id: string, action: "接受新" | "保留旧" | "并存") {
    if (busyId) return;
    setBusyId(id);
    try {
      await fetch(`/api/v1/conflicts/${id}/review`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action }),
      });
      await load();
    } catch {
      // 审核失败时保留待审状态，可重试
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="panel">
      <h4>
        <Icon name="shield" /> 冲突待审（{conflicts.filter((c) => c.status === "待审").length}）
      </h4>
      {conflicts.length === 0 && (
        <p className="placeholder">暂无冲突，上传的新知识与已有图谱一致</p>
      )}
      {conflicts.map((c) => (
        <div key={c.id} className="conflict-item">
          <div className="conflict-titles">
            <span className="tag">{c.existing_knowledge?.title ?? "?"}</span>
            <span>→</span>
            <span className="tag">{c.new_knowledge?.title ?? "?"}</span>
            <span className="doc-status">{c.status}</span>
          </div>
          {c.diff_description && (
            <p className="conflict-desc">差异：{c.diff_description}</p>
          )}
          {(c.existing_knowledge?.content || c.new_knowledge?.content) && (
            <div className="conflict-body">
              <p>旧：{c.existing_knowledge?.content ?? "（无）"}</p>
              <p>新：{c.new_knowledge?.content ?? "（无）"}</p>
            </div>
          )}
          {c.status === "待审" && (
            <div className="conflict-actions">
              <button
                disabled={busyId === c.id}
                onClick={() => review(c.id, "接受新")}
                title="用新知识替换旧节点"
              >
                接受新
              </button>
              <button
                disabled={busyId === c.id}
                onClick={() => review(c.id, "保留旧")}
                title="丢弃新知，保留旧节点"
              >
                保留旧
              </button>
              <button
                disabled={busyId === c.id}
                onClick={() => review(c.id, "并存")}
                title="新旧双节点保留并标注差异"
              >
                并存
              </button>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function SessionPanel({
  name,
  granularity,
  msgCount,
}: {
  name: string;
  granularity: Granularity;
  msgCount: number;
}) {
  return (
    <div className="panel">
      <h4>当前会话</h4>
      <p>
        会话名称：<strong>{name}</strong>
      </p>
      <p>
        追问粒度：<strong>{granularity}</strong>
      </p>
      <p>对话轮数：{msgCount}</p>
      <p className="placeholder">已确认的教学要素会显示在这里（开发中）</p>
      <p className="placeholder">会话仅保存在本浏览器，刷新或重开后自动恢复</p>
    </div>
  );
}

function App() {
  // 会话本地持久化：消息、生成物、追问粒度都挂在当前会话上，store 是唯一事实来源；
  // 变更即落 localStorage，刷新或重开浏览器完整恢复（读取失败回落全新会话）。
  const [store, setStore] = useState<SessionStore>(
    () => loadSessionStore() ?? freshStore(),
  );
  const active: StoredSession =
    store.sessions.find((s) => s.id === store.activeId) ?? store.sessions[0];
  const [input, setInput] = useState("");
  const [activeTab, setActiveTab] = useState<(typeof TABS)[number]>("会话");
  const [sending, setSending] = useState(false);
  const [markReference, setMarkReference] = useState(false);
  const [listening, setListening] = useState(false);
  const [revising, setRevising] = useState(false);
  const [generatingInteractive, setGeneratingInteractive] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState("");
  const [historyOpen, setHistoryOpen] = useState(false);
  const [sessionQuery, setSessionQuery] = useState("");
  const chatScrollRef = useRef<HTMLDivElement>(null);
  const working = sending || revising || generatingInteractive || uploading;

  useEffect(() => {
    const el = chatScrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [active.messages, sending]);
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);
  const [kbRefresh, setKbRefresh] = useState(0); // 上传后触发知识库面板刷新
  const recognitionRef = useRef<any>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    saveSessionStore(store);
  }, [store]);

  // 当前会话更新统一入口（消息/生成物/追问粒度），顺带刷新 updatedAt 供会话列表排序
  function updateActive(fn: (s: StoredSession) => Partial<StoredSession>) {
    setStore((st) => mapActiveSession(st, (s) => ({ ...s, ...fn(s) })));
  }

  function appendMessages(...msgs: Message[]) {
    updateActive((s) => ({ messages: [...s.messages, ...msgs] }));
  }

  // 多会话：新建 / 切换 / 删除；删空回落全新会话，保证界面始终可用
  function startNewSession() {
    setSessionQuery("");
    const s = createSession();
    setStore((st) => ({
      ...st,
      activeId: s.id,
      sessions: [s, ...st.sessions],
    }));
    setHistoryOpen(false);
    setActiveTab("会话");
    setPendingDeleteId(null);
  }

  function switchTo(id: string) {
    setStore((st) => ({ ...st, activeId: id }));
    setHistoryOpen(false);
    setActiveTab("会话");
    setPendingDeleteId(null);
  }

  function deleteSession(id: string) {
    if (pendingDeleteId !== id) {
      setPendingDeleteId(id); // 两段式确认，防误删
      return;
    }
    setStore((st) => removeSession(st, id));
    setPendingDeleteId(null);
    setHistoryOpen(false);
    setActiveTab("会话");
  }

  async function send() {
    const text = input.trim();
    if (!text || sending) return;
    const userMsg: Message = { role: "user", content: text };
    const history = [...active.messages, userMsg];
    // 首条教师消息到达时给会话命名，便于按班级/课程区分
    const isFirstUserMsg = active.messages.every((m) => m.role !== "user");
    updateActive((s) => ({
      messages: [...s.messages, userMsg],
      ...(isFirstUserMsg ? { name: sessionName(history) ?? s.name } : {}),
    }));
    setInput("");
    setSending(true);
    // 参考资料：已标记且解析完成的文档 id，随备课请求下发（检索加权 + 溯源）
    let referenceDocIds: string[] = [];
    try {
      const dres = await fetch("/api/v1/documents");
      const ddata = await dres.json();
      referenceDocIds = (ddata.documents ?? [])
        .filter((d: Doc) => d.is_reference && d.status === "已完成")
        .map((d: Doc) => d.id);
    } catch {
      // 参考资料列表获取失败不阻断备课，退化为无参考标识
    }
    try {
      const res = await fetch("/api/v1/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          messages: history.map((m) => ({ role: m.role, content: m.content })),
          granularity: active.granularity,
          reference_doc_ids: referenceDocIds,
        }),
      });
      const data = await res.json();
      const artifacts = data.artifacts;
      if (artifacts) updateActive(() => ({ artifacts }));
      appendMessages({
        role: "assistant",
        content: data.content ?? `（后端响应异常：${res.status}）`,
      });
    } catch {
      appendMessages({
        role: "assistant",
        content: "（无法连接后端，请先启动服务）",
      });
    } finally {
      setSending(false);
    }
  }

  // 修改闭环（双入口）：预览面板输入=修改意见，只作用单个产物；
  // 新文件落盘后替换当前版本（当前会话的生成物），历史文件仅留磁盘不展示。
  async function reviseArtifact(
    target: ReviseTarget,
    feedback: string,
  ): Promise<boolean> {
    const lastArtifacts = active.artifacts;
    if (!lastArtifacts || revising) return false;
    setRevising(true);
    try {
      if (target === "课件") {
        const res = await fetch("/api/v1/revise", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ slides: lastArtifacts.ppt.slides, feedback }),
        });
        if (!res.ok) return false;
        const data = await res.json();
        updateActive(() => ({
          artifacts: {
            ...lastArtifacts,
            ppt: {
              ...lastArtifacts.ppt,
              slides: data.slides,
              filename: data.filename,
            },
          },
        }));
      } else {
        const res = await fetch("/api/v1/revise/word", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            word: lastArtifacts.word.data,
            feedback,
            references: lastArtifacts.references,
          }),
        });
        if (!res.ok) return false;
        const data = await res.json();
        updateActive(() => ({
          artifacts: {
            ...lastArtifacts,
            word: {
              ...lastArtifacts.word,
              data: data.word,
              filename: data.filename,
            },
          },
        }));
      }
      return true;
    } catch {
      // 修改失败时保持当前版本不变
      return false;
    } finally {
      setRevising(false);
    }
  }

  // 互动内容一键生成（产物区入口）：按上次备课意图生成单文件 HTML；
  // 对话中的互动诉求命中时由后端自动附带，无需教师额外操作。
  async function generateInteractive(): Promise<boolean> {
    const lastArtifacts = active.artifacts;
    if (!lastArtifacts || generatingInteractive) return false;
    setGeneratingInteractive(true);
    try {
      const res = await fetch("/api/v1/interactive/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ intent: lastArtifacts.intent }),
      });
      if (!res.ok) return false;
      const data = await res.json();
      updateActive(() => ({
        artifacts: {
          ...lastArtifacts,
          interactive: { html: data.html, filename: data.filename },
        },
      }));
      return true;
    } catch {
      // 生成失败时保持当前版本不变
      return false;
    } finally {
      setGeneratingInteractive(false);
    }
  }

  async function uploadFile(file: File) {
    if (uploading) return;
    setUploading(true);
    setUploadStatus(`正在上传「${file.name}」…`);
    const formData = new FormData();
    formData.append("file", file);
    if (markReference) formData.append("is_reference", "true");
    const marked = markReference;
    setMarkReference(false);
    try {
      const res = await fetch("/api/v1/documents/upload", {
        method: "POST",
        body: formData,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "上传失败");
      setUploadStatus(`「${file.name}」已上传，正在解析入库`);
      appendMessages({
        role: "assistant",
        content: marked
          ? `已上传参考资料「${file.name}」，正在解析入库，备课生成时将优先采用并在教案中注明来源。`
          : `已上传「${file.name}」，正在解析入库，完成后可用于备课检索。`,
      });
      void data;
      setKbRefresh((n) => n + 1);
    } catch {
      setUploadStatus(`上传「${file.name}」失败，请重试`);
      appendMessages({
        role: "assistant",
        content: `上传「${file.name}」失败`,
      });
    } finally {
      setUploading(false);
    }
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) uploadFile(file);
    e.target.value = "";
  }

  function toggleVoice() {
    const SR =
      (window as any).SpeechRecognition ||
      (window as any).webkitSpeechRecognition;
    if (!SR) {
      appendMessages({
        role: "assistant",
        content: "（当前浏览器不支持语音输入，请使用 Chrome）",
      });
      return;
    }
    if (listening) {
      recognitionRef.current?.stop();
      setListening(false);
      return;
    }
    const recognition = new SR();
    recognition.lang = "zh-CN";
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.onresult = (event: any) => {
      let transcript = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        transcript += event.results[i][0].transcript;
      }
      setInput(transcript);
    };
    recognition.onend = () => setListening(false);
    recognition.onerror = () => setListening(false);
    recognitionRef.current = recognition;
    recognition.start();
    setListening(true);
  }

  // 会话列表按最近使用排序展示
  const sortedSessions = [...store.sessions].sort((a, b) =>
    b.updatedAt.localeCompare(a.updatedAt),
  );

  return (
    <div className={`studio-shell${historyOpen ? " history-open" : ""}`}>
      <nav className="primary-sidebar" aria-label="主导航">
        <a className="studio-brand" href="#" onClick={(e) => { e.preventDefault(); setActiveTab("会话"); }} aria-label="EduMind 首页">
          <span className="studio-emblem"><Icon name="layers" size={23} /></span><span>EduMind<span className="brand-subtitle">教学灵感工作室</span></span>
        </a>
        <button className="new-session glass-button" aria-label="新建会话" title="新建会话" onClick={startNewSession} disabled={working}><Icon name="plus" /><span>新建会话</span></button>
        <span className="nav-caption">工作空间</span>
        <div className="nav-items">
          {TABS.map((item) => <button key={item} className={`nav-item${activeTab === item ? " selected" : ""}`} aria-current={activeTab === item ? "page" : undefined} onClick={() => { setActiveTab(item); setHistoryOpen(false); }} title={item}>
            <Icon name={NAV_ICONS[item]} /><span>{item}</span>{item === "会话" && <span className="nav-count">{store.sessions.length}</span>}
          </button>)}
        </div>
        <div className="sidebar-bottom"><div className="local-note"><Icon name="shield" size={15} /><span>会话保存在本机浏览器</span></div><div className="profile"><span className="profile-avatar">T</span><div><strong>教师工作空间</strong><span>让每一堂课更进一步</span></div></div></div>
      </nav>

      {activeTab === "会话" && <>
        {historyOpen && <button className="history-scrim" aria-label="关闭会话列表" onClick={() => setHistoryOpen(false)} />}
        <aside className="conversation-sidebar" aria-label="会话列表">
          <div className="history-title"><h2>会话</h2><span>{store.sessions.length}</span><button className="icon-button mobile-history-close" aria-label="关闭会话列表" onClick={() => setHistoryOpen(false)}><Icon name="close" /></button></div>
          <label className="session-search"><Icon name="search" size={15} /><input aria-label="搜索会话" placeholder="搜索会话…" value={sessionQuery} onChange={(e) => setSessionQuery(e.target.value)} /></label>
          <div className="history-group">最近的备课</div>
          <div className="conversation-list">
            {sortedSessions.filter(s => s.name.toLowerCase().includes(sessionQuery.toLowerCase())).map(s => <div className={`conversation-item${s.id === active.id ? " selected" : ""}`} key={s.id}>
              <button className="conversation-link" onClick={() => switchTo(s.id)} disabled={working} aria-current={s.id === active.id ? "true" : undefined}>
                <span className="conversation-name"><Icon name="chat" size={15} /><span>{s.name}</span></span><span className="conversation-meta">{formatTime(s.updatedAt)}{s.artifacts ? " · 已有生成物" : " · 备课会话"}</span>
              </button>
              <button className={`conversation-delete${pendingDeleteId === s.id ? " confirm" : ""}`} disabled={working} aria-label={pendingDeleteId === s.id ? `确认删除 ${s.name}` : `删除 ${s.name}`} title={pendingDeleteId === s.id ? "再次点击确认删除" : "删除会话"} onClick={() => deleteSession(s.id)}><Icon name={pendingDeleteId === s.id ? "check" : "trash"} size={14} /></button>
            </div>)}
            {!sortedSessions.some(s => s.name.toLowerCase().includes(sessionQuery.toLowerCase())) && <p className="history-empty">没有找到匹配的会话</p>}
          </div>
          <div className="history-footer"><span className="subtle-dot" />从一个想法，开始下一堂课</div>
        </aside>
      </>}

      <main className="studio-main">
        <header className="workspace-bar">
          <div className="workspace-breadcrumb">{activeTab === "会话" && <button className="icon-button history-toggle" aria-label="打开会话列表" aria-expanded={historyOpen} onClick={() => setHistoryOpen(!historyOpen)}><Icon name="panel" /></button>}<span>{activeTab}</span><span className="breadcrumb-divider">/</span><strong>{active.name}</strong></div>
          <span className="workspace-status"><span className="subtle-dot" />{working ? "正在处理" : "准备就绪"}</span>
        </header>

        <section className={`conversation-workspace${active.messages.length <= 1 ? " is-empty" : ""}`} hidden={activeTab !== "会话"} aria-label="备课对话">
          <div className="conversation-scroll" ref={chatScrollRef}>
            {active.messages.length <= 1 ? <div className="welcome">
              <div className="welcome-symbol"><Icon name="spark" size={31} /></div>
              <span className="eyebrow">A LITTLE INSPIRATION, A GREAT LESSON</span>
              <h1>今天，想带来怎样的一堂课？</h1>
              <p>从一个想法开始。一起梳理知识，让教学设计自然成形。</p>
              <div className="suggestions">
                <button onClick={() => setInput("请帮我设计一节 45 分钟的 TCP 三次握手课程，面向大学一年级学生，包含生活类比和课堂练习。")}><Icon name="chat" /><strong>设计一堂新课</strong><span>梳理目标与课堂活动</span><Icon name="diagonal" size={14} /></button>
                <button onClick={() => setActiveTab("修改 PPT")}><Icon name="slides" /><strong>打磨已有课件</strong><span>上传 PPT，按需求调整</span><Icon name="diagonal" size={14} /></button>
                <button onClick={() => fileInputRef.current?.click()}><Icon name="library" /><strong>从参考资料开始</strong><span>连接你的教学知识库</span><Icon name="diagonal" size={14} /></button>
              </div>
            </div> : <div className="message-list">{active.messages.map((m, i) => <div key={i} className={`message-row ${m.role}`}>
              <span className="message-avatar">{m.role === "assistant" ? <Icon name="layers" size={17} /> : "我"}</span><div className="message-body"><span className="message-author">{m.role === "assistant" ? "EduMind" : "你"}</span><div className="message-text">{m.content}</div></div>
            </div>)}{sending && <div className="thinking" role="status"><span /><span /><span />正在整理教学思路</div>}</div>}
          </div>
          <div className="composer-wrap">
            <div className={`composer${listening ? " recording" : ""}`}>
              <textarea rows={3} aria-label="教学需求" value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); void send(); } }} placeholder="描述你的教学想法，剩下的交给 EduMind…" />
              <div className="composer-toolbar">
                <div className="composer-tools">
                  <button className="icon-button" title="上传资料" aria-label="上传资料" onClick={() => fileInputRef.current?.click()}><Icon name="attach" /></button>
                  <button className={`icon-button${markReference ? " enabled" : ""}`} title="将下次上传标记为参考资料" aria-label="标记为参考资料" aria-pressed={markReference} onClick={() => setMarkReference(!markReference)}><Icon name="pin" /></button>
                  <button className={`icon-button${listening ? " enabled" : ""}`} title={listening ? "停止语音输入" : "语音输入"} aria-label={listening ? "停止语音输入" : "语音输入"} onClick={toggleVoice}><Icon name="mic" /></button>
                  <span className="tool-divider" />
                  <div className="composer-granularity" role="group" aria-label="追问粒度">{(["快速", "标准", "精细"] as Granularity[]).map((g) => <button key={g} className={g === active.granularity ? "active" : ""} aria-pressed={g === active.granularity} onClick={() => updateActive(() => ({ granularity: g }))}>{g}</button>)}</div>
                </div>
                <button className="send-button" onClick={() => void send()} disabled={sending || !input.trim()} aria-label={sending ? "备课中" : "发送"} title="发送"><Icon name={sending ? "spark" : "arrow"} /></button>
              </div>
            </div>
            <div className="composer-footnote"><span>{markReference ? "下次上传将作为参考资料" : "AI 辅助创作，教学内容请审阅"}</span><span>Enter 发送 · Shift + Enter 换行</span></div>
          </div>
        </section>

        <section className="resource-workspace" hidden={activeTab === "会话"} aria-label="资源工作区">
          <div className="resource-heading"><span className="eyebrow">YOUR TEACHING SPACE</span><h1>{activeTab}</h1><p>{RESOURCE_DESCRIPTIONS[activeTab]}</p></div>
          <div className="resource-content">
            {uploadStatus && activeTab === "知识库" && <p className="upload-status" role="status">{uploadStatus}</p>}
            <div hidden={activeTab !== "修改 PPT"}><PresentationEditor /></div>
            {activeTab === "知识库" && <><button className="resource-upload glass-button" onClick={() => fileInputRef.current?.click()}><Icon name="plus" />上传教学资料</button><KnowledgePanel refreshKey={kbRefresh} /></>}
            {activeTab === "产物预览" && <PreviewPanel key={active.id} artifacts={active.artifacts} revising={revising} generatingInteractive={generatingInteractive} onRevise={reviseArtifact} onGenerateInteractive={generateInteractive} />}
            {activeTab === "冲突审核" && <ConflictPanel />}
            {activeTab === "会话信息" && <SessionPanel name={active.name} granularity={active.granularity} msgCount={active.messages.length} />}
          </div>
        </section>
        <input ref={fileInputRef} type="file" accept=".pdf,.doc,.docx,.ppt,.pptx,.png,.jpg,.jpeg,.mp4,.mp3,.wav,.m4a,.aac,.flac,.ogg,.oga,.opus,.wma,.amr" hidden onChange={handleFileChange} />
      </main>
    </div>
  );
}

export default App;
