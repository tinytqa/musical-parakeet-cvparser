from fastapi import FastAPI
from fastapi.responses import JSONResponse
from filtering.semantic_model import rank_with_sbert
from filtering.bm25 import rank_with_bm25
from fastapi import UploadFile, File
from text_extraction import process_and_parse_jd
from text_extraction import get_text_from_file
from fastapi import HTTPException, Form
from pathlib import Path
import json
from datetime import datetime
from text_extraction import process_and_parse_cv
from fastapi import Query
from filtering.pipeline import rank_combined
from pydantic import BaseModel
from typing import Dict, Optional

app = FastAPI()

@app.post("/extract-text")
async def extract_text(file: UploadFile = File(...), file_role: str = Form(...)):
    """
    Upload file (CV hoặc JD), trích xuất text, lưu ra file .md, trả về đường dẫn và preview text.
    """
    try:
        file_bytes = await file.read()
        filename = file.filename

        saved_path = get_text_from_file(file_bytes, filename, file_role, return_path=True)

        # Đọc lại 2000 ký tự đầu để preview
        preview_text = ""
        with open(saved_path, "r", encoding="utf-8") as f:
            preview_text = f.read(2000)

        return JSONResponse(content={
            "status": "success",
            "saved_path": saved_path,
            "preview_text": preview_text
        })

    except HTTPException as e:
        raise e
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
    
@app.post("/parse/cv") 
async def parse_cv(files: list[UploadFile] = File(...)):
    """
    Nhận nhiều file CV đã extract text (.md), parse ra JSON, lưu ra output/extracted_json/cv.
    """
    results = []

    try:
        for file in files:
            # --- Đọc text từ file .md upload ---
            file_bytes = await file.read()
            file_name = file.filename
            text = file_bytes.decode("utf-8", errors="ignore")

            # --- Parse text ra JSON ---
            parsed_data = process_and_parse_cv(text, file_name)

            # --- Lưu JSON ra folder output/extracted_json/cv ---
            output_dir = Path("output/extracted_json/cv")
            output_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            json_filename = output_dir / f"{Path(file_name).stem}_{timestamp}.json"
            with open(json_filename, "w", encoding="utf-8") as f:
                json.dump(parsed_data, f, ensure_ascii=False, indent=2)

            results.append({
                "filename": file_name,
                "json_path": str(json_filename),
                "parsed_json": parsed_data
            })

        return JSONResponse(content={"status": "success", "results": results})

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
    
@app.post("/parse/jd") 
async def parse_jd(file: UploadFile = File(...)):
    """
    Nhận file JD đã extract text (.md), parse ra JSON, lưu ra output/extracted_json/jd.
    """
    try:
        # --- Đọc text từ file .md upload ---
        file_bytes = await file.read()
        file_name = file.filename
        text = file_bytes.decode("utf-8", errors="ignore")

        # --- Parse text ra JSON ---
        parsed_data = process_and_parse_jd(text, file_name)

        # --- Lưu JSON ra folder output/extracted_json/jd ---
        output_dir = Path("output/extracted_json/jd")
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        json_filename = output_dir / f"{Path(file_name).stem}_{timestamp}.json"
        with open(json_filename, "w", encoding="utf-8") as f:
            json.dump(parsed_data, f, ensure_ascii=False, indent=2)

        return JSONResponse(content={
            "status": "success",
            "json_path": str(json_filename),
            "parsed_json": parsed_data
        })

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
    

#rank with bm25
@app.get("/test-bm25")
def test_bm25_api():
    try:
        results = rank_with_bm25()
        return JSONResponse(content={"status": "success", "data": results})
    except Exception as e:
        return JSONResponse(content={"status": "error", "message": str(e)}, status_code=500)
    
#rank with sbert and cohere
@app.get("/test-sbert-cohere")
def test_pipeline():
    try:
        res = rank_with_sbert()
        return JSONResponse(content={"status": "success", "data": res})
    except Exception as e:
        return JSONResponse(content={"status": "error", "message": str(e)}, status_code=500)
    

@app.get("/rank")
async def rank(
    jd_folder: str = Query("output/extracted_json/jd", description="Folder chứa các JD JSON"),
    cv_folder: str = Query("output/extracted_json/cv", description="Folder chứa các CV JSON"),
    top_k_bm25: int = Query(8, description="Số top kết quả BM25"),
    top_k_sbert: int = Query(4, description="Số top kết quả SBERT"),
    top_k_final: int = Query(3, description="Số top kết quả cuối cùng sau Cohere rerank")
):
    """
    Kết hợp BM25 -> SBERT -> Cohere rerank, trả về kết quả từng bước.
    """
    try:

        results = rank_combined(
            jd_folder=jd_folder,
            cv_folder=cv_folder,
            top_k_bm25=top_k_bm25,
            top_k_sbert=top_k_sbert,
            top_k_final=top_k_final
        )

        return JSONResponse(content={
            "status": "success",
            "results": results
        })

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
    


# class RankingInput(BaseModel):
#     jd_data: Dict[str, str]  # {"JD1": "text of JD1", ...}
#     cv_data: Dict[str, str]  # {"CV1": "text of CV1", ...}
#     top_k_bm25: Optional[int] = 8
#     top_k_sbert: Optional[int] = 4
#     top_k_final: Optional[int] = 3

# @app.post("/rank-text")
# async def rank_text(input_data: RankingInput):
#     """
#     Ranking trực tiếp từ text string của JD và CV, không cần file.
#     """

#     # --- BM25 step ---
#     bm25_results = rank_with_bm25(jd_data=input_data.jd_data, cv_data=input_data.cv_data, top_k=input_data.top_k_bm25)
#     final_results = {}

#     for jd_name, bm25_rankings in bm25_results.items():
#         candidate_cvs = [item["cv_name"] for item in bm25_rankings]

#         # SBERT rerank
#         sbert_results = rank_with_sbert(jd_data={jd_name: input_data.jd_data[jd_name]},
#                                         cv_data=input_data.cv_data,
#                                         top_k=input_data.top_k_sbert)
#         filtered_sbert = [r for r in sbert_results.get(jd_name, []) if r["cv_name"] in candidate_cvs][:input_data.top_k_sbert]

#         # Cohere rerank
#         if any(r.get("cohere_relevance_score") for r in filtered_sbert):
#             top_final = sorted(filtered_sbert, key=lambda x: x.get("cohere_relevance_score", 0),
#                                reverse=True)[:input_data.top_k_final]
#         else:
#             top_final = filtered_sbert[:input_data.top_k_final]

#         final_results[jd_name] = {
#             "bm25_top": bm25_rankings,
#             "sbert_top": filtered_sbert,
#             "final_top": top_final
#         }

#     return {"status": "success", "results": final_results}