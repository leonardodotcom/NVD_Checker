def cve(cve_id, published="2026-09-28T10:00:00.000", score=9.8, severity="CRITICAL", desc="desc"):
    return {
        "cve": {
            "id": cve_id,
            "published": published,
            "lastModified": published,
            "descriptions": [{"lang": "es", "value": "otro"}, {"lang": "en", "value": desc}],
            "metrics": {
                "cvssMetricV31": [
                    {"type": "Secondary", "cvssData": {"baseScore": 1.0, "baseSeverity": "LOW", "version": "3.1"}},
                    {"type": "Primary", "cvssData": {"baseScore": score, "baseSeverity": severity, "version": "3.1"}},
                ]
            },
            "weaknesses": [{"description": [{"lang": "en", "value": "CWE-79"}, {"lang": "en", "value": "NVD-CWE-noinfo"}]}],
            "references": [{"url": "https://example.com/advisory"}],
        }
    }


def page(items, start_index=0, total=None, per_page=None):
    return {
        "resultsPerPage": per_page if per_page is not None else len(items),
        "startIndex": start_index,
        "totalResults": total if total is not None else len(items),
        "vulnerabilities": items,
    }
