import os
import json
from nltk.tokenize import word_tokenize
from rank_bm25 import BM25Okapi
from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI()

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

def rank_with_bm25(jd_folder="output/extracted_json/jd", cv_folder="output/extracted_json/cv", top_k=6):
  """Rank CVs against JDs using BM25 algorithm"""
  results = {} # lưu kết quả cuối cùng

  # Load JD and CV JSON files
  jd_files = load_json_files(jd_folder)
  cv_files = load_json_files(cv_folder)

    # Gộp JD thành 1 chuỗi lớn
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
    top_bm25 = ranked[:top_k]


    print("🔍 Top CVs theo BM25:")
    jd_results = []
    for i, (cv_name, score) in enumerate(top_bm25, 1):
        cv_index = cv_names.index(cv_name)
        cv_tokens = cv_corpus[cv_index]
        common_tokens = list(set(jd_tokens) & set(cv_tokens))
        print(f" {i}. {cv_name} — BM25 score: {score:.3f} | Matching keywords: {list(common_tokens)}")

        jd_results.append({
            "rank": i,
            "cv_name": cv_name,
            "bm25_score": round(float(score), 3),
            "matching_keywords": common_tokens
        })
    results[jd_name] = jd_results

  return results


@app.get("/test-bm25")
def test_bm25_api():
    try:
        results = rank_with_bm25()
        return JSONResponse(content={"status": "success", "data": results})
    except Exception as e:
        return JSONResponse(content={"status": "error", "message": str(e)}, status_code=500)