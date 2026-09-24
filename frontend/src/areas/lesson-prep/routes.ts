/**
 * 备课会话区的地址。
 *
 * 与 `areas/lesson-prep/index.tsx` 里注册的 `path` 一致；这里不引区注册表，
 * 因为注册表会用 `import.meta.glob` 反向加载本目录（引它会形成循环依赖）。
 */
export const LESSON_PREP_PATH = '/lesson-prep'

/** 选中一次备课后的地址（URL 即路由：刷新、分享都能回到同一次备课）。 */
export function sessionPath(sessionId: string): string {
  return `${LESSON_PREP_PATH}/${encodeURIComponent(sessionId)}`
}
