/**
 * 生成物区的地址。
 *
 * 与 `areas/artifacts/index.tsx` 里注册的 `path` 一致；这里不引区注册表
 * （注册表用 `import.meta.glob` 反向加载本目录，引它会形成循环依赖）。
 * URL 即状态：选中哪一次备课、回看哪一版都写在地址上，刷新与分享都能回到同一处。
 */
export const ARTIFACTS_PATH = '/artifacts'

/** 生成物区总览（未选中会话）。 */
export const artifactsPath = ARTIFACTS_PATH

/** 某一次备课的版本时间线；`versionId` 非空时同时选中回看的那一版。 */
export function timelinePath(sessionId: string, versionId?: string | null): string {
  const base = `${ARTIFACTS_PATH}/${encodeURIComponent(sessionId)}`
  return versionId ? `${base}?${new URLSearchParams({ v: versionId }).toString()}` : base
}
