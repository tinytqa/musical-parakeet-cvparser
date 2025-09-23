import os
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from text_extraction import extract_text_from_file 

# app = FastAPI()

# @app.post("/parse-resume")
# async def parse_resume(file: UploadFile = File(...)):
#     try:
#         # đọc file bytes
#         file_bytes = await file.read()

#         # extract và parse luôn sang JSON chuẩn
#         parsed_result = extract_text_from_file(
#             file_bytes,
#             file.filename,
#             postprocess=True,
#             to_json=True  # trả về dict, không phải str
#         )

#         return JSONResponse(content={
#             "filename": file.filename,
#             "parsed_result": parsed_result
#         })
#     except HTTPException as he:
#         # nếu extract_text_from_file raise HTTPException
#         raise he
#     except Exception as e:
#         # các lỗi khác
#         raise HTTPException(status_code=500, detail=str(e))
    


def main():
    # Đường dẫn file test (có thể là DOCX hoặc PDF)
    test_file = "C:/Users/tranq/Downloads/HĐ. TVGS- Đan Hoài, Hoài Đức.pdf"
    
    # Đọc file bytes
    with open(test_file, "rb") as f:
        file_bytes = f.read()
    
    # Gọi hàm extract_text_from_file
    try:
        extracted_text = extract_text_from_file(
            file_bytes=file_bytes,
            filename=test_file,
            postprocess=True,
            to_json=False
        )
        print("=== Extracted Text ===")
        print(extracted_text[:500])  # in thử 500 ký tự đầu

        # Đặt tên folder
        folder_name = "cv"
        output_dir = os.path.join("output", folder_name)
        os.makedirs(output_dir, exist_ok=True)

        # Lưu ra .md
        path = Path(test_file)
        output_md_path = os.path.join(output_dir, f"{path.stem}.md")
        with open(output_md_path, "w", encoding="utf-8") as f:
            f.write(extracted_text)

        print(f"\n✅ Done! Kết quả đầy đủ đã được lưu trong: {output_md_path}")
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    main()

