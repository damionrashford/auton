let idCounter = 0;
export function generateId(prefix: string = "id"): string {
  return `${prefix}_${Date.now().toString(36)}_${(idCounter++).toString(36)}`;
}
