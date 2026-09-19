import requests
from xml.etree import ElementTree as ET

PUBMED_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_SUMMARY_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"

def search_medical_sources(query: str, max_results: int = 5):
    """
    Uses PubMed/NCBI as a trusted medical-information source.
    For production, add WHO/MedlinePlus connectors and source allowlisting.
    """
    try:
        r = requests.get(
            PUBMED_URL,
            params={
                "db": "pubmed",
                "term": query,
                "retmax": max_results,
                "retmode": "json",
            },
            timeout=10,
        )
        r.raise_for_status()
        ids = r.json().get("esearchresult", {}).get("idlist", [])
        if not ids:
            return []

        s = requests.get(
            PUBMED_SUMMARY_URL,
            params={
                "db": "pubmed",
                "id": ",".join(ids),
                "retmode": "json",
            },
            timeout=10,
        )
        s.raise_for_status()
        data = s.json().get("result", {})

        output = []
        for pid in ids:
            item = data.get(pid, {})
            output.append({
                "source": "PubMed/NCBI",
                "title": item.get("title", ""),
                "pubmed_id": pid,
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{pid}/",
                "date": item.get("pubdate", ""),
            })
        return output
    except Exception as exc:
        return [{
            "source": "PubMed/NCBI",
            "error": str(exc),
        }]
