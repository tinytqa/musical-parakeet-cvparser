from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from text_extraction import extract_text_from_file 

app = FastAPI()

@app.post("/parse-resume")
async def parse_resume(file: UploadFile = File(...)):
    try:
        # đọc file bytes
        file_bytes = await file.read()

        # extract và parse luôn sang JSON chuẩn
        parsed_result = extract_text_from_file(
            file_bytes,
            file.filename,
            postprocess=True,
            to_json=True  # trả về dict, không phải str
        )

        return JSONResponse(content={
            "filename": file.filename,
            "parsed_result": parsed_result
        })
    except HTTPException as he:
        # nếu extract_text_from_file raise HTTPException
        raise he
    except Exception as e:
        # các lỗi khác
        raise HTTPException(status_code=500, detail=str(e))
