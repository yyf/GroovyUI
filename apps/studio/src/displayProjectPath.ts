/** Normalize separators and strip trailing slashes for path prefix checks. */
function normalizePath(path: string): string {
  return path.replace(/\\/g, "/").replace(/\/+$/, "");
}

/**
 * Show a project-relative path in the UI so absolute home directories
 * (e.g. `/Users/…`) never appear in Settings screenshots or OSS demos.
 * Paths outside the project root are returned unchanged.
 */
export function displayProjectPath(absolutePath: string, projectDir: string): string {
  if (!absolutePath?.trim()) return absolutePath;
  if (!projectDir?.trim()) return absolutePath;

  const abs = normalizePath(absolutePath.trim());
  const root = normalizePath(projectDir.trim());
  if (!root) return absolutePath;

  if (abs === root || abs.toLowerCase() === root.toLowerCase()) {
    return ".";
  }

  const prefix = `${root}/`;
  if (abs.startsWith(prefix)) {
    return abs.slice(prefix.length);
  }
  if (abs.toLowerCase().startsWith(prefix.toLowerCase())) {
    return abs.slice(root.length + 1);
  }

  return absolutePath;
}
