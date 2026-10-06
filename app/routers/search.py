import csv
import io

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from .. import db
from ..models import SearchKeyword, SearchRequest, SearchResponse, SourceInfo
from ..services.aggregator import aggregate, resolve_window
from ..sources.registry import get_sources, list_sources

router = APIRouter(prefix="/api", tags=["search"])


@router.get("/sources", response_model=list[SourceInfo])
def sources():
    return list_sources()


async def _run(req: SearchRequest) -> SearchResponse:
    keywords: list[SearchKeyword] = []
    if req.project_id is not None:
        project = db.get_project(req.project_id)
        if not project:
            raise HTTPException(404, "Project not found")
        keywords += [SearchKeyword(term=k.term, exact_match=k.exact_match) for k in project.keywords]
    keywords += req.keywords
    # de-duplicate keywords case-insensitively, keeping the first occurrence
    seen, unique = set(), []
    for k in keywords:
        if k.term.strip() and k.term.lower() not in seen:
            seen.add(k.term.lower())
            unique.append(SearchKeyword(term=k.term.strip(), exact_match=k.exact_match))
    if not unique:
        raise HTTPException(422, "No keywords to search for")

    registry = get_sources()
    unknown = [s for s in req.sources if s not in registry]
    if unknown:
        raise HTTPException(422, f"Unknown sources: {', '.join(unknown)}")
    selected = [registry[s] for s in req.sources if registry[s].enabled]
    if not selected:
        raise HTTPException(422, "Select at least one available source")

    try:
        start, end = resolve_window(req)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return await aggregate(selected, unique, start, end, req.date_field)


@router.post("/search", response_model=SearchResponse)
async def search(req: SearchRequest):
    return await _run(req)


@router.post("/search/export.csv")
async def export_csv(req: SearchRequest):
    resp = await _run(req)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["id", "sources", "aliases", "severity", "cvss_score", "cvss_version", "published",
         "last_modified", "matched_keywords", "cwe", "url", "description"]
    )
    for v in resp.results:
        writer.writerow([
            v.id, "; ".join(v.sources or [v.source]), "; ".join(v.aliases), v.severity,
            v.cvss_score or "", v.cvss_version or "",
            v.published.isoformat() if v.published else "",
            v.last_modified.isoformat() if v.last_modified else "",
            "; ".join(v.matched_keywords), "; ".join(v.cwe), v.url or "", v.description,
        ])
    filename = f"nvd_results_{resp.end:%Y%m%d}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
