import os
import json
import textwrap
from sentence_transformers import SentenceTransformer, util
from rank_bm25 import BM25Okapi
from nltk.tokenize import word_tokenize
import cohere
from mxbai_rerank import MxbaiRerankV2

import re

# === Load models ===
sbert_model = SentenceTransformer("all-MiniLM-L6-v2")
co = cohere.Client("hg5tqF6kReVF5QeViXHMDZgfjf2JKaeSM6S7UGjy")
model = MxbaiRerankV2("mixedbread-ai/mxbai-rerank-base-v2")
def load_json_files(folder_path):
  """Load all JSON files from a given folder"""
  files = []
  for filename in os.listdir(folder_path):
    if filename.endswith(".json"):
      path = os.path.join(folder_path, filename)
      with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
        files.append((filename, data))
  return files

def get_experience_from_json(data):
  """
  Trích xuất số năm kinh nghiệm từ JSON CV hoặc JD.
  Ưu tiên trường có tên 'years_of_experience' hoặc tương tự.
  Nếu không có, fallback sang quét text thủ công.
  """
  # Nếu JSON có sẵn trường years_of_experience
  for key in data.keys():
    if "year" in key.lower() and "experience" in key.lower():
      val = data[key]
      if isinstance(val, (int, float)):
        return float(val)
      # nếu là string ví dụ: "3 years"
      if isinstance(val, str):
        match = re.search(r"(\d+)", val)
        if match:
          return float(match.group(1))
  
  # Nếu không có, quét text fallback
  exp_text = ""
  for key, value in data.items():
    if "experience" in key.lower() or "kinh nghiệm" in key.lower():
      exp_text = str(value)
      break
  return extract_experience_years(exp_text)

def extract_experience_years(text):
  text = text.lower().replace("\n", " ").replace("\r", " ")
  text = re.sub(r"\s+", " ", text) # loại bỏ khoảng trắng thừa

  # 1️⃣ Pattern cho < 1 năm
  if re.search(r"(<\s*1\s*(?:year|years|năm))", text) or \
   any(x in text for x in ["less than 1", "under 1", "no experience", "fresh graduate"]):
    return 0

  # 2️⃣ Pattern cho "1-2 năm" hoặc "2+ năm"
  match = re.search(r'(\d+)\s*(?:\+|\-|\sto\s)?\s*(\d+)?\s*(?:year|years|năm)', text)
  if match:
    lower = int(match.group(1))
    upper = match.group(2)
    if upper:
      return round((lower + int(upper)) / 2, 1)
    return lower

  # 3️⃣ Pattern cho "more than 5 years"
  match_more = re.search(r"(?:more than|over|trên)\s*(\d+)\s*(?:year|years|năm)", text)
  if match_more:
    return int(match_more.group(1)) + 1

  return None


def experience_alignment_score(jd_exp, cv_exp):
  """
  Tính điểm phù hợp về kinh nghiệm giữa CV và JD.
  """
  if jd_exp is None or cv_exp is None:
    return 0.5 # không rõ thì điểm trung bình

  # JD = 0 nghĩa là không yêu cầu kinh nghiệm
  # -> chỉ nên cho điểm cao nếu ứng viên không quá thừa kinh nghiệm
  if jd_exp == 0:
    if cv_exp == 0:
      return 1.0
    elif cv_exp <= 2:
      return 0.8 
    else:
      return 0.5 

  # Còn lại tính theo độ lệch
  diff = abs(cv_exp - jd_exp)
  exp_align = max(0, 1 - diff / (jd_exp + 1))
  return round(exp_align, 2)


def rerank_skills_with_cohere(jd_skills, cv_skills, jd_skill_weights, co):
    """
    Dùng Cohere Rerank để so khớp kỹ năng JD ↔ CV.
    Trả về tổng điểm có trọng số và debug chi tiết skill nào khớp.
    """
    # 💡 Loại bỏ kỹ năng rỗng hoặc chỉ có khoảng trắng
    cv_skills = [s.strip() for s in cv_skills if isinstance(s, str) and s.strip()]
    jd_skills = [s.strip() for s in jd_skills if isinstance(s, str) and s.strip()]

    if not cv_skills or not jd_skills:
        return 0.0, [{"warning": "No valid skills found in JD or CV"}]

    total_score = 0
    total_weight = sum(jd_skill_weights.values()) or 1
    skill_debug = []

    for jd_skill in jd_skills:
        jd_weight = jd_skill_weights.get(jd_skill, 1)

        try:
            response = co.rerank(
                model="rerank-v3.5",
                query=jd_skill,
                documents=cv_skills,
                top_n=1
            )
            best_result = response.results[0]
            best_cv_skill = cv_skills[best_result.index]
            best_score = best_result.relevance_score

        except Exception as e:
            print(f"⚠️ Cohere error for skill '{jd_skill}': {e}")
            best_cv_skill = None
            best_score = 0.0

        weighted = best_score * jd_weight
        total_score += weighted

        skill_debug.append({
            "jd_skill": jd_skill,
            "matched_cv_skill": best_cv_skill,
            "score": round(best_score, 3),
            "weight": jd_weight,
            "weighted_score": round(weighted, 3)
        })

    normalized_score = total_score / total_weight
    return normalized_score, skill_debug



def rank_with_bm25_and_sbert(
    jd_folder="output/extracted_json/jd",
    cv_folder="output/extracted_json/cv",
    top_k_bm25=6,
    top_k_sbert=4,
    top_k_cohere=3
):
    results = {}

    jd_files = load_json_files(jd_folder)
    cv_files = load_json_files(cv_folder)

    for jd_name, jd_data in jd_files:
        print(f"\n🧩 Processing JD: {jd_name}")
        jd_text = " ".join(map(str, jd_data.values())).lower()
        jd_tokens = word_tokenize(jd_text)

        # === Build CV corpus ===
        cv_corpus, cv_names = [], []
        for cv_name, cv_data in cv_files:
            text = " ".join(map(str, cv_data.values())).lower()
            tokens = word_tokenize(text)
            cv_corpus.append(tokens)
            cv_names.append(cv_name)

        # === Run BM25 ===
        bm25 = BM25Okapi(cv_corpus)
        scores = bm25.get_scores(jd_tokens)
        ranked = sorted(zip(cv_names, scores), key=lambda x: x[1], reverse=True)
        top_bm25 = ranked[:top_k_bm25]

        print("🔍 Top CVs theo BM25:")
        for i, (cv_name, score) in enumerate(top_bm25, 1):
            cv_index = cv_names.index(cv_name)
            cv_tokens = cv_corpus[cv_index]
            common_tokens = set(jd_tokens) & set(cv_tokens)
            print(f" {i}. {cv_name} — BM25 score: {score:.3f} | Matching keywords: {list(common_tokens)}")

        # === SBERT reranking ===
        top_cv_texts = []
        for cv_name, _ in top_bm25:
            cv_data = dict(next(cv for cv in cv_files if cv[0] == cv_name)[1])
            cv_text = " ".join(map(str, cv_data.values()))
            top_cv_texts.append(cv_text)

        jd_embedding = sbert_model.encode(jd_text, convert_to_tensor=True)
        cv_embeddings = sbert_model.encode(top_cv_texts, convert_to_tensor=True)
        cosine_scores = util.cos_sim(jd_embedding, cv_embeddings)[0]

        sbert_ranked = sorted(
            zip([cv for cv, _ in top_bm25], cosine_scores),
            key=lambda x: x[1],
            reverse=True
        )

        print("\n💡 SBERT reranking:")
        for i, (cv_name, score) in enumerate(sbert_ranked, 1):
            print(f" {i}. {cv_name} — Cosine similarity: {float(score):.4f}")
            cv_data = dict(next(cv for cv in cv_files if cv[0] == cv_name)[1])
            short_preview = textwrap.shorten(" ".join(map(str, cv_data.values())), width=120)
            print(f"   Preview: {short_preview}")

        jd_skills = jd_data.get("skills", [])
        jd_skill_weights = jd_data.get("skill_weights", {})

        jd_results = []

        for cv_name, _ in sbert_ranked[:top_k_sbert]:
            cv_data = dict(next(cv for cv in cv_files if cv[0] == cv_name)[1])
            cv_skills = cv_data.get("skills", [])

            # === Skill Matching với Cohere ===
            skill_score, skill_debug = rerank_skills_with_cohere(jd_skills, cv_skills, jd_skill_weights, co)

            print("🧠 Skill Matching:")
            for s in skill_debug:
                jd_skill = s.get("jd_skill", "N/A")
                matched_cv_skill = s.get("matched_cv_skill", "N/A")
                score = s.get("score", 0)
                weight = s.get("weight", 1)
                print(f"     - {jd_skill} ↔ {matched_cv_skill} ({score:.3f}) [weight={weight}]")


                        # === Tính điểm tổng hợp ===
   

            jd_exp = get_experience_from_json(jd_data)
            cv_exp = get_experience_from_json(cv_data)
            exp_score = experience_alignment_score(jd_exp, cv_exp)

            final_score = 0.8 * skill_score + 0.2 * exp_score

            print(f"📄 CV: {cv_name}")
            print(f"   Skill Score: {skill_score:.3f}")
            print(f"   Exp Align: {exp_score:.2f}")
            print(f"   Final Score: {final_score:.3f}")

            jd_results.append({
                "cv_name": cv_name,
                "skills_matches": skill_matches,
                "skill_score": round(skill_score, 3),
                "exp_score": round(exp_score, 3),
                "final_score": round(final_score, 3)
            })

        # === Save per-JD results ===
        results[jd_name] = {
            "bm25": [(cv, float(score)) for cv, score in top_bm25],
            "sbert": [(cv, float(score)) for cv, score in sbert_ranked[:top_k_sbert]],
            "skills": jd_results
        }

    print("\n🎯 Kết quả cuối cùng:")
    print(json.dumps(results, indent=2, ensure_ascii=False))
    return results






#chỉ áp dụng reranking cho skill 