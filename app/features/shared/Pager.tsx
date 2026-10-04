import type { PageResult } from "./pagination";

export default function Pager<T>({ page, onPage }: { page: PageResult<T>; onPage: (offset: number) => void }) {
  return <div className="pager"><button disabled={page.offset === 0} onClick={() => onPage(Math.max(0, page.offset - page.limit))}>Previous</button><span>{page.total ? page.offset + 1 : 0}-{Math.min(page.total, page.offset + page.limit)} of {page.total}</span><button disabled={page.offset + page.limit >= page.total} onClick={() => onPage(page.offset + page.limit)}>Next</button></div>;
}

