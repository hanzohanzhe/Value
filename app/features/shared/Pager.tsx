import type { PageResult } from "./pagination";
import { useT } from "../../i18n/LocaleProvider";

export default function Pager<T>({ page, onPage }: { page: PageResult<T>; onPage: (offset: number) => void }) {
  const t = useT();
  return <div className="pager"><button disabled={page.offset === 0} onClick={() => onPage(Math.max(0, page.offset - page.limit))}>{t("pager.previous")}</button><span>{t("pager.range", { first: page.total ? page.offset + 1 : 0, last: Math.min(page.total, page.offset + page.limit), total: page.total })}</span><button disabled={page.offset + page.limit >= page.total} onClick={() => onPage(page.offset + page.limit)}>{t("pager.next")}</button></div>;
}
