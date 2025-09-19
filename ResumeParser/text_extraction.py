import json
import os
from pathlib import Path
from pyexpat import model
from fastapi import HTTPException
from docx import Document
import fitz  # PyMuPDF
import numpy as np
from PIL import Image
import io
from paddleocr import PaddleOCR
from text_processing import process_text_ocr   
from prompt import post_parse_cv, prompt_to_parse_cv
from PyPDF2 import PdfReader
import google.generativeai as genai 
from dotenv import load_dotenv
from langdetect import detect
load_dotenv()

# Lấy API_KEY ra dùng
api_key = os.getenv("api_key")

genai.configure(api_key=api_key)


import fitz  # PyMuPDF
from paddleocr import PaddleOCR
from PIL import Image
import numpy as np

def guess_vi_en_from_pdf(file_bytes: bytes) -> str:
    """
    Nhận diện file PDF là tiếng Việt hay tiếng Anh.
    - Ưu tiên đọc text trực tiếp từ PDF.
    - Nếu không có text (PDF scan) → dùng OCR.
    Trả về 'vi' hoặc 'en'.
    """
    text = ""

    try:
        pdf_doc = fitz.open(stream=file_bytes, filetype="pdf")

        # Đọc text từ 2 trang đầu
        for page in pdf_doc[:2]:
            page_text = page.get_text("text")
            if page_text:
                text += page_text

        # Nếu text rỗng → fallback OCR (chỉ OCR trang đầu để tiết kiệm)
        if not text.strip():
            page = pdf_doc[0]
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

            # OCR đa ngôn ngữ (en+vi)
            ocr = PaddleOCR(use_angle_cls=True, lang="en")  # có thể đổi thành "multilingual" nếu cài đủ model
            results = ocr.ocr(np.array(img))

            if results and results[0]:
                text = " ".join([line[1][0] for line in results[0]])

        pdf_doc.close()

    except Exception as e:
        print("PDF read error:", e)
        return "en"

    # Nếu vẫn rỗng thì fallback 'en'
    if not text.strip():
        return "en"

    # Heuristic check tiếng Việt
    vietnamese_chars = "ăâđêôơưÁÀẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬÉÈẺẼẸÊẾỀỂỄỆÓÒỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢÚÙỦŨỤƯỨỪỬỮỰÍÌỈĨỊÝỲỶỸỴ"
    count_vi = sum(c in vietnamese_chars for c in text)

    return "vi" if count_vi > 3 else "en"


def extract_text_from_file(file_bytes: bytes, filename: str, postprocess: bool = True, to_json: bool = True) -> str:
    path = Path(filename)
    text = ""

    # ----------- DOCX -----------
    if path.suffix.lower() == ".docx":
        doc = Document(io.BytesIO(file_bytes))
        parts = []

        # Đọc tất cả paragraphs ngoài bảng
        for para in doc.paragraphs:
            if para.text.strip():
                parts.append(para.text.strip())

        # Đọc thêm nội dung trong bảng
        for table in doc.tables:
            for row in table.rows:
                row_text = []
                for cell in row.cells:
                    cell_text = " ".join(p.text.strip() for p in cell.paragraphs if p.text.strip())
                    if cell_text:
                        row_text.append(cell_text)
                if row_text:
                    parts.append(" | ".join(row_text))  # nối các ô trong cùng 1 hàng

        formatted_text = "\n".join(parts)

        # Lưu ra file txt
    
        text = formatted_text

    # ----------- PDF -----------
    elif path.suffix.lower() == ".pdf":
        try:
            pdf_doc = fitz.open(stream=file_bytes, filetype="pdf")
            
            for page in pdf_doc:
                page_text = page.get_text("text").strip()

                if page_text:
                    text += page_text + "\n"
                    
                else:
                    # PDF scan → OCR
                    
                    ocr = PaddleOCR(use_angle_cls=True, lang="vi")

                    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

                    try:
                        results = ocr.predict(np.array(img))
                    except Exception as e:
                        raise HTTPException(status_code=400, detail=f"OCR failed: {e}")

                    page_ocr_text = []

                    if results:
                        if hasattr(results, "rec_texts") and hasattr(results, "rec_scores"):
                            for txt, score in zip(results.rec_texts, results.rec_scores):
                                if score > 0.6:
                                    page_ocr_text.append(txt)
                        elif isinstance(results, list):
                            for res in results:
                                if isinstance(res, dict) and "rec_texts" in res and "rec_scores" in res:
                                    for txt, score in zip(res["rec_texts"], res["rec_scores"]):
                                        if score > 0.6:
                                            page_ocr_text.append(txt)

                    if page_ocr_text:
                        text += "\n".join(page_ocr_text) + "\n"
            print(text)
            pdf_doc.close()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Error processing PDF file: {e}")

    else:
        raise HTTPException(status_code=415, detail="Unsupported file type. Only DOCX and PDF are supported.")

    # ----------- Postprocess -----------
    text = text.strip()
    if postprocess:
        try:
            text = process_text_ocr(text)   # hàm xử lý OCR của bạn
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"LLM postprocess failed: {e}")

    # ----------- Chuyển sang JSON + Lưu file -----------
    if to_json:
        try:
            prompt = prompt_to_parse_cv(text)
            response = genai.GenerativeModel("gemini-2.5-flash").generate_content(prompt)
            
            parsed_json = post_parse_cv(response.text)
            #print (parsed_json)
            return parsed_json
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"LLM JSON parse failed: {e}")

    return text




