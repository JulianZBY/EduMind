/**
 * 本区一级路由常量单独成文件：区注册表（index.tsx）要在启动时**同步**拿到这个路径，
 * 但区实现（KnowledgeGraphArea.tsx）带着 mermaid/elk/katex 一大串重依赖。若注册表从
 * 实现文件里导入这个常量，会顺手把那串依赖拽回 index chunk，代码分割（M6）就白做了。
 * 单独放这里，注册表只拉这个几行的模块；实现文件也从此处导入，路径仍然只有一处定义。
 */
export const KNOWLEDGE_GRAPH_PATH = '/knowledge-graph'
