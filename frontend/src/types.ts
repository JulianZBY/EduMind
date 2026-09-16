// 领域词汇对齐 CONTEXT.md：生成物 / 追问粒度 / 备课对话。
// App 与会话持久化模块共用，避免循环依赖。

export type Granularity = "快速" | "标准" | "精细";

export interface WordData {
  objectives?: {
    knowledge?: string[];
    ability?: string[];
    emotion?: string[];
  };
  key_points?: string[];
  difficult_points?: string[];
  process?: { stage?: string; minutes?: number; content?: string }[];
  activities?: string[];
  homework?: string[];
}

export interface Artifacts {
  intent: { topic: string };
  knowledge_hits: boolean;
  references: string[];
  ppt: {
    slides: { title: string; points: string[] }[];
    path: string;
    filename: string;
  };
  // data：教案完整结构，供预览面板发起教案修改（当前版本随之更新）
  word: { data?: WordData; path: string; filename: string };
  outline: string;
  // 互动内容：意图互动诉求命中时自动附带，或产物区一键生成（单文件 HTML）
  interactive?: { html: string; filename: string } | null;
}

export interface Message {
  role: "user" | "assistant";
  content: string;
}
