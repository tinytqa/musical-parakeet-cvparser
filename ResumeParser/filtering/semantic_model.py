
import re

from dotenv import load_dotenv
import torch
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from filtering.bm25 import load_json_files
from sentence_transformers import SentenceTransformer, util, CrossEncoder
import cohere  
import os
from mixedbread_ai.client import MixedbreadAI
import numpy as np
import numpy as np
import streamlit as st
from sentence_transformers import SentenceTransformer
app = FastAPI()

load_dotenv()

# Lấy API key từ biến môi trường
api_key = os.getenv("COHERE_API_KEY")

# Tạo client
co = cohere.Client(api_key)

# --- Chuẩn hóa skill (đảm bảo luôn ra string sạch) ---
def normalize_skill(s):
    if isinstance(s, dict):
        return s.get("name") or s.get("skill") or str(s)
    elif isinstance(s, list):
        return " ".join(map(str, s))
    return str(s)

# --- Hàm chính ---
def extract_candidate_skills_from_cv(cv_data):
    candidates = []

    # 1) explicit skills
    raw_skills = cv_data.get("skills", [])
    if isinstance(raw_skills, list):
        for s in raw_skills:
            if isinstance(s, dict):
                candidates.append(
                    s.get("skill_name") or s.get("name") or s.get("skill") or str(s)
                )
            else:
                candidates.append(str(s))
    elif isinstance(raw_skills, str):
        candidates.extend([x.strip() for x in raw_skills.split(",") if x.strip()])

    # 2) project fields
    projects = cv_data.get("projects", [])
    if isinstance(projects, list):
        for p in projects:
            if isinstance(p, dict):
                techs = (
                    p.get("project_technologies")
                    or p.get("technologies")
                )
                if techs:
                    if isinstance(techs, str):
                        candidates.extend(
                            [x.strip() for x in techs.split(",") if x.strip()]
                        )
                    elif isinstance(techs, list):
                        candidates.extend([str(x).strip() for x in techs if x])
                desc = p.get("project_description") or p.get("project_responsibilities")
                if desc:
                    text = " ".join(map(str, desc)) if isinstance(desc, list) else str(desc)
                    parts = [x.strip() for x in re.split(r"[;,]", text) if x.strip()]
                    candidates.extend(parts)
            else:
                candidates.extend([x.strip() for x in str(p).split(",") if x.strip()])

    # 3) experience
    work_exps = cv_data.get("work_exp", []) or cv_data.get("experience", [])
    if isinstance(work_exps, list):
        for w in work_exps:
            if isinstance(w, dict):
                resp = (
                    w.get("work_responsibilities")
                    or w.get("responsibilities")
                    or w.get("work_description")
                )
                if resp:
                    text = " ".join(map(str, resp)) if isinstance(resp, list) else str(resp)
                    parts = [x.strip() for x in re.split(r"[;,]", text) if x.strip()]
                    candidates.extend(parts)
            else:
                candidates.extend([x.strip() for x in str(w).split(",") if x.strip()])

    # --- Clean & dedupe ---
    def clean_token(t):
        tt = normalize_skill(t).strip()
        if not tt or len(tt) <= 1:
            return None
        if tt.lower() in {"n/a", "none", "null", "nan"}:
            return None
        return tt

    cleaned = []
    seen = set()
    for c in candidates:
        cc = clean_token(c)
        if cc:
            key = cc.lower()
            if key not in seen:
                cleaned.append(cc)
                seen.add(key)

    return cleaned



# --- Cohere skill-level debug: match each JD skill to best CV skill ---
def cohere_match_skills(jd_skill, cv_skills, max_retries=2):
    """Gọi co.rerank cho một jd_skill trên danh sách cv_skills, trả về top result (index, score)."""
    # nếu không có cv_skills thì trả về None
    if not cv_skills:
        return None
    attempt = 0
    while attempt <= max_retries:
        try:
            # top_n = len(cv_skills) để co.rerank trả về các kết quả xếp hạng theo relevance
            resp = co.rerank(
                model="rerank-v3.5",
                query=jd_skill,
                documents=cv_skills,
                top_n=min(len(cv_skills), 20)  # giới hạn top_n để không request quá lớn; sửa nếu cần
            )
            time.sleep(4)
            return resp  # trả nguyên response, caller sẽ phân tích resp.results
        except Exception as e:
            attempt += 1
            if attempt > max_retries:
                print(f"⚠️ Cohere rerank failed for skill '{jd_skill}': {e}")
                return None
            else:
                # simple backoff
                import time
                time.sleep(0.5 * attempt)


def extract_candidate_experience_from_cv(cv_data):
    candidates = []

    # 3) experience
    year_work_exps = cv_data.get("years_of_experience", [])
    if isinstance(year_work_exps , list):
        for w in  year_work_exps :
            if isinstance(w, dict):
                resp = (
                    w.get("work_responsibilities")
                    or w.get("responsibilities")
                    or w.get("work_description")
                )
                if resp:
                    text = " ".join(map(str, resp)) if isinstance(resp, list) else str(resp)
                    parts = [x.strip() for x in re.split(r"[;,]", text) if x.strip()]
                    candidates.extend(parts)
            else:
                candidates.extend([x.strip() for x in str(w).split(",") if x.strip()])



def weighted_embedding_debug(skills_with_weights, model):
    """
    Debug quá trình tính embedding có và không có trọng số.
    Hiển thị trực tiếp log chi tiết trên giao diện Streamlit.
    """
    embeddings, weights = [], []

    #st.markdown("### 🧩 Weighted Embedding Debug Log")
    #exp = st.expander("🔍 Chi tiết từng kỹ năng", expanded=False)

    for skill, weight in skills_with_weights.items():    
        emb = model.encode(skill, convert_to_tensor=False, normalize_embeddings=True)
        embeddings.append(emb)
        weights.append(weight)
        # with exp:
        #     st.markdown(f"**Skill:** `{skill}` | Weight: `{weight}`")
            #st.write(f"🔸 Embedding (first 5 dims): {np.round(emb[:5], 4).tolist()}")

    embeddings = np.array(embeddings)
    # weights = np.array(weights)
    weights = np.array(weights, dtype=np.float32)
    embeddings = np.array(embeddings, dtype=np.float32)
    weighted_emb = np.average(embeddings, axis=0, weights=weights)

    norm_weights = weights / np.sum(weights)
    print ("Normalized weights:", norm_weights)
    # Tính 2 loại embedding
    unweighted_emb = np.mean(embeddings, axis=0)
    # weighted_emb = np.average(embeddings, axis=0, weights=norm_weights)
    print("Weighted embedding debug:", weighted_emb, unweighted_emb)
    return (
        # unweighted_emb,
        # weighted_emb
        torch.tensor(unweighted_emb, dtype=torch.float32),
        torch.tensor(weighted_emb, dtype=torch.float32),
    )

# === Test trực tiếp ===
def debug_weight_effect(jd_data, cv_text, model, unweighted_emb=None, weighted_emb=None):
    """
    So sánh độ ảnh hưởng của trọng số đến similarity giữa JD và CV.
    """
    if unweighted_emb is None or weighted_emb is None:
        st.warning("⚠️ Chưa có embedding để debug.")
        return

    # Encode CV
    cv_emb = model.encode(cv_text, convert_to_tensor=True, normalize_embeddings=True)

    # Tính similarity
    sim_unweighted = util.cos_sim(unweighted_emb, cv_emb).item()
    sim_weighted = util.cos_sim(weighted_emb, cv_emb).item()

    st.markdown("### 🎯 So sánh điểm cosine similarity")
    st.write(f"**Trước khi áp dụng trọng số:** {sim_unweighted:.4f}")
    st.write(f"**Sau khi áp dụng trọng số:** {sim_weighted:.4f}")
    st.write(f"**🔺 Chênh lệch:** {sim_weighted - sim_unweighted:+.6f}")



def rank_with_sbert(jd_folder="output/extracted_json/jd", cv_folder="output/extracted_json/cv", top_k=4):
    results = {}
    model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

    jd_files = load_json_files(jd_folder)
    cv_files = load_json_files(cv_folder)

    for jd_name, jd_data in jd_files:
        #st.markdown(f"## 🧩 JD: `{jd_name}`")
        
        # --- Tạo embedding cho JD ---
        if isinstance(jd_data.get("skills", {}), dict) and len(jd_data["skills"]) > 0:
            #st.info("🧠 Using weighted skill embeddings...")
            
            # Gọi debug và lấy 2 embedding (chỉ chạy 1 lần)
            unweighted_emb, weighted_emb = weighted_embedding_debug(jd_data["skills"], model)
            print("Weighted embedding computed: ", weighted_emb, unweighted_emb)
            # 👉 Gọi debug_weight_effect nhưng KHÔNG gọi lại weighted_embedding_debug bên trong
            cv_sample_text = " ".join(map(str, cv_files[0][1].values())).lower()

            print (cv_sample_text)
            # debug_weight_effect(jd_data, cv_sample_text, model, unweighted_emb, weighted_emb)

            # Sử dụng embedding có trọng số cho ranking chính
            jd_embedding = weighted_emb

        else:
            jd_text = " ".join(map(str, jd_data.values())).lower()
            jd_embedding = model.encode(jd_text, convert_to_tensor=True, normalize_embeddings=True)

        # --- Encode toàn bộ CV ---
        cv_names, cv_doc_embeddings, cv_texts = [], [], []
        for cv_name, cv_data in cv_files:
            text = " ".join(map(str, cv_data.values())).lower()
            cv_names.append(cv_name)
            cv_texts.append(text)
            cv_doc_embeddings.append(model.encode(text, convert_to_tensor=True, normalize_embeddings=True))

        cv_doc_embeddings = torch.stack(cv_doc_embeddings)
        cosine_scores = util.cos_sim(jd_embedding, cv_doc_embeddings)[0]
        sbert_ranked = sorted(zip(cv_names, cv_texts, cosine_scores), key=lambda x: x[2], reverse=True)
        top_sbert = sbert_ranked[:top_k]
        jd_results = []

        print("### 💡 Matched skills each CV with JD")
        for i, (cv_name, cv_text, score) in enumerate(top_sbert, 1):
            score_float = float(score.item())
            print(f"{i}. **{cv_name}** — SBERT score: {score_float:.3f}")

            # --- Skill-level comparison ---
            # cv_data = dict(next(cv for cv in cv_files if cv[0] == cv_name)[1])
            # jd_skills = jd_data.get("skills", [])
            # cv_candidate_skills = extract_candidate_skills_from_cv(cv_data)

            # if not cv_candidate_skills:
            #     cv_text_parts = [
            #         " ".join(map(str, cv_data.get("skills", []))),
            #         " ".join(map(str, cv_data.get("projects", []))),
            #         " ".join(map(str, cv_data.get("experience", []))),
            #     ]
            #     cv_candidate_skills = [" ".join(cv_text_parts).strip()]

            # jd_skill_names = list(jd_skills.keys()) if isinstance(jd_skills, dict) else jd_skills
            # jd_skills_clean = [normalize_skill(s).strip().lower() for s in jd_skill_names if s]
            # cv_skills_clean = [normalize_skill(s).strip().lower() for s in cv_candidate_skills if s]

            # matches = []
            # if jd_skills_clean and cv_skills_clean:
            #     with torch.no_grad():
            #         jd_emb = model.encode(jd_skills_clean, convert_to_tensor=True, normalize_embeddings=True)
            #         cv_emb = model.encode(cv_skills_clean, convert_to_tensor=True, normalize_embeddings=True)
            #         sim_matrix = util.cos_sim(jd_emb, cv_emb)

            #     threshold = 0.55
            #     for idx_jd, jd_skill in enumerate(jd_skills_clean):
            #         for idx_cv, cv_skill in enumerate(cv_skills_clean):
            #             sim = float(sim_matrix[idx_jd][idx_cv])
            #             if sim >= threshold:
            #                 matches.append({
            #                     "jd_skill": jd_skill,
            #                     "cv_skill": cv_skill,
            #                     "similarity": round(sim, 3)
            #                 })

            #     if matches:
            #         print(f"🎯 Matched skills for {cv_name}:")
            #         for m in matches:
            #             print(f"- {m['jd_skill']} ↔ {m['cv_skill']} ({m['similarity']})")
            #     else:
            #         print(f"⚪ No skill matched for {cv_name}")
            # else:
            #     print(f"⚠️ No JD skills or CV candidate skills for {cv_name}")
            # --- Skill-level comparison với trọng số ---
            cv_data = dict(next(cv for cv in cv_files if cv[0] == cv_name)[1])
            jd_skills = jd_data.get("skills", {})

            cv_candidate_skills = extract_candidate_skills_from_cv(cv_data)
            if not cv_candidate_skills:
                cv_text_parts = [
                    " ".join(map(str, cv_data.get("skills", []))),
                    " ".join(map(str, cv_data.get("projects", []))),
                    " ".join(map(str, cv_data.get("experience", []))),
                ]
                cv_candidate_skills = [" ".join(cv_text_parts).strip()]

            jd_skill_names = list(jd_skills.keys()) if isinstance(jd_skills, dict) else jd_skills
            jd_skills_clean = [normalize_skill(s).strip().lower() for s in jd_skill_names if s]
            cv_skills_clean = [normalize_skill(s).strip().lower() for s in cv_candidate_skills if s]

            matches = []

            if jd_skills_clean and cv_skills_clean:
                with torch.no_grad():
                    # Encode JD skills & CV skills
                    jd_emb = model.encode(jd_skills_clean, convert_to_tensor=True, normalize_embeddings=True)  # (n_jd, dim)
                    cv_emb = model.encode(cv_skills_clean, convert_to_tensor=True, normalize_embeddings=True)  # (n_cv, dim)

                    # Lấy trọng số JD
                    # weights = np.array([jd_skills[s] for s in jd_skill_names if s in jd_skills_clean], dtype=np.float32)
                    # weights = torch.tensor(weights, dtype=torch.float32).unsqueeze(1)  # (n_jd, 1)
                    weights_list = [jd_skills[s] for s in jd_skill_names]  # key gốc từ JSON
                    weights = torch.tensor(weights_list, dtype=torch.float32).unsqueeze(1)  # (n_jd, 1)
                    # Nhân embedding JD với trọng số
                    jd_emb_weighted = jd_emb * weights

                    # Cosine similarity
                    sim_matrix = util.cos_sim(jd_emb_weighted, cv_emb)

                threshold = 0.55
                for idx_jd, jd_skill in enumerate(jd_skills_clean):
                    for idx_cv, cv_skill in enumerate(cv_skills_clean):
                        sim = float(sim_matrix[idx_jd][idx_cv])
                        if sim >= threshold:
                            matches.append({
                                "jd_skill": jd_skill,
                                "cv_skill": cv_skill,
                                "similarity": round(sim, 3)
                            })

                # In log
                if matches:
                    print(f"🎯 Matched skills for {cv_name}:")
                    for m in matches:
                        print(f"- {m['jd_skill']} ↔ {m['cv_skill']} ({m['similarity']})")
                else:
                    print(f"⚪ No skill matched for {cv_name}")
            else:
                print(f"⚠️ No JD skills or CV candidate skills for {cv_name}")

            # --- Cohere rerank ---
            try:
                resp = co.rerank(
                    model="rerank-v3.5",
                    query=" ".join(jd_skills_clean) if jd_skills_clean else jd_text,
                    documents=[cv_text],
                    top_n=1
                )
                cohere_score = float(resp.results[0].relevance_score)
                cohere_score_percentage = cohere_score * 100
            except Exception as e:
                cohere_score = None
                print(f"⚠️ Cohere rerank failed for {cv_name}: {e}")

            jd_results.append({
                "rank": i,
                "cv_name": cv_name,
                "semantic_score": round(score_float, 4),
                "cohere_relevance_score": round(cohere_score_percentage, 2) if cohere_score else None,
                "matched_skills": matches
            })

        results[jd_name] = jd_results
        return results







