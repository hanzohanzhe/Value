/** Row keys from `rowKey`; a repeated key is reported and made unique with
 * its occurrence number so React never merges two rows. */
export function stableRowKeys<Row>(rows: readonly Row[], rowKey: (row: Row) => string): { keys: string[]; duplicates: string[] } {
  const counts = new Map<string, number>();
  const duplicates: string[] = [];
  const keys = rows.map((row) => {
    const key = rowKey(row);
    const seen = counts.get(key) ?? 0;
    counts.set(key, seen + 1);
    if (seen === 1) duplicates.push(key);
    return seen ? `${key}#${seen + 1}` : key;
  });
  return { keys, duplicates };
}
