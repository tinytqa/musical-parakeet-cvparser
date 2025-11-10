# combined_pipeline.py
from filtering.bm25 import rank_with_bm25
from filtering.semantic_model import rank_with_sbert
import streamlit as st


def rank_combined(jd_folder="output/extracted_json/jd", cv_folder="output/extracted_json/cv",
                  top_k_bm25=8, top_k_sbert=4, top_k_final=3):
    """
    Kết hợp BM25 -> SBERT -> Cohere rerank
    Trả về dict chứa kết quả các bước để giao diện hiển thị.
    """

    bm25_results = rank_with_bm25(jd_folder, cv_folder, top_k=top_k_bm25)
    final_results = {}

    for jd_name, bm25_rankings in bm25_results.items():
        candidate_cvs = [item["cv_name"] for item in bm25_rankings]

        # SBERT rerank
        sbert_results = rank_with_sbert(jd_folder=jd_folder, cv_folder=cv_folder, top_k=top_k_sbert)
        filtered_sbert = [
            r for r in sbert_results.get(jd_name, [])
            if r["cv_name"] in candidate_cvs
        ][:top_k_sbert]

        # Cohere rerank
        if any(r.get("cohere_relevance_score") for r in filtered_sbert):
            top_final = sorted(filtered_sbert,
                               key=lambda x: x.get("cohere_relevance_score", 0),
                               reverse=True)[:top_k_final]
        else:
            top_final = filtered_sbert[:top_k_final]

        final_results[jd_name] = {
            "bm25_top": bm25_rankings,
            "sbert_top": filtered_sbert,
            "final_top": top_final
        }

    return final_results

