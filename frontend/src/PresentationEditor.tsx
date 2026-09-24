import { useState } from "react";
import Icon from "./Icon";

type EditResult = { filename: string; slides: number; changes: { slide: number; before: string; after: string }[] };

export default function PresentationEditor() {
  const [file, setFile] = useState<File | null>(null);
  const [feedback, setFeedback] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<EditResult | null>(null);

  async function submit() {
    if (!file || !feedback.trim() || busy) return;
    setBusy(true); setError(""); setResult(null);
    const body = new FormData();
    body.append("file", file); body.append("feedback", feedback);
    try {
      const response = await fetch("/api/v1/presentations/edit", { method: "POST", body });
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "修改失败，请检查文件和修改要求");
      setResult(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "连接失败，请重试");
    } finally { setBusy(false); }
  }

  return <div className="ppt-editor">
    <span className="eyebrow">PRESENTATION STUDIO</span>
    <h2>让已有课件，<br />更适合下一堂课。</h2>
    <p className="editor-intro">上传课件，告诉 EduMind 需要调整哪些文字。保留原有页面、图片与布局，另存一份新课件。</p>
    <label className="upload-zone">
      <span className="upload-symbol"><Icon name="slides" size={28} /></span>
      <strong>{file ? file.name : "选择你的 PPT 课件"}</strong>
      <span>PPTX · 最大 20 MB · 最多 80 页</span>
      <input type="file" accept=".pptx" disabled={busy} aria-label="选择 PPTX 课件" onChange={e => {
        const selected = e.target.files?.[0] ?? null;
        setError(""); setResult(null);
        if (selected && (selected.size > 20 * 1024 * 1024 || !selected.name.toLowerCase().endsWith(".pptx"))) {
          setFile(null); setError("请选择不超过 20 MB 的 .pptx 文件");
        } else setFile(selected);
      }} />
    </label>
    <label className="field-label" htmlFor="ppt-feedback">你希望怎样调整？</label>
    <textarea id="ppt-feedback" value={feedback} maxLength={2000} disabled={busy}
      onChange={e => { setFeedback(e.target.value); setResult(null); }}
      placeholder="例如：把第 3 页的专业术语改成初中生能理解的表达，其他页面保持不变。" rows={5} />
    <p className="editor-note">支持标题与正文文本框。暂不修改图片、表格、图表和组合图形，也不增删页面。修改段落统一沿用该段首处文字样式，请下载后检查长文本排版。</p>
    <button className="primary-action" onClick={() => void submit()} disabled={!file || !feedback.trim() || busy}>
      {busy ? "正在理解要求并修改…" : "按要求修改课件"}
    </button>
    {error && <p role="alert" className="error-message">{error}</p>}
    {busy && <p role="status" className="editor-note">通常需要几十秒，请保持页面打开。</p>}
    {result && <div className="edit-result" role="status">
      <span className="eyebrow">修改完成</span>
      <h3>{result.slides} 页课件 · {result.changes.length} 处文字调整</h3>
      <a className="primary-action" href={`/api/v1/files/${encodeURIComponent(result.filename)}`} download>下载修改后的 PPTX <Icon name="download" /></a>
      <details open><summary>查看修改对照</summary>{result.changes.map((c, i) => <div className="change-card" key={i}>
        <strong>第 {c.slide} 页</strong><p className="change-before">{c.before}</p><p>{c.after}</p>
      </div>)}</details>
    </div>}
  </div>;
}
