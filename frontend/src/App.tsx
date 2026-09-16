import { useEffect, useRef, useState } from "react";
import "./App.css";
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

const TABS = ["知识库", "产物预览", "冲突审核", "会话信息"] as const;

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
        📦 当前版本（
        {artifacts.knowledge_hits ? "已融合知识库" : "AI 直接生成"}）
      </div>
      <div className="artifact-buttons">
        <a
          className="btn"
          href={`/api/v1/files/${artifacts.ppt.filename}`}
          download
        >
          ⬇ PPT（{artifacts.ppt.slides.length} 页）
        </a>
        <a
          className="btn"
          href={`/api/v1/files/${artifacts.word.filename}`}
          download
        >
          ⬇ Word 教案
        </a>
        <button
          className="btn"
          onClick={generateExam}
          disabled={generatingExam}
          title="根据本次备课意图与知识库自编试卷，题目自动收入题库"
        >
          {generatingExam ? "出题中…" : "📝 生成试卷"}
        </button>
        {exam && (
          <a className="btn" href={`/api/v1/files/${exam.filename}`} download>
            ⬇ 试卷（{exam.questions.length} 题）
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
            ▶ 互动内容
          </a>
        )}
        <button
          className="btn"
          onClick={() => void onGenerateInteractive()}
          disabled={generatingInteractive}
          title="按本次备课意图生成本节课的互动内容（HTML5 小游戏/知识点动画）"
        >
          {generatingInteractive ? "生成中…" : "✨ 生成互动内容"}
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
        💡 方向性调整（主题/学段/目标级变化）请回对话区说明
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
      <h4>📁 已上传文档（{docs.length}）</h4>
      {docs.length === 0 && (
        <p className="placeholder">还没有上传资料，用输入框旁的 📎 上传</p>
      )}
      {docs.map((d) => (
        <div key={d.id} className="doc-item">
          <span className="doc-name">{d.filename}</span>
          {d.is_reference && <span className="tag">参考资料</span>}
          <span className={`doc-status ${d.status}`}>{d.status}</span>
        </div>
      ))}
      <h4>
        🧠 知识图谱（{nodes.length} 节点 / {edges} 关系）
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
        ⚠️ 冲突待审（{conflicts.filter((c) => c.status === "待审").length}）
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
  const [activeTab, setActiveTab] = useState<(typeof TABS)[number]>("知识库");
  const [sending, setSending] = useState(false);
  const [markReference, setMarkReference] = useState(false);
  const [listening, setListening] = useState(false);
  const [revising, setRevising] = useState(false);
  const [generatingInteractive, setGeneratingInteractive] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
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
    const s = createSession();
    setStore((st) => ({
      ...st,
      activeId: s.id,
      sessions: [s, ...st.sessions],
    }));
    setMenuOpen(false);
    setPendingDeleteId(null);
  }

  function switchTo(id: string) {
    setStore((st) => ({ ...st, activeId: id }));
    setMenuOpen(false);
    setPendingDeleteId(null);
  }

  function deleteSession(id: string) {
    if (pendingDeleteId !== id) {
      setPendingDeleteId(id); // 两段式确认，防误删
      return;
    }
    setStore((st) => removeSession(st, id));
    setPendingDeleteId(null);
    setMenuOpen(false);
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
      appendMessages({
        role: "assistant",
        content: marked
          ? `已上传参考资料「${file.name}」，正在解析入库，备课生成时将优先采用并在教案中注明来源。`
          : `已上传「${file.name}」，正在解析入库，完成后可用于备课检索。`,
      });
      void data;
      setKbRefresh((n) => n + 1);
    } catch {
      appendMessages({
        role: "assistant",
        content: `上传「${file.name}」失败`,
      });
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
    <div className="app">
      <header className="topbar">
        <div className="logo">EduMind</div>
        <div className="granularity" title="追问粒度（随会话保持）">
          {(["快速", "标准", "精细"] as Granularity[]).map((g) => (
            <button
              key={g}
              className={g === active.granularity ? "active" : ""}
              onClick={() => updateActive(() => ({ granularity: g }))}
            >
              {g}
            </button>
          ))}
        </div>
        <div className="spacer" />
        <div className="session-wrap">
          <button
            className={`ghost${menuOpen ? " menu-open" : ""}`}
            onClick={() => {
              setMenuOpen(!menuOpen);
              setPendingDeleteId(null);
            }}
          >
            会话（{store.sessions.length}）
          </button>
          {menuOpen && (
            <>
              <div
                className="menu-backdrop"
                onClick={() => setMenuOpen(false)}
              />
              <div className="session-menu">
                <button className="session-new" onClick={startNewSession}>
                  ＋ 新建备课会话
                </button>
                <p className="session-hint">
                  不同班级 / 课程的备课分开存放，仅保存在本浏览器
                </p>
                {sortedSessions.map((s) => (
                  <div
                    key={s.id}
                    className={`session-item${s.id === active.id ? " active" : ""}`}
                  >
                    <div
                      className="session-main"
                      onClick={() => switchTo(s.id)}
                    >
                      <div className="session-name">
                        {s.name}
                        {s.id === active.id && (
                          <span className="tag">当前</span>
                        )}
                      </div>
                      <div className="session-meta">
                        {formatTime(s.updatedAt)} · {s.messages.length} 条消息
                        {s.artifacts ? " · 已有产物" : ""}
                      </div>
                    </div>
                    <button
                      className={`session-delete${pendingDeleteId === s.id ? " confirm" : ""}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        deleteSession(s.id);
                      }}
                    >
                      {pendingDeleteId === s.id ? "确认删除？" : "删除"}
                    </button>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
        <button className="ghost">设置</button>
      </header>

      <div className="main">
        <section className="chat-panel">
          <div className="chat-history">
            {active.messages.map((m, i) => (
              <div key={i} className={`msg ${m.role}`}>
                {m.content}
              </div>
            ))}
          </div>
          <div className="input-area">
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.doc,.docx,.ppt,.pptx,.png,.jpg,.jpeg,.mp4,.mp3,.wav,.m4a,.aac,.flac,.ogg,.oga,.opus,.wma,.amr"
              style={{ display: "none" }}
              onChange={handleFileChange}
            />
            <button
              className="voice"
              onClick={() => fileInputRef.current?.click()}
              title="上传资料"
            >
              📎
            </button>
            <button
              className={markReference ? "voice ref-on" : "voice"}
              onClick={() => setMarkReference(!markReference)}
              title="标记为参考资料：下一个上传的资料在备课生成时优先采用，并在回复与教案中注明来源"
            >
              📌
            </button>
            <button
              className={listening ? "voice listening" : "voice"}
              onClick={toggleVoice}
              title="语音输入"
            >
              {listening ? "🔴" : "🎤"}
            </button>
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && send()}
              placeholder="输入教学需求，或上传资料建知识库…"
            />
            <button onClick={send} disabled={sending}>
              {sending ? "备课中…" : "发送"}
            </button>
          </div>
        </section>

        <aside className="context-panel">
          <div className="tabs">
            {TABS.map((t) => (
              <button
                key={t}
                className={t === activeTab ? "active" : ""}
                onClick={() => setActiveTab(t)}
              >
                {t}
              </button>
            ))}
          </div>
          <div className="tab-content">
            {activeTab === "知识库" && (
              <KnowledgePanel refreshKey={kbRefresh} />
            )}
            {activeTab === "产物预览" && (
              <PreviewPanel
                key={active.id}
                artifacts={active.artifacts}
                revising={revising}
                generatingInteractive={generatingInteractive}
                onRevise={reviseArtifact}
                onGenerateInteractive={generateInteractive}
              />
            )}
            {activeTab === "冲突审核" && <ConflictPanel />}
            {activeTab === "会话信息" && (
              <SessionPanel
                name={active.name}
                granularity={active.granularity}
                msgCount={active.messages.length}
              />
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}

export default App;
