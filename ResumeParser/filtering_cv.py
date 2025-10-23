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

    # === Cohere Reranking ===
    print("\n🔥 Cohere Rerank (final stage):")
    top_cv_texts_for_cohere = []
    for cv_name, _ in sbert_ranked[:top_k_sbert]:
      cv_data = dict(next(cv for cv in cv_files if cv[0] == cv_name)[1])
      cv_text = " ".join(map(str, cv_data.values()))
      top_cv_texts_for_cohere.append(cv_text)

    response = co.rerank(
      model="rerank-v3.5",
      query=jd_text,
      documents=top_cv_texts_for_cohere,
      top_n=top_k_cohere
    )
    
    cohere_ranked = [
      (sbert_ranked[result.index][0], result.relevance_score)
      for result in response.results
    ]
    adjusted_ranked = []
    

    jd_exp = get_experience_from_json(jd_data)
    print(f" JD: {jd_name} | Extracted Experience: {jd_exp} years")

    for cv_name, score in cohere_ranked:
      cv_data = dict(next(cv for cv in cv_files if cv[0] == cv_name)[1])
      cv_text = " ".join(map(str, cv_data.values()))
      cv_exp = get_experience_from_json(cv_data)
      print(f" CV: {cv_name} | Extracted Experience: {cv_exp} years")
      exp_score = experience_alignment_score(jd_exp, cv_exp)
      final = 0.8 * score + 0.2 * exp_score
      adjusted_ranked.append((cv_name, final, score, exp_score))

    # Sắp xếp lại
    adjusted_ranked.sort(key=lambda x: x[1], reverse=True)

    print("\n🎯 Final rerank with experience adjustment:")
    for i, (cv_name, final, s_score, e_score) in enumerate(adjusted_ranked, 1):
      print(f" {i}. {cv_name} — Final: {final:.4f} | Cohere: {s_score:.4f} | ExpAlign: {e_score:.2f}")

      #debug preview
    
    # cohere_ranked = []
    # for i, result in enumerate(response):
    #   if isinstance(result, dict):
    #     score = result.get("score") or result.get("relevance_score")
    #   elif hasattr(result, "score"):
    #     score = result.score
    #   elif isinstance(result, (tuple, list)) and len(result) >= 2:
    #     score = result[1]
    #   else:
    #     score = float(result)

    #   cohere_ranked.append((sbert_ranked[i][0], float(score)))

    # for i, (cv_name, score) in enumerate(cohere_ranked, 1):
    #   print(f" {i}. {cv_name} — MixedBread relevance: {score:.4f}")

    # === Save results ===
    results[jd_name] = {
      "bm25": [(cv, float(score)) for cv, score in top_bm25],
      "sbert": [(cv, float(score)) for cv, score in sbert_ranked[:top_k_sbert]],
      "cohere": [(cv, float(score)) for cv, score in cohere_ranked]
    }

  print("\n🎯 Kết quả cuối cùng:")
  print(json.dumps(results, indent=2, ensure_ascii=False))
  return results





#chỉ áp dụng reranking cho skill 