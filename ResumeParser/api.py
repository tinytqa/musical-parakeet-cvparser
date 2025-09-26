
# # from fastapi import FastAPI, File, HTTPException, UploadFile
# # from fastapi.responses import JSONResponse
# # from ResumeParser.text_extraction import extract_text_from_file


# # app = FastAPI()

# # @app.post("/parse-resume")
# # async def parse_resume(file: UploadFile = File(...)):
# #     try:
# #         # đọc file bytes
# #         file_bytes = await file.read()

# #         # extract và parse luôn sang JSON chuẩn
# #         parsed_result = extract_text_from_file(
# #             file_bytes,
# #             file.filename,
# #             postprocess=True,
# #             to_json=True  # trả về dict, không phải str
# #         )

# #         return JSONResponse(content={
# #             "filename": file.filename,
# #             "parsed_result": parsed_result
# #         })
# #     except HTTPException as he:
# #         # nếu extract_text_from_file raise HTTPException
# #         raise he
# #     except Exception as e:
# #         # các lỗi khác
# #         raise HTTPException(status_code=500, detail=str(e))



from fastapi import FastAPI, UploadFile, File, HTTPException, Body
from fastapi.responses import JSONResponse, FileResponse
import os, json
from pathlib import Path
from pydantic import BaseModel

from export_resume import create_docx_file, post_process
from text_extraction import extract_text_from_file
from dotenv import load_dotenv
from docx import Document
import google.generativeai as genai
from rag import build_rag_pipeline  

load_dotenv()


app = FastAPI(title="Resume Parser API")

OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ===========================
# Parse Resume
# ===========================
@app.post("/parse-resume")
async def parse_resume(file: UploadFile = File(...)):
    try:
        file_bytes = await file.read()

        parsed_result = extract_text_from_file(
            file_bytes,
            file.filename,
            postprocess=True,
            to_json=True
        )

        # Lưu JSON
        json_path = OUTPUT_DIR / f"{Path(file.filename).stem}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(parsed_result, f, ensure_ascii=False, indent=4)

        return JSONResponse(content={
            "status": "success",
            "filename": file.filename,
            "saved_path": str(json_path),
            "parsed_result": parsed_result
        })

    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ===========================
# Export JSON
# ===========================
@app.get("/export/json/{filename}")
def export_json(filename: str):
    json_path = OUTPUT_DIR / f"{Path(filename).stem}.json"
    if not json_path.exists():
        raise HTTPException(status_code=404, detail="Resume JSON not found")

    return FileResponse(
        path=json_path,
        filename=json_path.name,
        media_type="application/json"
    )


# ===========================
# Export DOCX
# ===========================
@app.get("/export/docx/{filename}")
def export_docx(filename: str):
    json_path = OUTPUT_DIR / f"{Path(filename).stem}.json"
    if not json_path.exists():
        raise HTTPException(status_code=404, detail="Resume JSON not found")

    with open(json_path, "r", encoding="utf-8") as f:
        resume_data = json.load(f)

    # Làm sạch dữ liệu
    resume_data = post_process(resume_data)

    # Tạo file DOCX từ JSON
    doc = create_docx_file(resume_data)

    docx_path = OUTPUT_DIR / f"{Path(filename).stem}.docx"
    doc.save(docx_path)

    return FileResponse(
        path=docx_path,
        filename=docx_path.name,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )


# Biến toàn cục lưu pipeline
qa_chain = None

class ChatRequest(BaseModel):
    question: str

@app.post("/upload_cv")
async def upload_cv(file: UploadFile = File(...)):
    global qa_chain

    # Kiểm tra đúng định dạng txt
    if not file.filename.endswith(".txt"):
        raise HTTPException(status_code=400, detail="Chỉ hỗ trợ file .txt")

    # Đọc nội dung file
    content = await file.read()
    cv_text = content.decode("utf-8")

    if not cv_text.strip():
        raise HTTPException(status_code=400, detail="File rỗng")

    # Build pipeline
    qa_chain = build_rag_pipeline(cv_text, output_dir="uploaded_chunks")

    if qa_chain is None:
        raise HTTPException(status_code=500, detail="Không thể khởi tạo pipeline từ CV")

    return {"message": f"Đã upload CV: {file.filename} và build pipeline thành công."}

@app.post("/chat")
async def chat_with_bot(request: ChatRequest):
    global qa_chain
    if qa_chain is None:
        raise HTTPException(status_code=400, detail="Chưa upload CV nào.")

    try:
        response = qa_chain({"question": request.question})
        return {
            "question": request.question,
            "answer": response["answer"],
            "chat_history": [
                {"role": "user", "content": msg.content} if msg.type == "human" else
                {"role": "assistant", "content": msg.content}
                for msg in response["chat_history"]
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


