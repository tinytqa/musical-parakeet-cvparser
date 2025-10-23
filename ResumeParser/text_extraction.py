import json
import os
from pathlib import Path
from pyexpat import model
import tempfile
from fastapi import HTTPException
from docx import Document
import fitz  # PyMuPDF
from jd_prompt import post_parse_jd, prompt_to_parse_jd
from docx2pdf import convert
import numpy as np
from PIL import Image
import io
from text_processing import process_text_ocr   
from prompt import post_parse_cv, prompt_to_parse_cv
from PyPDF2 import PdfReader
import google.generativeai as genai 
from dotenv import load_dotenv
import easyocr
from datetime import datetime
load_dotenv()

api_key = os.getenv("api_key")

genai.configure(api_key=api_key)

import cv2
def get_text_from_file(file_bytes: bytes, filename: str, file_role) -> str:
    """
    Chỉ làm một việc: Chuyển đổi file (PDF, DOCX, có OCR) thành văn bản thô.
    Hàm này có thể dùng cho cả CV và JD.
    """
    path = Path(filename)
    text = ""

    # ----------- DOCX -> convert sang PDF bytes -----------
    if path.suffix.lower() == ".docx":
        file_bytes = convert_docx_to_pdf(file_bytes)
        file_type = "pdf"
    else:
        file_type = path.suffix.lower().lstrip(".")

    # ----------- PDF xử lý (bao gồm cả logic OCR) -----------
    if file_type == "pdf":
        if file_type == "pdf":
            try:
                pdf_doc = fitz.open(stream=file_bytes, filetype="pdf")
                ocr = easyocr.Reader(['vi'])  

                for page in pdf_doc:
                    page_text = page.get_text("text").strip()
                    if page_text:
                        text += page_text + "\n"
                    else:
                        # PDF scan → OCR
                        pix = page.get_pixmap(matrix=fitz.Matrix(3, 3))
                        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                        pre_img = preprocess_for_easyocr(img)

                        try:
                            results = ocr.readtext(pre_img, detail=0, paragraph=True)
                            print("OCR raw results:", results)
                        except Exception as e:
                            raise HTTPException(status_code=400, detail=f"OCR failed: {e}")

                        if results:
                            text += "\n".join(results) + "\n"

                pdf_doc.close()
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Error processing PDF file: {e}")

    else:
        raise HTTPException(status_code=415, detail="Unsupported file type. Only DOCX and PDF are supported.")   
    

    output_dir = Path("output") / file_role.lower()   # => output/jd hoặc output/cv
    output_dir.mkdir(parents=True, exist_ok=True)

    # Tên file md có timestamp để tránh trùng
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = output_dir / f"{path.stem}_{timestamp}.md"

    with open(output_filename, "w", encoding="utf-8") as f:
        f.write(text.strip())

    print(f"✅ Extracted text saved to: {output_filename}")


    # ----------- Save raw text vào folder output -----------
    # cv_name = Path(cv_filename).stem
    # save_dir = Path("output") / cv_name
    # save_dir.mkdir(parents=True, exist_ok=True)
    # raw_text_path = save_dir / "raw_text.md"
    
    # try:
    #     with open(raw_text_path, "w", encoding="utf-8") as f:
    #         f.write("# Processed Text Extracted from CV\n\n")
    #         f.write("```\n")
    #         f.write(processed_text.strip()) 
    #         f.write("\n```")
    #     print(f"✅ Processed CV text saved to {raw_text_path}")
    # except Exception as e:
    #     print(f"⚠️ Could not save processed text: {e}")

    return text.strip()

def preprocess_for_easyocr(pil_img):
    img = np.array(pil_img.convert("RGB"))
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)

    # Resize lớn hơn để OCR dễ đọc
    scale = 2
    resized = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_LINEAR)

    # Không dùng threshold cứng, chỉ normalize độ sáng
    norm = cv2.normalize(resized, None, 0, 255, cv2.NORM_MINMAX)

    return norm

def convert_docx_to_pdf(file_bytes):
    # Tạo file tạm docx

    try:
        import pythoncom
    except Exception:
        pythoncom = None

    if pythoncom:
        try:
            pythoncom.CoInitialize()
        except Exception as e:
            print("pythoncom.CoInitialize failed:", e)
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp_docx:
        tmp_docx.write(file_bytes)
        tmp_docx_path = tmp_docx.name

    tmp_pdf_path = tmp_docx_path.replace(".docx", ".pdf")

    # Chuyển đổi
    convert(tmp_docx_path, tmp_pdf_path)

    # Đọc pdf ra bytes
    with open(tmp_pdf_path, "rb") as f:
        pdf_bytes = f.read()

    # Cleanup thủ công
    try:
        os.remove(tmp_docx_path)
        os.remove(tmp_pdf_path)
    except Exception as e:
        print("Cleanup error:", e)

    return pdf_bytes

def process_and_parse_cv(cv_text: str, cv_filename: str) -> dict:
    """
    Nhận text của CV, hậu xử lý, lưu file và parse ra JSON.
    """
    # ----------- Postprocess -----------
    processed_text = process_text_ocr(cv_text)

    # ----------- Save raw text vào folder output -----------
    # cv_name = Path(cv_filename).stem
    # save_dir = Path("output") / cv_name
    # save_dir.mkdir(parents=True, exist_ok=True)
    # raw_text_path = save_dir / "raw_text.md"
    
    # try:
    #     with open(raw_text_path, "w", encoding="utf-8") as f:
    #         f.write("# Processed Text Extracted from CV\n\n")
    #         f.write("```\n")
    #         f.write(processed_text.strip()) 
    #         f.write("\n```")
    #     print(f"✅ Processed CV text saved to {raw_text_path}")
    # except Exception as e:
    #     print(f"⚠️ Could not save processed text: {e}")

    

    # ----------- Parse JSON bằng LLM -----------
    prompt = prompt_to_parse_cv(processed_text)
    response = genai.GenerativeModel("gemini-2.5-flash").generate_content(prompt)
    parsed_json = post_parse_cv(response.text)
    
    return parsed_json

def process_and_parse_jd(jd_text: str, jd_filename: str) -> dict:
    """
    Nhận text của CV, hậu xử lý, lưu file và parse ra JSON.
    """
    # ----------- Postprocess -----------
    processed_text = process_text_ocr(jd_text)

    # ----------- Save raw text vào folder output -----------
    # cv_name = Path(cv_filename).stem
    # save_dir = Path("output") / cv_name
    # save_dir.mkdir(parents=True, exist_ok=True)
    # raw_text_path = save_dir / "raw_text.md"
    
    # try:
    #     with open(raw_text_path, "w", encoding="utf-8") as f:
    #         f.write("# Processed Text Extracted from CV\n\n")
    #         f.write("```\n")
    #         f.write(processed_text.strip()) 
    #         f.write("\n```")
    #     print(f"✅ Processed CV text saved to {raw_text_path}")
    # except Exception as e:
    #     print(f"⚠️ Could not save processed text: {e}")


    # ----------- Parse JSON bằng LLM -----------
    prompt = prompt_to_parse_jd(processed_text)
    response = genai.GenerativeModel("gemini-2.5-flash").generate_content(prompt)
    parsed_json = post_parse_jd(response.text)
    
    return parsed_json


